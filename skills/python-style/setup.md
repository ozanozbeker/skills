# Setting up a repo

The config files that [`SKILL.md`](SKILL.md) assumes live in the `templates` repo, a [Copier](https://copier.readthedocs.io/) template: `ozanozbeker/templates` on GitHub and `~/templates` when cloned.
Each comment inside a file records the reason for a setting, so the template is the reference and this page is the map.

## Answer the questions

Copier asks these, and the answers decide which files exist and what they hold:

| Question | Answer by repo kind |
| --- | --- |
| `language` | `python` for a package or an application, `none` for a repo of prose and config |
| `pypi` | `true` for a package released to PyPI, `false` for an application or pipeline |
| `docs` | `true` for a package with a site on GitHub Pages; asked only when `pypi` is `true` |
| `framework` | `dagster`, `fastapi`, or empty |
| `python_floor` | The oldest CPython the repo supports, which sets `.python-version`, `requires-python`, the classifiers and the CI matrix |
| `repo`, `owner`, `package` | The GitHub name, the GitHub owner, and the import name under `src/` |

| Answer | Files |
| --- | --- |
| every repo | `prek.toml` (Conventional Commits, gitleaks, zizmor, actionlint, typos, the built-in hooks, rumdl, tombi), `rumdl.toml`, `tombi.toml`, `SECURITY.md`, and the `github-style` workflows that every repo carries |
| `language: python` | `prek.toml` adds `default_language_version` and the local `ruff`, `uv lock --check` and `ty` hooks; `ruff.toml`, `ty.toml`, `pytest.ini`, `.coveragerc`, `typos.toml`; `rumdl.toml` gains the quarto flavor |
| `pypi` | release-please and the release workflows; `rumdl.toml` excludes `CHANGELOG.md` |
| `docs` | The `docs` job in CI and the `site` and `pages` jobs after a release; the tasks add the `docs` group and the Documentation link |
| `framework: dagster` | `ruff.toml` ignores on `definitions.py` and the asset modules, runtime-evaluated decorators; `pytest.ini` sets `pythonpath = .`; the tasks add `dagster-dg-cli` and `dagster-webserver` to `dev` |
| `framework: fastapi` | `ruff.toml` ignores `B008` and names `pydantic.BaseModel` as runtime-evaluated; `pytest.ini` adds the `anyio` marker; the tasks add `httpx` to `dev` |

## Create the project

GitHub writes the README, license and `.gitignore`, `uv init` writes the project, and the template adds beside them:

```sh
gh repo create <owner>/<repo> --public --clone --add-readme --license mit --gitignore Python
cd <repo>
uv init --lib --python <floor>   # a library: src/ layout, py.typed, uv_build
uv init --app --python <floor>   # an application: src/ layout, uv_build, and a [project.scripts] entry point
uvx copier copy --trust gh:ozanozbeker/templates .   # or ~/templates while editing the template
```

Both `uv init` forms give the `src/` layout (measured with uv 0.13.7), which keeps the tests importing the installed package and never the working tree.
Never pass `--bare` or `--no-package`, which drop the layout and the build backend.
Copier writes none of the files GitHub or `uv init` wrote.
With `--trust`, its tasks append to `.gitignore`, run `uv add --raw --group dev` for the tools, and set the classifiers and `[project.urls]` in `pyproject.toml`; without it, Copier refuses to run, and `--skip-tasks` or the answer `apply: false` prints those steps to do by hand instead.
Replace the `hello()` stub `uv init` wrote and write a first test, because the stub fails D103 and `fail_under = 100`, and pytest exits 5 with no test.
Then `uv add` each runtime dependency.
`uvx copier update` later re-applies the template's files from its newest tag and merges the change onto the repo's own edits.

## Layout

```text
src/<package>/           # _private.py modules, a public __init__.py, py.typed
tests/                   # test_*.py and conftest.py, no __init__.py
tests/typing/            # one file per public surface, checked by ty
user_guide/              # Quarto pages built by great-docs, upgrading.qmd first
docs/adr/                # one decision per file
docs/agents/             # issue tracker, triage labels, domain pointers
docs/research/           # cited notes
CONTEXT.md               # the glossary
CONTRIBUTING.md          # setup, pull request flow, release flow
CLAUDE.md                # navigation pointers, and @CONTRIBUTING.md
```

## What the files pin down

Each setting below is in the template with its reason as a comment.
This list is what to check when a repo's config departs from them.

- `prek.toml`: every `rev` is a frozen SHA with the tag beside it, and `prek update --freeze` keeps it so.
  The local hooks run through `uv run`, so each uses the locked version.
  `zizmor`, `actionlint` and the `gitleaks-ci` alias guard the workflows, which `github-style` owns; they stay in this file because one `prek.toml` runs everything.
- `ruff.toml`: `select = ["ALL"]`, numpy docstrings, `docstring-code-format`, and an `ignore` list where each entry carries why.
  Tests ignore `S101` and the docstring rules.
- `ty.toml`: `error-on-warning` and ty's stricter rule set, with `unused-ignore-comment = "error"`.
- `pytest.ini`: `filterwarnings = error`, `--strict-config --strict-markers --import-mode=importlib`, `xfail_strict`.
  `.coveragerc`: `fail_under = 100`.
  `pyproject.toml`: a `dev` group of bare tool names, which `uv add --group dev` writes.
- `rumdl.toml`: `line-length = 0` with one sentence per line, so a diff shows the sentence that changed.
- `tombi.toml`: `toml-version = "v1.1.0"`, because `prek.toml` uses multi-line inline tables.

A `pygrep` hook bans a pattern in `src/` that no lint rule covers, with the reason in the module docstring the hook names.
A ban is a text search, not a test.

### Typing tests

`tests/typing/` holds one file per public surface, as code a caller would write.
The positive space is `assert_type` on each public attribute and return.
The negative space is a call that must fail, marked with the rule that fails it:

```python
"""Code a caller writes against the payloads, which `ty check` checks."""

from typing import Literal, assert_type

import <package> as pkg

payload = pkg.Payload(source="universal", url="https://example.com")
assert_type(payload.render, Literal["html", "png", ""] | None)

pkg.Payload(source="universal", url="https://example.com", render="htm")  # ty: ignore[invalid-argument-type]
pkg.Payload(url="https://example.com")  # ty: ignore[missing-argument]
payload.url = "https://example.org"  # ty: ignore[invalid-assignment]
```

`unused-ignore-comment` at `error` makes each marked line fail the hook when its error stops firing, so the file asserts both spaces with the main `ty check` and needs no second hook.

### Confining a dependency

A dependency the package wraps is confined to its wrapper module:

```toml
[lint.flake8-tidy-imports.banned-api]
"sqlglot".msg = "Only `<package>._read` imports sqlglot (ADR 0004)."

[lint.per-file-ignores]
# Each module that may import a banned library, with the ADR that allows it.
"src/<package>/_read.py" = ["TID251"]
```

The wrapper's module docstring states that it is the only importer, so the config and the code assert the same seam.

### Per-repo additions

- Where a module reexports `typing.override` through a compat shim, add `typing-modules = ["<package>._compat"]` under `[lint]` in `ruff.toml`, so ruff recognizes the decorator in rules such as `ARG002`.
- A workspace member that CI does not install goes under `[environment] extra-paths` in `ty.toml`.
- A test library that pins a runtime dependency keeps a floor, because its latest release would raise that dependency above the runtime floor.
- A dependency that `filterwarnings = ["error"]` cannot tolerate gets its own `ignore::DeprecationWarning:<module>` entry with the reason above it.
