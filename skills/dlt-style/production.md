# Running in production

Source: [running](https://dlthub.com/docs/running-in-production/running), [performance](https://dlthub.com/docs/reference/performance) and [deploying with Dagster](https://dlthub.com/docs/walkthroughs/deploy-a-pipeline/deploy-with-dagster).

## Runs and retries

- `pipeline.run` first finishes any package a failed run left pending, and returns without extracting new data when it does.
  Run the pipeline again after a recovery, so the new data loads.
- dlt retries no step on its own.
  Wrap the run in `tenacity` with `retry_load(("extract", "load"))` from `dlt.pipeline.helpers`, and never retry a `TerminalException`.
- Since 1.30, a job that fails for good keeps its package pending and raises.
  Recover with `dlt.attach(name).load()` after the fix, or abort with `dlt pipeline <name> abort-packages`, which rewinds the state.
- Never delete rows from a `merge` or `replace` table by hand to undo a load; abort the package and rerun.
- Set `[runtime] log_level = "INFO"` in production, not DEBUG, and `log_format = "JSON"` when the logs go to a collector.

## Monitoring

- Load the run's record into the destination after each run: `pipeline.run([load_info], table_name="_load_info")`, and the same for `pipeline.last_trace`; dlt strips secrets from both.
- Alert on schema changes by reading `package.schema_update` for each package in `load_info.load_packages`, and sending only when one is non-empty.
- `last_trace.last_normalize_info.row_counts` gives rows per table, for a volume check.

## Performance

- Files do not rotate by default, which stops normalize and load from running in parallel; set `[data_writer] file_max_bytes` or `file_max_items`.
- `[normalize] workers` starts a process pool, off by default; leave cores free, and set `start_method = "spawn"` when your code starts threads.
- `[load] workers` defaults to 20.
- `buffer_max_items` (default 5000) sets how many items sit in memory before a write.
- `dlt pipeline <name> trace metrics` shows files and sizes per step.

## Parallel pipelines

- Never run one pipeline name in one working directory twice at once, because both runs write the same state and packages.
- Give each pipeline that loads one dataset at the same time its own `staging_dataset_name_layout`, because a shared staging dataset loses or duplicates rows.

## Dagster

- Wrap the pipeline with `@dlt_assets(dlt_source=..., dlt_pipeline=..., group_name=...)` from the `dagster-dlt` package, and yield from `dlt.run(context=context)` on a `DagsterDltResource`.
- `@dlt_assets` takes a `@dlt.source`, not a bare resource.
- Configure secrets through environment variables in the Dagster deployment instead of a `.dlt` folder.
- Use an executor that runs each op in its own process, because dlt intercepts SIGTERM only in the main thread.
