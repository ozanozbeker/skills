# Repository settings

Every setting a repo needs, in the order that works, with the command for each.
`R=<owner>/<repo>` throughout.
A step marked **human** needs a browser or a secret, so an agent stops there, says what to do, and waits.

| Tier | Steps |
| --- | --- |
| Package released to PyPI | 1 to 13 |
| Application or pipeline with no release | 1 to 4, 8 to 11 with a `main` ruleset that requires the checks its pull requests report |

## 1. Create the repo

```bash
gh repo create $R --public --source . --push
gh repo edit $R --description "<the README's first line>" --enable-wiki=false --enable-projects=false
```

The description is also the PyPI summary.

## 2. Open the first pull request

Rulesets come last, because a ruleset can require only a check that has already run.
So push the files, then open and merge one pull request so that `all-green` and `title` exist.

## 3. Install the release App (human)

A GitHub App of your own that release-please and `prek-update.yml` use for tokens.
Its permissions: Contents, Issues and Pull requests read and write, Metadata read, nothing else.
On the App's page: install it on the repo, then generate a private key, which downloads a `.pem`.

Check and record the ids the later steps use:

```bash
gh api user/installations --jq '.installations[] | select(.app_slug == "<app slug>") | {app_id, id}'
```

`app_id` is the `<app id>` in the `version tags` ruleset.

## 4. The `release` environment (human for the key)

```bash
gh api -X PUT repos/$R/environments/release --input - <<'EOF'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh api -X POST repos/$R/environments/release/deployment-branch-policies -f name=main -f type=branch
gh variable set APP_CLIENT_ID --env release --body "<the App's client id>"
gh secret set APP_PRIVATE_KEY --env release < <path to the .pem>
```

Only jobs in this environment read the key.
Delete the `.pem` after the upload, and never paste its contents into a chat.

## 5. The `pypi` environment

Tag policy `v*`, the owner as required reviewer, self-review allowed, admin bypass off.
Self-review stays allowed, because a release published by hand makes the maintainer its initiator.

```bash
OWNER_ID=$(gh api user --jq .id)
gh api -X PUT repos/$R/environments/pypi --input - <<EOF
{"wait_timer": 0, "prevent_self_review": false,
 "reviewers": [{"type": "User", "id": $OWNER_ID}],
 "can_admins_bypass": false,
 "deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh api -X POST repos/$R/environments/pypi/deployment-branch-policies -f name='v*' -f type=tag
gh api repos/$R/environments/pypi --jq '{can_admins_bypass, deployment_branch_policy}'
```

The REST docs omit `can_admins_bypass`, but the API accepts it.
If the `GET` still shows `true`, untick "Allow administrators to bypass configured protection rules" on the environment page.

## 6. PyPI trusted publisher (human)

PyPI has no API for this.
On pypi.org, under the account's publishing page, add a pending publisher: the owner, the repo, workflow `release.yml`, environment `pypi`.
Check that the environment field is filled in: the reviewer only binds if PyPI requires the environment.
A pending publisher does not reserve the name; only the first upload does.

## 7. Pages

```bash
gh api -X POST repos/$R/pages -f build_type=workflow
gh api -X PUT repos/$R/pages -F https_enforced=true
gh api -X PUT repos/$R/environments/github-pages --input - <<'EOF'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh api -X POST repos/$R/environments/github-pages/deployment-branch-policies -f name='v*' -f type=tag
gh repo edit $R --homepage "https://<owner>.github.io/<repo>/"
```

The first `POST` fails with 409 when Pages already exists; then run only the rest.

## 8. Merge settings

```bash
gh api -X PATCH repos/$R -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
  -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY \
  -F allow_auto_merge=true -F delete_branch_on_merge=true
```

## 9. Actions

```bash
gh api -X PUT repos/$R/actions/permissions -F enabled=true -f allowed_actions=all -F sha_pinning_required=true
gh api -X PUT repos/$R/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
```

## 10. Security

```bash
gh api -X PUT repos/$R/vulnerability-alerts
gh api -X PUT repos/$R/automated-security-fixes
gh api -X PUT repos/$R/private-vulnerability-reporting
gh api -X PATCH repos/$R --input - <<'EOF'
{"security_and_analysis": {"secret_scanning": {"status": "enabled"}, "secret_scanning_push_protection": {"status": "enabled"}}}
EOF
gh api -X PATCH repos/$R/code-scanning/default-setup -f state=configured -f query_suite=default \
  -f 'languages[]=actions' -f 'languages[]=python'
gh api repos/$R --jq .security_and_analysis
```

## 11. Rulesets

Both run only after step 2, and the second needs `<app id>` from step 3.

The `main` ruleset blocks every push to `main`, and a merge before `all-green` and `title` pass.
The admin can still merge a failing pull request with **Merge without waiting for requirements to be met**, so keep that for emergencies.
`actor_id: 5` with `RepositoryRole` is the admin role, and `integration_id: 15368` is GitHub Actions.

```bash
gh api -X POST repos/$R/rulesets --input - <<'EOF'
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"exclude": [], "include": ["~DEFAULT_BRANCH"]}},
  "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": false, "required_reviewers": [], "require_code_owner_review": false, "require_last_push_approval": false, "required_review_thread_resolution": false, "require_extra_approval_for_unattributed_changes": true, "allowed_merge_methods": ["squash"]}},
    {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": false, "do_not_enforce_on_create": false, "required_status_checks": [{"context": "all-green", "integration_id": 15368}, {"context": "title", "integration_id": 15368}]}}
  ]
}
EOF
```

A repo without `all-green` and `title` lists the checks its pull requests report instead.

The `version tags` ruleset lets only the App and the admin create, update or delete a `v*` tag.

```bash
gh api -X POST repos/$R/rulesets --input - <<'EOF'
{
  "name": "version tags",
  "target": "tag",
  "enforcement": "active",
  "conditions": {"ref_name": {"exclude": [], "include": ["refs/tags/v*"]}},
  "bypass_actors": [
    {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"},
    {"actor_id": <app id>, "actor_type": "Integration", "bypass_mode": "always"}
  ],
  "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}]
}
EOF
```

## 12. First release

A pull request whose description ends with `Release-As: 0.0.1`, then the release pull request that release-please opens, then the `pypi` approval on the `release.yml` run.
From the terminal, once the maintainer says approve:

```bash
RUN_ID=$(gh run list --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')
ENV_ID=$(gh api repos/$R/environments/pypi --jq .id)
gh api -X POST repos/$R/actions/runs/$RUN_ID/pending_deployments \
  -F "environment_ids[]=$ENV_ID" -f state=approved -f comment="Approved after reading the log."
```

Check one PEP 740 attestation per file on PyPI and the site over HTTPS.

## 13. Optional live environment

A `live` environment limited to `main`, no reviewer, holding the secrets a live test needs.
Keep no secret at repo level.
