---
compatibility: Requires dbt 2.0 or later.
description: dbt style. Use when writing, reviewing or restructuring a dbt model, source, macro, test, snapshot or project YAML, choosing a materialization or incremental strategy, setting up dbt CI, or planning a project split.
license: Apache-2.0
name: dbt-style
---

# dbt style

The conventions from the [dbt Labs best-practice guides](https://docs.getdbt.com/best-practices), Apache-2.0, read on 2026-11-03.
Each rule carries its reason in one sentence; the page linked under each heading holds the long argument.
It assumes dbt 2.0 or later.
This skill decides what the code looks like.
When `using-dbt-for-analytics-engineering` is installed, it decides how the work is done: data discovery, `dbt show` validation, impact analysis.
Load both for model work; without it, the steps below stand alone.

dbt Labs calls its own guides a starting point and puts consistency above every specific rule.
So the project wins: a `.sqlfluff`, a written style guide, or a pattern the existing models share overrides the rule here.
These rules are the default for a new project and for a choice the project has not made yet.

| Reference | Load when |
| --- | --- |
| [`incremental.md`](incremental.md) | Writing an incremental model or a snapshot, choosing between them, or building near-real-time models (microbatch, streams, dynamic tables, lambda views) |
| [`workflows.md`](workflows.md) | Setting up the `prek` hooks, a CI job, a slim CI selector, a rerun, grants, static analysis, or Databricks Unity Catalog, or reading a build's timings |
| [`packages.md`](packages.md) | Adding a package, or about to hand-write a generic test, a macro, a source or YAML, or profiling a slow model |
| [`tests.md`](tests.md) | Writing a custom generic test or overriding a built-in one |
| [`mesh.md`](mesh.md) | Deciding whether and where to split a project, grouping a monolith, or retiring a model version; `working-with-dbt-mesh`, when installed, holds the mechanics |

## Steps

1. **Read the project's conventions.**
   Open `dbt_project.yml`, `.sqlfluff` if present, the style guide if the README or a wiki names one, and two or three models in the layer you are touching.
   Note the layer folders, the naming prefixes, the comma position and the materialization defaults.
   Done means you can name the project's convention for each section below, or say the project has none.
2. **Write under the project's conventions, then the rules below.**
   Done means every rule below is applied, or you can name the project convention that overrides it.
3. **Run the tools.**
   Run `dbt format`, then `dbt lint`, then `dbt compile --static-analysis strict`, in that order.
   `dbt format` fixes only the layout, so `dbt lint` still catches the rest, such as keyword case, and `dbt lint --fix` repairs what it can.
   Both read only SQL files, so `dbt compile` is the step that checks the YAML.
   When the project has no `.sqlfluff` or no style guide, propose one as [`workflows.md`](workflows.md) says.
   Done means every command exits 0 with zero ignores added.

## Layers

[How we structure our dbt projects](https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview).
Data moves from source-conformed (shaped by systems outside our control) to business-conformed (shaped by the business's definitions).
Each layer is one step along that arc, and the DAG narrows as it goes: many narrow staging models join into fewer marts.

Development runs the other way from the DAG: mock the output in a spreadsheet with the stakeholder first, then build back from the mart to the staging models it needs.

### Staging

[Staging](https://docs.getdbt.com/best-practices/how-we-structure/2-staging).

- One staging model per source table, and staging is the only layer that calls `{{ source() }}`, so each raw table has exactly one entry point and a loader's column rename is a one-file edit.
- Folder per source system (`staging/stripe/`), because tables from one system share a loader and its quirks.
  Business groupings start at intermediate, so finance and marketing read the same staged table.
- Name it `stg_<source>__<entity>s.sql`.
  The double underscore separates a multi-word source from the entity: `stg_google_analytics__campaigns`.
  A single-source project may drop the source: `stg_orders.sql`.
- Staging renames, casts, does basic arithmetic (cents to dollars) and categorizes with `case`.
  Every transformation every consumer wants happens here once.
- Keep staging at the source grain: joins and aggregations start at intermediate, so the raw grain stays available downstream.
  When a concept needs a join to exist, build `base_<source>__<entity>s` models in a `base/` subfolder and join them in the staging model.
  Unioning or deduplicating a source to reach its true grain is still source-conformed work and belongs here.
- Materialize as a view, so downstream models always read fresh source data and no storage goes to tables nobody queries.
- Write the first few staging models by hand to learn the pattern, then generate the rest with `codegen` ([`packages.md`](packages.md)).

### Intermediate

[Intermediate](https://docs.getdbt.com/best-practices/how-we-structure/3-intermediate).

- Add the layer when a mart grows complex; a small project goes from staging straight to marts.
- Folder per business area (`intermediate/finance/`).
  Split into subfolders only when the folder grows past what one person can scan.
- Name it `int_<entity>s_<verb>s.sql`: `int_payments_pivoted_to_orders`, `int_orders_fanned_out_by_quantity`.
  The verb names the transformation, since an intermediate model exists to do one.
  The style template writes the same with a double underscore (`int_customers__unioned`); the project picks one.
- Use it to re-grain, to isolate a hard piece of logic, or to bundle four to six concepts so a mart joins two models instead of ten.
- Split a CTE into its own model when a second model needs it, when it changes the grain (so the grain change gets its own tests), or when the query runs long.
- Materialize as ephemeral by default.
  Switch to a view in a restricted custom schema once you need to query the step while debugging.
- Keep intermediate models in their own schema, away from the production schema end users browse.

### Marts

[Marts](https://docs.getdbt.com/best-practices/how-we-structure/4-marts).

- Marts are a star schema: fact tables and dimension tables, each at its declared grain, designed under `kimball-style` when it is installed.
  This departs from the structure guide, which builds one wide, denormalized mart per entity, because a star keeps one definition of each dimension that every fact table shares.
- Name a fact table `fct_<process>` and a dimension `dim_<entity>`, so the prefix tells end users which relations to query.
- One definition per concept.
  `finance_orders` beside `marketing_orders` is two truths; build it once and let teams filter.
  A legitimate second definition (revenue reported to a regulator) gets a name that says so.
- A consumer that cannot join reads a wide view built over the star, so the wide shape adds no second definition.
  With the Semantic Layer, MetricFlow joins the star itself; follow `building-dbt-semantic-layer` when it is installed.
- Materialize as a table, or incremental once the table takes too long to build.
  Set `table` on the folder in `dbt_project.yml` and `incremental` in the model's own config.
- Keep the time grain out of the atomic fact table (`orders_per_day`); a rollup belongs in a metric, or in an aggregate fact table built from the atomic one.
- A dimension may ref a fact table to carry an aggregate as an attribute (lifetime value on `dim_customers`), and the DAG may widen here.
- A dbt snapshot holds a Type 2 dimension's history: `dbt_valid_from` and `dbt_valid_to` are the row's effective and expiration dates, and `dbt_valid_to` is null on the current row.
  A fact table joins the dimension on the natural key and on its event time between the two dates, with a null `dbt_valid_to` read as open, so each row takes the surrogate key in effect at the event.
- A surrogate key is `dbt_utils.generate_surrogate_key` over the natural key, plus `dbt_valid_from` for a Type 2 dimension.
- An audit dimension identifies the run with `invocation_id` and `run_started_at`.
- Eight simple joins in one mart can be fine; four concepts each needing a heavy window function is the signal to add an intermediate model.
- While debugging, materialize the upstream views as tables for the session, because an error that surfaces in a mart often starts several models up and a table lets you query the step.

### The rest of the project

[The rest of the project](https://docs.getdbt.com/best-practices/how-we-structure/5-the-rest-of-the-project) and [mapping folders to schemas](https://docs.getdbt.com/best-practices/how-we-structure/6-mapping-folders-to-warehouse).

- One `_<folder>__models.yml` per folder, one `_<folder>__sources.yml` per staging folder, and one `_<folder>__docs.md` per folder that uses doc blocks.
  The underscore sorts it to the top; the folder name makes it fuzzy-findable.
- Set materialization and `+schema` on folders in `dbt_project.yml`, and configure a single model only for an exception.
  Name custom schemas after the folders: `staging`, `intermediate`, `marts`.
  A warehouse that says bronze, silver and gold maps to sources, staging plus intermediate, and marts; keep the dbt folders and set `+schema` to the warehouse's names when it requires them, with two names for staging and intermediate so they stay separate.
- dbt prefixes a custom schema with the target schema (`alice_dev_marts`), so development never overwrites production.
  Use the built-in `generate_schema_name_for_env` macro when production should use the bare custom schema name.
- Write the allowed dependencies down as a folder rule, such as "a mart selects from marts or staging only", because the folder tree is one of the three views of the project's knowledge graph beside the DAG and the warehouse.
- Seeds hold lookup tables that exist in no source system, such as zip codes to states.
  Source data arrives through the EL tool into the raw area.
- `analyses/` holds audit queries, such as `audit_helper` comparisons, that need Jinja but no warehouse object.
- `snapshots/` turns a source that overwrites rows into Type 2 history.
- `macros/` holds repeated transformations, documented in `_macros.yml`.
- Define `groups` with `private` access early, even in a monolith, because group boundaries become project boundaries later.
- Semantic models and metrics live under `model-paths`, either beside the mart (`orders.yml`) or in `models/semantic_models/` with a `sem_` prefix; a file outside `model-paths` parses silently into an empty `semantic_manifest.json`.
  Default to the subfolder on a project that already has marts.

## Naming

[How we style our dbt models](https://docs.getdbt.com/best-practices/how-we-style/1-how-we-style-our-dbt-models).

- `snake_case` for every schema, table and column, and underscores in model names, because dots collide with `database.schema.object`.
- Plural model names.
- Every model has a primary key named `<object>_id`, typed as a string.
  The same key keeps the same name everywhere: `customer_id` in every model.
- A dimension's surrogate key is `<object>_key`, and its natural key keeps `<object>_id`.
- Business terms over source terms: the source's `user_id` becomes `customer_id` when the business says customer.
- Full words: `customer`, not `cust`; `orders`, not `o`.
- Booleans start with `is_` or `has_`.
- Timestamps are `<event>_at` in UTC, with a suffix for any other zone (`created_at_pt`).
  Dates are `<event>_date`.
  Event names are past tense: `created`, `updated`, `deleted`.
- Money is decimal currency (`19.99`); a column in minor units says so (`price_in_cents`).
- Model versions take a `_v1`, `_v2` suffix; when installed, `working-with-dbt-mesh` decides when to version.
- Columns go in type order, with a comment heading each group: ids, strings, numerics, booleans, dates, timestamps.

## SQL

[How we style our SQL](https://docs.getdbt.com/best-practices/how-we-style/2-how-we-style-our-sql).

- Lowercase keywords, functions and fields; four-space indents; lines up to 80 characters; trailing commas; explicit `as` on every alias.
- Import CTEs first: every `{{ ref() }}` and `{{ source() }}` sits in a CTE at the top, named after the model it reads, selecting only the columns and rows the model uses.
- Functional CTEs next, one unit of work each, named for what they do: `events_joined_to_users`.
  A CTE with logic that needs explaining gets a `{# #}` comment above it.
- The file ends `select * from <final_cte>`, so you can audit any step by changing one word.
- Fields before aggregates and window functions.
  Aggregate on the smallest data set possible, before the join.
- `group by 1, 2` over column names; more than a few group-by columns signals a model design to revisit.
- `union all` unless you want duplicates removed.
- Name the join type (`inner join`, `left join`).
  Joins run left to right, so a `right join` means swapping the `from` and the joined table.
- With two or more tables, prefix every column with the full CTE name, never an initialism.
- A blank line separates each calculation block in a long `select`; a `case` puts each `when` on its own line with `then` indented under it; a multi-line `where` ends each line with its `and` or `or`.
- `{# #}` for a comment that should stay out of the compiled SQL.
- A model-specific config (a sort or dist key) goes in the model's `config()` block, one argument per line; a config shared by a folder goes in `dbt_project.yml`.

A staging model in this style:

```sql
with

source as (

    select * from {{ source('ecom', 'raw_orders') }}

),

renamed as (

    select

        ---------- ids
        id as order_id,
        customer as customer_id,

        ---------- strings
        status as order_status,

        ---------- numerics
        (order_total / 100.0)::numeric(16, 2) as order_total,

        ---------- timestamps
        ordered_at

    from source

)

select * from renamed
```

## Jinja

[How we style our Jinja](https://docs.getdbt.com/best-practices/how-we-style/4-how-we-style-our-jinja) and [don't nest your curlies](https://docs.getdbt.com/best-practices/dont-nest-your-curlies).

- Spaces inside delimiters: `{{ this }}`.
- A newline around each logical block, and four spaces of indent inside it.
- Readable source over tidy compiled whitespace; add `{%-` whitespace control only when the output breaks.
- Inside `{{ }}` or `{% %}`, write the expression bare: `{{ dbt_utils.date_spine(start_date=var('start_date')) }}`.
  A nested `{{ }}` passes the literal string.
  Hooks (`pre-hook`, `post-hook`, `on-run-start`, `on-run-end`) are the exception: there the nested `{{ this }}` is a string dbt renders at run time.

## YAML

[How we style our YAML](https://docs.getdbt.com/best-practices/how-we-style/5-how-we-style-our-yaml).

- Two-space indents, list items indented under their key, lines up to 80 characters.
- A one-item argument is still a list: `select: ['other_user']`.
- A blank line between list items that are dictionaries, such as columns.

## Python models

A dbt Python model follows `python-style` when it is installed, and the project's own linter otherwise.
The dbt guide names black and ruff; `python-style`'s ruff setup covers both.
Confirm the adapter runs Python before writing one, and materialize it as a table or incremental, because a Python model cannot be a view.

## Materializations

[Best practices for materializations](https://docs.getdbt.com/best-practices/materializations/5-best-practices) and [available materializations](https://docs.getdbt.com/best-practices/materializations/2-available-materializations).

The golden rule: start with a view; when it takes too long to query, make it a table; when the table takes too long to build, make it incremental.

| Materialization | Use for |
| --- | --- |
| view | Staging, and small models whose consumers need rows from the current hour |
| ephemeral | Intermediate steps nobody queries |
| table | Marts that end users and BI tools query, and any model with several children, since each child otherwise re-runs the parent's logic |
| incremental | A table whose full build takes too long |

- A view's cost grows with query frequency, because its SQL re-runs on every query; a heavy view queried often costs more than the table it replaces.
- A table shows only the rows present at its last build.
- An incremental model's first run costs a full table build.
- A view builds in under a second or two; a slower view, or any table or incremental model, is where to look when a job slows.
- Custom and adapter-specific materializations exist; reach for one only after view, table and incremental fail.

## Incremental models and idempotence

[Incremental models in depth](https://docs.getdbt.com/best-practices/materializations/4-incremental-models) and [idempotence](https://docs.getdbt.com/best-practices/idempotence).
[`incremental.md`](incremental.md) holds the strategies, snapshots and the near-real-time patterns.

Every model is idempotent: one run and a hundred runs leave the same data.
`--full-refresh` must rebuild the same result the incremental path builds.

- Wrap the cutoff filter in `{% if is_incremental() %}`, so the first run and a full refresh read everything.
- Set a `unique_key`, so a re-run merges or replaces the boundary rows instead of appending duplicates.
- Subtract a lookback window from `max(updated_at)` in `{{ this }}`, so rows that land late still arrive.
  A longer window costs more per run and drifts less; a row later than the window is still missed.
- Schedule a regular `--full-refresh` (weekly or monthly) when the table's size allows, to reset the drift.
- Keep one row per `unique_key` per run: `row_number() over (partition by <unique_key> order by <event_ts> desc)` and keep row 1 before the merge.
- Set `on_schema_change` deliberately for every incremental model.
- Derive every value from the data: a source timestamp instead of `current_timestamp()` or today's date, and `dbt_utils.generate_surrogate_key` instead of a random key.
