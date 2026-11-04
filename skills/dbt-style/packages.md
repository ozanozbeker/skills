# Packages

Add these four dbt Labs packages to `packages.yml`, each pinned to an exact version, because each replaces code the project would otherwise write and maintain.

| Package | Reach for it when |
| --- | --- |
| [`dbt_utils`](https://hub.getdbt.com/dbt-labs/dbt_utils/latest/) | A test or a macro is about to be written: it holds the common generic tests, `generate_surrogate_key`, `date_spine`, `star` and `union_relations` |
| [`codegen`](https://hub.getdbt.com/dbt-labs/codegen/latest/) | A source, a staging model or a YAML file is about to be typed out by hand |
| [`dbt_project_evaluator`](https://hub.getdbt.com/dbt-labs/dbt_project_evaluator/latest/) | A project needs a check that it follows the structure guide across modeling, testing, documentation, performance and governance |
| [`dbt_query_profiler`](https://hub.getdbt.com/dbt-labs/dbt_query_profiler/latest/) | A model is slow: it finds the query, its plan and its stats on Snowflake, BigQuery, Databricks, Redshift or DuckDB |

- Check a package's dbt v2 status on its hub page before adding it, and run what the project will use on its own warehouse, because the hub's status covers parsing only.
- `dbt_project_evaluator` 2.x builds no models: each rule is a native dbt check over the information schema, which needs no warehouse.
  The checks run before every `dbt build` and on demand with `dbt check`, and warn by default.
  Set `+severity: error` under `checks: dbt_project_evaluator:` in `dbt_project.yml`, so a violation fails `dbt check` and `dbt build`.
- `dbt_project_evaluator` and `dbt_query_profiler` ship agent skills, which `dbt deps` installs once `dbt_project.yml` sets `flags: ai_provider: claude`.
- `dbt_query_profiler` finds a model's queries by the `node_id` in dbt's default query comment.
- On dbt 2.0.9 and DuckDB (measured 2026-11-04), three calls failed, likely from DuckDB under dbt 2.0 rather than the packages; confirm on the project's warehouse before relying on them.
  `codegen` 0.14.1's `generate_source` fails in `dbt_utils.get_relations_by_pattern`, which queries an `information_schema.tables` that DuckDB does not expose there.
  `dbt_query_profiler` 0.3.0's `print_query_stats` and `print_execution_plan` find nothing by `model_name`, because DuckDB's query log holds no query comment.
  `dbt_utils` 1.4.1, the rest of `codegen`, `dbt_project_evaluator` 2.0.2 and `print_query_plan` worked.
