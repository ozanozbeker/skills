---
description: Dimensional modeling, from the Kimball Group's official techniques. Business process, grain, star schemas, fact and dimension tables, surrogate and durable keys, slowly changing dimensions, hierarchies, bridge tables, conformed dimensions and the bus matrix. Use when designing, reviewing or extending a star schema, a data mart, a fact table or a dimension, declaring a grain, choosing a fact table type or a slowly changing dimension type, modeling a hierarchy or a many-to-many relationship, or planning a bus matrix.
name: kimball-style
---

# Kimball style

The [Kimball dimensional modeling techniques](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/), the Kimball Group's summary of *The Data Warehouse Toolkit*, third edition, read on 2026-11-03.
The text is all rights reserved, so the rules here restate it instead of quoting it.
Each rule carries its reason in one sentence; the [PDF](https://www.kimballgroup.com/wp-content/uploads/2013/08/2013.09-Kimball-Dimensional-Modeling-Techniques11.pdf) holds every technique in full, for when a rule needs defending or a case is not covered here.
This skill decides the model: the grain, the keys, the fact and dimension tables, and how they change over time.
The model holds in any warehouse and any tool.
In a dbt project with `dbt-style` ([ozanozbeker/skills](https://github.com/ozanozbeker/skills/tree/main/skills/dbt-style)) installed, it decides what the code looks like, and a mart loads both skills together.
When `building-dbt-semantic-layer` ([dbt-labs/dbt-agent-skills](https://github.com/dbt-labs/dbt-agent-skills)) is installed, it owns the metrics on top of the marts.

| Reference | Load when |
| --- | --- |
| [`scd.md`](scd.md) | Implementing a slowly changing dimension of Type 2 or above, a mini-dimension, as-was and as-is reporting, or a fact or dimension row that arrives late |
| [`bridges.md`](bridges.md) | Modeling a ragged or variable-depth hierarchy, or a dimension that takes several values for one fact row |
| [`bus-matrix.md`](bus-matrix.md) | Planning more than one fact table, conforming a dimension across processes, building an aggregate or a consolidated fact table, or comparing two fact tables |
| [`patterns.md`](patterns.md) | Heterogeneous products, a sequence of steps, several time zones, a value-band report, customer behavior tags or cohorts, an aggregate as a dimension attribute, a private copy of a dimension, a fact surrogate key, a fact row with a validity span, hundreds of sparse measures, load metadata on a fact row, a real-time fact table, or a data-quality schema |

## Steps

1. **Read the project's models.**
   Open the existing fact and dimension tables, the date dimension, and the bus matrix if the project keeps one.
   Note the prefixes (`fct_`, `dim_`), the key suffix (`_key`, `_sk`), how the dimensions keep history (a dbt snapshot, effective and expiration dates, a current flag), and which dimensions several fact tables already share.
   The project's convention overrides the rule here, because two conventions in one warehouse cost more than one imperfect one.
   Done means you can name the conformed dimensions the new table reuses and the project's convention for each section below, or say the project has none.
2. **Gather the business questions and the data realities.**
   The user stands in for the business: when the prompt names no questions, ask which questions the model must answer, or write down the ones you assume, because the grain and the dimensions follow from the questions and a model designed in isolation gets rebuilt.
   Profile the source tables that record the process: their grain, their keys, how a change and a delete appear, and how late a row can arrive.
   Done means you hold the questions and the grain of each source table.
3. **Select the business process.**
   A process is one operational activity (taking an order, posting a payment, snapshotting every account at month end), and each gets its own fact table, because each produces its own metrics at its own grain and cadence.
   A request that spans two processes (actuals against forecast) is two fact tables, or a consolidated fact table at their shared grain.
   Done means the fact table records one event stream.
4. **Declare the grain.**
   Write one sentence: one row per order line, one row per account per month, one row per claim across its milestones.
   Declare it before the dimensions and the facts, because every candidate column is tested against it, and keep one grain per table.
   Start at the atomic grain, the lowest level the process records, because atomic rows answer the question nobody predicted and a rollup presupposes the question.
   Done means the sentence is written and names which fact table type below it is.
5. **Identify the dimensions.**
   List the who, what, where, when, why and how of one event at that grain.
   Take the conformed dimension from step 1 where one exists, and add a new dimension only for context no existing dimension carries.
   Done means every dimension takes one value per fact row, or is routed to a bridge table in [`bridges.md`](bridges.md).
6. **Identify the facts.**
   A fact is a numeric measurement the event produces: the quantity and the extended price of a sale, and never the store manager's salary.
   Done means every fact fits one row of the grain and carries its additivity label.
7. **Write the design down.**
   The design is the grain sentence, the table and column names, sample domain values per attribute, each attribute's slowly changing dimension type, each fact's additivity, and the business rule behind every derived column.
   Add the fact table as a row of the project's bus matrix, or start one from [`bus-matrix.md`](bus-matrix.md).
   In a dbt project, `dbt-style` writes the code from this design.
   Done means every rule below is applied, or the departure is written beside the table with its reason.

## Fact tables

A fact table holds the measurements of one event per row at the declared grain, with a foreign key to each dimension, the degenerate dimension keys, and a timestamp when the event has one.
Its design follows the physical event, not the report someone wants from it.

| Type | One row per | Load |
| --- | --- | --- |
| Transaction | One event at a point in time | Insert only; sparse, because a row exists only where an event happened |
| Periodic snapshot | One entity per period (day, week, month) | Insert at the period end; dense, because a row exists for every entity even with no activity, holding zero or null facts |
| Accumulating snapshot | One instance of a pipeline (an order line, a claim), with a date key per milestone | Insert at the start and update at each milestone; the only type whose rows are revisited |

- A factless fact table records an event with no measurement (a student attends a class) as a row of foreign keys.
  To find what did not happen, build a coverage table of what could happen and subtract the activity table.
- Label every fact.
  An additive fact sums across every dimension.
  A semi-additive fact (a balance) sums across every dimension except time.
  A non-additive fact (a ratio) sums across none, so store its additive components and compute the ratio in the BI layer after the sum.
- A null fact is fine, because SUM, COUNT, MIN, MAX and AVG handle it.
  A null foreign key breaks referential integrity, so the dimension holds a row for unknown and a row for not applicable, and the fact row points at one.
- A measurement that appears in two fact tables keeps one name only when its definition is identical, and gets a different name when it is not, so nobody adds incompatible numbers.
- A transaction identifier with no attributes of its own (an invoice number) stays in the fact table as a degenerate dimension, with no dimension table, which is common in transaction and accumulating snapshot tables.
- A header and its lines are one fact table at the line grain: every header-level foreign key and degenerate dimension repeats on each line, and a header-level fact (a freight charge) is allocated to the lines by a business rule, so every fact rolls up by every dimension and a header table exists only as an aggregate.
- An accumulating snapshot stores one lag per milestone measured from the process start, so the lag between any two milestones is a subtraction instead of one stored column per pair.
- A financial fact in several currencies is a pair of columns, the transaction currency and the standard currency converted by an approved rule, plus a currency dimension naming the transaction currency.
- A fact reported in several units of measure is stored once in the standard unit, with a conversion factor per other unit on the same row, and exposed through one view per audience, so the view's arithmetic stays simple and the factors cannot drift from the row.
- A numeric value used in calculations is a fact; a stable numeric value used for filtering and grouping (a list price) is a dimension attribute, with a value-band attribute beside it; a value used both ways is stored both ways.
- Compute year-to-date and period-to-date in the BI layer, because a stored year-to-date column turns into fiscal-period-to-date on the next request.
- A query reads one fact table.
  Two fact tables are read by two queries merged on conformed row headers (drilling across, in [`bus-matrix.md`](bus-matrix.md)), because a join across two fact tables' foreign keys has uncontrolled cardinality and returns wrong numbers.
- An aggregate fact table is an index: summed from the atomic table, keyed to shrunken dimensions, chosen by the BI layer's aggregate navigation, and never the only copy of the data.
- Two processes compared in most queries (actuals and forecast) earn a consolidated fact table at their shared grain, which moves the drill-across from every query into the load.
- Collapse the levels of a hierarchy into one dimension: a fact table with a date key, a month key, a quarter key and a year key, or one key per flag, is a centipede, and the levels belong in one dimension and the flags in a junk dimension.
- One column per measure, because a generic measure column multiplies the row count and makes arithmetic between measures hard.

## Dimension tables

A dimension table has one single-column primary key and is wide, flat and verbose: many low-cardinality text attributes, because the attributes are what queries filter and group by and what report labels show.

- The primary key is a surrogate: an anonymous integer assigned in sequence from 1, owned by the warehouse, because the natural key repeats across Type 2 rows and is administered by source systems outside your control.
  When the load path has no sequence, a hash of the natural key and the effective date is the substitute, at the cost of a wider key; `dbt_utils.generate_surrogate_key` is that hash in dbt.
- Keep the natural key as an attribute, and add a durable key (a sequential integer that never changes) when the natural key can change, as an employee number does on rehire, so one entity keeps one durable key across many surrogate keys.
- Name the surrogate key for the dimension, `customer_key`, identical in the dimension and in every fact table, and keep the natural key as `customer_id`, so a reader tells the warehouse's key from the source's.
- Denormalize every fixed-depth many-to-one hierarchy into attributes on one row.
  A snowflake holds the same information and costs legibility and query speed, so it is the shape to flatten, never to build.
  Several hierarchies (calendar and fiscal, two geographies) coexist in one table.
- Every code, flag and indicator gets a full-text attribute beside it that reads on its own, and a code with embedded meaning is split into one attribute per part.
- An attribute with no value holds the string `Unknown` or `Not applicable`, because databases group and constrain on null inconsistently.
- A calendar date dimension joins to every fact table, with week number, month name, fiscal period and holiday indicators, so Easter is looked up, never computed in SQL.
  Its key is the exception to the surrogate rule: an integer `YYYYMMDD` that partitions well, plus a row for an unknown date.
  Filter and group on its attributes, never on the key.
  A precise timestamp is a plain column on the fact table, and a time-of-day dimension joins only when users group by shift or day part.
- One physical dimension plays several roles (order date, ship date) through one view per role with uniquely named columns, and one foreign key per role.
- The miscellaneous low-cardinality flags of a transaction go in one junk dimension holding only the combinations that occur in the data, not the Cartesian product.
- A dimension that references another dimension is an outrigger; use one sparingly, and demote the correlation to the fact table as two foreign keys instead.
  An outrigger key inside a Type 2 dimension multiplies its rows, because every Type 2 change in the outrigger forces a Type 2 row in the base, so the fact table is where the key belongs.
- One dimension per entity: a store, a warehouse and a customer each carry their own geography, labeled for the entity (`store_state`, `customer_state`), because a generic location or person dimension mixes attribute sets and grows large.
- Free text goes in a comments dimension, or as attributes of a dimension with one row per transaction when every comment is unique, and never in the fact table.

## Slowly changing dimensions

The decision is per attribute, not per table; one dimension mixes types.
[`scd.md`](scd.md) holds the mechanics of Types 2 to 7 and of rows that arrive late.

| Type | On a change | Use for |
| --- | --- | --- |
| 0 | Keeps the original value | An attribute labeled original, a durable identifier, most date attributes |
| 1 | Overwrites the value | An attribute whose history has no analytic value |
| 2 | Adds a row with a new surrogate key, an effective date, an expiration date and a current flag | An attribute that reports must see as it was at the event |
| 3 | Adds a column holding the prior value and overwrites the main one | Two realities compared side by side; rare |
| 4 | Moves a group of attributes to a mini-dimension with its own key, both keys on the fact table | Fast-changing or hot attributes of a large dimension |
| 5 | Type 4, plus a Type 1 key to the current mini-dimension row in the base dimension | The current profile without going through a fact table |
| 6 | Type 2, plus a Type 1 current copy of each attribute on every row of the durable key | As-was and as-is on one row |
| 7 | Both the surrogate and the durable key on the fact table, with a current-rows view and an all-rows view | As-was and as-is through two views |

- Default to Type 2 for an attribute a report must reproduce as it was, Type 1 for one where only the current value matters, and Type 0 for anything labeled original.
- A Type 2 change assigns a new surrogate key, and facts from that moment on carry it; the durable key stays on every row.
- A Type 1 overwrite recomputes every aggregate table and cube that grouped by the attribute, because their rows carry the old value.
- In dbt, a snapshot of the source or staging model produces the Type 2 rows; `dbt-style`'s `incremental.md` holds the strategy and the tests.

## Hierarchies

- A fixed-depth hierarchy (product to brand to category to department) with agreed level names is positional attributes on the dimension row, the easiest shape to query and the fastest.
- A slightly ragged hierarchy (three to six levels of geography) is forced into positional attributes for the maximum depth, filled by business rules, so it needs no bridge.
- A hierarchy of indeterminate depth, with shared ownership, with alternatives swapped at query time, or that changes over time, takes a bridge table or a pathstring attribute, in [`bridges.md`](bridges.md).

## Conformed dimensions

- A dimension conforms when its attributes carry the same column names and the same domain values in every fact table that uses it, so a row header from one fact table lines up with the same header from another.
- Define each conformed dimension once with the business's data governance representatives, load it once, and reuse it, because a second definition is a second truth and a second build.
- A shrunken rollup dimension is a subset of a conformed dimension's rows or columns (month from date, brand from product), built from the base dimension so the values match, for aggregate fact tables and for a process captured at that grain, such as a forecast by month and brand.
- Each business process is a row of the bus matrix and each dimension a column; build one row at a time, in [`bus-matrix.md`](bus-matrix.md).

## Extending a model

Four changes break no existing query and change no existing result:

- A new fact consistent with the grain is a new column.
- A new dimension that keeps the grain is a new foreign key column.
- A new attribute is a new column on the dimension.
- A more atomic grain is new attributes on a dimension and the fact table restated at the lower grain, with every existing column name kept.

Shape a change as one of these four.
A change outside them (a coarser grain, a renamed column, a redefined fact) breaks consumers: version the table, and retire the old version on a schedule the consumers agree to.
In dbt, `dbt-style`'s `mesh.md` holds the rules.
