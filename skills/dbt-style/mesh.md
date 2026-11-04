# Mesh planning

Source: [how we build our dbt Mesh](https://docs.getdbt.com/best-practices/how-we-mesh/mesh-1-intro), pages 2 to 6.
When `working-with-dbt-mesh` is installed, it owns the mechanics (groups, access, contracts, versions, cross-project `ref`); otherwise the dbt docs do.
This file is the decisions before and after.

## Whether to split

- Under about 500 models and a dozen regular contributors is monolith scale, and Mesh gives no immediate benefit.
- An enterprise with ten domain engineers per platform engineer, or a hub-and-spoke org at five to one, fits Mesh; a single small team usually does not.
- Weekly coordinated cross-project changes, or a cross-project prerequisite on a fifth of the work, mean the split landed in the wrong place.

## Where to split

- A vertical split follows the DAG: staging from marts, PII isolation, or expensive models on their own.
  A horizontal split follows the source or the domain: team consumption, different sources, different cadences.
  Pick one kind first.
- DRY applies to data, not only code: no two nodes anywhere in the mesh source the same rows and columns.
- Hub-and-spoke rules: a spoke produces no public models; a spoke defines its own domain sources; no two sources in the mesh point at one relation, so a spoke that needs a hub source asks the hub to change its interface; the hub team holds at least read access to every spoke for impact analysis.
- Shared macros ship as a dbt package (a library) with a maintaining team, separate from public models (an API).
- Git: a monorepo for a smaller team that wants speed; one repo per project for larger groups that need decoupling.
  The common shape is one project, one team, one repo.

## Grouping a monolith

- Find the interfaces in the jobs (which models build together), the lineage graph and `selectors.yml`.
- A model whose relationships stay inside its group is `private`; a model with cross-group relationships, or at a group's terminal node, is `protected`.
  Choose the most private level that keeps today's behaviour.
- Validate the groups by running jobs with group selectors beside production before splitting; frequent cross-group edits mean regrouping.

## Splitting

- Split one group at a time, starting inside the same repository so the change reverts easily.
- Move the grouped models and their YAML into a subfolder, add a `dbt_project.yml`, copy the macros, add a `packages.yml`, switch to the two-argument `ref`, mark upstream models `access: public` with a contract, and add `dependencies.yml`.
- Keep one-to-one parity during the migration and log refactors as issues, so a difference in output has one cause.
- For a mutual dependency: project A runs and publishes, project B adds A and runs, and only then does A add B.
- Replace a package install of another project with `dependencies.yml` and two-argument refs; replace `source()` reads of another project's output with cross-project `ref()` and delete those source definitions.

## Retiring a version

- A contracted versioned model gets a `deprecation_date` (a past date for an immediate removal), merged and run so state-aware CI records it, before the removal or rename lands; otherwise CI reports a breaking contract change.
- Hard delete: remove the v1 SQL, rename the `_v2` file to the base name, drop the version YAML, drop the warehouse objects.
  Soft delete: repoint the alias or view, set `enabled: false` on the old version, drop the object.
- A consumer tests with `ref('upstream', 'model', v=2)` on the deprecation warning, pins `v=1` when broken, and migrates before the date by dropping the `v=` argument.
- Removing, renaming or retyping a column breaks consumers; adding a column or fixing a bug does not; changing a metric's logic, grain or filter depends on the business meaning, so ask the consumer.
