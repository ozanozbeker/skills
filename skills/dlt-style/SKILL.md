---
compatibility: Requires open-source dlt 1.30 or later; dltHub and dlt[hub] features are out of scope.
description: dlt style, from the open-source dlt docs. Project config and secrets, sources and resources, write dispositions, incremental loading, schema contracts, REST API, SQL database and filesystem sources, destinations, testing and production runs. Use when writing, reviewing or debugging a dlt pipeline, choosing a write disposition or an incremental cursor, setting a schema contract, configuring `.dlt/config.toml` or `.dlt/secrets.toml`, or running dlt under Dagster.
license: Apache-2.0
name: dlt-style
---

# dlt style

The conventions for [dlt](https://dlthub.com/docs), the open-source data load tool, from its docs at version 1.32.0, Apache-2.0, read on 2026-11-04.
Each rule carries its reason in one sentence; the docs page named under each heading holds the long argument.
dlt loads raw data into a dataset, and the modeling happens downstream, in dbt or in SQL.
The pipeline code is Python, so it also follows `python-style` ([ozanozbeker/skills](https://github.com/ozanozbeker/skills/tree/main/skills/python-style)) when that skill is installed.

This skill covers open-source dlt only.
Anything that needs a dltHub account, a dltHub license or the `dlt[hub]` extra is out of scope: `@dlt.hub.transformation`, `@dlt.hub.run`, dltHub data quality checks, the dltHub Platform, workspace profiles, `uvx dlthub-init` and the `dlthub` CLI.
dltHub's own agent toolkits are licensed for use with dltHub services only, so this skill never loads or copies them.

| Reference | Load when |
| --- | --- |
| [`incremental.md`](incremental.md) | Adding an incremental cursor, backfilling, splitting a long load, or debugging a cursor that does not advance |
| [`sources.md`](sources.md) | Writing a REST API, SQL database or filesystem source |
| [`production.md`](production.md) | Retrying, recovering a failed load, monitoring, tuning performance, running pipelines in parallel, or running dlt under Dagster |

## Steps

1. **Read the project's pipelines.**
   Open `.dlt/config.toml`, the pipeline scripts, and the destination dataset if it exists.
   Note each pipeline's name, destination and dataset, each resource's write disposition, primary key and incremental cursor, and any schema contract.
   Done means you can name, for each resource you touch, how it writes and how it finds new data.
2. **Choose the write disposition and the cursor per resource,** under [Write dispositions](#write-dispositions) and [`incremental.md`](incremental.md).
   Done means each resource has a disposition, a key when it merges, and a cursor or a stated reason it reloads in full.
3. **Write the source under the rules below.**
4. **Run it against DuckDB with a small sample.**
   Use `add_limit` on the source and `dev_mode=True` on the pipeline, so the run is fast and the dataset is thrown away.
   Run it twice: the second run of a merge resource must leave the row counts unchanged, and the second run of an incremental resource must load only new rows.
   Done means both runs finish, `load_info.has_failed_jobs` is false, and the tables and columns match what step 2 declared.

## Project, config and secrets

[Configuration and secrets](https://dlthub.com/docs/general-usage/credentials/setup).

- Non-secret settings go in `.dlt/config.toml`, which is committed; credentials go in `.dlt/secrets.toml`, which never is, and production reads them from environment variables.
  dlt reads no secret from `config.toml`, so a credential there fails to resolve.
- An environment variable is the TOML path in capitals with `__` between sections: `SOURCES__GITHUB__ACCESS_TOKEN`, `DESTINATION__POSTGRES__CREDENTIALS__PASSWORD`.
  Environment variables win over the TOML files, so production overrides a file without editing it.
- Write sections as `[sources.<module>]` and `[destination.<name>.credentials]`.
  dlt drops the rightmost section on each miss, so a key under `[sources.<module>]` reaches every resource in the module.
- Pass no credential in code: give a source argument the default `dlt.secrets.value` or `dlt.config.value`, so dlt injects it and raises when it is missing.
- Annotate every source and resource argument, because dlt parses the value into the annotated type and builds the sample config from it.
- dlt reads `.dlt` from the working directory, not from the script's folder, so run every pipeline from the project root.
- A pipeline name uses letters, digits, `-` and `_` only, because every config provider accepts those.
- Declare the destination on `dlt.pipeline`, and name it (`[destination.warehouse] destination_type = "duckdb"`) so development and production swap by config, not by code.

## Sources and resources

[Source](https://dlthub.com/docs/general-usage/source) and [resource](https://dlthub.com/docs/general-usage/resource).

- A `@dlt.source` function groups resources; a `@dlt.resource` generator yields the data.
  Extract nothing in the source function's body, because it runs the moment it is called, outside dlt's error handling, metrics and parallelism.
- Yield pages, not rows: each yield passes through the extract pipe once, so a list of rows per yield is far faster.
- A resource may yield dicts, Pydantic models, Arrow tables, pandas frames or Polars frames.
  Arrow and Polars input skips most of normalization and goes straight to Parquet on a destination that takes it.
- Yield real `datetime`, `date` and `Decimal` values, or hint the column type, because a date sent as a string loads as `text` (measured 2026-11-04).
- A transformer (`@dlt.transformer(data_from=parent)`, or `parent | child`) fetches details per parent item; running the child also runs its parent.
- Build resources in a loop with `dlt.resource(func, name=...)(arg)`, passing the function and not a called generator, so each keeps its own incremental state.
- Set `max_table_nesting` on the source or resource when unnesting goes deep: `0` keeps nested data as JSON, and 2 or 3 gives the most readable tables for deep documents.
  Set it on the resource when you select resources by key, because a source-level value does not reach `source.resources["x"]`.
- Mark async generators, or set `parallelized=True` on a sync generator, to extract several resources at once.
- Use `add_limit` for samples and tests only; it counts yields, not rows.

## Write dispositions

[Incremental loading](https://dlthub.com/docs/general-usage/incremental-loading), [merge](https://dlthub.com/docs/general-usage/merge-loading) and [full loading](https://dlthub.com/docs/general-usage/full-loading).

| Data | Disposition |
| --- | --- |
| Stateless events that never change | `append` |
| Rows that change, read incrementally | `merge`, default strategy `delete-insert` |
| Rows that change, where the history matters | `merge` with `"strategy": "scd2"` |
| A small table read in full every run | `replace` |

- `merge` needs a `primary_key` or a `merge_key`; without one it appends.
  It dedupes the load on the key, and deletes the stale nested rows with the root row (measured 2026-11-04).
- `scd2` writes `_dlt_valid_from` and `_dlt_valid_to`, null on the current row, and expects a full extract.
  For an incremental extract, set the natural key as `merge_key`, so a row absent from the batch is not retired.
  It does not see a change in nested data unless the root row changes.
- `upsert` runs on a few destinations only, not DuckDB; use `delete-insert` unless the destination's MERGE is the point.
- Write `replace` as `{"disposition": "replace"}`, because the bare string also resets the resource's incremental state.
  The default `truncate-and-insert` leaves the table empty mid-load; set `[destination] replace_strategy = "insert-from-staging"` when readers query during loads.
- To reload a resource from scratch once, run with `refresh="drop_resources"` or `refresh="drop_data"`, and leave the disposition alone.
- Set `@dlt.source(root_key=True)` on a source that may move to `merge` later, because dlt cannot add the NOT NULL `_dlt_root_id` column to tables that already hold rows.

## Schema

[Schema](https://dlthub.com/docs/general-usage/schema), [contracts](https://dlthub.com/docs/general-usage/schema-contracts) and [destination tables](https://dlthub.com/docs/general-usage/destination-tables).

- Let the data drive the schema, and hint only what the data cannot say: keys, types the source sends as strings, `precision` and `scale` for money, and `json` for a field that must not unnest.
  Money is never a float.
- A schema contract sets `evolve`, `freeze`, `discard_row` or `discard_value` for `tables`, `columns` and `data_type`.
  Freeze columns and data types on a resource whose downstream models break on drift; `freeze` fails the run at normalize (measured 2026-11-04).
  A new table accepts its columns on its first run whatever the contract says.
- A Pydantic model as `columns` validates each row and sets the contract to `discard_value` for new columns and `freeze` for types.
- Nested lists load to `<parent>__<child>` tables, joined on `_dlt_parent_id` to the parent's `_dlt_id`.
- A root row whose `_dlt_load_id` is not in `_dlt_loads` with `status = 0` came from an unfinished load; downstream models read only finished loads.
- The default naming convention is `snake_case`; keep it, because changing it on existing tables fails normalize.
- Read cursor and key names as the source spells them, not as normalized, because dlt matches them before normalization.

## Destinations

[Destinations](https://dlthub.com/docs/general-usage/destination), [DuckDB](https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb) and [filesystem](https://dlthub.com/docs/dlt-ecosystem/destinations/filesystem).

- Build and test against DuckDB, then switch the named destination for production.
- Name the DuckDB dataset differently from the database file, because a match raises a Binder Error.
- Read loaded data back with `pipeline.dataset()`, which returns pandas or Arrow and needs no SQL client.
- `dev_mode=True` resets state and gives the dataset a timestamp suffix on every run, so it belongs in tests, never in production.
- The filesystem destination merges only with the `delta` or `iceberg` table format, and appends otherwise.
- The staging dataset `<dataset>_staging` is kept after a load; set `[load] truncate_staging_dataset = true` unless another pipeline shares it.

## Testing

The docs have no testing guide, so these rules are this skill's own.

- Test against a DuckDB file under `tmp_path` or `duckdb.connect(":memory:")`, with `pipelines_dir` under `tmp_path`, so a test leaves no state behind.
- Assert on `load_info.has_failed_jobs`, on `pipeline.last_trace.last_normalize_info.row_counts`, and on the rows `pipeline.dataset()` returns.
- Test idempotence: run the pipeline twice on the same input and assert the counts of a merge table do not change.
- Mock the HTTP layer of a REST source at the `requests` level, so the test exercises dlt's pagination and incremental code.
