---
description: Set up a repo to the python-style and github-style standards, asking the few questions that decide which files and settings it gets.
disable-model-invocation: true
name: setup-repo
---

# Set up a repo

Scaffold a repo to the standard the two style skills describe: the files from the `templates` repo, a Copier template that [`python-style/setup.md`](../python-style/setup.md) and [`github-style/workflows.md`](../github-style/workflows.md) map, and the repository settings from [`github-style/settings.md`](../github-style/settings.md).
This skill holds the questions and the order.
The three files hold the content, so read each one before writing from it.

Prompt-driven, not a script.
Explore, present what you found, confirm, then write.
Every settings command that changes the repo runs only after the user has seen the plan.

## Process

### 1. Explore

Read the repo before asking anything:

- `git remote -v`: is there a GitHub remote, and what is `<owner>/<repo>`?
  No remote means the repo is not on GitHub yet, and step 4 creates it there first.
- `.copier-answers.yml`: present means the repo came from the template, and the job is `copier update`, not `copier copy`.
- `pyproject.toml`: does it exist, and does it have `src/`, `[build-system]`, `requires-python`, `[project.scripts]`?
- `prek.toml`, `ruff.toml`, `ty.toml`, `rumdl.toml`, `tombi.toml`, `.python-version`: which exist already?
- `.github/workflows/`, `.github/dependabot.yml`, `release-please-config.json`: any of them?
- Framework signals: `dagster` or `fastapi` in the dependencies, a `definitions.py`, a `defs/` directory, an `app.py` with a `FastAPI()` call.
- `CLAUDE.md`, `CONTRIBUTING.md`, `docs/agents/`: present or not.
- `~/templates/copier.yml`: is the template on this machine?
- `gh auth status`: logged in, and as whom?
- For an existing GitHub repo, the current settings: `gh api repos/$R --jq '{allow_squash_merge, allow_auto_merge, delete_branch_on_merge, security_and_analysis}'` and `gh api repos/$R/rulesets --jq '.[].name'`.

### 2. Present findings and ask

Summarise what exists and what is missing, then take the sections in order.
Lead each with the recommended answer so the user can accept it in a word.
Skip a section the exploration already settled.
Each section maps to a Copier question, named in bold.

**Section A: Tier.**
One of three, and everything else follows from it:

- **Package**: released to PyPI, with docs on Pages.
  `language: python`, `pypi: true`.
  Recommend when `pyproject.toml` has a `[build-system]` and no `[project.scripts]`, or the user says library.
- **Application**: Python with no release.
  `language: python`, `pypi: false`.
  Recommend when there is a `[project.scripts]` entry or framework signals.
- **No Python**: prose, config and hooks only.
  `language: none`.
  Recommend when there is no `pyproject.toml`.

**Section B: Template source.**
`gh:ozanozbeker/templates` at its newest tag, unless the user is editing the template, in which case `~/templates` so the edits render.
Say that `.copier-answers.yml` records the source, and a later `copier update` resolves it again.
Ask only when exploration found `~/templates/copier.yml`.

**Section C: Python floor.**
Package or application only: `python_floor`.
Recommend the oldest CPython that has not reached its end of life, or the existing `requires-python` when there is one.

**Section D: Framework.**
Only when exploration found framework signals: `framework`.
Ask once: `dagster`, `fastapi`, or none?
Recommend the one the signals name.

**Section E: Docs site.**
Package only: `docs`.
Recommend yes: the `docs` group, the `docs` job and the `site` and `pages` jobs.
On no, skip settings step 7.

**Section F: Repository settings.**
Only with a GitHub remote.
Ask whether to apply the settings now or write the files only.
Recommend now for a fresh repo.
For an existing repo, show the differences the exploration found and ask per difference.

### 3. Confirm the plan

Show one list: the `gh repo create` command if the repo is not on GitHub yet, the `copier copy` command with every `--data` answer, every file it will write, every existing file it will ask to overwrite, and every settings step that will run, in order, with the human steps marked.
Let the user edit the list before anything is written.

### 4. Write the files

A repo with no GitHub remote is created there first, with the README, license and `.gitignore` GitHub offers:

```sh
gh repo create <owner>/<repo> --public --clone --add-readme --license mit --gitignore Python
```

Ask the visibility and the license before running it.
Then, inside the clone, for a package or an application, `uv init` writes the project:

```sh
uv init --lib --python <floor>   # package
uv init --app --python <floor>   # application
```

Then the template, with every answer on the command line so nothing is asked twice:

```sh
uvx copier copy --trust --data repo=<repo> --data owner=<owner> --data language=<python|none> --data package=<package> --data python_floor=<floor> --data pypi=<bool> --data docs=<bool> --data framework=<name> gh:ozanozbeker/templates .
```

Copier writes none of the files GitHub or `uv init` wrote, and asks before overwriting any other file that exists.
`--trust` lets its tasks append to `.gitignore`, run `uv add` for the tools, and set the classifiers and `[project.urls]`; say so in the plan, since the tasks run code from the template.
Replace the `hello()` stub in `src/<package>/__init__.py` with a module docstring, and write `tests/test_<package>.py` with one test that imports the package.
For a package, add the badges from `github-style/SKILL.md` under the README's title.
Show `git status` and the diff of any overwritten file before going on.

Then:

```sh
uv sync
uv run prek install
uv run prek run --all-files
```

For a repo with no Python, `uvx prek install` and `uvx prek run --all-files`.
Done when every hook passes.

### 5. Apply the settings

Follow `settings.md` in its order for the tier.
Run each command and show its output.
At a step marked **human**, stop, say exactly what to do and where, and wait for the user to say it is done before going on.
Never ask for a secret's value in the chat: the user runs the `gh secret set` line themselves, or pastes the path to a file.

Done when every step for the tier has run or been explicitly skipped, and `gh api repos/$R/rulesets --jq '.[].name'` lists the rulesets the tier needs.

### 6. Done

Say what was written and which settings were applied, list the steps skipped and why, and name the first pull request to open.
For a package, that is the one ending with `Release-As: 0.0.1`.
