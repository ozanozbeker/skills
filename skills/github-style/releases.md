# Released packages

What a package released to PyPI adds to `SKILL.md`.

```text
main ─► release-please PR ─► merge ─► tag + release
                                          │
          release.yml: build ─► pypi (approval) ─► site ─► pages
```

A person approves one thing only: the upload to PyPI.

## Versions

Versions follow SemVer.
Below 1.0, a new minor always means a breaking change.

| Commit | Changelog | Bump below 1.0 |
| --- | --- | --- |
| `feat`, `fix`, `perf`, `docs`, `deps`, `revert` | visible | patch |
| `refactor`, `test`, `build`, `ci`, `style`, `chore` | hidden | none on its own |
| any type with `!`, or a `BREAKING CHANGE:` footer | visible | minor |

`bump-minor-pre-major` and `bump-patch-for-minor-pre-major` in `release-please-config.json` set the last column.
No commit reaches 1.0 on its own: leaving `0.x` takes a `Release-As: 1.0.0` footer.

The pull request that makes a break also writes its migration into `user_guide/upgrading.qmd`, under the next minor's heading.
Every break before a release goes into the same next minor, so the heading is known when the pull request opens.

## Releasing

1. release-please keeps a release pull request open with the next version, `CHANGELOG.md` and `uv.lock`.
2. Merging it makes the App create the tag and the GitHub release.
3. `release.yml` builds the distributions, and its `pypi` job waits for approval.
   Before approving, read `git log <previous tag>..<new tag>`.
   The `main` ruleset requires no review, so this approval is the last check a person makes.
   On the run's page, click **Review deployments**, tick `pypi`, then **Approve and deploy**.
   The job uploads with PEP 740 attestations.
4. After the upload, `release.yml` builds the site and deploys it, so the site documents the version PyPI has.

A release published by hand starts the same workflow, which makes it the recovery path.

A release publishes only a tag that `main` contains.
The App can tag any commit, so `build` checks `git merge-base --is-ancestor` first.

## Badges

On one line under the title of the `README.md` that `gh repo create --add-readme` wrote:

```markdown
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/<repo>)](https://pypi.org/project/<repo>/) [![Python](https://img.shields.io/pypi/pyversions/<repo>)](https://pypi.org/project/<repo>/) [![License](https://img.shields.io/pypi/l/<repo>)](LICENSE)
```

One line, because rumdl's sentence-per-line reflow joins them anyway.

The PyPI badges read the package's metadata, so they need no updating.

## A new package's first release

The template writes `.release-please-manifest.json` as `{".": "0.0.0"}`.
Set `bootstrap-sha` in `release-please-config.json` to the commit before the one that adds release-please, and end the first pull request with a `Release-As: 0.0.1` footer.

## Changelog entries and breaking changes

- To correct a merged entry, edit the merged pull request's description.
  Put the corrected message between `BEGIN_COMMIT_OVERRIDE` and `END_COMMIT_OVERRIDE`, and release-please uses it on its next run.
- A breaking change ends the description with a one-line `BREAKING CHANGE:` footer that links to its section of the upgrade page.

## When something fails

- **A changelog entry is wrong after the merge.**
  `BEGIN_COMMIT_OVERRIDE`, as above.
- **`release.yml` fails after the tag exists.**
  `gh run rerun <run-id> --failed`.
  The `pypi` job sets `skip-existing`, so a rerun after a partial upload skips the files PyPI already has.
- **`build` fails the ancestor check.**
  The tag points at a commit that `main` does not contain, so nothing was published.

## Traps

- Never pass `release-type` to `release-please-action`.
  The action then ignores `release-please-config.json` and prints no warning.
- The `uv.lock` JSONPath in `release-please-config.json` reads `@.name.value`, not `@.name`. release-please parses each TOML value into an object, and without `.value` it updates nothing.
- An edit to the release pull request's body is lost when `main` moves before the merge, and it never reaches `CHANGELOG.md`.
  Migration notes go in the upgrade page.
- The `pypi` and `github-pages` environments accept `v*` tags only, and `release.yml` runs on the release's tag.
