# The bus matrix

The enterprise data warehouse bus architecture, its matrix, and drilling across.
Source: the [Kimball techniques](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/) for conformed dimensions, shrunken rollup dimensions, drilling across, the value chain, the bus architecture, the bus matrix, the opportunity/stakeholder matrix, aggregate fact tables and consolidated fact tables.

## The matrix

- Rows are business processes, one per event stream in the value chain (purchasing, warehousing, retail sales; budgeting, commitments, payments), because each produces its own metrics at its own grain and cadence, and so its own fact table.
- Columns are dimensions, and a marked cell says the dimension applies to the process.
- Read a row to test each candidate dimension against the process; read a column to find where a dimension must conform across processes.
- Build one row at a time, in an order agreed with business management, so the matrix is both the architecture and the backlog.
- The detailed implementation matrix expands each row to its fact tables, with the grain sentence and the fact list per table.
- The opportunity/stakeholder matrix replaces the dimension columns with business functions (marketing, sales, finance) and marks who cares about each process, which names who joins the design sessions for that row.
- In a repo, keep the matrix as a Markdown table beside the marts' documentation, one row per fact table, so a new process is a row before it is a model.

## Conforming across processes

- A conformed dimension is one table, loaded once and used by every fact table in its column, with the same names and the same values, so drill-across row headers align.
- A shrunken rollup dimension is built from the base conformed dimension, never from the source again, so the values match.
  It serves aggregate fact tables and a process captured at the higher grain (a forecast by month and brand).
  A same-grain subset of rows (the stores of one region) is conformed the same way.

## Drilling across

- Two fact tables are compared by one query per table, each grouped by identical conformed attributes, merged on those row headers; BI tools call it stitch or multipass.
- In SQL, aggregate each fact table to the shared grain in its own CTE, then full outer join the aggregates on the conformed keys, because joining the atomic tables first multiplies rows.
- A consolidated fact table is that query written into the load: build one when the comparison runs constantly, because it adds load work and removes the drill-across from every report.
- An aggregate fact table is keyed to shrunken dimensions, summed from the atomic table, and published at the same time as the atomic table, and built only when a measured query on the atomic table is too slow.
