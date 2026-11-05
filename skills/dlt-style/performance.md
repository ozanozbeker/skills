# Performance

How to find the slow step of a dlt run, and the levers that make each step faster or lighter on memory.
Source: [optimizing dlt](https://dlthub.com/docs/reference/performance), [loader file formats](https://dlthub.com/docs/dlt-ecosystem/file-formats), [Arrow, pandas and Polars](https://dlthub.com/docs/dlt-ecosystem/verified-sources/arrow-pandas), [DuckDB](https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb), [parallel resources](https://dlthub.com/docs/general-usage/resource#declare-parallel-and-async-resources) and [progress monitors](https://dlthub.com/docs/general-usage/pipeline#monitor-the-loading-progress).

## Find the slow step

1. Run the pipeline once with `progress="log"` on `dlt.pipeline`, or `PROGRESS=log` in the environment, after `uv add psutil` so the log shows memory.
   It prints rows (jobs in the load step), rate and process memory for each step, at most once a second while items arrive; its CPU figure stays at 0.00%.
   Done means the log covers extract, normalize and load.
2. Read the step times with `uv run dlt pipeline <name> trace`, or from `pipeline.last_trace.steps`, whose items carry `step`, `started_at` and `finished_at`.
   The `run` step spans the other three, so compare `extract`, `normalize` and `load`.
   Done means you can name the slowest step and its seconds.
3. Run `uv run dlt pipeline <name> trace metrics --steps <step>` for files and bytes per table, and rows for extract and normalize; add `-v` to list each file.
   A table with one file in a step gets one worker in that step, whatever the worker settings.
   Done means you know the slow table's file count and file format.
4. Change one lever from the sections below, rerun on the same data, and compare that step's seconds.
   Done means the step got faster, or you reverted the lever.

## Levers

3,000,000 rows of 8 columns into a local DuckDB file on a 16-core Mac, median of two runs.

| Lever | Step | Before | After |
| --- | --- | --- | --- |
| Pages of 10,000 dicts per yield, not one dict | extract | 26 s | 13 s |
| `loader_file_format="parquet"` for dicts | normalize, load | 35 s, 84 s | 19 s, 1.5 s |
| Polars frames of 100,000 rows, not dict pages as Parquet | whole run | 33 s | 1.5 s |
| 4 normalize workers on 30 rotated extract files | normalize | 19 s | 6 s |
| 4 normalize workers on 1 extract file | normalize | 19 s | 19 s |
| 15 Parquet files, 20 load workers instead of 1 | load | 1.7 s | 0.3 s |

A local API that answers a page in 0.2 s and a detail request in 0.1 s:

| Lever | Before | After |
| --- | --- | --- |
| `parallelized=True` on 4 endpoints of 10 pages each | 9.2 s | 2.4 s |
| 500 rows per page instead of 50, for 2,000 rows | 8.6 s | 1.1 s |
| 100 detail calls: parallelized transformer, then 20 workers | 11.2 s | 2.5 s, then 0.9 s |

## Extract

- Yield frames when the source is already tabular (a DuckDB query, Parquet files, a database table read with the `pyarrow` or `connectorx` backend), because dlt writes them to Parquet as they arrive and normalize only links the file.
  Yield the Polars frame itself; dlt converts it, and it ran as fast as Arrow.
  [`sql-database.md`](sql-database.md) chooses the SQL backend and [`filesystem.md`](filesystem.md) the file reader.
- The `add_dlt_load_id` setting that every pipeline of frames carries added 0.1 s to 3,000,000 rows, while `add_dlt_id` rewrites each file.
- Ask a REST API for its largest page, because every request pays the API's latency; [`rest-api.md`](rest-api.md) names the paginator parameters.

### Parallel extraction

- `parallelized=True` overlaps resources, not pages: on the extract thread pool each resource still reads its own pages one after another.
- The resource's flag is silently ignored when its function has an injected argument: a plain default such as `page_size: int = 100` (dlt makes it configurable), a `dlt.config.value` or `dlt.secrets.value` default, or a `dlt.sources.incremental`.
  Call `.parallelize()` on the resource after calling it, or set `@dlt.source(parallelized=True)`.
  For the REST API source, pass `rest_api_source(config, parallelized=True)` or set `@dlt.source(parallelized=True)` on a source that yields from `rest_api_resources`, because `"parallelized": True` on a top-level endpoint or in `resource_defaults` hits the same trap.
  On a child endpoint, set `"parallelized": True` in its config, because that key, not the source flag, sends its per-parent requests side by side: 100 detail calls took 11.0 s under the source flag alone and 2.3 s with the key.
- An async generator resource runs concurrently with no flag, injected arguments included.
- For one request per parent item, give the transformer `parallelized=True` or write it as `async def`, because dlt then runs the calls side by side, whether the transformer returns or yields its item (see the table).
- Raise `[extract] workers` (default 5) and `[extract] max_parallel_items` (default 20) together, because `max_parallel_items` caps the items in flight in the thread pool and the async pool alike: 100 detail calls took 0.8 s with 50 workers and the default cap, and 0.5 s with the cap at 50.
- `[extract] next_item_mode = "fifo"` reads resources in declaration order; it changes the order, not the speed, and parallelized resources still overlap, so use it to debug.

## Normalize

- Normalize parses dicts row by row, so it is the step to scale for a dict source; frames skip it.
- `[normalize] workers` starts a process pool (the default, 1, runs in the main process) that hands whole extract files to workers, so rotate the extract files first, because nothing rotates them on DuckDB.
  Set `[sources.data_writer] file_max_bytes`, which applies to extract only, to the extracted size divided by the workers and by 8, for 8 files per worker.
- When the files are too few for the workers, extract logs a warning that names the table to split; act on it.

```toml
# .dlt/config.toml
[sources.data_writer]
file_max_bytes = 50000000

[normalize]
workers = 4
```

- Each worker writes one load file per table, so N workers also give the load step N files.
- dlt starts the workers with `spawn` on macOS and Windows, inside Airflow, Dagster or Prefect, and from a non-main thread, and with `fork` elsewhere on Linux.
  `spawn` re-imports the main script in every worker, so keep `pipeline.run` under `if __name__ == "__main__":` and run the pipeline from a file: without the guard the run failed in normalize, and from stdin the pool broke.
- Set `[normalize] start_method = "spawn"` on Linux when your code or a library starts threads, because a forked worker can inherit a held lock and hang.

## Load

- On DuckDB, load dicts as Parquet with `loader_file_format="parquet"` on `pipeline.run`, or `file_format="parquet"` on one resource, because the default `insert_values` writes and parses SQL text (see the table).
- Leave the format unset for frames, because they pick Parquet on DuckDB by themselves; forcing `insert_values` on them took 72 s against 1.5 s.
- Yield frames of 200,000 to 500,000 rows, because each frame becomes one Parquet row group, up to pyarrow's cap of 1,048,576 rows, and DuckDB loads a file's row groups in parallel: 3,000,000 rows loaded in 0.75 s from frames of 100,000, 0.16 to 0.31 s from 200,000 to 500,000, and 0.43 s from 1,000,000.
- `[load] workers` (default 20) runs one job per file, so it matters only when a table has several load files: dicts get them from `[normalize.data_writer] file_max_items` or `file_max_bytes` or from several normalize workers, and frames only from `[sources.data_writer]`, because normalize links their extract files as they are.
- Split a table into several load files only for Parquet on DuckDB, because parallel `insert_values` jobs multiply memory: 15 such files on 20 workers loaded in 18 s but peaked at 10 GB, against 83 s and 1.7 GB on one worker.
  Several load files load in no fixed order, even on one worker, so the table loses the order its rows were yielded in; sort with `ORDER BY` when you read it.

## Memory

With a paged or batched source, the DuckDB load step holds the peak: extract and normalize of 3,000,000 dicts stayed near 0.2 GB, and the load reached 1.1 GB for one Parquet file and 1.9 GB for `insert_values`.

- Read a big source in batches and yield each one, so extract holds one batch at a time: `to_arrow_reader(batch_size=...)` on a DuckDB relation (`fetch_record_batch(rows_per_batch=...)` on DuckDB 1.4), or `collect_batches(chunk_size=...)` on a Polars `LazyFrame`.
  Extracting 20,000,000 Parquet rows peaked at 0.5 GB with the DuckDB reader, 1.1 GB with Polars batches, and 2.8 to 3.2 GB with a whole frame.

```python
from collections.abc import Iterator

import dlt
import duckdb
import pyarrow as pa


@dlt.resource(name="orders", write_disposition="append")
def orders(path: str) -> Iterator[pa.RecordBatch]:
    with duckdb.connect() as con:
        yield from con.read_parquet(path).to_arrow_reader(batch_size=100_000)


def main() -> None:
    pipeline = dlt.pipeline(pipeline_name="orders", destination="duckdb", dataset_name="raw")
    pipeline.run(orders("data/orders.parquet"))


if __name__ == "__main__":
    main()
```

- dlt collects a yielded `LazyFrame` in full before writing it, so it costs as much as a whole frame.
- Yield dicts in pages, because Python dicts are large: one list of 3,000,000 dicts peaked at 4.3 GB against 1.1 GB for pages of 10,000.
- Leave `[data_writer] buffer_max_items` (default 5000) alone, because the peak sits in the load step: 100,000 changed neither time nor peak memory for pages of 10,000 dicts.
- Cap DuckDB during the load with `memory_limit` in `[destination.<name>.credentials.global_config]`, because its default is 80% of RAM (51.1 GiB on a 64 GB Mac): 256 MB held a Parquet load to 0.4 GB at the same speed.
  It does not bound an `insert_values` load, which is one more reason for Parquet.
  Put the table in `.dlt/config.toml` only while the database path itself comes from `secrets.toml` or `DESTINATION__<NAME>__CREDENTIALS`, because a `credentials` table that only `config.toml` holds fails the run at `step=sync` with `ValueNotSecretException`.
  With no path set, use the variable `DESTINATION__<NAME>__CREDENTIALS__GLOBAL_CONFIG='{"memory_limit": "1GB"}'` instead, in JSON, because dlt ignores `DESTINATION__<NAME>__CREDENTIALS__GLOBAL_CONFIG__MEMORY_LIMIT`.

```toml
# .dlt/config.toml
[destination.duckdb.credentials.global_config]
memory_limit = "1GB"
```

- Read loaded data back in chunks as [`data.md`](data.md) shows, because `iter_arrow` held 3,000,000 rows to a 0.3 GB peak against 0.5 GB for `.arrow()`.
