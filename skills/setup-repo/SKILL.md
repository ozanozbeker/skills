---
compatibility: Requires the python-style and github-style skills, git, gh and uv.
description: Get a repo from any state to the python-style and github-style standard, asking the few questions that decide which files and settings it gets. Use only when the user asks to set up or scaffold a repo.
disable-model-invocation: true
name: setup-repo
---

# Set up a repo

Scaffold a repo to the standard that `python-style` ([ozanozbeker/skills](https://github.com/ozanozbeker/skills/tree/main/skills/python-style)) and `github-style` ([ozanozbeker/skills](https://github.com/ozanozbeker/skills/tree/main/skills/github-style)) describe: the files from the `templates` repo, a Copier template that `python-style`'s `setup.md` and `github-style`'s `workflows.md` map, and the repository settings from `github-style`'s `settings.md`.
This skill holds the questions and the order.
The three files hold the content, so load both skills and read each file before writing from it.
When either skill is missing, stop and tell the user to install it, because the content lives only there.

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
- `gh auth status`: logged in, and as whom?
- For an existing GitHub repo, the current settings: `gh api repos/$R --jq '{allow_squash_merge, allow_auto_merge, delete_branch_on_merge, security_and_analysis}'` and `gh api repos/$R/rulesets --jq '.[].name'`.

### 2. Present findings and ask

Summarise what exists and what is missing, then take the sections in order.
Lead each with the recommended answer so the user can accept it in a word.
Skip a section the exploration already settled.
Each section maps to a Copier question, named in bold.

**Section A: Tier.**
One of two, and everything else follows from it:

- **Package**: released to PyPI, with docs on Pages.
  `pypi: true`.
  Recommend when `pyproject.toml` has a `[build-system]` and no `[project.scripts]`, or the user says library.
- **Application**: Python with no release.
  `pypi: false`.
  Recommend when there is a `[project.scripts]` entry or framework signals.

**Section B: Python floor.**
`python_floor`.
Recommend the oldest CPython that has not reached its end of life, or the existing `requires-python` when there is one.

**Section C: Framework.**
Only when exploration found framework signals: `framework`.
Ask once: `dagster`, `fastapi`, or none?
Recommend the one the signals name.

**Section D: Docs site.**
Package only: `docs`.
Recommend yes: the `docs` group, the `docs` job and the `site` and `pages` jobs.
On no, skip settings step 7.

**Section E: Repository settings.**
Only with a GitHub remote.
Ask whether to apply the settings now or write the files only.
Recommend now for a fresh repo.
For an existing repo, show the differences the exploration found and ask per difference.

### 3. Confirm the plan

Show one list: the `gh repo create` command if the repo is not on GitHub yet, the `copier copy` command with every `--data` answer, every file it will write, every existing file it will ask to overwrite, and every settings step that will run, in order, with the human steps marked.
Let the user edit the list before anything is written.

### 4. Write the files

Three commands, in this order, from `python-style`'s `setup.md`, which holds what each one writes and what to do after.
The template always comes from `gh:ozanozbeker/templates` at its newest tag, and `.copier-answers.yml` records that source for a later `copier update`:

```sh
gh repo create <owner>/<repo> --public --clone --add-readme --license mit --gitignore Python   # skip when the repo is on GitHub already
uv init --lib --python <floor>   # or --app; skip when pyproject.toml exists
uvx copier copy --trust --data repo=<repo> --data owner=<owner> --data package=<package> --data python_floor=<floor> --data pypi=<bool> --data docs=<bool> --data framework=<name> gh:ozanozbeker/templates .
```

Ask the visibility and the license before the first.
Pass every answer as `--data` so nothing is asked twice, and say in the plan that `--trust` runs the template's tasks.
A repo with `.copier-answers.yml` runs `uvx copier update --trust` instead of the third.
Show `git status` and the diff of any overwritten file before going on.
Then follow the rest of `setup.md`: the stub, the first test, `uv sync`, `uv run prek install` and `uv run prek run --all-files`.
For a package, add the badges from `github-style`'s `SKILL.md` under the README's title.
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
