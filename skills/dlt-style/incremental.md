# Incremental loading

How a cursor picks the rows of each run, how to backfill or split a long load, and how to read, check and reset the stored cursor.
Source: [cursor-based incremental loading](https://dlthub.com/docs/general-usage/incremental/cursor), [lag](https://dlthub.com/docs/general-usage/incremental/lag), [troubleshooting](https://dlthub.com/docs/general-usage/incremental/troubleshooting), [state](https://dlthub.com/docs/general-usage/state), [full loading](https://dlthub.com/docs/general-usage/full-loading), [SQL database advanced usage](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/advanced) and the [CLI reference](https://dlthub.com/docs/reference/command-line-interface).

## The cursor

- Declare the cursor as a typed resource argument, `updated_at: dlt.sources.incremental[datetime] = dlt.sources.incremental("updated_at", initial_value=...)`, because dlt injects the bound instance there and the type argument sets the unit of `lag`.
  dlt keeps the stored cursor in the pipeline state and commits it to the destination with the data.
- Spell the cursor and an incremental resource's `primary_key` as the source does, because dlt reads them before normalization: `"updated_at"` on a field `UpdatedAt` raises `IncrementalCursorPathMissing`, and `primary_key="user_id"` raises `IncrementalPrimaryKeyMissing`.
- Filter the API or the query on `updated_at.start_value`, because it stays fixed for the run while `last_value` moves after every page: a page-number loop filtered on `last_value` lost rows.
- Pair a cursor on a column that changes, such as `updated_at`, with `merge` on a primary key, because an updated row returns with a newer cursor value and `append` keeps both versions.
- The default closed range re-reads the rows equal to the stored cursor, and dlt drops the ones it loaded before by a hash of their primary key, or of the whole row when there is no key.
  With a primary key, a boundary row that changed without moving its cursor is dropped as well.
- Use `range_start="open"` only on a unique cursor such as an auto-increment id, because it skips every row equal to the stored cursor: a row written late with the same timestamp was lost, and so was the rest of a group of equal values cut at a round boundary.
- Pass `primary_key=()` to the incremental when hashing the boundary rows costs more than loading them again into a `merge` table; the rows then load again, and the table keeps its key hint.
- Set `row_order` only when the source returns rows sorted by the cursor, because dlt closes the generator at the first row out of range: an unsorted source lost new rows.
  `"desc"` stops below `start_value`, and `"asc"` stops only at `end_value`, so `"asc"` saves requests in a backfill alone.
- Use `lag` for a source that writes rows late, and pair it with `merge`, because lag re-reads a window behind the stored cursor with deduplication off: `append` loaded the window twice.
  The unit follows the declared cursor type: seconds for `datetime`, days for `date`, the cursor's own unit for numbers.
  Without a `datetime` type argument, a date-shaped string such as `initial_value="2024-01-01"` declares a date cursor, so `lag=3600` meant 3600 days and every run reloaded from `initial_value`.
  The window stops at `initial_value`, and the stored cursor never moves back.
- Keep a string cursor as text when every value shares one ISO 8601 shape, the same fields, precision and offset, such as `2024-01-02T09:30:00Z`, because such strings sort in time order.
  Convert it to `datetime` with `add_map` only when the shape varies, because text compares character by character: `"2024-10-01"` sorted before `"2024-9-30"`, `"2024-01-01T10:00:00.500Z"` before `"2024-01-01T10:00:00Z"`, and both newer rows were dropped.
  dlt places the map before the incremental step when `insert_at` is left out, while `insert_at=2` put it after and the run failed.
  Give `initial_value` the same type, because a `str` against `datetime` rows raises `IncrementalCursorInvalidCoercion`; a pipeline that already stored a string needs one run with `refresh="drop_resources"`.
  The `rest_api` form is in [`rest-api.md`](rest-api.md#incremental).
- On frames, name a top-level column as the cursor, because a nested path raises `IncrementalCursorPathMissing`.
- Choose `on_cursor_value_missing` for rows without a cursor value: `"raise"` (the default), `"include"` or `"exclude"`.
  On `sql_table`, `"include"` adds `OR <cursor> IS NULL` to the query, so those rows return on every run and belong in a `merge` table.
- Keep resource names stable, because state is keyed by resource name and a renamed resource started again from `initial_value`.

## The cursor in each core source

- `rest_api`: the endpoint's `incremental` key takes the arguments of `dlt.sources.incremental` plus `convert`, and `{incremental.start_value}` in the request carries the stored cursor; syntax in [`rest-api.md`](rest-api.md).
- `sql_table` and `sql_database`: `incremental=` on `sql_table`, or `apply_hints(incremental=...)` on a `sql_database` resource, and dlt writes the range into the query's `WHERE` clause; the generated SQL is in [`sql-database.md`](sql-database.md).
- `filesystem`: `incremental=dlt.sources.incremental("modification_date")` on `filesystem(...)` reads only the files modified since the stored cursor, and `row_order` sorts the listing; syntax in [`filesystem.md`](filesystem.md).

## Backfills

- Pass the range when you call the resource, `orders(updated_at=dlt.sources.incremental(initial_value=..., end_value=...))`, because dlt merges it with the declared default and keeps the cursor path.
- A run with `end_value` reads `[initial_value, end_value)` and neither reads nor writes the stored cursor, so the scheduled run continues from its own stored cursor.
  Chain the chunks so each `end_value` is the next `initial_value`, then start the scheduled run at the last `end_value`.
- On DuckDB, run the chunks one after another in one process, because DuckDB takes one writer process.
- On a warehouse, run parallel chunks after one small chunk has created the dataset, each process with its own `pipelines_dir` and its own staging dataset, because parallel chunks race on all three.
  On Postgres, parallel chunks failed with `SchemaUpdateTerminalError` on a new dataset, a `UniqueViolation` from the shared `<dataset>_staging` and `FileNotFoundError` in a shared `pipelines_dir`, and with all three in place none failed.
  Set the staging dataset as [Parallel pipelines](production.md#parallel-pipelines) does.

## Splitting a long load

Run time-boxed rounds until a round loads no rows into the table:

```python
import dlt
from dlt.sources import DltResource
from dlt.sources.sql_database import sql_table


def load_in_rounds(
    pipeline: dlt.Pipeline, resource: DltResource, table: str, *, seconds: float, rounds_max: int
) -> int:
    """Run `resource` in time-boxed rounds until a round loads no rows into `table`."""
    for number in range(1, rounds_max + 1):
        pipeline.run(resource.add_limit(max_time=seconds))
        trace = pipeline.last_trace
        normalize_info = trace.last_normalize_info if trace is not None else None
        if normalize_info is not None and not normalize_info.row_counts.get(table):
            return number
    msg = f"{table} still had rows to load after {rounds_max} rounds"
    raise RuntimeError(msg)


messages = sql_table(table="messages", incremental=dlt.sources.incremental("created_at", row_order="asc"))
pipeline = dlt.pipeline(pipeline_name="chat", destination="duckdb", dataset_name="chat_raw")
load_in_rounds(pipeline, messages, table="messages", seconds=600, rounds_max=100)
```

- Limit each round by `max_time`, because on `sql_table` `add_limit(max_items)` becomes a SQL `LIMIT` of `max_items` times `chunk_size` rows, and a cursor value shared by more rows than that stalls the closed range, and the loop stopped or spun.
- Set `row_order="asc"` on `sql_table` and `filesystem`, because it is what adds the `ORDER BY` or sorts the listing, and without it the rounds lost rows.
- Exit on the table's row count, because a round with no new rows can still load a state package and keep `load_info.is_empty` false, so a `while not load_info.is_empty` loop ran to its cap.

## State

- Read the stored cursor with `uv run dlt pipeline <name> info -v`, which prints the `sources` state with each `last_value`.
- In Python, read `dlt.attach("<name>").state["sources"][source]["resources"][resource]["incremental"][cursor_path]["last_value"]`.
  `source` is the source's name (`sql_database`, `rest_api`, or the `@dlt.source` name), or, for a standalone resource such as `sql_table`, the pipeline's default schema name, which is the pipeline name unless a source ran in that pipeline first.
  The next run starts from that value, less any `lag`.
- Prefer a cursor with a time over a date, because each row that shares the stored cursor keeps a hash in state, and dlt warns above 200 with `Large number of records ... sharing the same value of cursor field`.
- Keep custom state to cursors and short lists, because dlt writes the whole state, compressed, as a new `_dlt_pipeline_state` row on every run that changes it: 100,000 ids made a 300 KB row.
  Past the docs' limit of about 100,000 items, read the high-water mark from the destination inside the resource with `pl.DataFrame(dlt.current.pipeline().dataset()("select max(id) as max_id from comments").arrow())`, run only when `"comments" in dlt.current.source_schema().data_table_names(seen_data_only=True)`, because the table exists only after a load that put rows in it, while `first_run` turns false after any load and the query then failed.
- State belongs to the pipeline name, the destination and the dataset: a new pipeline name, database file or dataset name started from `initial_value`, and a deleted pipeline's working directory restored the stored cursor from the destination.
- Re-read a window without moving the stored cursor with a backfill run, and reset one resource's stored cursor with `uv run dlt -y pipeline <name> drop <resource> --state-only`, which keeps its tables.

## A cursor that does not advance

Check, in order:

1. Run `uv run dlt pipeline <name> info` and compare `pipeline_name`, `destination_type`, `dataset_name` and the destination location, which `uv run dlt pipeline <name> trace` prints, with the earlier runs, because a change in any of them starts from `initial_value`.
   Done means all four match.
2. Remove `dev_mode=True`, because it wipes the state each time the pipeline is created.
   Done means `info` shows `_dev_mode: False`.
3. Remove every `refresh`, in `dlt.pipeline()`, in `run()` and as `PIPELINES__<NAME>__REFRESH`, because each mode resets the state of the resources it selects.
   Done means no `refresh` is set in the code, `.dlt/config.toml` or the environment.
4. Give a resource with a cursor `append` or `merge`, and keep `write_disposition` off `run()`, because a bare `"replace"` on the resource or on `run()` resets the stored cursor on every run, and the dict form keeps the stored cursor but empties the table on a run with no new rows.
   Done means no `replace` reaches a resource that has a cursor.
5. Run once with `RUNTIME__LOG_LEVEL=INFO` and find `Bind incremental on <resource> with initial_value: ..., start_value: ...`, which dlt logs only at INFO and only for a cursor it bound.
   Done means the line names the resource and shows the `start_value` you expect.
6. Compare `last_value` from `info -v` before and after a run.
   Done means it moved, or the source had no rows past it.
