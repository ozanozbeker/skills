# Setting up a repo

A repo is set up when each core tool runs from the repo and has its config file there:

| Tool | Runs from | Config |
| --- | --- | --- |
| `prek` | the `dev` group in `pyproject.toml` | `prek.toml` |
| `ruff` | the `dev` group, through a local hook in `prek.toml` | `ruff.toml` |
| `ty` | the `dev` group, through a local hook in `prek.toml` | `ty.toml` |
| `pytest` | the `dev` group | `pytest.ini` |
| `rumdl` | a hook in `prek.toml` | `rumdl.toml` |
| `tombi` | a hook in `prek.toml` | `tombi.toml` |

A tool in the `dev` group runs under `uv run`, so every run uses the version `uv.lock` pins.
A local hook in `prek.toml` runs its tool with `uv run --frozen`, such as `entry = "uv run --frozen ruff check"`, because a plain `uv run` can relock and rewrite `uv.lock` in the middle of a commit.

What each config holds is the template's job: [ozanozbeker/templates](https://github.com/ozanozbeker/templates), a [Copier](https://copier.readthedocs.io/) template.
Its README lists the questions it asks and the files it writes, and each comment inside a file records the reason for a setting.
Read the template, not this page, for the content of a config.

## Check a repo

For each core tool, check that it runs from the repo and that its config file exists.
Done means you can name each tool that is missing, or its missing config.

## Start a bare repo from the template

A repo is bare when it has no `pyproject.toml`, or only the files `gh repo create` and `uv init` wrote.
Offer the template.
On a no, leave the repo as it is: the rules in `SKILL.md` still apply to the code.

1. **Read the template's README** for the questions Copier asks.
2. **Ask each question,** leading with the recommended answer so the user can accept it in a word, and skip one the repo already settles.
   With no GitHub remote, also ask the visibility and the license.
3. **Show the plan, and wait for a yes.**
   The plan lists the commands with every answer, each file they write, each existing file they overwrite, and that `--trust` runs the template's tasks.
4. **Run the commands.**

   ```sh
   gh repo create <owner>/<repo> --<visibility> --clone --add-readme --license <license> --gitignore Python
   cd <repo>
   uv init --lib --python <floor>   # or --app for an application
   uvx copier copy --trust --data <question>=<answer> gh:ozanozbeker/templates .
   ```

   Skip `gh repo create` when the repo is on GitHub already, and `uv init` when `pyproject.toml` exists.
   Pass every answer as its own `--data`, so Copier asks nothing twice.
   Both `uv init` forms give the `src/` layout (measured with uv 0.13.7), which keeps the tests importing the installed package and never the working tree.
   Never pass `--bare` or `--no-package`, which drop the layout and the build backend.
5. **Finish the project.**
   Replace the stub `uv init` wrote and write a first test, because pytest exits 5 with no test.
   Then `uv add` each runtime dependency, and run the hooks:

   ```sh
   uv sync
   uv run prek install
   uv run prek run --all-files
   ```

   Done means every hook passes.
6. **Apply the repository settings** with `github-style` when it is installed.
   Without it, say which settings are left.

## Add a missing tool to an existing repo

An existing repo gains a missing tool one change at a time, because the template copied over it would overwrite choices the repo made on purpose.

- With `.copier-answers.yml`, the repo came from the template: run `uvx copier update --trust`, and review the diff of every file it changes.
- Without it, propose each missing tool as its own change: add it to the `dev` group or `prek.toml`, and take its config file from the template.

A config the repo already has stays as the repo wrote it.
A config change waits for the user's yes, because a setting the repo departs from may be a decision, not a gap.
