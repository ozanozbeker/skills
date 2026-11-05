# Filesystem source

How to list files in a local folder or a bucket, pick or write the reader that turns them into rows, and load only new or changed files.
Source: the [filesystem source](https://dlthub.com/docs/dlt-ecosystem/verified-sources/filesystem), the [filesystem tutorial](https://dlthub.com/docs/tutorial/filesystem), [bucket credentials](https://dlthub.com/docs/dlt-ecosystem/destinations/filesystem#set-up-the-destination-and-credentials), [full loading](https://dlthub.com/docs/general-usage/full-loading) and [cursor-based incremental loading](https://dlthub.com/docs/general-usage/incremental/cursor).

`filesystem()` lists files and reads none; the reader after `|` is a `@dlt.transformer` that receives pages of `FileItemDict` and yields the rows, and the pipe's name becomes the table's name.

## Steps

Steps 1 and 2 refine step 4 of [`SKILL.md`](SKILL.md), and step 3 is its step 5 for files.

1. **List the files first.**
   Print `[item["relative_path"] for item in filesystem(bucket_url=..., file_glob=...)]`, because a missing folder, a `~` path or a glob that matches nothing lists zero files, and the run still succeeds with no table.
   Done means the list holds exactly the files to load.
2. **Build the pipe** with a reader from [Readers](#readers), shaped like [the example](#a-polars-reader): the file cursor on `filesystem()`, then `| reader`, then `.with_name()`, then every other hint on the pipe.
   Done means the reader yields frames, or is `read_jsonl()` for nested lists, and `filesystem()` carries no hint but the cursor.
3. **Run it three times in a test**: once, again with nothing changed, and again after touching one file; when files can be re-sent, run a fourth after re-sending an older file with one corrected value.
   Done means the second run loads no rows, the third loads only the touched file's rows and leaves one row per key, in the table or its downstream pick, and the fourth keeps the correction and every newer row.

## Buckets and globs

| `bucket_url` | Extra | Keys in `[sources.filesystem.credentials]` |
| --- | --- | --- |
| An absolute path, `file:///abs/path`, or a path relative to the current directory | none | none |
| `s3://bucket/prefix` | `dlt[s3]` | `aws_access_key_id`, `aws_secret_access_key`; `region_name`, `profile_name`, and `endpoint_url` for an S3-compatible store |
| `gs://bucket/prefix` | `dlt[gs]` | `client_email`, `private_key`, `project_id` |
| `az://container/prefix` or `abfss://` | `dlt[az]` | `azure_storage_account_name` with `azure_storage_account_key` or `azure_storage_sas_token`, or with `azure_tenant_id`, `azure_client_id`, `azure_client_secret` |
| `sftp://host/path` | `dlt[sftp]` | `sftp_username` with `sftp_password`, or `sftp_key_filename` and `sftp_key_passphrase`; `sftp_port` defaults to 22 |

- Keep `bucket_url` under `[sources.filesystem]` in `config.toml`, pointing at a local folder, because production then sets `SOURCES__FILESYSTEM__BUCKET_URL=s3://...` and the code stays the same.
- Leave the keys out where the machine has a cloud identity, because dlt falls back to botocore's chain for s3, Google default credentials for gs, and Azure's default chain for az once `azure_storage_account_name` is set.
- Give a second bucket its own section by renaming the resource before calling it: `filesystem.with_name("events_files")(file_glob="*.jsonl")` reads `[sources.filesystem.events_files]` and its `credentials` before `[sources.filesystem]`.
  Set its production variables at that level, `SOURCES__FILESYSTEM__EVENTS_FILES__BUCKET_URL`, because `SOURCES__FILESYSTEM__BUCKET_URL` and `SOURCES__FILESYSTEM__CREDENTIALS__...` beat its TOML section too.
- The default `file_glob="*"` stays at the top level; `**/*.csv` matches every level including the top, on a local folder and on fsspec's in-memory bucket alike.
- Narrow a large bucket with the glob's prefix (`orders/2026/11/*.csv`), because dlt lists every match before the reader gets its first page, and `files_per_page` does not limit the listing.

## Readers

Loading 1,000,000 rows in four files into DuckDB, with the whole process's peak memory:

| Reader | Yields | Time | Peak memory |
| --- | --- | --- | --- |
| `read_csv()`, `read_jsonl()`, `read_parquet()` | dicts | 44 to 45 s | 1.6 to 1.7 GB |
| `read_csv_duckdb(use_pyarrow=True)` | Arrow, `chunk_size` rows (5000) per batch | 1.1 s | 0.6 GB |
| `read_parquet(use_pyarrow=True)` | Arrow, `chunksize` rows (1000) per batch | 0.9 s | 0.5 GB |
| A Polars reader, one frame per file | Polars | 0.6 to 0.8 s | 0.7 to 0.9 GB |

- Yield frames, because dicts are normalized row by row and DuckDB loads them as `insert_values`; `loader_file_format="parquet"` brings the dict readers to about 11 s, still ten times slower ([`performance.md`](performance.md)).
- CSV: `read_csv_duckdb(use_pyarrow=True)`, or a Polars reader to cast types or add columns such as the file's path, which `filename=True` fails to add to Arrow batches.
  Skip `read_csv()`: it needs pandas, which dlt does not install, and it turned the text `N/A` into null, a nullable integer column into `DOUBLE` and a date column into text.
- JSONL: a Polars reader, unless nested lists should become nested tables, because only the dict reader `read_jsonl()` unnests them into `<table>__<field>`.
- Parquet: `read_parquet(use_pyarrow=True)`, because the default dicts also widen `DECIMAL(10,2)` to `DECIMAL(38,9)`.
- Parse timestamps in the reader, because dlt detects ISO timestamps in dicts but not in frames: an ISO string from `pl.read_ndjson` lands as `VARCHAR` until `pl.col(...).str.to_datetime()`.
- DuckDB and Polars infer types from the first rows, and a column that turned to text after row 30,000 failed the extract.
  Pass `sample_size=-1` or `all_varchar=True` to `read_csv_duckdb`, or `infer_schema_length=None` to Polars.

## A Polars reader

This reader reads new or changed order files, keeps money as a decimal, tags each row with its file and merges on the key; run it from the project root, with `bucket_url = "landing"` under `[sources.filesystem]`.

```python
from collections.abc import Iterator

import dlt
import polars as pl
from dlt.sources import DltResource
from dlt.sources.filesystem import FileItemDict, filesystem


@dlt.transformer
def read_orders(items: Iterator[FileItemDict]) -> Iterator[pl.DataFrame]:
    for file_obj in items:
        with file_obj.open() as f:
            frame = pl.read_csv(
                f,
                try_parse_dates=True,
                infer_schema_length=None,
                schema_overrides={"amount": pl.Decimal(10, 2)},
            )
        yield frame.with_columns(source_file=pl.lit(file_obj["relative_path"]))


def orders() -> DltResource:
    new_files = filesystem(
        file_glob="orders/**/*.csv",
        incremental=dlt.sources.incremental("modification_date"),
    )
    pipe = (new_files | read_orders()).with_name("orders")
    pipe.apply_hints(write_disposition="merge", primary_key="order_id")
    return pipe


if __name__ == "__main__":
    pipeline = dlt.pipeline(
        pipeline_name="landing", destination="duckdb", dataset_name="raw"
    )
    print(pipeline.run(orders()))
```

- Open the file with `file_obj.open()`, because it works on every bucket and decompresses `.gz`; `file_obj.local_file_path` raises `ValueError` on a bucket that is not local.
- The `primary_key` on this pipe logs `several column hints were different` on every run; the frames bullet in [`SKILL.md`](SKILL.md) gives the not-null cast that silences it.
- Give a `pl.Decimal` override the source's own scale, or read the column at that scale and round it with an explicit mode before the cast, as in `pl.col("amount").round(2, mode="half_away_from_zero").cast(pl.Decimal(10, 2))`, because a narrower scale rounds half to even without an error: `1.005` reads as `1.00`.
- One frame per file holds the whole file in memory; for files of hundreds of megabytes, use a chunked reader from [Large files and backlogs](#large-files-and-backlogs).

## New files, changed files and dispositions

- Call `.with_name()` on the pipe after the reader, because the name sets the table and the state key of its `filesystem()`, `filesystem_<name>`.
  Without it the table is `_read_csv_duckdb` or `_read_jsonl`, and every unnamed pipe shares the key `filesystem`, so a second folder's older files were skipped.
  Renaming a pipe starts a new table and cursor, and the next run reads every file again.
- Put only the file cursor on `filesystem()`, and the disposition, keys and any row cursor on the pipe.
  A `merge` on `filesystem()` never reaches the table, and a `primary_key` there replaces the `file_url` key the file cursor needs, which failed the extract with `IncrementalPrimaryKeyMissing`.
- The `modification_date` cursor reads a touched or rewritten file again whole, so `append` duplicated its rows; use `merge` on the row key when a rewritten file always holds each row's newest version.
- A file that lands with a modification time older than the cursor is never loaded, as `cp -p` and `rsync -t` leave it.
  Copy without keeping times, or reload once with `pipeline.run(pipe, refresh="drop_resources")`, which loaded the skipped file.
- `replace` on the pipe, in either form, keeps the file cursor, and a run with no new files emptied the table.
  For a full snapshot on every run, use `replace` with no file cursor.
- Add a row cursor on the pipe beside `merge`, as `pipe.apply_hints(incremental=dlt.sources.incremental("updated_at"))`, only when every change moves the cursor, because it drops each row older than the stored cursor: a re-sent day whose corrected amounts kept their `updated_at` loaded no rows.
  The cursor rules are in [`incremental.md`](incremental.md).
- When files can be re-sent or arrive out of order, use one of two shapes, because `merge` alone lets an older file overwrite newer rows: a re-sent day 1 set a shipped order back to placed.
  - `append` every version with its `source_file`, and pick each key's newest `updated_at`, then its latest `_dlt_load_id`, downstream.
  - Guard the `merge`: the reader reads the stored `(key, cursor)` pairs through `dlt.current.pipeline().dataset()` once `dlt.current.source_schema().data_table_names(seen_data_only=True)` lists the table, and drops each row older than its pair, keeping an equal one as a correction; `"dedup_sort": "desc"` on the cursor keeps the newest when one run reads both versions.

## Large files and backlogs

- `files_per_page` (default 100) is how many files one reader call gets, and `add_limit(n)` counts those pages; every file in a page is read to its end.
- Work through a backlog a page per run with `files_per_page=1`, `row_order="asc"` on the cursor, and `pipe.add_limit(1)` in place of `max_time` in the round loop of [`incremental.md`](incremental.md), which stops when a round loads no rows, because without `row_order` the loop skipped a file.

Peak memory of the extract step for one large file:

| File | Whole file in Polars | dlt's chunked reader | DuckDB by local path |
| --- | --- | --- | --- |
| Parquet, 20,000,000 rows, 1.2 GB in memory | 3.0 GB | 0.8 to 1.0 GB, `read_parquet(use_pyarrow=True)` | 0.4 GB |
| CSV, 1.6 GB on disk | 4.2 GB | 2.1 GB, `read_csv_duckdb(use_pyarrow=True)` | 0.4 GB |

On a local bucket, stream big files through DuckDB by path; `con.read_csv` does the same for CSV.

```python
from collections.abc import Iterator

import dlt
import duckdb
import pyarrow as pa
from dlt.sources.filesystem import FileItemDict


@dlt.transformer
def read_parquet_local(items: Iterator[FileItemDict]) -> Iterator[pa.RecordBatch]:
    with duckdb.connect() as con:
        for file_obj in items:
            relation = con.read_parquet(file_obj.local_file_path)
            yield from relation.to_arrow_reader(batch_size=100_000)
```

- On a remote bucket, read Parquet with `read_parquet(use_pyarrow=True)`, because DuckDB reading through fsspec, from `file_obj.open()` or a registered filesystem, peaked at 1.3 to 2.5 GB on the same file.
  When DuckDB does read a file object, keep the relation in a variable while its batches stream, because a temporary relation failed with `FileNotFoundError` partway through the file.
- `file_obj.open()` decompresses gzip by the extension, `.gz` or `.tgz` but not `.GZ`, and no built-in reader opens `.bz2`, `.zst` or gzip under another name.
  Polars reads `.zst` and unnamed gzip from the bytes, and reads `.bz2` once the file is wrapped in `bz2.open()`.
