# Slowly changing dimensions in depth

The mechanics behind the type table in `SKILL.md`.
Source: the [Kimball techniques](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/) for Types 0 to 7, late arriving dimensions and late arriving facts; the banding of a mini-dimension is from *The Data Warehouse Toolkit*.

## Type 2

- Three columns at minimum: a row effective date, a row expiration date and a current row indicator, as timestamps when a member can change twice in a day.
- The current row's expiration is null (what a dbt snapshot writes to `dbt_valid_to`) or a far-future date; the project picks one and keeps it, because a `between` on the two reads differently.
- A change inserts a row with a new surrogate key and the same durable key, and expires the previous row at the change time.
- A fact posted after the change carries the new key; a fact for an event before the change carries the key effective then (late arriving rows, below).
- In dbt, the snapshot section of the `incremental.md` file of `dbt-style` ([ozanozbeker/skills](https://github.com/ozanozbeker/skills/tree/main/skills/dbt-style)) holds the strategy choice and the tests for the rows, when that skill is installed.

## Type 3

- A `prior_<attribute>` column is written once at the change, and the main column takes the new value as a Type 1.
- A user groups by either column, so it fits a planned realignment (sales territories) the business compares both ways, and little else.

## Type 4: mini-dimension

- Candidates are the attributes of a multimillion-row dimension that change fast, and the hot attributes queried most even when they are stable.
- Band continuous values (age, income, score) into ranges, so the mini-dimension holds the combinations the business uses and stays small.
- The mini-dimension has its own surrogate key, and the fact table carries the base key and the mini-dimension key current at the event, so the profile at the event is reachable without a Type 2 row in the base.
- The base dimension no longer carries the attributes, so a member's current profile is reachable only through a fact table; Type 5 fixes that.

## Type 5

- The base dimension carries the current mini-dimension key as a Type 1 outrigger, overwritten whenever the member's assignment changes.
- Present the base dimension and the current mini-dimension row as one table, through a view, so users see the current profile beside the base attributes without a fact table.

## Type 6

- A Type 2 dimension plus a `current_<attribute>` column per tracked attribute.
- A change inserts the new Type 2 row, then overwrites `current_<attribute>` on every row with the same durable key, so the historical row carries both the value at the time and the value now.
- A query groups by the Type 2 attribute for as-was and by the current attribute for as-is, in one pass.

## Type 7

- The fact table carries both the surrogate key and the durable key.
- The as-is view joins on the durable key and constrains the current flag; the as-was view joins on the surrogate key with no constraint.
- Both views read the same table, and the BI layer sees two dimensions.

## Late arriving rows

- A late arriving fact is one whose event time predates the current dimension rows.
  In each Type 2 dimension, look up the surrogate key whose effective and expiration dates bracket the event time, instead of the current key.
- A late arriving dimension is a fact that arrives before its context, such as a real-time inventory row naming a customer the dimension lacks.
  Insert a placeholder row with the natural key and `Unknown` attributes, post the fact against its surrogate key, and overwrite the placeholder as a Type 1 when the context arrives.
- A retroactive change to a Type 2 attribute inserts the row with the true effective date, expires its neighbours, and restates the fact rows in that window to the new key.
