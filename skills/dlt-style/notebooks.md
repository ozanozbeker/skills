# Exploring a pipeline's data in marimo

How to wire a marimo notebook to a pipeline's DuckDB file, query it with SQL and Polars, chart it with Altair, and prove that it runs.
Notebook mechanics (cells, reactivity, UI elements, the file format) belong to `marimo-notebook` and Polars idioms to `polars`, when they are installed; this page keeps what dlt changes.
Source: [dataset access](https://dlthub.com/docs/general-usage/dataset-access/dataset), [DuckDB destination](https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb), and marimo's [SQL](https://docs.marimo.io/guides/working_with_data/sql/), [plotting](https://docs.marimo.io/api/plotting/), [scripts](https://docs.marimo.io/guides/scripts/), [exporting](https://docs.marimo.io/guides/exporting/) and [CLI](https://docs.marimo.io/cli/) pages.

`uv run dlt pipeline <name> show` and `uv run dlt dashboard` need `dlt[hub]` in 1.32.0, although the CLI reference asks only for marimo: without it, both print `WARNING: Install dlt[hub] for workspace dashboard and mcp support` and exit 0.
Write the notebook below instead.

## Wiring

- Open one read-only DuckDB connection, set it to UTC, and build the dlt dataset on it with `dlt.dataset(dlt.destinations.duckdb(connection), "shop_data")`.
  `mo.sql` and the dataset then share one lock and one time zone, and the dataset needs no local pipeline state.
- Build the dataset on that connection rather than with `dlt.attach(...).dataset()`, because the attached dataset opens the file read-write, which DuckDB refuses in a process that already holds it read-only: `Can't open a connection to same database file with a different configuration than existing connections`.
- Locate the file with `mo.notebook_dir()`, and start marimo from the project root, because the kernel's current directory is the folder marimo started in, not the notebook's folder, and dlt reads `.dlt/` from it.
  [`data.md`](data.md) shows what a subfolder start breaks.
- Stop the kernel before the next pipeline run, because its read-only connection holds the lock that fails the run.
  When the pipeline must load while the notebook stays open, open and close the connection inside each SQL cell, with `with duckdb.connect(str(database), read_only=True) as connection:` and the UTC setting, because `mo.sql` returns a Polars frame that outlives the connection.
- For a production destination, read through `dlt.attach(pipeline_name="shop").dataset()` as [`data.md`](data.md) describes.

## The notebook

The `shop` pipeline ran from the project root and wrote `shop.duckdb` there; the notebook is `notebooks/explore.py`.
It takes its dependencies from the project's `pyproject.toml` and needs no PEP 723 header, because `uv run marimo ...` runs it in the project's environment.

```python
"""Explore the orders the shop pipeline loaded."""

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import altair as alt
    import dlt
    import duckdb
    import marimo as mo
    import polars as pl

    return alt, dlt, duckdb, mo, pl


@app.cell
def _(dlt, duckdb, mo):
    database = mo.notebook_dir().parent / "shop.duckdb"
    connection = duckdb.connect(str(database), read_only=True)
    connection.execute("SET TimeZone = 'UTC'")
    dataset = dlt.dataset(dlt.destinations.duckdb(connection), "shop_data")
    return connection, dataset


@app.cell
def _(dataset, mo):
    mo.mermaid(
        dataset.schema.to_mermaid(include_dlt_tables=False, hide_descriptions=True)
    )
    return


@app.cell
def _(dataset, pl):
    pl.DataFrame(dataset.row_counts().arrow())
    return


@app.cell
def _(connection, mo):
    daily_revenue = mo.sql(
        """
        SELECT date_trunc('day', ordered_at) AS day, count(*) AS orders, sum(total) AS revenue
        FROM shop_data.orders
        GROUP BY ALL
        ORDER BY day
        """,
        engine=connection,
    )
    return (daily_revenue,)


@app.cell
def _(alt, daily_revenue, mo, pl):
    revenue_by_day = daily_revenue.with_columns(pl.col("revenue").cast(pl.Float64))
    revenue_chart = mo.ui.altair_chart(
        alt.Chart(revenue_by_day)
        .mark_line(point=True)
        .encode(
            x="utcyearmonthdate(day):T",
            y="revenue:Q",
            tooltip=["utcyearmonthdate(day):T", "orders:Q", "revenue:Q"],
        )
    )
    revenue_chart
    return


@app.cell
def _(connection, mo):
    _top_skus = mo.sql(
        """
        SELECT item.sku, sum(item.quantity) AS units, count(*) AS order_lines
        FROM shop_data.orders__items AS item
        JOIN shop_data.orders AS parent ON item._dlt_parent_id = parent._dlt_id
        GROUP BY ALL
        ORDER BY units DESC
        LIMIT 10
        """,
        engine=connection,
    )
    return


if __name__ == "__main__":
    app.run()
```

- Pass `engine=connection` to every `mo.sql`, because the default engine is a separate in-memory DuckDB, where `shop_data.orders` fails with `schema "shop_data" does not exist`.
  Qualify each table with the dataset, as [`data.md`](data.md) explains.
- Cast money to `Float64` in the frame you chart, and keep the `Decimal` everywhere else, because Altair's JSON encoder cannot serialize a `Decimal`: `chart.to_json()` raises `TypeError: Object of type Decimal is not JSON serializable`, and a bare `alt.Chart` cell logs it.
  `mo.ui.altair_chart` sends the frame as Arrow instead, and drew the uncast frame the same.
- Give every time field a `utc` time unit, in the tooltip too, as `utcyearmonthdate(day):T` above, and chart a UTC `Datetime` rather than a `Date`, because marimo sends a UTC `Datetime` with its offset but a Polars `Date` without one, which the browser reads as local midnight.
  In New York, the plain `day:T` drew January 1 as December 31, and in Tokyo, `utcyearmonth` on a `Date` labeled January as December; cast a `Date` with `pl.col("month").cast(pl.Datetime("us", "UTC"))`.
- Read the diagram for tables and parent links, and the types from `DESCRIBE`, because the diagram shows dlt's schema, as check 4 in [`data.md`](data.md#checks-after-a-load) explains.
- Give `notebooks/*.py` these per-file ignores in `ruff.toml`, or under `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml`, because under `select = ["ALL"]` marimo's cell format trips them, and `INP001` flags a folder that is not a package.
  Give each notebook a module docstring above `import marimo` for `D100` instead, because marimo keeps it when it saves.
  Name a result no other cell reads with a leading `_`, as `_top_skus` above, because marimo writes a bare `return` for it, so `F841` flags the name unless it starts with `_`.

  ```toml
  [lint.per-file-ignores]
  "notebooks/*.py" = [
    "ANN001",  # a cell's parameters are the names it reads, unannotated
    "ANN202",  # a cell is a function with no return annotation
    "B018",  # a cell shows its last expression
    "INP001",  # notebooks/ is not a package
    "PLC0415",  # the imports sit inside a cell
    "PLR0913",  # a cell takes every name it reads
    "PLR1711",  # a cell that no other cell reads from ends in a bare return
  ]
  ```

## Proving it runs

1. Run `uv run marimo check notebooks/explore.py`.
   It checks structure only: a notebook whose SQL fails still exits 0.
   Done means it exits 0 and prints nothing.
2. Run `uv run python notebooks/explore.py` from the project root.
   Done means it exits 0; a failing cell exits 1 with its traceback.
3. When the outputs should be kept, run `uv run marimo export html notebooks/explore.py -o explore.html`.
   A failing cell makes it exit 1 with `Export was successful, but some cells failed to execute`.
   It also saves every cell's output, query results included, to `notebooks/__marimo__/session/explore.py.json`, so keep `__marimo__/` out of git.
   Use it or step 2 after a new load, because `marimo export session` skips a notebook whose file has not changed and exits 0, even when its last run failed, unless given `--force-overwrite`.
   Done means it exits 0.

`uv run marimo edit notebooks/explore.py` opens the notebook to change it, and `uv run marimo run notebooks/explore.py` serves it as a read-only app.
