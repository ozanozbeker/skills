# Secrets and credentials

How to wire a credential into a dlt pipeline with every secret value kept out of the transcript, and how to use one in ad-hoc code.

Source: [configuration and secrets](https://dlthub.com/docs/general-usage/credentials/setup), [access in code](https://dlthub.com/docs/general-usage/credentials/advanced), [built-in credentials](https://dlthub.com/docs/general-usage/credentials/complex_types), [vaults](https://dlthub.com/docs/general-usage/credentials/vaults) and [adding credentials](https://dlthub.com/docs/walkthroughs/add_credentials).

## The secrets tool

`scripts/dlt_secrets.py` reads and writes secrets files without showing a value.
Run it from the project root as `uv run <skill-dir>/scripts/dlt_secrets.py <command>`, where `<skill-dir>` is this skill's folder.
uv gives the script its own environment, built from its inline metadata, so the project's environment stays as it is.

- `show` prints the project's `.dlt/secrets.toml` and the global `~/.dlt/secrets.toml` with each `<...>` placeholder verbatim and every other value as `***`.
  It then lists each key's environment variable as `set`, `set (empty)` or `unset`, and ends with the keys dlt would still read as a placeholder, counting the samples `uv run dlt init` writes with `# fill this in!`.
- `add` merges a TOML fragment of `<...>` placeholders into `.dlt/secrets.toml`, creating the file with owner-only permissions.
  It keeps every existing key, value and comment, and refuses the whole fragment when one value is not a placeholder.
- `move <from> <to>` moves one value of `.dlt/secrets.toml` to another key, both written as dotted paths such as `sources.shop.credentials.token`, with the comment after the value.
  It refuses when `<from>` is missing or a table, or `<to>` exists, and drops a table it leaves with no key and no comment.
- `remove <path>` deletes one key, or a whole table with the comments inside it, and refuses a path the file lacks.
  Use it on the `<configure me>` keys of `uv run dlt init` that the project does not need, such as an AWS pair beside a local bucket, or the `sql_database` credentials table before you `add` the URL as one key.
- `add`, `move` and `remove` end by printing the project file redacted.

## Guardrails

- Leave `uv run dlt deploy` to the user, because it prints every secret it resolves under `Secret:`.
- Read `load_info`, `pipeline.last_trace`, `uv run dlt pipeline <name> info` and `uv run dlt pipeline <name> trace` freely while every credential travels in `auth` and no key sits in a URL, because only then do they carry no secret.
  DEBUG logs print each request's `headers` and `params` as written, so a token placed there appears; [`rest-api.md`](rest-api.md#the-config) covers the query-string cases.

## Wiring a credential

1. **Find the keys.**
   Run the pipeline.
   A source raises `ConfigFieldMissingException` when it is called; a destination raises it inside `PipelineStepFailed` at `step=sync`, and `pipeline.sync_destination()` checks the destination alone.
   The message opens with ``Missing 1 field(s) in configuration `GithubConfiguration`: `access_token` ``, then lists, per field, every `(provider, key)` pair dlt tried, in order.
   For a source key, dlt tries `sources.<module>.<source>.<key>`, `sources.<module>.<key>`, `sources.<source>.<key>`, `sources.<key>` and `<key>`, in that order.
   Take a path from that list without the pipeline-name prefix: `(secrets.toml, sources.github.access_token)`, or, while every secrets file is missing or empty, the variable `SOURCES__GITHUB__ACCESS_TOKEN` read in lower case with `.` for `__`.
   For a source defined in `github_pipeline.py`, `sources.github_pipeline.access_token` and `sources.github.access_token` both reach it.
   When `show` lists the user's credential under a key dlt does not try, `move` it to a path from that list, because `move` changes the key without showing the value.
   The message lists required fields only: `ConnectionStringCredentials` requires only `drivername`, so write the whole connection string as one key, such as `sources.sql_database.credentials`.
   Done means every field the message lists has a key path.
2. **Write a placeholder per key** with `add`.
   The placeholder names the value and its format, and a comment after it says where the value comes from; `add` keeps the comment in the file.

   ```bash
   uv run <skill-dir>/scripts/dlt_secrets.py add <<'EOF'
   [sources.sql_database]
   credentials = "<connection string: postgresql+psycopg2://user:password@host:5432/database>"  # a read-only role

   [destination.postgres.credentials]
   database = "<database name, such as dlt_data>"
   username = "<role name, such as loader>"
   password = "<password of that role>"
   host = "<host name or IP address>"
   EOF
   ```

   Done means `show` lists each key with its placeholder.
3. **Keep every credential out of git.**
   `uv run dlt init` copies its `.gitignore`, which ignores `secrets.toml`, only into a folder that has none; in a `uv init` project it keeps uv's file, which leaves `.dlt/secrets.toml` unignored.
   When `git check-ignore -v .dlt/secrets.toml` prints nothing, add the line `.dlt/secrets.toml` to `.gitignore`.
   When `git ls-files .dlt/secrets.toml` prints the path, the file is already tracked: run `git rm --cached .dlt/secrets.toml` and ask the user to rotate every credential in it, because the history keeps the old values.
   When a `.py` file holds a credential, flag it by file and line without repeating the value, replace it with an argument defaulted to `dlt.secrets.value` and an `add` placeholder for its key, and ask the user to revoke and rotate it, because the git history keeps it.
   Done means `git check-ignore -v .dlt/secrets.toml` prints the rule, `git ls-files .dlt/secrets.toml` prints nothing, and no `.py` file holds a credential.
4. **Hand off to the user.**
   For each key under `placeholders left`, name the file, the key, what to paste and where it comes from: the Setup guide on the destination's page in the dlt docs, the source's setup page, or the provider's token page with the narrowest read-only scope.

   ```text
   Open .dlt/secrets.toml and replace each <...> placeholder, keeping the quotes:
   - destination.postgres.credentials: the database, role and password you created
     in the Setup guide of https://dlthub.com/docs/dlt-ecosystem/destinations/postgres
   - sources.sql_database.credentials: a connection string for a read-only role
   Paste the values into the file, not into this chat, and tell me when it is done.
   ```

   Done means the user says the file is filled.
5. **Confirm.**
   Run `show`, then the pipeline.
   A placeholder left in place raises no missing-field error: a string resolves to the placeholder text, with a logged warning only for `<configure me>`, and a connection string fails with `InvalidNativeValue`.
   Done means `show` ends with `placeholders left: 0` and the run gets past `step=sync` and the extract.

## Reading a secret in ad-hoc code

- `dlt.secrets["sources.github.access_token"]` raises `ConfigFieldMissingException`, a `KeyError`, when the key is missing, and casts a string that looks like a number: `"0123"` comes back as `123`.
  Read a string with `dlt.secrets.get(key, str)`, which keeps the text and returns `None` when the key is missing.
- The accessor reads one exact path, with no section fallback, from the first provider that holds it.
  `dlt.secrets.get(path, ConnectionStringCredentials)` therefore drops a password set as a variable beside a TOML table; resolve typed credentials with `resolve_configuration`, as below, which reads field by field like a source argument.
- `str(credentials)` masks the password, while `to_native_representation()` and `dict(credentials)` show it, so pass those straight into the client call.
- Query the database with `pl.read_database(query, connection)` on a SQLAlchemy connection, because connectorx 0.4.6 rejects a driver-qualified URL such as `postgresql+psycopg2://` with `invalid connection string`.
- In a marimo cell, hold the secret in a cell-local `_name` and end the cell with something else, because marimo renders a cell's last expression and saves it to `__marimo__/session/*.json`.
  The rest of the notebook follows `marimo-notebook`, when it is installed, and [`notebooks.md`](notebooks.md).

```python
import dlt
import polars as pl
import sqlalchemy as sa
from dlt.common.configuration import resolve_configuration
from dlt.sources.credentials import ConnectionStringCredentials


def read_orders() -> pl.DataFrame:
    """Query the source database with credentials dlt resolves."""
    credentials = resolve_configuration(
        ConnectionStringCredentials(),
        sections=("sources", "sql_database"),
    )
    print(f"reading {credentials}")  # the password prints as ***
    engine = sa.create_engine(credentials.to_native_representation())
    with engine.connect() as connection:
        return pl.read_database("select id, amount from orders", connection)


token = dlt.secrets.get("sources.github.access_token", str)
print("GitHub token set:", token is not None)
print(read_orders().height)
```

## Typed credentials

- Import credential types from `dlt.sources.credentials`: `ConnectionStringCredentials`, `AwsCredentials`, `AzureCredentials`, `GcpServiceAccountCredentials`, `GcpOAuthCredentials`, `OAuth2Credentials` and `SFTPCredentials`.
  Annotate the source argument with one and default it to `dlt.secrets.value`, so dlt parses whichever form the user writes.
- A connection string in one key, a TOML table of fields, and one variable holding the string all fill the same `ConnectionStringCredentials`.
- Keep every field of a `credentials` table in `secrets.toml` or the environment, host and port included, because a `credentials` table in `config.toml` raises `ValueNotSecretException` unless `secrets.toml` holds the same credential or one variable holds all of it.
- Prefer the machine's own cloud login to a key in a file, because each cloud type falls back to its default chain when no key is set.
  `AwsCredentials` uses botocore's chain, which picked up the standard `AWS_ACCESS_KEY_ID` variables, the GCP types use `google.auth.default()`, and `AzureCredentials` uses `DefaultAzureCredential` but still needs `azure_storage_account_name`.

## Environment variables in production

- Set each key `show` lists as a variable in the deployment's secret store.
  A whole credential fits in one variable, such as `SOURCES__SQL_DATABASE__CREDENTIALS` holding the connection string or `DESTINATION__WAREHOUSE__CREDENTIALS` holding the database path of the `warehouse` destination, which `DESTINATION__DUCKDB__CREDENTIALS` does not reach.
- Unset a variable instead of emptying it, because an empty variable still wins over the files and resolves to `""`; `show` marks it `set (empty)`.
- A variable the user exports in another terminal, or after the agent started, never reaches the agent's shell, so a local run the agent starts reads `.dlt/secrets.toml`.
- Prefix a variable with the pipeline name, as in `GITHUB_PROD__SOURCES__GITHUB__ACCESS_TOKEN` for a pipeline named `github_prod`, to give two pipelines different credentials for one source, because dlt tries the prefixed name first.
  The TOML form is a `[github_prod.sources.github]` section, and dlt reads either form only once `dlt.pipeline()` has run, so create the pipeline before you call the source.
- Under Docker or Kubernetes secrets, dlt also reads a secret-typed key from `/run/secrets/<name>`, the variable name in lower case with `-` for `_`, such as `sources--github--access-token`.
  A `str` argument receives the file's text unstripped, so write the file without a final newline.
- `DLT_DATA_DIR` moves each pipeline's working directory, not the global secrets file, which stays in `~/.dlt`; `DLT_PROJECT_DIR` moves the folder `.dlt` is read from.
- dlt can also read Google Secret Manager or AWS Secrets Manager once `[providers] enable_google_secrets` or `enable_aws_secrets` is `true`; the vaults page has the secret names it expects.
- Retries, monitoring, Dagster and the first production run are in [`production.md`](production.md).
