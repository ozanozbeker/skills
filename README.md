# ozanozbeker-skills

My custom skills, packaged as a Claude Code plugin.

They assume every project uses Python and `uv`.

## Install

### Claude Code plugin

Claude Code clones the repo as a marketplace, reads `.claude-plugin/marketplace.json`, and installs the plugin it lists.
Nothing is registered anywhere else.

```text
/plugin marketplace add ozanozbeker/skills
/plugin install ozanozbeker-skills@ozanozbeker
```

### npx skills

With [`npx skills`](https://github.com/vercel-labs/skills), which installs into any agent it supports:

```bash
npx skills add ozanozbeker/skills
```

## Update

A push does not reach an installed copy on its own.
In Claude Code:

```text
/plugin marketplace update ozanozbeker
/plugin update ozanozbeker-skills
/reload-plugins
```

With `npx skills`:

```bash
npx skills update
```

## Skills

- [writing-style](skills/writing-style/SKILL.md): prose a person reads, under ISO 24495-1 plain language, with the tidyverse reference pages as the model for a docs page.
  Docstrings, comments, docs, commit messages, pull request bodies and chat; a document an agent reads is `writing-for-agents`'s.
- [python-style](skills/python-style/SKILL.md): Python style, from TigerStyle.
  Safety, then performance, then developer experience, enforced by the repo's tools.
  It checks that a repo has the core tools and their configs, and offers the [templates](https://github.com/ozanozbeker/templates) Copier template for a bare repo.
- [dbt-style](skills/dbt-style/SKILL.md): dbt style, from the dbt Labs best-practice guides.
  Layers, naming, SQL, Jinja, YAML and materializations, with reference pages for incremental and near-real-time models, CI workflows, custom generic tests and Mesh planning; marts are Kimball star schemas, and the official `dbt` plugin's skills own the workflow.
- [kimball-style](skills/kimball-style/SKILL.md): dimensional modeling, from the Kimball Group's official techniques.
  Business process, grain, fact and dimension tables, keys and slowly changing dimensions, with reference pages for the hybrid SCD types and late rows, ragged hierarchies and bridge tables, the bus matrix and special-purpose patterns, for any warehouse and any tool.
- [github-style](skills/github-style/SKILL.md): everything that happens to a commit after `git push`.
  Pull requests, CI, Dependabot, release-please, PyPI and the docs site.

## External skills

These skills come from other authors.
My skills above work well combined with them.

### Workflow

- [mattpocock/skills](https://github.com/mattpocock/skills): engineering workflow skills.
  `writing-for-agents` owns any `CLAUDE.md`, `AGENTS.md` or skill; `tdd`, `diagnosing-bugs`, `grilling`, `code-review` and `domain-modeling` cover the rest.
- [github/awesome-copilot](https://github.com/github/awesome-copilot): `github-actions-hardening` and `github-actions-efficiency`.
- [vercel-labs/skills](https://github.com/vercel-labs/skills): `find-skills`, which searches for a skill that fits a task.
- [tt-a1i/archify](https://github.com/tt-a1i/archify): architecture, flow, sequence and ER diagrams as standalone HTML pages.

### Data

- [dbt-labs/dbt-agent-skills](https://github.com/dbt-labs/dbt-agent-skills): the official dbt Labs skills for running dbt, building models, tests, the Semantic Layer and Mesh.
  `dbt-style` covers only how the code looks.
- [polars-inc/skills](https://github.com/polars-inc/skills): idiomatic lazy Polars, the streaming engine and pandas migration.
- [quantco/dataframely](https://github.com/quantco/dataframely): schemas and validation for Polars data frames.
- [duckdb/duckdb-skills](https://github.com/duckdb/duckdb-skills): querying, reading and converting data files with DuckDB, including files on S3 and spatial data.
- [dagster-io/skills](https://github.com/dagster-io/skills): the `dg` CLI, assets, components and pipeline debugging.

### Notebooks and apps

- [marimo-team/skills](https://github.com/marimo-team/skills): writing marimo notebooks, converting Jupyter and Streamlit to marimo, and checking WebAssembly compatibility.
- [marimo-team/marimo-pair](https://github.com/marimo-team/marimo-pair): working in a live marimo notebook beside the user.
- [posit-dev/skills](https://github.com/posit-dev/skills): Quarto authoring, `brand.yml` and Shiny apps.

### Python tooling and docs

- [j178/prek](https://github.com/j178/prek): hooks with `prek`, the pre-commit replacement.
- [posit-dev/great-docs](https://github.com/posit-dev/great-docs): documentation sites for Python packages, with skills for the site config, docstrings and user guides.
