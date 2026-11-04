# Incremental loading

Source: [cursor-based incremental loading](https://dlthub.com/docs/general-usage/incremental/cursor), [lag](https://dlthub.com/docs/general-usage/incremental/lag), [troubleshooting](https://dlthub.com/docs/general-usage/incremental/troubleshooting) and [state](https://dlthub.com/docs/general-usage/state).

## The cursor

- Declare the cursor as a resource argument: `updated_at=dlt.sources.incremental("updated_at", initial_value=...)`.
  dlt keeps its last value in the pipeline state, which it commits to the destination with the data.
- Pass `updated_at.start_value` to the API or the query, never `last_value`, because `start_value` stays fixed for the run and `last_value` moves after every page.
- Pair the cursor with `merge` on a primary key, because the default closed range re-reads the boundary rows and only merge removes the duplicates for good.
- `range_start="open"` skips the boundary rows and turns off deduplication; use it only when no two rows share a cursor value.
- `row_order="asc"` stops reading at the first row out of range, so set it only when the source returns rows sorted by the cursor, or rows go missing.
- `lag` re-reads a window behind the last value (seconds for a datetime cursor, days for a date), for sources that write rows late.
- The cursor value must have the column's type: a cursor on a string date compares strings, so yield a `datetime` or convert it in an `add_map` placed before the filter with `insert_at=1`.

## Backfills

- Set `end_value` to backfill a range.
  A run with `end_value` reads and writes no incremental state, so backfill chunks can run side by side.
- Load one small chunk first, so the dataset and schema exist before parallel chunks race to create them.
- After the backfill, start the scheduled run with `initial_value` equal to the last chunk's `end_value`.
- To load a long range in steps, loop `pipeline.run(source.add_limit(max_time=...))` while `not load_info.is_empty`; this needs a source sorted by the cursor.

## State

- Keep state small: a last value, a list of a few thousand ids at most.
  Around 100,000 list items is where the docs say state stops being practical; query the destination through `dlt.current.pipeline()` instead.
- State belongs to the pipeline name, destination and dataset; change any of the three and the next run starts from `initial_value`.

## A cursor that does not advance

Check, in order:

1. The pipeline name, destination and dataset match the earlier runs.
2. `dev_mode` is off, because it resets state on every run.
3. No `refresh` is set, because every mode resets the selected state.
4. `replace` is written as `{"disposition": "replace"}`, because the bare string resets the resource's state.
5. The log shows "Bind incremental on", which proves dlt found the cursor argument.
