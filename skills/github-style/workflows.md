# Workflow files

The workflows live in the `templates` repo, a [Copier](https://copier.readthedocs.io/) template: `ozanozbeker/templates` on GitHub, under `shared/.github/` and `python/.github/`.
Each comment inside a workflow records the reason for a step, so the template is the reference and this page is the map.
Read a workflow there before changing it, and change it there first, so every repo gets the fix on its next `copier update`.

## Which answer carries which file

| File | Answer | Job |
| --- | --- | --- |
| `.github/workflows/ci.yml` | every repo | `lint` runs `prek run --all-files` and `gitleaks-ci`; `dependency-review` on a pull request; `all-green` is the one required check |
| `.github/workflows/ci.yml` | every repo | Adds `test` across the OS matrix, `next-python` (may fail) and `lowest`, which also checks coverage |
| `.github/workflows/ci.yml` | `docs` | Adds the `docs` job that runs `great-docs build` |
| `.github/workflows/pr-title.yml` | every repo | Checks the title is a Conventional Commit, because the squash commit takes it and release-please reads that commit |
| `.github/workflows/dependabot-auto-merge.yml` | every repo | Turns auto-merge on for each Dependabot pull request, so it merges once `all-green` and `title` pass |
| `.github/workflows/prek-update.yml` | every repo | Daily `prek update --freeze --cooldown-days 7`; also `uv lock --upgrade`. Opens its pull request with the App token so CI runs on it |
| `.github/dependabot.yml` | every repo | Daily with a 7-day cooldown for the actions and the `uv` ecosystem with `increase-if-necessary`, so a floor rises only in a `deps:` commit |
| `.github/workflows/release-please.yml` | `pypi` | Opens and updates the release pull request from the commits on `main` |
| `.github/workflows/release.yml` | `pypi` | On a tag: build, `pypi` with approval and attestations; with `docs`, then `site` and `pages` |
| `release-please-config.json`, `.release-please-manifest.json` | `pypi` | The Python release type, a `uv.lock` extra file, and the changelog sections |

Inside a `.jinja` file, an `{% if %}` block holds the lines that an answer adds, so one `ci.yml.jinja` shows every variant.

## The versions in `ci.yml`

`copier.yml` computes `python_versions` from `python_floor` to the newest release, and the template writes them into the `test` matrix, excludes the middle versions on macOS and Windows, and sets `next-python` to `python_next`.
The classifiers in `pyproject.toml` list the same versions, and the template's task writes them.
Raising the floor is `uvx copier update --trust --data python_floor=<floor>`, then `requires-python` and `.python-version` by hand, then a review of the diff.

## Merges that start no workflow

Auto-merge turned on with `GITHUB_TOKEN` produces a merge whose push starts no workflow, so `release-please.yml` runs on the next push to `main` and reads those commits then.
That is fine for `chore` and `ci` commits, which start no release on their own.

## A new package's first release

The template writes `.release-please-manifest.json` as `{".": "0.0.0"}`.
Set `bootstrap-sha` in `release-please-config.json` to the commit before the one that adds release-please, and end the first pull request with a `Release-As: 0.0.1` footer.
