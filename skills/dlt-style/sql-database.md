# SQL databases

How to load tables with the core `sql_database` source and `sql_table` resource: look at the database first, connect, pick the backend and reflection level, query incrementally, add a table, and read the failures.
Source: the SQL database [setup](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/setup), [configuration](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/configuration), [usage](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/usage), [advanced](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/advanced) and [troubleshooting](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/troubleshooting) pages, and [incremental loading from SQL databases](https://dlthub.com/docs/walkthroughs/sql-incremental-configuration).

## Look at the database first

1. Take the quick look in DuckDB, which installs and loads its `sqlite`, `postgres` or `mysql` extension on the first `ATTACH`.
   For Postgres attach `'host=db.internal dbname=shop user=reader'` with `TYPE postgres`; for MySQL, `'host=db.internal user=reader database=shop'` with `TYPE mysql`.

   ```bash
   duckdb -c "ATTACH 'shop.sqlite' AS src (TYPE sqlite, READ_ONLY);
   SELECT name, column_names FROM (SHOW ALL TABLES) WHERE database = 'src';
   DESCRIBE src.orders; SELECT count(*) FROM src.orders;"
   ```

   Done means you have each table's columns and row count.

2. Read the types, keys and indexes from dlt and SQLAlchemy without loading a row, because DuckDB shows its own types: a SQLite `NUMERIC(12,2)` reads as `DOUBLE` and `JSON` as `VARCHAR`.

   ```python
   import sqlalchemy as sa
   from dlt.common.configuration import resolve_configuration
   from dlt.sources.credentials import ConnectionStringCredentials
   from dlt.sources.sql_database import sql_database

   tables = ["orders", "customers"]
   sections = ("sources", "sql_database")
   credentials = resolve_configuration(ConnectionStringCredentials(), sections=sections)
   inspector = sa.inspect(sa.create_engine(credentials.to_native_representation()))
   source = sql_database(credentials=credentials, table_names=tables, backend="pyarrow")
   for table in tables:
       print(table, [index["column_names"] for index in inspector.get_indexes(table)])
       columns = source.resources[table].compute_table_schema()["columns"]
       for name, column in columns.items():
           print(f"  {name}: {column}")
   ```

   Done means every table has a primary key or a chosen one, money and timestamp columns show the precision and timezone you expect, and you know which cursor columns have an index.

## Connect

The `sql-database` extra installs SQLAlchemy and no driver, so add the driver with `uv add` and name it in the URL.

| Database | URL | Package |
| --- | --- | --- |
| PostgreSQL | `postgresql+psycopg2://` or `postgresql+psycopg://` | `psycopg2-binary` or `psycopg[binary]` |
| MySQL | `mysql+pymysql://` | `pymysql` |
| SQL Server | `mssql+pyodbc://` | `pyodbc`, plus unixODBC from the system package manager |
| Oracle | `oracle+oracledb://` | `oracledb`, which needs no Oracle client |
| SQLite | `sqlite:////absolute/path.db` | none |

- Name the driver even when it is the default, because SQLAlchemy 2.1 loads `psycopg` for a bare `postgresql://` and `oracledb` for `oracle://`, where 2.0 loaded `psycopg2` and `cx_Oracle`.
- Write the credentials as one URL under `[sources.sql_database]`, the section `sql_table` reads too, for a role with only `SELECT`, which was enough to reflect and load on Postgres; [`secrets.md`](secrets.md) shows how to write it without seeing it.
- `sql_database()` and `sql_table()` connect and reflect when called, so a missing driver or an unreachable database fails on that line, before `pipeline.run`.
  `defer_table_reflect=True`, which needs `table_names`, moves the connection and the reflection into extraction; use it where sources are built at import, as in Dagster's `@dlt_assets(dlt_source=...)` (see `dagster-expert`, when it is installed).

## Tables and settings

- Pass `table_names`, because `.with_resources()` reflects every table in the schema first; views load only when named there or with `include_views=True`.
- Set each table's disposition with `apply_hints`, because `sql_table` defaults to `append`, and a table without a cursor then duplicates its rows every run.
- Per-table keys go under `[sources.sql_database.<table>]`, for `sql_table` too, and `write_disposition` there must be an inline table, `{ disposition = "merge" }`, because a string raises `ConfigValueCannotBeCoercedException` and no environment variable can set it.
- Load a second database through a clone, `sql_database.clone(name="crm", section="crm")(...)`, because it reads its own `[sources.crm]` section.

## Choose the backend

Seconds to load 300,000 rows into DuckDB, with the columns all four backends can read:

| Backend | SQLite, 9 columns | Postgres, 4 columns | Types |
| --- | --- | --- | --- |
| `pyarrow` | 1.0 s | 1.1 s | Exact, `numeric(38,18)`, `timestamptz` and JSON included |
| `sqlalchemy` | 15.7 s | 11.8 s | Exact; every row passes the normalizer as a dict |
| `connectorx` | 0.6 s | 0.6 s | Decimals as doubles on SQLite and rounded to 10 places on Postgres; can fail past 18 integer digits, and fails on SQLite text timestamps with an offset |
| `pandas` | 1.2 s | 1.2 s | Decimals as doubles, so no `numeric(38,18)` value loaded intact while the column still read `DECIMAL(38,18)`; JSON fails, and mixed UTC offsets fail or lose the offset |

- Use `pyarrow`, because it is as exact as `sqlalchemy` and 8 to 15 times faster; it needs `pyarrow` (the `parquet` extra) and neither numpy nor pandas.
- Keep `sqlalchemy` only to unnest a JSON column into nested tables, which it alone does: a `type_adapter_callback` returning `None` for `sa.JSON` leaves that column to the data while the rest keep their reflected types.
  On DuckDB, run it with `pipeline.run(..., loader_file_format="parquet")`, which cut 16.2 s to 5.8 s.
- Take `connectorx` only for a table checked against those limits, with `backend_kwargs={"return_type": "arrow_stream"}`, because otherwise it ignores `chunk_size` and returns the table as one Arrow table.
  Reflection still runs through SQLAlchemy, so keep its driver; `backend_kwargs={"conn": "<url>"}` overrides the URL connectorx gets.
- The arrow backends yield frames, so their tables carry `_dlt_load_id` only with the `add_dlt_load_id` setting in [`SKILL.md`](SKILL.md#sources-and-resources).
- Size `chunk_size` (default 50,000 rows) for memory, because it does not change speed: 1,000 to 200,000 all took 1.0 s on `pyarrow` while peak memory rose from 290 MB to 500 MB; the other levers are in [`performance.md`](performance.md).

## Reflection and adapters

- Keep the default `reflection_level="full"`, because it carries the declared decimal precision and scale, keeps naive timestamps naive and types JSON as `json`.
- Fix one column with a hint such as `apply_hints(columns={"amount": {"data_type": "decimal", "precision": 18, "scale": 4}})`, not with `minimal`, because `minimal` infers every column from data: naive timestamps became `TIMESTAMP WITH TIME ZONE`, `NUMERIC(12,2)` became `DECIMAL(38,9)`, or on `pyarrow` the first chunk's `DECIMAL(7,2)`, and `sqlalchemy` unnested JSON.
- Reflection sets the primary key at every level, composite keys included, so `merge` needs no `primary_key`.
  A table or view without a declared key merges as an append with only the warning `no primary or merge keys defined`, so give it `apply_hints(primary_key=...)`.
- `query_adapter_callback(query, table, incremental, engine)` receives the SELECT with the cursor `WHERE` already on it, so narrow it with `query.where(...)`; a returned `sa.text(...)` replaces the whole query, cursor filter included.
- Pass `table_adapter_callback=remove_nullability_adapter` from the first run, because a `NOT NULL` column the source later drops fails every run after with `ArrowInvalid`.

## Incremental queries

- The query is `WHERE <cursor> >= :start_value` with no `ORDER BY`; the cursor rules behind it are in [`incremental.md`](incremental.md).
  `row_order="asc"` adds `ORDER BY <cursor> ASC`, `range_start="open"` turns `>=` into `>`, `end_value` adds `AND <cursor> < :end_value`, `on_cursor_value_missing="include"` adds `OR <cursor> IS NULL`, and `add_limit(n)` adds `LIMIT n * chunk_size`.
- Index the cursor column, because the query is a range scan on it; SQLite and Postgres both answered it from the index.
- Give `initial_value` the column's awareness, aware UTC for `timestamptz` and naive for `timestamp`, because a mismatch only warns `differ in timezone awareness` while the database reads the value in the session time zone.
  With the session in `America/Chicago`, a naive value on a Postgres `timestamptz` cursor skipped rows, and an aware value on a naive column read extra rows that dlt then dropped.
  In TOML, `initial_value = 2024-07-01T00:00:00Z` is aware and `2024-07-01T00:00:00` naive.
- Keep a cursor that the database stores as ISO 8601 text, as SQLite does for timestamps, as text: write `initial_value` and `end_value` in its shape, such as `"2026-10-30T00:00:00Z"`, and cast the column downstream, because a `timestamp` hint makes the stored cursor a `datetime` that SQLAlchemy binds as `2026-10-31 23:59:28.000000`, which sorts as text before every value of its day.
  That re-read the cursor's whole day on each run, skipped the last day of a backfill with `end_value`, and logged a conversion WARNING per chunk.
- A cursor never sees a row deleted from the source.
  Have the source soft-delete and mark the flag with `columns={"is_deleted": {"hard_delete": True}}`, so `merge` removes the row, or reload the table on a schedule.

## Add a table to a working pipeline

1. Add the table to `table_names` with its hints (a key if it has none, a disposition, a cursor), and load it alone once with `pipeline.run(source.with_resources("<table>"))`.
   Done means only the new table loaded, `compute_table_schema()` shows its key and disposition, and the other cursors in `pipeline.state` did not move.
2. Run the whole source on its schedule.
   Done means the old tables load only rows past their cursors and the new one loads as its disposition says.

## The production shape

The source a scheduled run loads, with the destination named in `config.toml` and the URL in `SOURCES__SQL_DATABASE__CREDENTIALS`; [`production.md`](production.md) holds the checks before its first scheduled run.

```python
from datetime import UTC, datetime

import dlt
from dlt.sources.sql_database import remove_nullability_adapter, sql_database


def shop() -> dlt.sources.DltSource:
    """Orders merge on their key from an updated_at cursor; customers reload in full."""
    source = sql_database(
        table_names=["orders", "customers"],
        backend="pyarrow",
        table_adapter_callback=remove_nullability_adapter,
    )
    since = datetime(2024, 7, 1, tzinfo=UTC)
    source.orders.apply_hints(
        write_disposition="merge",
        incremental=dlt.sources.incremental("updated_at", initial_value=since),
        columns={"is_deleted": {"hard_delete": True}},
    )
    source.customers.apply_hints(write_disposition="replace")
    return source


if __name__ == "__main__":
    pipeline = dlt.pipeline("shop", destination="warehouse", dataset_name="shop_raw")
    print(pipeline.run(shop()))
```

## Failure signatures

| Signature | Cause and fix |
| --- | --- |
| `No module named 'psycopg'` on `sql_database(...)` | A bare `postgresql://` under SQLAlchemy 2.1; write `postgresql+psycopg2://` or add `psycopg[binary]` |
| ``Cursor column `UpdatedAt` does not exist in table `orders` `` | The cursor is not spelled as the database reflects it; copy the name from `compute_table_schema()` |
| Warning `several column hints were different` | Rerun with `RUNTIME__LOG_LEVEL=INFO`; `decimal defined in resource will overwrite arrow hint with value double` means the backend delivered doubles, so use `pyarrow`; `json ... with value text` also shows on `pyarrow`, and the JSON still loads intact |
| `ConnectorX returned decimal columns ... with lower precision`, `decimal scale is not equal to expected scale`, `Malformed JSON ... Input: "{'channel': 'web', ...}"` or `Table schema does not match schema used to create file` | `connectorx` or `pandas` could not carry a decimal, a JSON value or a time zone; use `pyarrow`, and after a failure at load, such as `Malformed JSON`, first discard the pending package as [`production.md`](production.md) shows, because the next run retries it |
| `ArrowInvalid: Column 'customer_id' is declared non-nullable but contains nulls` | The source dropped a `NOT NULL` column; use `remove_nullability_adapter` |
