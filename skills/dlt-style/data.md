# Reading and checking loaded data

How to read what a pipeline loaded, DuckDB and Polars first, and the checks to run after a load before anything builds on it.
Exploring the data in a notebook is in [`notebooks.md`](notebooks.md).
Source: [dataset access](https://dlthub.com/docs/general-usage/dataset-access/dataset), [destination tables](https://dlthub.com/docs/general-usage/destination-tables), [DuckDB destination](https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb), [view the schema](https://dlthub.com/docs/general-usage/dataset-access/view-dlt-schema), [schema](https://dlthub.com/docs/general-usage/schema), [refresh](https://dlthub.com/docs/general-usage/pipeline), and DuckDB's [concurrency](https://duckdb.org/docs/stable/connect/concurrency) and [SUMMARIZE](https://duckdb.org/docs/stable/guides/meta/summarize) pages.

## Where the data is

- A DuckDB destination with no configured path writes `<pipeline_name>.duckdb`, or `<destination_name>.duckdb` for a named destination such as `[destination.warehouse]`, in the folder where the pipeline first ran.
  Later runs from other folders write to the same file, because the pipeline keeps that folder as `initial_cwd` in its local state.
  `print(load_info)` names the full path.
- Each dataset sits in the file as a DuckDB schema of the same name, so write `shop_data.orders` or run `USE shop_data`, because a new connection starts in `main`.
- Read from `<dataset>`, because `<dataset>_staging` holds only each merge table's last batch, even though DuckDB's "Did you mean" hint offers both.
- After a `dev_mode=True` run, read the dataset named by `pipeline.dataset_name`, because dev mode appends a timestamp, as in `dev_data_20261104074541`.

## Reading the DuckDB file

Read the file for ad-hoc SQL, `DESCRIBE` and `SUMMARIZE`; read through `pipeline.dataset()` in code that must also run on the production destination.

- Open the file read-only, and close it before the next pipeline run, because an open reader fails the run as [Destinations](SKILL.md#destinations) describes.
  A running pipeline holds the file read-write while it loads, so every other open fails then, read-only included; read-only readers admit each other.
- Attach the file read-only too, as in `ATTACH IF NOT EXISTS 'shop.duckdb' AS shop (READ_ONLY)`, also in the `state.sql` that `duckdb-skills:attach-db` writes when it is installed, because a plain `ATTACH` opens the file read-write and fails while a notebook holds it.
- Run `SET TimeZone = 'UTC'` on every connection, because DuckDB shows `TIMESTAMP WITH TIME ZONE` in the machine's zone while dlt reads in UTC, so `date_trunc('day', ordered_at)` files an order under a different day: 03:00 UTC on October 1 falls on September 30 in New York.

```python
from pathlib import Path

import duckdb
import polars as pl


def read_orders(database: Path) -> pl.DataFrame:
    with duckdb.connect(str(database), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        return connection.sql(
            "SELECT order_id, ordered_at, total FROM shop_data.orders"
        ).pl()


if __name__ == "__main__":
    print(read_orders(Path("shop.duckdb")))
```

```bash
duckdb -readonly shop.duckdb -c "SET TimeZone = 'UTC'; SUMMARIZE shop_data.orders"
```

When an agent's environment variable, such as `AI_AGENT` or `CLAUDECODE`, is set and stdout is not a terminal, the DuckDB 2.0 CLI prints markdown tables and shows only the first and last 20 rows of a result over 1,000 rows or 10,000 bytes; `-no-agent` restores the box tables.

## Reading through `pipeline.dataset()`

- Run `dlt.attach(pipeline_name="shop").dataset()` from the project root, because it reads the destination from the pipeline's state and the project's config.
  From another folder, a path set in `.dlt/` is invisible: dlt opens a new, empty `<pipeline_name>.duckdb`, and the query fails with `schema "shop_data" does not exist` or `DatabaseUndefinedRelation`.
- Each query opens and closes its own read-write connection, so it fails while another process holds the file and holds nothing between queries; `with dataset:` keeps one connection open.
- Get Polars with `pl.DataFrame(relation.arrow())`, because a relation has `.arrow()`, `.iter_arrow()`, `.df()` and `.fetchall()` but no `.pl()`, and the constructor's `DataFrame` type passes a `-> pl.DataFrame` return under `ty`.
  On duckdb 1.5, `.arrow()` emits a `DeprecationWarning` from dlt's DuckDB client, `fetch_arrow_table() is deprecated`, which fails a test under `filterwarnings = error`; [Testing](SKILL.md#testing) in `SKILL.md` holds the filter.
- Stream a large table with `relation.iter_arrow(chunk_size=100_000)`, because `relation.arrow(chunk_size=n)` returns only the first `n` rows.
- `dataset("SELECT ...")` runs one `SELECT` on the dataset's own tables.
  `SUMMARIZE`, `DESCRIBE` and `information_schema` raise `LineageFailedException`, so run those on the file.
- Join a nested table with `dataset["orders"].join("orders__items")`, because it finds the `_dlt_parent_id` link itself; the nested columns arrive prefixed `orders__items__`.

```python
import dlt
import polars as pl


def shipped_orders(dataset: dlt.Dataset) -> pl.DataFrame:
    relation = (
        dataset["orders"]
        .where("status", "eq", "shipped")
        .select("order_id", "ordered_at", "total")
        .order_by("ordered_at", "desc")
        .limit(100)
    )
    return pl.DataFrame(relation.arrow())


def main() -> None:
    dataset = dlt.attach(pipeline_name="shop").dataset()
    print(pl.DataFrame(dataset.row_counts().arrow()))
    print(shipped_orders(dataset))
    revenue = dataset(
        "SELECT status, sum(total) AS revenue FROM orders GROUP BY status"
    )
    print(pl.DataFrame(revenue.arrow()))
    for batch in dataset["orders__items"].iter_arrow(chunk_size=100_000):
        print(pl.DataFrame(batch).height)


if __name__ == "__main__":
    main()
```

## Checks after a load

Run them after the first load of a resource, after a schema change, and in tests.

1. **The load finished.**
   Count each root table's rows outside finished loads: `SELECT count(*) FROM shop_data.orders WHERE _dlt_load_id NOT IN (SELECT load_id FROM shop_data._dlt_loads WHERE status = 0)`.
   A failed run leaves the rows of the jobs that did load, with no `_dlt_loads` row.
   `status = 0` marks a finished package, not a clean one: under `raise_on_failed_jobs = false`, a package with a failed job still writes it.
   A table of frames carries `_dlt_load_id` only with the `add_dlt_load_id` setting in [Sources and resources](SKILL.md#sources-and-resources).
   When the tables carry no `_dlt_load_id`, read the last finished load with `SELECT max(inserted_at) FROM shop_data._dlt_loads WHERE status = 0` and check key uniqueness as in check 5 instead, because no query can then tell a failed load's rows apart.
   Done means every count is 0, or, without `_dlt_load_id`, the last finished load is the run you expect and no key repeats.
2. **The counts add up.**
   `dataset.row_counts()` totals each data table, and `pipeline.last_trace.last_normalize_info.row_counts` gives the rows this run sent.
   An `append` table grows by the rows sent; a `merge` table grows by at most that, because a row with a known key replaces the old one.
   `row_counts(load_id=...)` leaves out every table without `_dlt_load_id`, and raises a `ValueError` when none has one.
   Count a nested table's rows from one load with `dataset.table("orders__items", load_ids=[load_id])`, which filters through the root.
   Done means each total matches the source's own count, or the gap has a named reason.
3. **The shape is the one you expected.**
   `uv run dlt pipeline shop schema --format mermaid` draws the tables, keys and parent links.
   Every `--format` prints `Found pipeline ...` and `Found schema ...` on stdout before the document, so write a file from the schema instead: `pipeline.default_schema.to_mermaid(include_dlt_tables=False)` for the diagram, or `to_pretty_yaml()` for the whole schema.
   Besides the parent link in [`SKILL.md`](SKILL.md), a merge table's nested tables carry `_dlt_root_id`, which joins any depth to the root's `_dlt_id`; an append table's nested tables lack it.
   Done means every table is one you expected, and a `LEFT JOIN` from each nested table to its parent finds no row without a parent.
4. **The types are right at the destination.**
   Read them with `DESCRIBE shop_data.orders`, because a hint added after the first load changes the dlt schema, its diagram and the relation's `columns_schema`, and leaves the table's type alone.
   The traps below come from dict rows; a Polars frame keeps its dtypes, so `Datetime` in UTC, `Date` and `Decimal(12, 2)` land as `TIMESTAMP WITH TIME ZONE`, `DATE` and `DECIMAL(12,2)`.
   - Money is `DECIMAL(p,s)`: a float loads as `DOUBLE`, and a `Decimal` as `DECIMAL(38,9)` until hinted.
   - Timestamps are `TIMESTAMP WITH TIME ZONE`, and dlt stores a naive datetime as if it were UTC, so compare one known row with the source.
   - Dates are `DATE`: an ISO date string loads as `VARCHAR`, while an ISO timestamp string becomes a timestamp.
   - A column named `<column>__v_<type>` is a variant column: some rows held a value that did not fit the column's type, and their main column is null.
     Find them with `contains(column_name, '__v_')` on `information_schema.columns`, because `_` is a wildcard in `LIKE`, and `LIKE '%__v_%'` also matched dlt's `engine_version`.

   Done means every column has its intended type and no variant column exists.
5. **Keys, nulls and distinct values look like the source.**
   Every table with a natural key holds one row per key, `append` tables included, because an `append` table that re-reads a full snapshot doubles every sum on the next run.
   `SELECT order_id FROM shop_data.orders GROUP BY ALL HAVING count(*) > 1` returns nothing; for a table that keeps every version on purpose, run it on the downstream pick of each key's latest version.
   Before you sum money, find its currency or unit column and group by it, because a sum across currencies adds EUR to USD.
   `SUMMARIZE shop_data.orders` gives `null_percentage`, `approx_unique`, `min` and `max` per column.
   `approx_unique` drifts both ways, 495 and 520 for 500 unique keys, so use `count(DISTINCT order_id)` when the number matters.
   Done means no key repeats, no sum mixes currencies, and no column is unexpectedly null, constant or out of range.

## Fixing a column type

1. Fix the type where the rows are made: cast in the frame on a Polars resource, as in `pl.col("shipped_on").str.to_date()`, and hint the column on dict rows, under the schema rules in [`SKILL.md`](SKILL.md).
   A hint on a Polars frame leaves the data as it was and only warns that the destination must coerce it, which DuckDB did.
   Done means the cast or hint sits in the resource's code.
2. Reload that resource alone: `pipeline.run(source.with_resources("orders"), refresh="drop_resources")`.
   A run without a refresh leaves the column's type, for dicts and frames alike, and `refresh="drop_data"` keeps the table with its old types.
   `drop_resources` drops the resource's tables and wipes its incremental state, so it reloads from `initial_value`.
   Use it while the source can still serve the whole history; otherwise keep the column as loaded and cast it in the downstream model.
   Done means the run finished and the other resources kept their `_dlt_load_id`.
3. Repeat check 4.
   Done means `DESCRIBE` shows the new type.
