# Debugging a failed or suspicious run

The loop for a run that raised or seems stuck: what each failure prints, the commands that inspect it, and the settings that make dlt say more.
Recovering in production (retrying, aborting, monitoring) is in [`production.md`](production.md).
Source: [running in production](https://dlthub.com/docs/running-in-production/running), the [CLI reference](https://dlthub.com/docs/reference/command-line-interface), [performance](https://dlthub.com/docs/reference/performance), the [REST client](https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced) and [viewing the schema](https://dlthub.com/docs/general-usage/dataset-access/view-dlt-schema).

## The loop

1. **Find the original exception.**
   Read up from the bottom block, `PipelineStepFailed`, which names the step and the exception it wraps, past dlt's wrapper to the block it was raised from: your file and line for a resource, the driver's message for a load job.
   Done means you can name the step (`sync`, `extract`, `normalize` or `load`), the original exception, and the resource or job that raised it.
2. **See what the run left behind** with `uv run dlt pipeline <name> info`.
   Done means you know whether a package is pending, and its load id.
3. **Inspect the trace and the package** with the commands under [Inspect](#inspect).
   Done means you hold the failing job's error text or the failing resource, and the rows the package already wrote.
4. **Rerun with more output,** setting the variables under [Make dlt say more](#make-dlt-say-more) on that one command.
   Done means the output names the failing request, resource, job or row.
5. **Fix the cause, then finish or discard the pending package** as [`production.md`](production.md) describes.
   Done means `info` lists no pending package and a rerun completes.
6. **Restore every debug setting.**
   Done means the code keeps no `progress=` or `add_limit` you added, and `git diff .dlt/` shows only the fix.

## What each failure prints

| Failure | Raised as | What to read |
| --- | --- | --- |
| Missing secret in a `@dlt.source` argument | `ConfigFieldMissingException` when the source function is called, before `run`, so no trace is saved | The keys dlt tried in order, `<PIPELINE_NAME>__SOURCES__...` first when `dlt.pipeline()` ran before the call, and the TOML paths it probed, which show the folder it read `.dlt` from |
| Missing secret in a `@dlt.resource` argument | `PipelineStepFailed` at `step=extract` | The same lookup list |
| Missing destination setting | `PipelineStepFailed` at `step=sync` | The same lookup list |
| Exception in a resource | `PipelineStepFailed` at `step=extract`, wrapping `ResourceExtractionError` | Only `str()` of your exception, so a `KeyError` reads `caused an exception: 'items'`; its type is `ex.exception.__cause__`; nothing stays pending |
| Schema contract violation | `PipelineStepFailed` at `step=normalize`, wrapping `NormalizeJobFailed` | The extracted package stays pending, so fixed code fails again on the same load id until you abort it |
| A job the destination rejects | `PipelineStepFailed` at `step=load`, wrapping `LoadClientJobTerminalRetry` | The driver's error, such as DuckDB's `Conversion Error ... out of range`, logged at `ERROR` even at the default level; the package stays pending |
| DuckDB file open in another process | `PipelineStepFailed` at `step=sync`, wrapping `DestinationConnectionError`; at `step=load`, with the package left pending, when the reader opened the file mid-run | `Could not set lock on file ... Conflicting lock is held in ... (PID n)`, also when the holder is read-only |

- `PipelineStepFailed` carries `step`, `load_id`, `exception`, `has_pending_data` and `is_package_partially_loaded`; the last is true when completed jobs already wrote rows.
- A failed extract keeps nothing, not even the resources that finished, so rerun after the fix.

## Inspect

- `uv run dlt pipeline <name> trace` shows each step's status, the rows normalize counted per table, and the error.
  After a load failure, `abort-packages` and `load-package <load_id> abort` replace the trace with their own load step, so read it before you abort.
- `uv run dlt pipeline <name> info` lists pending packages: "extracted packages ready to be normalized" after a normalize failure, "normalized packages ready to be loaded" after a load failure, with a warning when one is partially loaded.
- `uv run dlt pipeline <name> load-package <load_id>` lists the package's jobs by folder, and the newest package when you omit the id.
  A job that failed terminally waits in `new_jobs` and shows no error there; `load-package <load_id> job <pattern>` prints its exception for every attempt.
- `failed-jobs` reads only `failed_jobs`, so after a default load failure it prints "No failed jobs found" while the job waits in `new_jobs`.
- `load-package <load_id> row-counts` counts each table's rows with that load id and says whether `_dlt_loads` records the load.
  It skips tables without `_dlt_load_id`, which is every table of frames unless `[normalize.parquet_normalizer] add_dlt_load_id = true`.
- `trace metrics` shows files, rows and bytes per step, table and resource.

## Package files

- The pipeline's working directory is `$DLT_DATA_DIR/pipelines/<name>`, `~/.dlt/pipelines/<name>` by default; `pipeline.working_dir` prints it, and `load-package` prints the package's folder.
- A package moves from `normalize/extracted/<load_id>` to `load/normalized/<load_id>` to `load/loaded/<load_id>`, where loaded packages and packages aborted at load stay; abort deletes an extracted package.
- Inside a package, jobs sit in `new_jobs` (a retry count in the file name), `started_jobs`, `completed_jobs` or `failed_jobs`.
  `.exceptions/<job>.exception` starts with `retry: terminal` or `retry: transient`, and `.restore/state.json` is the state an abort restores.
- On DuckDB, rows from dicts become `insert_values.gz` jobs, frames become `parquet` jobs, and a `merge` adds a `.sql` job that moves the staging rows into the table, where a type mismatch surfaces.

```bash
# the rows a job carried, from the package folder that load-package prints
gzip -dc "$PACKAGE"/completed_jobs/payments.*.insert_values.gz | head
duckdb -c "from '$PACKAGE/new_jobs/*.parquet' limit 20"
cat "$PACKAGE"/new_jobs/payments.*.sql
```

## Make dlt say more

Set these on the one command, so nothing outlives the session: `RUNTIME__LOG_LEVEL=INFO PROGRESS=log uv run python pipelines/shop.py`.

| Variable | What it shows |
| --- | --- |
| `RUNTIME__LOG_LEVEL=INFO` | The normalize and load steps, each package and job, and each REST request URL, on stderr; the default `WARNING` prints nothing for a clean run |
| `PROGRESS=log` | Counters on stdout per step: resources done, items per resource, files, jobs, and memory when `psutil` is installed; the same as `progress="log"` on `dlt.pipeline` (`run` takes no `progress`), without a code change |
| `RUNTIME__HTTP_SHOW_ERROR_BODY=true` | The response body under the `HTTPError` of the REST API source and `RESTClient`, cut at `http_max_error_body_length` (8192), on an endpoint without `response_actions`; with any entry, the error shows no body and an unmasked URL |
| `RUNTIME__REQUEST_MAX_ATTEMPTS=1` and `RUNTIME__REQUEST_TIMEOUT=10` | An HTTP failure at once, instead of after the retries |
| `EXTRACT__NEXT_ITEM_MODE=fifo` | Resources extracted one at a time, in source order |

- In a hand-written resource over `dlt.sources.helpers.requests`, log `err.response.text` from the `requests.HTTPError` you catch, because `http_show_error_body` does not reach that client.

## A run that seems stuck

- dlt's HTTP clients log no retry, so an endpoint that keeps failing logs its URL once at `INFO` while it waits out the retry schedule in [`rest-api.md`](rest-api.md#rate-limits-and-retries).
- The progress counters print only when an item arrives, at most once a second, so counters that stop mean a resource is blocked inside a call.
- Under the default `round_robin`, one blocked resource stops all of them and every counter shows a partial count.
  Under `fifo`, the first counters after the stall show the finished resources at full counts and the blocked one last listed.
