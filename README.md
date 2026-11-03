# ozanozbeker-skills

My custom skills, packaged as a Claude Code plugin.

## Install

From GitHub, in one step:

```text
/plugin install ozanozbeker-skills --marketplace ozanozbeker/skills
```

Or in two steps, which also works for a local checkout by passing its path in place of `ozanozbeker/skills`:

```text
/plugin marketplace add ozanozbeker/skills
/plugin install ozanozbeker-skills@ozanozbeker
```

Claude Code clones the repo as a marketplace, reads `.claude-plugin/marketplace.json`, and installs the plugin it lists.
Nothing is registered anywhere else.

## Update

A push does not reach the installed copy on its own:

```text
/plugin marketplace update ozanozbeker
/plugin update ozanozbeker-skills
/reload-plugins
```

## Skills

- [python-style](skills/python-style/SKILL.md): Python style, from TigerStyle.
  Safety, then performance, then developer experience, enforced by the repo's tools.
- [github-style](skills/github-style/SKILL.md): everything that happens to a commit after `git push`.
  Pull requests, CI, Dependabot, release-please, PyPI and the docs site.
- [setup-repo](skills/setup-repo/SKILL.md): `/setup-repo` gets a repo from any state to both standards, asking only what decides the files and settings; the files come from the [templates](https://github.com/ozanozbeker/templates) Copier template.
