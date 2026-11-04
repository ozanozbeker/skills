# Core sources

Source: the [REST API](https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic), [SQL database](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/configuration) and [filesystem](https://dlthub.com/docs/dlt-ecosystem/verified-sources/filesystem) source pages.
All three ship with open-source dlt.

## REST API

- Declare the source as a `RESTAPIConfig` dict passed to `rest_api_source(...)`, or to `rest_api_resources(...)` inside a `@dlt.source` that adds logic around it.
  Type the dict as `RESTAPIConfig`, so the editor checks its shape.
- Set the paginator on every endpoint or in `resource_defaults`: auto-detection only logs a warning when it guesses wrong.
  The built-in types are `json_link`, `header_link`, `header_cursor`, `offset`, `page_number`, `cursor` and `single_page`; a custom one subclasses `BasePaginator`.
- Auth is `bearer`, `http_basic`, `api_key` or `oauth2_client_credentials`, with the token in `secrets.toml` or the environment.
- A child endpoint names its parent with a placeholder, such as `"path": "issues/{resources.issues.number}/comments"`; `resolve` is the legacy form.
- An incremental endpoint takes `{incremental.start_value}` in its params and an `incremental` block with `cursor_path` and `initial_value`.
  The `params`-type incremental and `start_param` are deprecated.
- `data_selector` takes a JSONPath to the records when the API wraps them.
- Outside the declarative source, use `RESTClient(...).paginate(...)` or `from dlt.sources.helpers import requests`, because both retry on 5xx, 429 and timeouts and honor `Retry-After`, which plain `requests` does not.

## SQL database

- `sql_database(credentials, table_names=[...])` reflects only the listed tables; `sql_table(...)` reads one.
- Pick the backend by size:

  | Backend | Use |
  | --- | --- |
  | `sqlalchemy` | The default: small tables and development; the most robust and the slowest |
  | `pyarrow` | Larger tables, with exact types |
  | `connectorx` | The fastest, about twice `pyarrow` on Postgres; check its timezone and decimal handling first |
  | `pandas` | Avoid for money: decimals become doubles unless configured |

- An incremental cursor becomes `WHERE cursor >= :start ORDER BY cursor`, so index the cursor column in the source database.
- Match a naive or aware `initial_value` to the column's timezone, because a mismatch fails the comparison.
- Set per-table options in TOML, such as `[sources.sql_database.orders.incremental] cursor_path = "updated_at"`.
- Try `reflection_level="minimal"` when reflected types fail to coerce.

## Filesystem

- `filesystem(bucket_url, file_glob)` lists files and reads none; pipe it into a reader: `filesystem(...) | read_csv()`, `read_jsonl()` or `read_parquet()`.
- Name each pipe with `.with_name("orders")`, so each gets its own table and state.
- Load only new files with an incremental on `modification_date`, set on `filesystem()`, and the write disposition on the reader after the pipe.
- Bucket credentials go in `secrets.toml` or the environment, never in `bucket_url`.
