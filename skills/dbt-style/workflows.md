# Workflows, CI and deployment

Sources: [best practices for workflows](https://docs.getdbt.com/best-practices/best-practice-workflows), [clone incremental models in CI](https://docs.getdbt.com/best-practices/clone-incremental-models), [optimize static analysis](https://docs.getdbt.com/best-practices/optimize-static-analysis-for-development-and-deployment), [examining builds](https://docs.getdbt.com/best-practices/materializations/6-examining-builds), [Unity Catalog](https://docs.getdbt.com/best-practices/dbt-unity-catalog-best-practices) and the [style conclusion](https://docs.getdbt.com/best-practices/how-we-style/6-how-we-style-conclusion).
When `running-dbt-commands` ([dbt-labs/dbt-agent-skills](https://github.com/dbt-labs/dbt-agent-skills)) is installed, it owns the command syntax; this file holds the patterns.

## Development

- Run from the command line against a `dev` target; only a deployment job targets `prod`, so a local run never writes production objects.
- Limit data in development with a target gate, so dev runs iterate fast:

  ```sql
  {% if target.name == 'dev' %}
      where created_at >= dateadd('day', -3, current_date)
  {% endif %}
  ```

  On the dbt platform, `env_var('DBT_CLOUD_INVOCATION_CONTEXT')` gives `prod`, `dev`, `staging` or `ci` instead.
- Before a command touches the warehouse, check five things: the selector's scope and downstream depth match the intent, the target is a development schema, `--defer` and `--state` point at the expected environment, a production comparison is read-only, and the cost and run time fit the task.
- Validate at a depth that matches the risk: a rename gets a compile and a `dbt show`; a change to grain, financial logic or a contracted model gets a run, tests and a production comparison.
  The summary lists what was validated, each outcome, the dev-to-prod differences, the downstream resources not run, and every assumption that needs a subject-matter expert.

## Enforcing the style guide

- Add [`dbt-checkpoint`](https://github.com/dbt-checkpoint/dbt-checkpoint) hooks once the style guide is written and the codebase conforms, so every commit follows it.
- Install [`dbt_project_evaluator`](https://github.com/dbt-labs/dbt-project-evaluator) to flag deviations from the structure guide across modeling, testing, documentation, performance and governance.

## Slim CI

- Build and test what changed, deferring the rest to production:

  ```sh
  dbt build --select state:modified+ --defer --state path/to/prod/artifacts
  ```

- Clone modified incremental models from production first, so they build in incremental mode and the CI result matches the first production build:

  ```sh
  dbt clone --select state:modified+,config.materialized:incremental,state:old
  dbt build --select state:modified+
  ```

  `state:old` skips brand-new incremental models, which have no production relation.
  `dbt clone` needs dbt 1.6 or later and a warehouse with zero-copy cloning; elsewhere it creates pointer views.
- With `on_schema_change='fail'`, an added column fails the incremental build in CI and passes a full refresh.
  dbt Labs prefers that red check, overridden on purpose, then `dbt build --full-refresh --select <model>` in production right after merge, over a green CI that hides the production failure.
- Test an incremental model in both incremental and full-refresh mode when the two paths can diverge.

## Reruns

`result:<status>` selectors read the last `run_results.json`; the statuses are `error`, `fail`, `warn`, `success`, `skipped` and `pass`.

- Rerun errored models plus the concurrent changes they may depend on:

  ```sh
  dbt build --select state:modified+ result:error+ --defer --state path/to/prod/artifacts
  ```

- Add `result:fail+` to include failed tests.
- Rerun failed tests minus one known failure: `dbt test --select result:fail --exclude <test> --defer --state path/to/prod/artifacts`.
- With `--state target/`, select `result:error` and `result:fail` together only under `dbt build`, because `dbt test` overwrites the `run_results.json` that `dbt run` wrote.
- Rebuild only what fresher sources feed: run `dbt source freshness` in one job to record state, then in the next job run it again and `dbt build --select source_status:fresher+ --state path/to/prod/artifacts`.

## Grants

Set `grants` in the model config or `dbt_project.yml` instead of writing `grant` SQL in hooks, so permissions are version-controlled, reapplied every run, and applied by the adapter's efficient path.

## Static analysis (dbt v2)

- Use `--static-analysis strict` in development and the default `baseline` in deployment, because `strict` downloads every source's schema and raises errors, while `baseline` skips the download and warns.
  `strict` compile time grows with the source count.
- Review deployment logs for the warnings that `strict` would have raised.
- Drive it per environment from `dbt_project.yml`: `+static_analysis: "{{ env_var('DBT_ENV_STATIC_ANALYSIS', 'baseline') }}"` with `DBT_ENV_STATIC_ANALYSIS=strict` set locally.
  The custom variable is distinct from the built-in `DBT_STATIC_ANALYSIS` flag override.

## Examining builds

- Read the completion line (`OK created sql view model main.stg_products ... [OK in 0.13s]`) for status, materialization and build time; a model's START and completion lines sit apart because threads interleave.
- Pick the longest-running models from the platform's Model Timing tab (critical path, longest model, wall clock) before changing a materialization.
  With several commands in one job, the tab shows the last command's timings, so put the command to measure last or run one command per job.
- Without the platform, the [`dbt_artifacts`](https://github.com/brooklyn-data/dbt_artifacts) package models `run_results` and `manifest` for a BI tool.

## Databricks Unity Catalog

- Define bronze data as dbt sources that every environment reads and none writes, so dev and prod start from the same inputs.
- Switch the source catalog with `target.name` when catalogs differ by environment; when workspaces differ, read `{{ env_var('DBT_HOSTNAME') }}.cloud.databricks.com` and `/sql/1.0/warehouses/{{ env_var('DBT_HTTP_PATH') }}` in the connection, with the domain suffix and path prefix hard-coded so the hostname passes validation.
- Generate each environment's token from that environment's workspace.
- Developers get `select` on sources, `select` and `modify` on the dev catalog, `select` or nothing on prod, and nothing on test.
  The prod service principal gets `select` on sources and `select` and `modify` on prod only.
  A separate test service principal serves CI only.
- Create only the top-level catalogs by hand, because dbt creates the schemas.
