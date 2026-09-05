# GitHub Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `pablontiv/handbook` public while making `pablontiv` the only human contributor and merge actor, permitting Dependabot as the sole automated proposer, and enforcing the approved GitHub security posture.

**Architecture:** Version the Dependabot contract and test it locally first. Deliver that change through the repository's pull-request workflow. Only after merge, render canonical digest-bound manifests for staged GitHub mutations, verify every postcondition from fresh reads, observe CodeQL's real check identity, and then add that check to branch protection under a second approval.

**Tech Stack:** GitHub REST API through `gh`, GitHub repository settings UI for AI findings, Dependabot v2 YAML, Python 3.11+ standard library and PyYAML 6.0.3, `unittest`, Rootline, Git.

**Spec:** `.workspace/docs/superpowers/specs/2026-09-04-github-security-hardening-design.md`

## Global Constraints

- `pablontiv` is the only authorized human contributor and merge actor.
- Dependabot is the only approved non-human change proposer.
- The repository remains public and pull-request creation remains `collaborators_only`.
- Public cloning and forks remain possible; no claim may state otherwise.
- `main` must require PRs, the observed CI checks, signed commits, linear history, resolved conversations, admin enforcement, and no force-push or deletion.
- GitHub-required approval count is `0`; independent review remains a workspace gate.
- Only squash merge remains enabled.
- GitHub Actions permits GitHub-owned actions only, with full-SHA pinning and a read-only workflow token.
- Dependabot checks `pip` and `github-actions` at `/`, weekly, with separate version and security groups per ecosystem; both entries use `cooldown: { default-days: 7 }` to reduce exposure to newly published versions for version updates without delaying security updates.
- CodeQL uses default setup with the `extended` query suite.
- AI findings may be enabled; agentic fixes and AI Credit consumption are not authorized.
- Any live mutation requires an exact canonical manifest and SHA-256 approval.
- A failed live request stops the rollout; no retry or substitute mutation is authorized.
- Do not modify or stage the main checkout's existing untracked `.claude/` content.

---

### Task 1: Add the Dependabot contract through TDD

**Files:**

- Modify: `tests/test_handbook_contract.py:1-228`
- Create: `.github/dependabot.yml`

**Interfaces:**

- Consumes: `PyYAML==6.0.3` from `requirements-test.txt`; existing `ROOT` constant in `tests/test_handbook_contract.py`.
- Produces: `DEPENDABOT_PATH: Path`, `HandbookContractTests.dependabot: dict`, and a Dependabot v2 configuration covering exactly `pip` and `github-actions`.

- [ ] **Step 1: Add the failing contract test**

Add `import yaml`, define `DEPENDABOT_PATH = ROOT / ".github" / "dependabot.yml"`, load it in `setUpClass`, and add this method to `HandbookContractTests`:

```python
    def test_dependabot_updates_are_weekly_and_grouped(self) -> None:
        self.assertEqual(self.dependabot.get("version"), 2)
        updates = self.dependabot.get("updates")
        self.assertIsInstance(updates, list)
        assert isinstance(updates, list)
        self.assertEqual(
            {
                (update.get("package-ecosystem"), update.get("directory"))
                for update in updates
            },
            {("pip", "/"), ("github-actions", "/")},
        )
        self.assertEqual(len(updates), 2)
        for update in updates:
            ecosystem = update["package-ecosystem"]
            with self.subTest(ecosystem=ecosystem):
                self.assertEqual(update.get("schedule"), {"interval": "weekly"})
                self.assertEqual(update.get("cooldown"), {"default-days": 7})
                groups = update.get("groups")
                self.assertIsInstance(groups, dict)
                assert isinstance(groups, dict)
                self.assertEqual(
                    {group.get("applies-to") for group in groups.values()},
                    {"version-updates", "security-updates"},
                )
                for group in groups.values():
                    self.assertEqual(group.get("patterns"), ["*"])
```

Load the YAML with a mapping guard:

```python
        cls.dependabot = yaml.safe_load(DEPENDABOT_PATH.read_text(encoding="utf-8"))
        if not isinstance(cls.dependabot, dict):
            raise TypeError("dependabot.yml must contain a mapping")
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python3 -m unittest tests.test_handbook_contract.HandbookContractTests.test_dependabot_updates_are_weekly_and_grouped -v
```

Expected: `ERROR` with `FileNotFoundError` for `.github/dependabot.yml`.

- [ ] **Step 3: Create the minimal Dependabot configuration**

Create `.github/dependabot.yml` with these exact semantics:

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
    cooldown:
      default-days: 7
    groups:
      python-version-updates:
        applies-to: version-updates
        patterns:
          - "*"
      python-security-updates:
        applies-to: security-updates
        patterns:
          - "*"
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    cooldown:
      default-days: 7
    groups:
      actions-version-updates:
        applies-to: version-updates
        patterns:
          - "*"
      actions-security-updates:
        applies-to: security-updates
        patterns:
          - "*"
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
python3 -m unittest tests.test_handbook_contract.HandbookContractTests.test_dependabot_updates_are_weekly_and_grouped -v
```

Expected: one test passes.

- [ ] **Step 5: Run the handbook contract suite**

Run:

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

Expected: all handbook contract tests pass.

- [ ] **Step 6: Commit the independently reviewable change**

```bash
git add .github/dependabot.yml tests/test_handbook_contract.py
git commit -m "chore(deps): configure dependabot updates"
```

Expected: one commit containing only the Dependabot configuration and its contract test.

---

### Task 2: Verify and deliver the versioned configuration

**Files:**

- Verify: `.workspace/docs/adr/0026-endurecer-seguridad-repositorio-publico.md`
- Verify: `.workspace/docs/superpowers/specs/2026-09-04-github-security-hardening-design.md`
- Verify: `.workspace/docs/superpowers/plans/2026-09-04-github-security-hardening.md`
- Verify: `.github/dependabot.yml`
- Verify: `tests/test_handbook_contract.py`

**Interfaces:**

- Consumes: the accepted ADR, approved spec, Task 1 commit, repository CI commands, and branch `design/github-security-hardening`.
- Produces: a reviewed pull request against `main`; no merge without a separate human gate.

- [ ] **Step 1: Validate governed Markdown**

```bash
rootline validate .workspace/docs/adr/0026-endurecer-seguridad-repositorio-publico.md --strict -o json
rootline validate .workspace/docs/superpowers/specs/2026-09-04-github-security-hardening-design.md --strict -o json
rootline validate .workspace/docs/superpowers/plans/2026-09-04-github-security-hardening.md --strict -o json
rootline validate --all .workspace/docs/adr -o json
rootline validate --all .workspace/docs/superpowers -o json
rootline validate --all profiles/pablontiv -o json
```

Expected: every result is valid with zero errors.

- [ ] **Step 2: Run the complete repository suite**

Run exactly:

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
python3 -m unittest discover -s profiles/pablontiv/tests -t profiles/pablontiv -p "test_*.py" -v
python3 -m unittest discover -s skills/adr/tests -t skills/adr -p "test_*.py" -v
python3 -m unittest discover -s skills/evidence-driven-development/tests -t skills/evidence-driven-development -p "test_*.py" -v
python3 -m unittest discover -s skills/systemic-issue-triage/tests -t skills/systemic-issue-triage -p "test_*.py" -v
python3 -m unittest discover -s skills/context-save/tests -t skills/context-save -p "test_*.py" -v
python3 -m unittest discover -s skills/sweep/tests -t skills/sweep -p "test_*.py" -v
python3 -m unittest discover -s skills/model-optimizer/tests -t skills/model-optimizer -p "test_*.py" -v
sh skills/sweep/assets/test-assets.sh
(
  cd skills/remove-gentle-context
  python3 -m unittest discover -s tests -t . -v
  python3 -m py_compile scripts/cleanup.py
  python3 scripts/cleanup.py --help >/dev/null
)
```

Expected: every Python and shell test passes; compile and help exit zero.

- [ ] **Step 3: Inspect the exact delivery diff**

```bash
git diff --check main...HEAD
git status --short --branch
git log --oneline main..HEAD
git diff --stat main...HEAD
git diff main...HEAD -- .github/dependabot.yml tests/test_handbook_contract.py .workspace/docs
```

Expected: no unstaged files, no whitespace errors, and only approved paths appear.

- [ ] **Step 4: Request independent code review**

Use `superpowers:requesting-code-review` against `main...HEAD`. Resolve every blocking finding locally, rerun the affected tests and the complete suite, and commit corrections conventionally before proceeding.

- [ ] **Step 5: Render the push/PR payload and request authorization**

Present these exact external effects before executing them:

```text
push refs/heads/design/github-security-hardening to origin
create pull request:
  base: main
  head: design/github-security-hardening
  title: chore(security): harden public repository
  body: list ADR 0026, spec path, tests run, and unresolved governance conflicts
```

The approval authorizes only the push and PR creation. It does not authorize merge or repository settings changes.

- [ ] **Step 6: Push and open the pull request after approval**

```bash
git push -u origin design/github-security-hardening
gh pr create \
  --repo pablontiv/handbook \
  --base main \
  --head design/github-security-hardening \
  --title "chore(security): harden public repository" \
  --body-file /tmp/handbook-security-pr-body.md
```

The body file must list ADR 0026, the spec and plan paths, the complete verification commands, and any unresolved conflict. Expected: GitHub returns one PR URL.

- [ ] **Step 7: Verify PR checks and request merge authorization**

```bash
gh pr checks --repo pablontiv/handbook --watch "$(gh pr view --repo pablontiv/handbook --json number --jq .number)"
gh pr view --repo pablontiv/handbook --json number,url,state,isDraft,mergeStateStatus,statusCheckRollup
```

Expected: all checks pass and the PR is mergeable. Present the exact PR number and head SHA. Merge only after a separate human authorization for that exact pair.

- [ ] **Step 8: Merge only the approved PR and verify delivery**

```bash
pr_number="$(gh pr view --repo pablontiv/handbook --json number --jq .number)"
pr_head="$(gh pr view --repo pablontiv/handbook "$pr_number" --json headRefOid --jq .headRefOid)"
test "$pr_head" = "$(git rev-parse HEAD)"
gh pr merge --repo pablontiv/handbook "$pr_number" --squash --delete-branch
gh pr view --repo pablontiv/handbook "$pr_number" --json state,mergedAt,mergeCommit,url
```

Execute this block only when Step 7's approval names the same `pr_number` and `pr_head`. Expected: state `MERGED`, non-null `mergedAt`, and a merge commit.

---

### Task 3: Render the first live-mutation manifest

**Files:**

- Create temporarily: `/tmp/handbook-security-manifest-v1.json`
- Do not modify repository files.

**Interfaces:**

- Consumes: merged Task 2 revision, current GitHub repository state, the nine expected CI check names, and the freshly observed GitHub Actions app ID.
- Produces: canonical JSON bytes and their SHA-256 digest; no live mutation.

- [ ] **Step 1: Re-observe identity and write-capable actors**

Use GET-only commands:

```bash
gh repo view pablontiv/handbook --json nameWithOwner,visibility,viewerPermission,defaultBranchRef,owner
gh api repos/pablontiv/handbook/collaborators?affiliation=direct\&per_page=100
gh api repos/pablontiv/handbook/invitations?per_page=100
gh api repos/pablontiv/handbook/keys?per_page=100
gh api repos/pablontiv/handbook/hooks?per_page=100
gh api repos/pablontiv/handbook/rulesets?includes_parents=true\&per_page=100
gh api repos/pablontiv/handbook/branches/main/protection || true
gh api user/installations?per_page=100
```

Resolve installation access to this repository rather than assuming an account installation can write it:

```python
import json
import subprocess


def api(path: str) -> object:
    result = subprocess.run(
        ["gh", "api", path],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


installations = api("user/installations?per_page=100")
assert isinstance(installations, dict)
repo_apps = []
for installation in installations.get("installations", []):
    installation_id = installation["id"]
    repositories = api(
        f"user/installations/{installation_id}/repositories?per_page=100"
    )
    assert isinstance(repositories, dict)
    if any(
        repository.get("full_name") == "pablontiv/handbook"
        for repository in repositories.get("repositories", [])
    ):
        repo_apps.append(
            {
                "app_slug": installation.get("app_slug"),
                "permissions": installation.get("permissions"),
            }
        )
print(json.dumps(repo_apps, sort_keys=True))
```

Expected: `[]`. Stop if the repository is not public, the owner is not `pablontiv`, another human has access, an invitation/key/hook/app can write, or `main` changed after the approved merge.

- [ ] **Step 2: Re-observe and validate CI identities**

```bash
gh api repos/pablontiv/handbook/commits/main/check-runs?per_page=100 > /tmp/handbook-main-check-runs.json
python3 - <<'PY'
import json
from pathlib import Path
expected = {
    "test (macos-latest, 3.11)",
    "test (macos-latest, 3.14)",
    "test (macos-latest)",
    "test (ubuntu-latest, 3.11)",
    "test (ubuntu-latest, 3.14)",
    "test (ubuntu-latest)",
    "test (windows-latest, 3.11)",
    "test (windows-latest, 3.14)",
    "test (windows-latest)",
}
data = json.loads(Path("/tmp/handbook-main-check-runs.json").read_text())
runs = [run for run in data["check_runs"] if run["name"] in expected]
assert {run["name"] for run in runs} == expected
assert {run["conclusion"] for run in runs} == {"success"}
apps = {(run["app"]["id"], run["app"]["slug"]) for run in runs}
assert len(apps) == 1
app_id, slug = apps.pop()
assert slug == "github-actions"
print(app_id)
PY
```

Expected: the script prints one integer app ID and exits zero.

- [ ] **Step 3: Generate canonical manifest v1**

Build `/tmp/handbook-security-manifest-v1.json` with `json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"`. The operation list must contain, in this order:

1. `PATCH /repos/pablontiv/handbook` with public visibility, pull requests enabled and collaborator-only, squash-only merge, deleted merged branches, web commit signoff, secret scanning, push protection, non-provider patterns, and validity checks enabled.
2. `PUT /repos/pablontiv/handbook/vulnerability-alerts` with no body.
3. `PUT /repos/pablontiv/handbook/automated-security-fixes` with no body.
4. `PUT /repos/pablontiv/handbook/private-vulnerability-reporting` with no body.
5. `PUT /repos/pablontiv/handbook/actions/permissions` with `enabled: true`, `allowed_actions: selected`, and `sha_pinning_required: true`.
6. `PUT /repos/pablontiv/handbook/actions/permissions/selected-actions` with GitHub-owned actions allowed, verified actions disallowed, and an empty pattern allowlist.
7. `PUT /repos/pablontiv/handbook/actions/permissions/workflow` with read-only default permissions and workflow PR approvals disabled.
8. `PUT /repos/pablontiv/handbook/actions/permissions/fork-pr-contributor-approval` with `approval_policy: all_external_contributors`.
9. `PATCH /repos/pablontiv/handbook/code-scanning/default-setup` with `state: configured` and `query_suite: extended`.
10. `PUT /repos/pablontiv/handbook/branches/main/protection` with strict app-bound checks for the nine exact CI names, admin enforcement, required PR reviews with count `0`, linear history, conversation resolution, and force-push/deletion disabled.
11. `POST /repos/pablontiv/handbook/branches/main/protection/required_signatures` with no body.

The repository PATCH body is:

```json
{
  "allow_auto_merge": false,
  "allow_merge_commit": false,
  "allow_rebase_merge": false,
  "allow_squash_merge": true,
  "delete_branch_on_merge": true,
  "has_pull_requests": true,
  "pull_request_creation_policy": "collaborators_only",
  "security_and_analysis": {
    "secret_scanning": {"status": "enabled"},
    "secret_scanning_non_provider_patterns": {"status": "enabled"},
    "secret_scanning_push_protection": {"status": "enabled"},
    "secret_scanning_validity_checks": {"status": "enabled"}
  },
  "visibility": "public",
  "web_commit_signoff_required": true
}
```

The branch-protection body uses the dynamically observed `app_id` for every check:

```python
protection = {
    "required_status_checks": {
        "strict": True,
        "checks": [
            {"context": name, "app_id": app_id}
            for name in sorted(expected)
        ],
    },
    "enforce_admins": True,
    "required_pull_request_reviews": {
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": False,
        "required_approving_review_count": 0,
        "require_last_push_approval": False,
    },
    "restrictions": None,
    "required_linear_history": True,
    "allow_force_pushes": False,
    "allow_deletions": False,
    "block_creations": False,
    "required_conversation_resolution": True,
    "lock_branch": False,
    "allow_fork_syncing": False,
}
```

- [ ] **Step 4: Compute and present the approval digest**

```bash
shasum -a 256 /tmp/handbook-security-manifest-v1.json
git status --short --branch
```

Present the complete manifest bytes, digest, target repository, and non-transactional partial-application risk. Request approval for that exact digest. Do not execute Task 4 without it.

---

### Task 4: Apply manifest v1 and verify every postcondition

**Files:**

- Read temporarily: `/tmp/handbook-security-manifest-v1.json`
- Do not modify repository files.

**Interfaces:**

- Consumes: exact approved v1 digest and unchanged canonical manifest bytes.
- Produces: verified repository settings or a stopped failed rollout.

- [ ] **Step 1: Recheck manifest integrity and repository revision**

Recompute the digest and compare it byte-for-byte with the approved digest. Re-read `origin/main` through GitHub and stop if its SHA differs from the manifest precondition.

- [ ] **Step 2: Apply operations sequentially with no retry**

For each manifest operation, invoke `gh api` with the exact method, endpoint, and body. After each successful mutation, immediately GET the smallest corresponding resource and assert the requested state. Stop on the first non-zero exit or mismatched postcondition.

Do not use a shell loop that continues after failure. Preserve the operation index and sanitized response status in the execution report.

- [ ] **Step 3: Verify exclusive access and branch protection**

Re-run the actor inventory from Task 3 and assert:

- only `pablontiv` has direct collaborator access;
- invitations, deploy keys, write-capable user installations, and webhooks remain empty;
- visibility is public;
- pull-request creation is `collaborators_only`;
- only squash merge is enabled;
- `main` protection enforces the nine app-bound checks, PRs, admins, signatures, linear history, conversation resolution, and no force-push/deletion.

- [ ] **Step 4: Verify Actions and security features**

GET and assert:

```text
/repos/pablontiv/handbook/actions/permissions
/repos/pablontiv/handbook/actions/permissions/selected-actions
/repos/pablontiv/handbook/actions/permissions/workflow
/repos/pablontiv/handbook/actions/permissions/fork-pr-contributor-approval
/repos/pablontiv/handbook/vulnerability-alerts
/repos/pablontiv/handbook/automated-security-fixes
/repos/pablontiv/handbook/private-vulnerability-reporting
/repos/pablontiv/handbook/code-scanning/default-setup
/repos/pablontiv/handbook
```

Expected: every approved setting reports enabled or the exact requested value. A `404`, `422`, missing field, or mismatched value is `failed`, not success.

---

### Task 5: Observe CodeQL and render manifest v2

**Files:**

- Create temporarily: `/tmp/handbook-security-manifest-v2.json`
- Do not modify repository files.

**Interfaces:**

- Consumes: successful Task 4 verification and completed CodeQL check runs on current `main`.
- Produces: exact CodeQL gate and AI-findings UI action under a second SHA-256 approval.

- [ ] **Step 1: Wait conditionally for CodeQL completion**

Poll GET-only endpoints with a bounded 20-minute deadline and 30-second interval:

```text
/repos/pablontiv/handbook/code-scanning/default-setup
/repos/pablontiv/handbook/commits/main/check-runs?per_page=100
/repos/pablontiv/handbook/code-scanning/alerts?state=open&per_page=100
```

Stop with `failed` if setup reports failure, a CodeQL run concludes unsuccessfully, or the deadline expires. Do not add a merge gate while the check identity or successful behavior is unknown.

- [ ] **Step 2: Derive the exact CodeQL check identities**

Select completed successful check runs whose tool/app and displayed name identify CodeQL. Record each `{context, app_id, app_slug, conclusion}` and require at least one. Do not filter only by a guessed name.

- [ ] **Step 3: Generate canonical manifest v2**

The canonical operation list contains exactly:

1. `PATCH /repos/pablontiv/handbook/branches/main/protection/required_status_checks` preserving `strict: true`, the nine existing app-bound GitHub Actions checks, and adding every observed successful CodeQL check with its observed app ID.
2. A browser operation on `https://github.com/pablontiv/handbook/settings/security_analysis` setting `AI findings` from `Off` to `On`, with precondition `CodeQL default setup == configured` and postcondition that the UI rereads `AI findings` as `On`.

Serialize with sorted keys and compact separators, write a trailing newline, and compute:

```bash
shasum -a 256 /tmp/handbook-security-manifest-v2.json
```

Present the complete bytes and request approval for the exact digest. Do not execute Task 6 without it.

---

### Task 6: Apply manifest v2 and complete remote verification

**Files:**

- Read temporarily: `/tmp/handbook-security-manifest-v2.json`
- Do not modify repository files.

**Interfaces:**

- Consumes: exact approved v2 digest and unchanged repository revision/settings.
- Produces: final verified GitHub security posture.

- [ ] **Step 1: Recheck digest and preconditions**

Recompute the v2 SHA-256, verify `main` has not changed, verify v1 postconditions still hold, and verify CodeQL check identities still match the manifest. Stop on drift.

- [ ] **Step 2: Add CodeQL checks to branch protection**

Apply the exact required-status-checks PATCH and immediately GET the resource. Assert that its normalized check set equals the manifest set and `strict` remains true.

- [ ] **Step 3: Enable AI findings through the observed settings UI**

Use the authenticated browser session to navigate to Advanced Security, verify `AI findings` is `Off`, set it to `On`, and reread the page. Do not click Copilot Autofix or invoke an agentic fix.

- [ ] **Step 4: Run the final read-only audit**

Re-observe repository identity, visibility, collaborators, invitations, keys, hooks, installed apps, PR policy, merge policy, branch protection, signatures, Actions policy, dependency/security features, CodeQL status, AI findings, immutable releases, and current `main` SHA.

Report every spec acceptance criterion as `passed`, `failed`, `unknown`, or `not_applicable`, with the exact GET/UI evidence. Completion of the procedure is not evidence of success.

- [ ] **Step 5: Offer local cleanup**

After delivery and remote verification, show the clean worktree state and offer removal of `.workspace/worktrees/github-security-hardening` and its local branch. Do not delete either automatically.
