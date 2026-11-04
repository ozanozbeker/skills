# Incremental models, snapshots and near-real-time data

The strategies behind the rules in `SKILL.md`'s "Incremental models and idempotence" section.
Sources: [incremental models in depth](https://docs.getdbt.com/best-practices/materializations/4-incremental-models), [change data capture](https://docs.getdbt.com/best-practices/how-we-handle-cdc/1-intro), [choosing incremental or snapshots](https://docs.getdbt.com/best-practices/how-we-handle-cdc/2-choosing-incremental-or-snapshots), and the six [near-real-time pages](https://docs.getdbt.com/best-practices/how-we-handle-real-time-data/1-intro).

## Choosing a strategy

| Strategy | Use for |
| --- | --- |
| `merge` with `unique_key` | Most tables: an append-mostly source filtered by `is_incremental()` |
| Warehouse CDC (a stream as the source) | A table whose rows update often |
| `microbatch` | Billions of rows of time series with years of history |

- Start with `merge`; move to a stream when updates dominate; move to microbatch when backfills get slow or late data is common.
- Set `cluster_by=['event_date']` (the key varies by warehouse) on a merge target, because clustering by date prunes partitions during the `merge`; watch the `merge` time as the table grows.
- A minute-cadence job uses a lookback of the form `event_ts > max(event_ts) - interval '1 hour'`; a daily job subtracts days.
- Set `full_refresh = false` on a multi-year table, so an accidental `--full-refresh` cannot rebuild it.

### Streams as the source

- Create the stream once, outside dbt: `create or replace stream raw.events_stream on table raw.events;`.
- Point `{{ source() }}` at the stream and drop the `is_incremental()` time filter, because the stream already returns only changed rows.
- Filter `metadata$action in ('INSERT', 'UPDATE')`, and handle `'DELETE'` there when deletes must propagate.
- A stream replaces the snapshot: the warehouse has already detected the change.

### Microbatch

- Config: `incremental_strategy='microbatch'`, `event_time`, `batch_size` (`'hour'`, `'day'`), `lookback` (`1` reprocesses one prior batch) and `unique_key`.
  dbt writes the `where event_ts between ...` predicate per batch, so the model has no `is_incremental()` block.
- Set `event_time` on every upstream model too, because without it each batch scans the full upstream table instead of pushing the time filter up.
- Each run is many small batch queries, so a failed backfill retries one batch.
- Needs dbt 1.9 or later; Microsoft Fabric lacks it.

## Snapshots

- Choose by what the table must answer.
  Current value per key only: incremental with `merge`.
  History of a source that overwrites rows: a snapshot.
  Both: an incremental staging model, a snapshot of it, then a model selecting the current rows.
- Snapshot the source or a lightly cleaned staging model, so a change in business logic stays out of the history.
- Use the `timestamp` strategy when `updated_at` is reliable and only moves forward, because dbt then detects a change from the clock instead of comparing every column.
  Use `check` when the timestamp is missing or untrustworthy.
- Run snapshots on a schedule between hourly and daily, because a snapshot records only the state present when it runs and misses a change overwritten between runs.
- Set `hard_deletes` when the loader marks deleted rows; an incremental model handles deletes in its own `merge`.
- Test a snapshot for a unique `(unique_key, dbt_valid_from)`, non-overlapping validity ranges, and at most one current row per key (`dbt_valid_to` is null).
- When the source already carries from and to dates, load the changes with `append` or `merge` and keep the latest row with a SQL filter; no snapshot is needed.

## Near-real-time data

dbt serves freshness of 5 to 15 minutes.
Sub-second freshness needs a streaming database in front of dbt, with dbt still owning the analytic tables and history.

- Two layers: the warehouse's streaming ingestion (Snowpipe, Databricks streaming tables, BigQuery Storage Write API) lands raw data, and dbt transforms on a schedule of 1 to 15 minutes.
  Keep the two tuned separately.
- Data is never fresher than ingestion; tune the landing cadence, the lookbacks and which sources join the real-time path.
- Treat minute-level freshness as a premium service: each step up in cadence raises compute and operational cost, so confirm the business needs it first.
- Add freshness monitoring (`loaded_at_field` on the source) and data tests, because no batch boundary catches bad data before users see it.

### Warehouse-native refresh

- Use a dynamic table or materialized view when the requirement is "always within X minutes" and the transformation is simple, because the warehouse then owns the refresh.
  Stay with incremental models when you need exact scheduling, a custom strategy such as microbatch, or ordered refreshes across several models.
- Snowflake dynamic table config: `materialized = 'dynamic_table'`, `target_lag` (`'1 minute'`, `'5 minutes'`, or `'downstream'` to refresh only when a dependent needs it) and `snowflake_warehouse`.
- `materialized = 'materialized_view'` behaves differently per adapter (BigQuery, Databricks, Postgres, Redshift, Snowflake); read the adapter's page before relying on incremental refresh.
- The trade: less timing control, harder cost prediction and less visibility into refresh decisions than explicit incremental SQL.

### Views only

- Materialize the whole path as views when the source already lands every few seconds and the logic is light (renames, casts, one or two joins to small reference tables), because the views inherit the source's latency.
- Move to incremental models or warehouse-native tables when the logic grows, several teams depend on the output, or cost matters, because every query re-runs the full view stack.
- Replicate an operational store into a warehouse table first, so analytics queries never load the OLTP system.
- Lean on tests and model contracts here, because a source schema change propagates through views instantly.
- There is no frozen step, so yesterday's logic cannot be re-run or debugged from a persisted table.

### Lambda views

dbt Labs calls this a legacy pattern; use it only when dynamic tables and materialized views are unavailable, all logic must stay in dbt SQL, or an existing lambda implementation is being extended.

- Three models: the incremental base table (run every 5 to 15 minutes), a view selecting source rows with `event_ts > (select max(event_ts) from {{ ref('base') }})`, and a view that `union all`s both.
  BI reads only the union.
- Every query against the union re-reads the real-time slice from the raw table, so reserve it for a dashboard that justifies the cost.
- The real-time view can show a temporary hole while the incremental load runs; a `-- depends_on: {{ ref('base') }}` comment on the view orders the build at the cost of coupling.

### Operating a frequent job

- Keep the job's runtime under its interval; a 5-minute schedule with a 7-minute run queues and cancels, and the fix is a narrower selector, more threads, faster SQL or a slower schedule.
- Distinct runs of one job execute serially, and frequent jobs can starve other jobs of run slots.
- Warehouse utilisation scales with cadence: a 30-minute job is about 2% daily, about 50% hourly, and about 100% at 5 minutes.
- A job deactivates after 100 consecutive failures, so a flaky model on a minute cadence reaches that in two hours.
- Keep `run_query()` results small and skip doc generation in a frequent job, because both hit memory limits.
