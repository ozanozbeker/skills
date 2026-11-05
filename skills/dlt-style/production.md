# Running in production

Recovering from a failed load, retries, logs, monitoring, staging, parallel pipelines and Dagster, with the one sequence for taking a pipeline to production.
Reading a failure is in [`debugging.md`](debugging.md), and tuning is in [`performance.md`](performance.md).
Source: [running in production](https://dlthub.com/docs/running-in-production/running), [performance](https://dlthub.com/docs/reference/performance), [staging](https://dlthub.com/docs/dlt-ecosystem/staging), the [filesystem destination](https://dlthub.com/docs/dlt-ecosystem/destinations/filesystem), [deploy with Dagster](https://dlthub.com/docs/walkthroughs/deploy-a-pipeline/deploy-with-dagster), Dagster's [dlt integration](https://dagster.io/docs/integrations/libraries/dlt/dlt-pythonic) and [dagster-dlt on PyPI](https://pypi.org/project/dagster-dlt/).

## Pending packages

- A run that fails at `step=normalize` or `step=load` leaves its package pending, and the next `pipeline.run(data)` only finishes that package, with a warning and nothing extracted from `data`, so trigger one more run after a recovery.
- Keep the pipeline's working directory, `$DLT_DATA_DIR/pipelines/<name>` or `~/.dlt/pipelines/<name>` by default, on persistent storage, because a wiped one loses the pending package; the next run restores state from the destination and extracts again, so the rows the failed load already wrote to an `append` table appear twice.
- Set `[load] delete_completed_jobs = true`, because every loaded package otherwise keeps its job files, which are the extracted rows, under `load/loaded/` for good.

## A load job that fails

Since dlt 1.30, a job the destination rejects stays queued for retry, its package stays pending, and the run raises `LoadClientJobTerminalRetry`.

| Way out | When | How |
| --- | --- | --- |
| Retry | The cause is fixed outside dlt, such as a widened column or a granted permission | `dlt.attach(pipeline_name="shop").load()`, or the next run |
| Fail the job | Its rows can never load, and the rest of the package should | `uv run dlt pipeline shop load-package <load_id> fail-job <job> -y`, then load |
| Abort | The package must not load | `uv run dlt pipeline shop abort-packages -y` |

- Failing a job lets the next load complete the package and commit the incremental cursor past the job's rows, so they never load again without a backfill.
- Abort rewinds local state and schemas, cursors included, to where the package started, so the next run extracts the same rows again.
- Abort keeps the rows that completed jobs already wrote, so delete an `append` table's rows with the aborted `_dlt_load_id` before the rerun, or they load twice.
  Leave `merge` and `replace` tables to the rerun, because it rewrites them, a merge by key and a replace in full.
- Keep `[load] raise_on_failed_jobs = true`, the default, because `false` completes the package, raises nothing and moves the cursor past the rows that failed; only `load_info.has_failed_jobs` or a call to `load_info.raise_on_failed_jobs()` then reports the failure.
- Keep `[load] auto_abort_on_terminal_error = false`, the default, because the `LoadClientJobFailed` it raises reaches `retry_load` as retryable, and `run_with_retries` below then extracted and failed three times instead of once.

## Retries

- dlt retries a transient job inside the load step and an HTTP request inside its clients, but never reruns a pipeline step.
  Wrap the run in `tenacity` with `retry_load()` from `dlt.pipeline.helpers`, which retries the load step and stops on terminal errors, as `run_with_retries` below does.
- Use `retry_load(("sync", "load"))` when the destination connection can drop or another process can hold the DuckDB file, because those failures raise at `step=sync`; it waited out a held DuckDB file and loaded once the other process closed it.
- Add `"extract"` only for a source whose client does not retry, because `retry_load(("extract", "load"))` also retries a bug in a resource and an HTTP 400.
- Build the source inside the retried call, because a resource made from a generator object raises `SourceExhausted` on the second attempt.

## Logs

- Run production at `[runtime] log_level = "INFO"`, because the default `WARNING` prints nothing for a healthy run and `INFO` names the package and job a crash interrupted; keep `DEBUG` for a local reproduction.
- Write `[runtime] log_format = "JSON"` in capitals for a log collector, because lowercase `json` is read as a Python format string and the run crashes with `ValueError: invalid format: no fields`.
  Its variable is `RUNTIME__LOG_FORMAT`, because the bare `LOG_FORMAT` the docs mention is ignored.
- Log the run's `LoadInfo` with dlt's logger, `from dlt.common import logger` then `logger.info(str(load_info))`, as the `__main__` block under [Monitoring](#monitoring) does, because the line then follows `log_level` and `log_format`, one JSON object under `JSON`, and ruff's `T201` finds no `print`.

## Monitoring

Record one flat row per run, failed or not, in a monitoring dataset beside the data.
The docs' `pipeline.run([load_info], table_name="_load_info")` strips secrets, but with the trace it adds 34 tables to the data schema, logs 8 warning blocks per run, and replaces `pipeline.last_trace` with its own run.

```python
from collections.abc import Callable

import dlt
from dlt.common import logger
from dlt.common.pipeline import LoadInfo
from dlt.extract import DltResource, DltSource
from dlt.pipeline.exceptions import PipelineStepFailed
from dlt.pipeline.helpers import retry_load
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential


def record_run(pipeline: dlt.Pipeline, info: LoadInfo | None) -> None:
    """Append one row about the pipeline's last run to <dataset>_monitoring.runs."""
    trace = pipeline.last_trace
    if trace is None:
        msg = f"pipeline {pipeline.pipeline_name} has no run to record"
        raise RuntimeError(msg)
    failed = next((step for step in trace.steps if step.step_exception is not None), None)
    normalize = trace.last_normalize_info
    packages = info.load_packages if info else []
    record = {
        "pipeline_name": pipeline.pipeline_name,
        "started_at": trace.started_at,
        "finished_at": trace.finished_at,
        "load_ids": ",".join(info.loads_ids) if info else "",
        "row_counts": dict(normalize.row_counts) if normalize else {},
        "schema_changes": ",".join(
            table for package in packages for table in package.schema_update if not table.startswith("_dlt")
        ),
        "failed_step": failed.step if failed else None,
        "error": str(failed.step_exception)[:4000] if failed else None,
    }
    monitor = dlt.pipeline(
        pipeline_name=f"{pipeline.pipeline_name}_monitoring",
        destination=pipeline.destination,
        dataset_name=f"{pipeline.dataset_name}_monitoring",
        pipelines_dir=pipeline.pipelines_dir,
    )
    hints = {"row_counts": {"data_type": "json"}, "failed_step": {"data_type": "text"}, "error": {"data_type": "text"}}
    monitor.run([record], table_name="runs", write_disposition="append", columns=hints)


def run_with_retries(pipeline: dlt.Pipeline, make_source: Callable[[], DltSource]) -> LoadInfo:
    """Retry the load step with backoff, record every attempt, re-raise the last failure."""
    info: LoadInfo | None = None
    for attempt in Retrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, max=60),
        retry=retry_if_exception(retry_load()),
        reraise=True,
    ):
        with attempt:
            try:
                info = pipeline.run(make_source())
            except PipelineStepFailed:
                record_run(pipeline, None)
                raise
    if info is None:
        msg = f"pipeline {pipeline.pipeline_name} ended its retries without a run"
        raise RuntimeError(msg)
    record_run(pipeline, info)
    return info


@dlt.source
def shop() -> DltResource:
    """Stand in for your source."""
    return dlt.resource([{"id": 1, "total": 10}], name="orders", primary_key="id", write_disposition="merge")


if __name__ == "__main__":
    pipeline = dlt.pipeline(pipeline_name="shop", destination="duckdb", dataset_name="shop_raw")
    logger.info(str(run_with_retries(pipeline, shop)))
```

- Alert when `schema_changes` is not empty: the first run lists every table, an unchanged run lists none, and a new column lists its table.
- Guard `last_normalize_info`, as the code does, because it is `None` after a run that only finished a pending package.
- Pass the data pipeline's `pipelines_dir` to the monitoring pipeline, as the code does, so a test that keeps `pipelines_dir` under `tmp_path` keeps the monitoring state there too.
- Expect no row for a failure at `step=sync`, such as a held DuckDB file, because `record_run` fails on the same destination and raises its own error, which names the `<dataset>_monitoring` dataset.
- The `error` column stores the exception text, so a key sent in a URL lands in the monitoring table too; [`rest-api.md`](rest-api.md#the-config) sends keys in a header.

## Destinations

- A `merge`, or a `replace` through `insert-from-staging`, loads through `<dataset>_staging`, which keeps the last batch after the load; set `[load] truncate_staging_dataset = true` to empty it, unless another pipeline shares that dataset.
- The filesystem destination merges only with `table_format="delta"` or `"iceberg"`; plain files log `Falling back to append` and keep both rows of a key.

## Parallel pipelines

- Give each concurrent run its own pipeline name or `DLT_DATA_DIR`, because two runs of one name share `state.json` and the schema file, and the last writer wins.
- Give each pipeline that loads one dataset at the same time its own staging dataset, with `staging_dataset_name_layout=f"%s_staging_{tenant}"` on the destination factory or a variable such as `DESTINATION__POSTGRES__STAGING_DATASET_NAME_LAYOUT="%s_staging_3"`, because a shared staging dataset loses or duplicates rows.
- Load a DuckDB file from one process at a time, because DuckDB locks the file to one process.
- Retry the DDL races of parallel runs with `retry_if_exception(retry_schema_update()) | retry_if_exception(retry_load())`, both from `dlt.pipeline.helpers`.

## Dagster

- Use the `dagster-dlt` package: `@dlt_assets(dlt_source=..., dlt_pipeline=..., name=..., group_name=...)` on a function that yields from `dlt.run(context=context)` on its `DagsterDltResource` argument.
- Pass a `@dlt.source` result as `dlt_source`, because the integration takes a `DltSource`, not a bare resource.
- Keep an executor that starts a process per op, such as Dagster's default multiprocess executor, because dlt intercepts SIGTERM only on the main thread, and the load step drains its jobs on SIGTERM.
- Limit concurrency on partitioned dlt assets, because every partition runs one pipeline name and its state.
- Leave the rest of the Dagster project to `dagster-expert`, when it is installed.

## Go to production

1. **Remove the development switches:** `add_limit`, and `dev_mode=True`, which loads into a new `<dataset>_<timestamp>` dataset on every run.
   Expect the first run without `dev_mode` to log `was previously created with dev_mode=True ... Local pipeline state and schemas will be reset`, because the pipeline then syncs its state from the destination.
   Drop the `<dataset>_<timestamp>` datasets and their `_staging` siblings that `dev_mode` left in a DuckDB file with `DROP SCHEMA <name> CASCADE` in a read-write `duckdb` session, because no run removes them.
   Done means `grep -rnE "add_limit|dev_mode" <pipeline code>` matches only tests, and the DuckDB file holds no `<dataset>_<timestamp>` dataset.
2. **Declare a write disposition on every resource, and a key on every `merge`,** under [`SKILL.md`](SKILL.md).
   Done means `uv run dlt pipeline <name> schema --format yaml --remove-defaults` shows the intended `write_disposition` on each table and `primary_key: true` on each merge key.
3. **Give every resource that is not reloaded in full an incremental cursor,** under [`incremental.md`](incremental.md).
   Done means the same schema shows `incremental: true` on each cursor column.
4. **Meet the conditions on your source's line.**
   - REST API: an explicit `paginator` on every endpoint, where one set in `resource_defaults.endpoint` counts for each, the `incremental` block and `merge` on the primary key, the API's deleted-records feed or a scheduled full reload with `refresh="drop_resources"` for deletes, and a full run that logs no paginator WARNING, under [`rest-api.md`](rest-api.md).
   - SQL database: a primary key, a cursor column that every write updates and that has an index, a soft-delete flag or a scheduled reload for deletes, and a `SELECT`-only role, under [`sql-database.md`](sql-database.md).
   - Filesystem: the file cursor on `filesystem()`, and for files that change or are re-sent, the approach under [`filesystem.md`](filesystem.md#new-files-changed-files-and-dispositions).

   Done means every condition on the line holds; for SQL, `EXPLAIN SELECT * FROM <table> WHERE <cursor> >= <value>` also shows an index scan for a recent `<value>`, and `compute_table_schema()` shows the key and the cursor's `timezone`.
5. **Read credentials from environment variables,** with the destination name in `config.toml` and every credential, a DuckDB path included, in the deployment's environment, as [`secrets.md`](secrets.md) says.
   Done means the deployment sets every key that `dlt_secrets.py show` lists, a SQL source's URL in `SOURCES__SQL_DATABASE__CREDENTIALS` included, and a run there needs no `secrets.toml`.
6. **Set `RUNTIME__LOG_LEVEL=INFO`, and `RUNTIME__LOG_FORMAT=JSON` for a collector, in the deployment.**
   Done means a run prints `INFO` lines.
7. **Run once in full** through `run_with_retries`.
   Done means it returns without raising, `uv run dlt pipeline <name> info` lists no pending package, `runs` holds the row with an empty `failed_step`, and each SQL table's count equals the source's count of undeleted rows in the cursor range.
8. **Run again with no new source data.**
   Done means no incremental data table appears in `pipeline.last_trace.last_normalize_info.row_counts`, though a `_dlt_pipeline_state` row can, the destination's row counts equal those after step 7, and each incremental REST endpoint's first `Making GET request to` line carries the stored cursor.
