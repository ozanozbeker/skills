---
compatibility: Requires open-source dlt 1.32 or later; DuckDB's upsert, insert-only and cdc merge strategies need duckdb 1.4 or later. dltHub and dlt[hub] features are out of scope.
description: dlt style. Use when writing, testing, reviewing, debugging or tuning a dlt pipeline, loading APIs, databases or files, choosing a write disposition or incremental cursor, wiring `.dlt` secrets, checking or exploring loaded data, or running in production.
license: Apache-2.0
name: dlt-style
---

# dlt style

The conventions for [dlt](https://dlthub.com/docs), the open-source data load tool, from its docs at version 1.32.0, Apache-2.0, read on 2026-11-04.
Every rule was run against dlt 1.32.0 and DuckDB 1.5.6 on 2026-11-04 unless it cites a docs page; where this skill and the docs disagree, follow this skill.
Each rule carries its reason in one sentence; the docs page named under each heading holds the long argument.
Load each source's rows as they arrive, fixing only types and keys, because the modeling happens downstream, in dbt under `dbt-style` when it is installed, or in SQL.

The stack is fixed:

- DuckDB is the development and test destination, and the engine that reads what a pipeline loaded.
- Polars is the dataframe library: a resource yields a *frame* (a Polars DataFrame, or an Arrow table where a library hands one over) when its data is tabular, and dicts otherwise.
  Loaded data comes back as Polars, as [`data.md`](data.md) shows, and pandas appears only where a library requires it.
- marimo holds notebooks, under [`notebooks.md`](notebooks.md).
- uv installs and runs everything: `uv add`, `uv run python <script>.py`, `uv run dlt ...`.
- Pipeline code follows `python-style`, when it is installed; the examples in this skill show dlt's shape, not a finished module.

Every task here runs on open-source dlt alone: the `dlt` CLI, the Python API, DuckDB and [`scripts/dlt_secrets.py`](scripts/dlt_secrets.py).
The dlt docs also describe dltHub features; skip any that needs `dlt[hub]`, the `dlthub` CLI or a dltHub account, such as `dlt ai`, `dlt dashboard` and `dlt pipeline <name> show`.
dltHub's agent toolkits are under the [dltHub AI Source Available License](https://dlthub.com/license), which limits their use to dltHub services, so this skill never loads or copies them.

| Reference | Load when |
| --- | --- |
| [`secrets.md`](secrets.md) | Wiring a new credential, a `ConfigFieldMissingException` or `ValueNotSecretException`, using a secret in ad-hoc code, or setting secrets for production |
| [`rest-api.md`](rest-api.md) | Loading an HTTP API with `rest_api` or `RESTClient`: a paginator, a child endpoint, an incremental cursor, rate limits and HTTP retries, or a 401, 403 or paginator warning |
| [`sql-database.md`](sql-database.md) | Looking at a database before loading it, connecting `sql_database` or `sql_table`, choosing a backend or reflection level, or a missing driver, a timezone warning or decimals that load as doubles |
| [`filesystem.md`](filesystem.md) | Reading CSV, JSONL or Parquet from a folder or a bucket, choosing a reader, or loading only new or changed files |
| [`incremental.md`](incremental.md) | Making a resource incremental or changing its cursor, backfilling a range, splitting a long load, reading or resetting a stored cursor, or a cursor that does not advance |
| [`schema.md`](schema.md) | Choosing `scd2`, `upsert`, `insert-only` or `cdc`, a replace strategy, a schema contract or a Pydantic model, or moving a table to `merge` |
| [`debugging.md`](debugging.md) | A run that raised or hangs |
| [`performance.md`](performance.md) | A run that is slow or uses too much memory |
| [`data.md`](data.md) | Reading loaded data from the DuckDB file or `pipeline.dataset()`, checking a load, fixing a column type after the first load, or rows that look wrong |
| [`notebooks.md`](notebooks.md) | Exploring or charting a pipeline's data in a marimo notebook |
| [`production.md`](production.md) | Shipping a pipeline to production, finishing or discarding a pending package, retrying a failed run, logging for a collector, run monitoring, parallel pipelines, or Dagster |

## Steps

A review runs step 1, then holds the code to the Done means of steps 3 and 4 and reports each departure.

1. **Read the project's pipelines.**
   Open `pyproject.toml`, `.dlt/config.toml`, the pipeline scripts and the destination dataset if it exists, and read `.dlt/secrets.toml` only through `show`, under [Project, config and secrets](#project-config-and-secrets).
   Note each pipeline's name, destination and dataset, and each resource's write disposition, primary key, incremental cursor and schema contract.
   Done means you can name, for each resource you touch, its write disposition, its key, and its cursor or the reason it reloads in full.
2. **Pick the source and load its page.**
   A verified source comes first when `uv run dlt init --list-sources` lists the system, because its endpoints, pagination and cursors are already written; then the core source for the data, in [`rest-api.md`](rest-api.md), [`sql-database.md`](sql-database.md) or [`filesystem.md`](filesystem.md); then a plain `@dlt.resource`.
   A new project starts under [New project](#new-project).
   Done means you checked `uv run dlt init --list-sources` for the system, or said that it could not reach GitHub and named the core source you chose, can say why each rung above your choice fails, and loaded the chosen page.
3. **Choose the write disposition and the cursor per resource,** under [Write dispositions](#write-dispositions) and [`incremental.md`](incremental.md).
   Done means each resource has a disposition, a key when it merges, and a cursor or a stated reason it reloads in full.
4. **Write the source under the rules below and its page,** with every credential wired as [`secrets.md`](secrets.md) says.
   Done means every rule below and on the source's page is applied, or the departure is stated with its reason.
5. **Run it twice on a sample in a test,** as under [Testing](#testing).
   A run that raises goes to [`debugging.md`](debugging.md).
   Done means both runs return without raising, the first run's `row_counts` name every table step 3 declared, a merge table keeps its row count on the second run, and an incremental resource loads only new rows on it.
6. **Run the real pipeline and check what loaded,** under the checks in [`data.md`](data.md).
   Done means each check passes, or its gap has a named reason.

## New project

[Installation](https://dlthub.com/docs/reference/installation) and the [CLI reference](https://dlthub.com/docs/reference/command-line-interface).

1. **Start a uv project and add dlt.**
   Create the project as `python-style` says, when it is installed, then run `uv add "dlt[duckdb,parquet,polars]"`.
   Keep `parquet`, because it installs pyarrow, and without it a frame fails to load with `No module named 'pyarrow'`.
   Done means `uv run dlt --version` prints the version.
2. **Scaffold with `uv run dlt --non-interactive init <source> duckdb` from the project root.**
   `<source>` is a core source (`rest_api`, `sql_database`, `filesystem`), a verified source, or any other name, which gets a starter template.
   Beside a `pyproject.toml` it writes `.dlt/config.toml`, a `.dlt/secrets.toml` of `<configure me>` placeholders for the example's secrets (empty for `rest_api`) and `<source>_pipeline.py`, no `requirements.txt`, and prints a `uv add` line with the source's extras.
   It also writes `<configure me>` for the source's settings in `.dlt/config.toml`, such as `bucket_url` for `filesystem`, which `show` does not list, so replace them in that file.
   Over an existing `.dlt/secrets.toml` it keeps every value and comment and adds placeholders only for the keys the file lacks, though a comment above a table can end up above the inserted one.
   Run that line with `>=1.32.0` as its floor, because `uv add` keeps the extras already listed but takes the line's floor, and `chess` printed `>=0.5.1`.
   Then replace the example code with your source.
   Done means `pyproject.toml` lists every extra the printed line named with dlt at `>=1.32.0`, and the script holds only your source.
3. **Ignore the secrets and the database files.**
   Keep `.dlt/secrets.toml` out of git as step 3 of [Wiring a credential](secrets.md#wiring-a-credential) says, and append `*.duckdb` and `*.wal` to `.gitignore`.
   Done means `git check-ignore .dlt/secrets.toml x.duckdb x.duckdb.wal` prints all three paths.

- A verified source arrives as a package in the project (`chess/` plus `.dlt/.sources`), so its code is yours to read and edit; a core source stays imported from `dlt.sources`.
- `uv run dlt init --list-sources` clones dlt's verified-sources repository into `~/.dlt/repos`, so it needs the network.

## Project, config and secrets

[Configuration and secrets](https://dlthub.com/docs/general-usage/credentials/setup) and [configuration in code](https://dlthub.com/docs/general-usage/credentials/advanced).

- Read and change `.dlt/secrets.toml` only with `uv run <skill-dir>/scripts/dlt_secrets.py` and its `show`, `add`, `move` and `remove` commands, where `<skill-dir>` is this skill's folder, run from the project root, because a file read or an edit puts every credential in the transcript.
- Check an environment variable with `show` too, because `env`, `printenv` and `echo` print its value.
- Ask the user to paste a secret into the file, because the chat transcript keeps whatever is pasted there.
- Put non-secret settings in `.dlt/config.toml`, which is committed, and every credential, a DuckDB file path included, in `.dlt/secrets.toml`, which never is, or in the environment, as production does, because a secret value found in `config.toml` fails with `ValueNotSecretException` naming its key.
  In development, keep the default DuckDB file, `<destination name>.duckdb` in the project root (`<pipeline name>.duckdb` for the plain `"duckdb"` destination), and give another path only through `DESTINATION__<NAME>__CREDENTIALS` or by asking the user to write it into `secrets.toml`, because `add` writes only placeholders.
- Default every credential argument to `dlt.secrets.value` and every setting to `dlt.config.value`, so dlt injects it when the function is called and raises when no provider holds it.
  An argument passed explicitly is never injected and never type-checked, and a `<...>` placeholder left in a file counts as a value.
  A DuckDB path passed in code is invisible to `uv run dlt pipeline` commands and `dlt.attach`, which read it from config: a CLI `drop` then opened an empty `<pipeline_name>.duckdb`, and every later run returned `None` without extracting.
- An environment variable is the TOML path in capitals with `__` between sections: `SOURCES__GITHUB__ACCESS_TOKEN`, `DESTINATION__POSTGRES__CREDENTIALS__PASSWORD`.
  It beats both TOML files, and dlt reads the environment at every lookup but the TOML files once per process, so a test sets config with `monkeypatch.setenv` and a marimo kernel through `os.environ`.
- Write sections as `[sources.<module>]` and `[destination.<name>.credentials]`, where `<module>` is the file name of the module that defines the source: `orders` for `myproj/sources/orders.py`, and the script's own name when the source sits in the script.
  A key under `[sources.<module>]` reaches every source and resource in the module, and one under `[sources.<source>]` reaches that source from any module.
- Read a `ConfigFieldMissingException` before you guess a section, because it lists every key dlt tried, in order.
- Annotate every source and resource argument, because dlt parses a configured string into the annotated type (`int`, `bool`, `list[str]`, `datetime.date`) and raises `ConfigValueCannotBeCoercedException` on a bad value, while an unannotated argument receives the raw string.
- Add `extend-immutable-calls = ["dlt.sources.incremental"]` to ruff's `[lint.flake8-bugbear]` table (`[tool.ruff.lint.flake8-bugbear]` in `pyproject.toml`), because ruff's `B008` flags the `dlt.sources.incremental(...)` default a cursor argument needs, and dlt copies that default on every call, so no call shares it.
- Run every pipeline and every `uv run dlt` command from the project root, because dlt reads `.dlt` from the current directory, not from the script's folder.
  A scheduler starts the run there, or sets both `DLT_PROJECT_DIR` and `DLT_LOCAL_DIR`, because with `DLT_PROJECT_DIR` alone a relative `bucket_url` still resolves against the current directory, and `filesystem()` lists nothing without raising.
- Pass `-y` to every `uv run dlt pipeline` command that changes something, because without a terminal it answers its own prompt with no, changes nothing and exits 0.
- Name a pipeline in snake_case, because `.`, `/`, `:`, `%`, `{` and `}` raise `InvalidPipelineName`, and a shell cannot `export` a pipeline-scoped variable whose name holds `-`.
- Name the destination, `destination="warehouse"`, with `[destination.warehouse] destination_type = "duckdb"` in `config.toml` and its `credentials` in `secrets.toml` or the environment, so development and production swap by config, not by code.
  Without `destination_type`, the name fails with `UnknownDestinationModule`.

## Sources and resources

[Source](https://dlthub.com/docs/general-usage/source), [resource](https://dlthub.com/docs/general-usage/resource) and [Arrow, pandas and Polars](https://dlthub.com/docs/dlt-ecosystem/verified-sources/arrow-pandas).

- Extract inside resources and keep a `@dlt.source` body to building them, because the body runs the moment the function is called, and an error there raises bare at the call, outside `PipelineStepFailed`.
- Yield pages, not rows, because each yield passes through the extract pipe once: 200,000 rows took 1.05 s to extract one by one and 0.18 s in pages of 1,000.
- Yield a frame when the data is already tabular, because it goes straight to Parquet and skips normalization: 300,000 rows normalized in 0.01 s, against 2.65 s as dicts.
  A frame's table gets neither `_dlt_load_id` nor `_dlt_id`, and its list and struct columns load as `json`, not as nested tables.
  A `primary_key` on a frame resource logs `several column hints were different` on every run, because the key's `nullable: false` overrides the frame's nullable field; the warning is harmless, and an Arrow table whose key field is cast `with_nullable(False)` silences it.
- Set `[normalize.parquet_normalizer] add_dlt_load_id = true` in `.dlt/config.toml` on every pipeline that yields frames, because the filter on finished loads under [Schema](#schema) needs `_dlt_load_id`.
  Leave `add_dlt_id` off for a table born from frames, because it rewrites each file, and frames make no nested tables to join on it.
  Turn it on, or reload the resource once with `refresh="drop_resources"`, when a table first loaded from dicts switches to frames, because that table's `_dlt_id` is `NOT NULL`, and frames without it fail the load with `NOT NULL constraint failed`.
- Yield real `date`, `datetime` and `Decimal` values, or hint the column type, because a date string loads as `text` and a float as `double`.
  dlt turns an ISO 8601 timestamp string in a dict into a UTC `timestamp`, even without an offset, and leaves the same string in a frame as text.
- A transformer (`@dlt.transformer(data_from=parent)`, or `parent | child`) receives each item the parent yields, so it gets a whole page when the parent yields pages.
- Build resources in a loop with `dlt.resource(func, name=...)(arg)`, passing the function and not a called generator.
  A called generator keeps no incremental state, so every run reloads every row; a resource decorated inside the loop reads the loop variable after the loop ends, so every table gets the last endpoint's rows.
- Set `max_table_nesting` on the resource when you select resources by key, because a source-level value reaches a resource only through the source or `with_resources`, not through `source.resources["x"]` or `source.x`.
  `0` keeps nested data as JSON, and 2 or 3 gives the most readable tables for deep documents.
- Extract resources side by side with async generators or `parallelized=True`, and read [`performance.md`](performance.md) first, because the flag is silently ignored on a resource whose function has an argument with a default.
- Use `add_limit` for samples, tests and the time-boxed rounds of a long load in [`incremental.md`](incremental.md); it counts yields, so `add_limit(10)` on 15-row pages loads 150 rows.
- Make every partial run (an `add_limit` sample, or a transformer or child endpoint selected alone) a *throwaway* run, under `dev_mode=True` or in a test's `tmp_path`, because a partial run on the real pipeline saves the cursor it reached, and the next real run skips the rows it left out.
  A transformer or child selected alone still runs its parent, which loads no table but saves its cursor, and an `add_limit` on a source read newest first or unsorted saves a cursor past rows it never loaded.
  An `add_limit` on a source read with `row_order="asc"` is the exception: the next run continues from the stored cursor and loses nothing, which the rounds in [`incremental.md`](incremental.md) rely on.

## Write dispositions

[Incremental loading](https://dlthub.com/docs/general-usage/incremental-loading), [merge](https://dlthub.com/docs/general-usage/merge-loading) and [full loading](https://dlthub.com/docs/general-usage/full-loading).

| Data | Disposition |
| --- | --- |
| Stateless events that never change | `append` |
| Rows that change, read incrementally | `merge`, default strategy `delete-insert` |
| Rows that change, where the history matters | `merge` with `"strategy": "scd2"`, under [`schema.md`](schema.md) |
| A full snapshot whose deleted rows must disappear | `merge` with `"strategy": "cdc"`, under [`schema.md`](schema.md) |
| A small table read in full every run | `replace` |

- Set the disposition on each resource and keep it off `pipeline.run`, because a run-level `write_disposition` overrides every resource's own and reaches parent resources too: a `merge` and a `replace` table both appended, and a run-level `replace` reset a filesystem cursor.
- `merge` needs a `primary_key` or a `merge_key`, because without one it appends.
  `delete-insert` keeps one row per key from the batch and deletes the stale nested rows with their root row; which duplicate survives is arbitrary unless a column carries `dedup_sort` (`"desc"` keeps the highest).
- Write a full reload as the bare string `"replace"` on a resource with no cursor, because the bare string resets the resource's stored cursor on every run.
  The dict form `{"disposition": "replace"}` keeps the stored cursor, so beside a cursor the table holds only the rows newer than the last run, and a run with none leaves it empty.
- To reload a resource from scratch once, pass `refresh="drop_resources"` or `refresh="drop_data"` to `pipeline.run` and leave the disposition alone.
  Pass it to `run`, because on `dlt.pipeline()` it applies to every run, and keep `drop_sources` for whole sources, because it drops every table of the source, the unselected ones too.

## Schema

[Schema](https://dlthub.com/docs/general-usage/schema) and [destination tables](https://dlthub.com/docs/general-usage/destination-tables).

- Let the data drive the schema, and hint only what the data cannot say: keys, money, the types a source sends as strings, and `json` for a field that must not unnest.
  Load money as `decimal` with `precision` and `scale`, because the float `0.1 + 0.2` loads as the `DOUBLE` `0.30000000000000004`.
  A hint coerces the value: with `{"data_type": "decimal", "precision": 18, "scale": 2}`, the string `"12.30"` and the float `0.1 + 0.2` load as `12.30` and `0.30`, and `"2024-01-31"` hinted `date` loads as a `DATE`.
  Build one hint dict per column, such as `{name: {"data_type": "decimal", "precision": 18, "scale": 2} for name in ("subtotal", "total")}`, because dlt writes each column's `name` into its dict, so one dict shared by several columns types only the last and logs `collides with other column`.
  Hint before the first load, because a later hint leaves the table's type alone until the resource reloads, as [Fixing a column type](data.md#fixing-a-column-type) shows.
- Nested lists load to `<parent>__<child>` tables, joined on `_dlt_parent_id` to the parent's `_dlt_id`, and only root tables carry `_dlt_load_id`.
- Read only finished loads downstream, because a failed load leaves its rows in root tables with a `_dlt_load_id` absent from `_dlt_loads`.
  Filter on `_dlt_load_id in (select load_id from _dlt_loads where status = 0)`.

## Destinations

[Destinations](https://dlthub.com/docs/general-usage/destination) and [DuckDB](https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb).

- Name the DuckDB dataset differently from the database file, because a match fails the load with `Binder Error: Ambiguous reference to catalog or schema`.
- Close every other connection to the DuckDB file before a run, because one held by another process, even read-only, fails the run at `step=sync` with a `DestinationConnectionError` that blames the credentials, though the message names the real cause, `Could not set lock on file`.
  A reader that opens the file mid-run fails the run at `step=load` instead, with the package left pending.
- Use `dev_mode=True` only for a throwaway run, because each new pipeline object gets empty state and a dataset suffixed `_YYYYMMDDhhmmss`, and the old datasets stay in the file.
  The `hh` runs on a 12-hour clock, so two objects made in the same second, or 12 hours apart, share one dataset.

## Testing

- Give each test its own DuckDB file under `tmp_path`, or a `duckdb.connect(":memory:")` connection, passed as `dlt.destinations.duckdb(...)`, and `pipelines_dir` under `tmp_path`, so the test leaves no state behind and no `.dlt` file or environment variable can redirect it.
- Assert on `last_trace.last_normalize_info.row_counts` and on the rows the dataset returns; a failed job raises `PipelineStepFailed` from `run`.
- An HTTP source's tests mock the API as [Testing](rest-api.md#testing) in `rest-api.md` shows.
- Import a pipeline script as a module, with `pythonpath = .` in `pytest.ini` for a script in the project root, because dlt's decorators look up the function's module in `sys.modules`, and a script loaded by file path fails with `AttributeError` in dlt's `spec.py`.
- Under `filterwarnings = error` in `pytest.ini`, add the line `ignore::DeprecationWarning:dlt\.`, because dlt's own code raises deprecations a test cannot fix: `.arrow()` on a dataset relation warns `fetch_arrow_table() is deprecated`, and `sql_database()` warns about `detect_precision_hints` even when you leave it out.
  The pattern matches only modules inside dlt, so a deprecation from the project's code, or from a deprecated dlt call the project makes, still fails the test.

```python
from collections.abc import Iterator
from pathlib import Path

import dlt
import polars as pl

ROWS = [{"id": 1, "cents": 999}, {"id": 2, "cents": 500}]


@dlt.resource(primary_key="id", write_disposition="merge")
def orders() -> Iterator[list[dict[str, int]]]:
    yield ROWS


def test_merge_is_idempotent(tmp_path: Path) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="test_orders",
        destination=dlt.destinations.duckdb(str(tmp_path / "test.duckdb")),
        dataset_name="raw",
        pipelines_dir=str(tmp_path / "pipelines"),
    )
    for _ in range(2):
        pipeline.run(orders())
    trace = pipeline.last_trace
    assert trace is not None
    assert trace.last_normalize_info is not None
    assert trace.last_normalize_info.row_counts["orders"] == len(ROWS)
    assert pl.DataFrame(pipeline.dataset()["orders"].arrow()).height == len(ROWS)
```
