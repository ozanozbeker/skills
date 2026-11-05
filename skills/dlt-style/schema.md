# Merge strategies and schema contracts

How to choose a `merge` strategy other than `delete-insert`, a replace strategy and a schema contract, and how to keep a source ready to move to `merge`.
Source: [merge loading](https://dlthub.com/docs/general-usage/merge-loading), [full loading](https://dlthub.com/docs/general-usage/full-loading), [schema contracts](https://dlthub.com/docs/general-usage/schema-contracts) and [naming convention](https://dlthub.com/docs/general-usage/naming-convention).

## Merge strategies

- `upsert`, `insert-only` and `cdc` also run on DuckDB 1.4 or later, as `MERGE` statements, but they do not deduplicate: a key repeated in one batch lands twice.
  `insert-only` never updates a row, and `cdc` deletes every row the load lacks, or, with a `merge_key`, only those whose `merge_key` value appears in the load.
- Add `"skip_unchanged_rows": True` to an `upsert` or `cdc` disposition that reloads a full snapshot, because dlt then updates only the rows that changed, so an unchanged row keeps the `_dlt_load_id` of the load that last changed it.
- `scd2` adds `_dlt_valid_from` and `_dlt_valid_to`, null on the current row, and retires every key absent from the load, so it expects a full extract.
  For an incremental extract, set the natural key as `merge_key`, so a key absent from the batch stays current.
- Set `"destination_scope"` to a SQL condition, such as `"region = 'EU'"`, on a `delete-insert`, `scd2` or `cdc` merge whose load covers one slice of the table, because the merge then deletes or retires rows only inside that slice, and dlt ignores a `merge_key` beside it.
  `delete-insert` deletes every row in the scope before it inserts the load, and `cdc` and `scd2` also delete or retire the scoped rows of a slice the load has no row for, which a `merge_key` leaves alone.
- `scd2` hashes the whole record, nested lists included, so a nested edit makes a new version, and so does a list that only changed order.
  Set `row_version_column_name` to a column you compute from the fields that matter; a frame needs one anyway, because without it the run fails at normalize with `UnboundColumnException`.
  DuckDB computes a NULL-safe one: `duckdb.from_arrow(frame).select("*, md5(struct_pack(*columns(*))::varchar) as row_version").pl()`.
- Set `@dlt.source(root_key=True)` on a source that may move to `merge` later, because switching a resource with nested tables from `append` to `merge` fails on DuckDB with `Adding columns with constraints not yet supported`.

## Replace strategies

- Set `[destination] replace_strategy = "insert-from-staging"` when readers query a table while it loads, because the default `truncate-and-insert` empties it first: after a failed load the root table was empty, while `insert-from-staging` kept the old rows.
  DuckDB fails `staging-optimized` at load with `AssertionError: Must be able to get replace strategy`.

## Schema contracts

- A schema contract sets `evolve`, `freeze`, `discard_row` or `discard_value` for `tables`, `columns` and `data_type`.
  `freeze` fails the run with a `DataValidationError`, at normalize for dicts and at extract for frames and Pydantic models; `discard_row` drops the row and `discard_value` drops the value.
- Freeze a resource with `{"columns": "freeze", "data_type": "freeze"}` rather than the shorthand `"freeze"`, because a new table accepts its columns on its first run, but the shorthand also freezes `tables` and rejects the new table itself.
- A Pydantic model as `columns` validates each row and sets the contract to `{"tables": "evolve", "columns": "discard_value", "data_type": "freeze"}`: an extra field is dropped, and a bad type fails the run at extract.

## Naming convention

- Keep the default `snake_case` naming (`UserID` becomes `user_id`), because changing the convention of an existing schema fails the next run at extract with `TableIdentifiersFrozen`.
