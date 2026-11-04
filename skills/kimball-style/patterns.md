# Special-purpose patterns

The cases the rules in `SKILL.md` leave out.
Source: the [Kimball techniques](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/) for supertype and subtype schemas, step dimensions, multiple time zones, dynamic value banding, behavior tag time series, behavior study groups, aggregated facts as dimension attributes, hot swappable dimensions, fact table surrogate keys, timespan tracking, measure type dimensions, audit dimensions, real-time fact tables and error event schemas.

## Heterogeneous products

- A bank's checking accounts, mortgages and business loans are all accounts, each with its own facts and attributes.
- One supertype fact table and dimension hold the intersection: the facts and attributes every type shares.
- One subtype fact table and dimension per type hold its full set.
- A single table with the union of everything has hundreds of incompatible, mostly empty columns, which is why the split exists.

## A sequence of steps

- A web session or a workflow is one transaction fact row per step.
- A step dimension carries the step number and the steps remaining to the end of the session, so a query finds the last step before abandonment or the share of sessions that reach step three.

## Several time zones

- Two role-playing date keys, and time-of-day keys when needed, per event: universal time and local time, so both roll up without conversion at query time.

## Value bands at query time

- A banding dimension with a label, a lower bound and an upper bound joins to the fact on `fact between lower and upper`, so the bands change by editing rows.
- It beats a `case` expression, because the `case` scans the fact table unconstrained, and the gap widens on a columnar store.

## Customer behavior over time

- Tags from periodic clustering are positional attributes on the customer dimension (`tag_2025_q1`), plus an optional string of the whole sequence, because the tags are queried together as a pattern and never summed.
- A study group is a table of the durable keys of the customers a long analysis found, joined to the customer dimension of any schema as a filter, and combined with other groups by union, intersection and difference.
- An aggregated fact users filter by (lifetime spend) goes on the customer dimension as a banded attribute, which moves the work from every query into the load.

## A private copy of a dimension

- A hot swappable dimension pairs the same fact table (stock quotes) with a different copy of the dimension per audience, each copy carrying that audience's own attributes.

## Fact table variants

- A fact surrogate key is a sequential integer with no dimension behind it, which identifies a row without its dimension keys, lets an interrupted load resume or back out, and turns an update into an insert and a delete.
- A fact row with an effective date, an expiration date and a current flag fits a slowly changing balance, where a periodic snapshot would write identical rows each period, and little else.
- A measure-type dimension collapses a row to one generic fact and a measure key; it pays off only when hundreds of facts are possible and a row carries a handful, because it multiplies the row count by the occupied columns.

## Load metadata on a fact row

- An audit dimension is keyed from every fact row and carries the run's data-quality indicators, code version and run timestamp, so a query drills to the rows a given run produced.
- In dbt, `invocation_id` and `run_started_at` identify the run.

## Real-time fact table

- A hot partition pinned in memory without aggregates or indexes, or deferred updates that let running queries finish first.
- The near-real-time patterns for dbt (microbatch, streams, dynamic tables, lambda views) are in the `incremental.md` file of `dbt-style` ([ozanozbeker/skills](https://github.com/ozanozbeker/skills/tree/main/skills/dbt-style)), when it is installed.

## Data-quality schema

- Screens test the data as it flows from the source to the BI layer, and each failure is an error event.
- An error event fact table has one row per event; an error event detail fact table has one row per column of each row that took part.
- It stays in the back room, and the audit dimension carries its summary to the front room.
