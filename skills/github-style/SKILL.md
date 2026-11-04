---
description: Everything that happens to a commit after `git push`. Use when opening or merging a pull request, setting up or fixing CI or Dependabot, changing repository settings, releasing a version, publishing to PyPI, or deploying the docs site.
name: github-style
---

# GitHub style

`python-style`, when installed, owns what happens on the machine: the code, the tools, and the hooks that run on `git commit`.
This skill owns what happens to the commit once it leaves: the pull request and CI, and for a repo that ships, the release, PyPI and the site.
The two meet at `prek.toml`, whose hooks CI runs on every file.

A package released to PyPI also follows [`releases.md`](releases.md): versions, the release flow, badges, and what fails.
[Tiers](#tiers) lists the files each kind of repo takes.

[`workflows.md`](workflows.md) maps the workflow files to the Copier answers in the `templates` repo that holds them, and [`settings.md`](settings.md) holds the repository settings and the rulesets.
Read the first when writing or changing a workflow, and the second when setting up a repo.

## The flow

```text
git push ─► pull request ─► all-green + title ─► squash merge ─► main
```

Every change reaches `main` through a pull request, the maintainer's included.
CI runs before the change lands.

## Rules for every repo

- **Every action is pinned to a full SHA**, with the version in a comment, and the repo setting `sha_pinning_required` enforces it.
  A tag can move; a SHA cannot.
- **`permissions: {}` at the top of every workflow**, and each job grants only what it uses.
  `actions/checkout` runs with `persist-credentials: false`, so no job holds a token it did not ask for.
- **Bot pull requests merge on their own.**
  A Dependabot or hook update already ran the full CI, and its `chore` or `ci` type starts no release, so a person adds nothing by clicking merge.
- **`GITHUB_TOKEN` cannot trigger a workflow.**
  A pull request it opens runs no CI, and a release it creates starts nothing.
  So a workflow whose pull request must run CI (`prek-update.yml`), or whose release must start another workflow (release-please), mints a token from a GitHub App, inside the `release` environment, which alone can read the key.
- **One required check.**
  `all-green` depends on every job and the `main` ruleset requires only it and `title`, so adding or renaming a job never touches the ruleset.
- **Squash merges only**, titled and described from the pull request, because the pull request title becomes the one commit message on `main`, and a repo that releases from its commits reads that message.
  A squash collapses the branch's commits into one commit on `main`, so local commits can stay rough and the pull request title is the one message that matters.
  A merge commit would keep them all in a graph, and a rebase would replay each one.
  The `title` check runs the same `commit-msg` hook that checks local commits, so one rule set covers both.
- **Local hooks miss a `--no-verify` commit and a fork's commits**, so the `lint` job runs every hook on every file, and `gitleaks-ci` on every commit the pull request adds.
- **A workflow holds no secret it does not need.**
  `uv lock` can run a package's build backend, so the `update` job of `prek-update.yml` runs without the App key, and only the pinned `pr` job sees it.

## Pull requests

```sh
git sync
git switch -c <branch>
git commit
gh ship
```

`git sync` and `gh ship` are aliases, which [`settings.md`](settings.md#once-per-machine) sets.

- `git sync` switches to `main`, pulls, and deletes each local branch whose remote branch is gone, which is every branch a squash merge finished with.
  Run it once a pull request merges and before starting a branch, so the local repo matches the remote.
- `gh ship` pushes the branch, opens the pull request, and turns auto-merge on.
- `git commit` runs the `pre-commit` and `commit-msg` hooks.
  A hook that fixes a file stops the commit, so run `git add -A` and commit again.
- `gh pr create --fill` copies the message of a single commit into the pull request.
  With several commits, pass `--title` yourself.
- `gh pr merge --auto --squash` runs before CI finishes.
  It turns auto-merge on, and GitHub merges the pull request the moment `all-green` and `title` pass, with no person involved.
  `gh pr checks --watch` shows the checks.
- Turn auto-merge on with the command, not the web form, because the form appears to save the squash title it shows (untested), so a later title fix may never reach the commit.
- The body carries `Closes #N` for the issue it resolves, and the merge closes the issue.

Pull requests from bots:

- Dependabot keeps one pull request per group open, such as `ci: bump the actions group`, and updates each as releases clear the cooldown.
- `prek-update.yml` keeps `chore: update prek hooks and uv.lock` open the same way.
- release-please, in a released package, opens `chore(main): release X.Y.Z` and updates it after each merge that users would see.

The first two start no release and merge on their own: `dependabot-auto-merge.yml` turns auto-merge on for each Dependabot pull request, and `prek-update.yml` does the same for its own.
A bot pull request that fails CI stays open, and the fix is a commit on `main` that the bot then rebases onto.
The release pull request waits until you want to release.

## Dependencies

Three kinds of dependency, three policies.

| Kind | Where | Policy |
| --- | --- | --- |
| Runtime library | `[project] dependencies` | A `>=` floor, as low as the `lowest` job proves. `uv.lock` holds the newest, and `test` runs it. A floor rises only in a `deps:` commit, which the changelog shows to users. |
| Dev tool | `[dependency-groups] dev` | A bare name. `uv.lock` pins it, and every update moves it to the latest release. |
| Action or hook | `uses:` SHA, `prek.toml` `rev` | A frozen SHA with the version beside it. Every update moves it to the latest release. |

Dependabot checks each ecosystem in `dependabot.yml` daily.
`cooldown` makes it wait 7 days after a release before taking it, so a release that gets yanked or hotfixed in its first week never reaches a pull request, and the daily check means the wait is 7 days, not up to 13.
`increase-if-necessary` moves `uv.lock` and leaves a `>=` floor alone unless the floor blocks the update.
The pull request runs the full CI, which is the test.
Dependabot's security updates ignore the cooldown and open on the day.

Dependabot does not read `prek.toml`, and its version updates move only the dependencies `pyproject.toml` declares, so `prek-update.yml` runs `prek update --freeze` daily with the same cooldown, and `uv lock --upgrade`.

Dependabot's `chore` and `ci` prefixes keep its pull requests out of the changelog.

## Python repos

- **CI tests the built wheel**, with `uv sync --locked --no-editable`, so a test that reads a package file checks what PyPI gets.
- **Every Python on Ubuntu, the floor and the newest on macOS and Windows.**
  An OS difference shows at the edges of the matrix, so the middle versions run once.
  The `exclude` list in `ci.yml` grows by one line per OS when a version joins.
- The `lowest` job resolves every runtime dependency to its floor and fails under 100% line coverage, so the floors stay true.
- pytest turns warnings into errors, so a new upstream deprecation fails the Dependabot pull request that brings it in, before the removal breaks the package.
- A package supports every CPython that has not reached its end of life.
  A version joins at its final release: add its classifier and its `test` matrix entry, and `next-python` stays on it until the next version reaches its first beta.
  A version leaves in the first release after its end of life, in a `feat!:` commit that raises `requires-python`, `.python-version` and `default_language_version` in `prek.toml`.

## Tiers

| Repo kind | Takes |
| --- | --- |
| Package released to PyPI | `pypi: true`: the six workflows, `dependabot.yml`, `release-please-config.json`, `.release-please-manifest.json`, steps 1 to 13 of `settings.md` |
| Application or pipeline with no release | `pypi: false`: `ci.yml` without the `docs` job, `pr-title.yml`, `dependabot.yml`, `dependabot-auto-merge.yml`, `prek-update.yml`, and steps 1 to 4 and 8 to 11 of `settings.md` |

## Not used, on purpose

- Codecov and other coverage services: `fail_under = 100` in the `lowest` job is a stricter guarantee with no token and no pull request comments.
- CODEOWNERS, a merge queue, a stale bot, a code of conduct: team and community tooling.
- harden-runner and OpenSSF Scorecard: a third-party action in every job; zizmor and CodeQL cover the workflows' threat model.
- Retrying a failed job: a flake is a bug.

## When something fails

- **A CI job fails.**
  `gh pr checks` names the job, and `gh run view <run-id> --log-failed` prints its log.
  Push a fix to the same branch, and auto-merge stays on.
- **The title check fails.**
  `gh pr edit --title`, and the check runs again.

## Traps

- zizmor skips its online audits without a token, so the `lint` job passes `GH_TOKEN`.
- gitleaks exits 0 when `git log` fails on a shallow clone, so `lint` checks that `HEAD^1` exists before `gitleaks-ci` runs.
