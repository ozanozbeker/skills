# Bridge tables

Ragged hierarchies and multivalued dimensions.
Source: the [Kimball techniques](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/) for ragged hierarchies and multivalued dimensions; the column shapes and the weighting factor are from *The Data Warehouse Toolkit*.

## Ragged hierarchy

- A bridge table fits a hierarchy whose depth is indeterminate (an organization chart, a chart of accounts), a node with several parents, alternative hierarchies swapped at query time, and a hierarchy that changes over time; the recursive extensions of SQL handle only the first.
- One row per path from an ancestor to a descendant, including the zero-length path from a node to itself, with the parent key, the child key, the depth, a lowest flag and a highest flag.
- To roll up a subtree, constrain the dimension to the root as the parent, join the bridge on the parent key, and join the fact table on the child key; `depth = 1` gives the direct children.
- Every query constrains the bridge to one parent or to depth 0, because a fact row otherwise counts once per ancestor.
- A node with two parents sits in both subtrees, so a report spanning both parents needs a weighting factor on the bridge rows or it double counts.
- A hierarchy that changes over time adds effective and expiration dates to the bridge rows, and every query constrains to a date.

## Pathstring

- One text attribute per dimension row encodes the full path from the top node (`/1/7/42/`), so a subtree is a `like '/1/7/%'` in plain SQL and no bridge is needed.
- It supports no alternative hierarchies and no shared ownership, and a restructure relabels every descendant, so it fits a stable single-parent hierarchy.

## Multivalued dimension

- One fact row legitimately has several members of one dimension: diagnoses per treatment, customers per account, sales reps per deal.
- The fact table carries a group key; the bridge has one row per group key and dimension key with a weighting factor that sums to 1 within the group; the dimension is unchanged.
- A weighted query multiplies each fact by the weight, so totals allocate correctly.
  An impact query omits the weight, so each member sees the full amount and the grand total overcounts on purpose.
  Name the report after the choice.
- When both sides are Type 2 (accounts and customers), the bridge carries effective and expiration dates, and the query constrains to a moment, so an old account row never pairs with a new customer row.
- A small fixed count can be positional attributes on the dimension instead (a primary and a secondary diagnosis), which is a plain query at the cost of generality.
