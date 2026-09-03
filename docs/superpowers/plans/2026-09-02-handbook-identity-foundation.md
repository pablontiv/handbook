# Handbook Identity Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the repository as a portable working handbook with a verified README, synchronized agent guidance, and a separately authorized post-merge GitHub rename.

**Architecture:** The repository root is the handbook; `README.md` is its outcome-led entry and `AGENTS.md` is its executable contributor contract. A standard-library test derives the published skill inventory from the filesystem, validates relative links and exact identity copy, and runs in the existing three-OS CI matrix. The public rename is a separate post-merge live operation and the local checkout path remains unchanged.

**Tech Stack:** Markdown, Python 3.11+ standard library `unittest`, GitHub Actions, Rootline v2, Git, GitHub CLI.

**Spec:** `docs/superpowers/specs/2026-09-02-handbook-identity-design.md`

## Global Constraints

- The approved hero is exactly: `Un handbook para convertir el trabajo de desarrollo improvisado en un método reproducible, verificable y adaptable.`
- The approved support line is exactly: `Reúne reglas, skills, herramientas y memoria para orientar el trabajo de personas y agentes.`
- Brands and agent runtimes are consumers or optional integrations, never the category.
- Do not claim that the `.workspace/` method, complete context, or end-to-end lifecycle exists.
- Do not create empty top-level artifact categories.
- Keep every skill self-contained under `skills/<name>/`; no sibling-skill dependencies.
- Do not edit existing ADR bodies, archived specs, plans, completed records, skill implementations, output-style content, or `LICENSE`.
- Keep `/Users/Shared/harness/skills` as the local checkout path.
- Do not mutate GitHub until the documentation PR is merged, the real repository is re-observed read-only, and the owner explicitly authorizes the exact live payload.
- Preserve unrelated work in the main checkout.

---

### Task 1: Add the failing handbook documentation contract

**Files:**
- Create: `tests/test_handbook_contract.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: repository tree, `README.md`, and `AGENTS.md` as UTF-8 text.
- Produces: `HandbookContractTests`, executed with `python -m unittest discover -s tests -p "test_*.py" -v`.

- [ ] **Step 1: Create the contract test**

Create `tests/test_handbook_contract.py` with this content:

```python
from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
AGENTS_PATH = ROOT / "AGENTS.md"
HERO = (
    "Un handbook para convertir el trabajo de desarrollo improvisado en un "
    "método reproducible, verificable y adaptable."
)
SUPPORT = (
    "Reúne reglas, skills, herramientas y memoria para orientar el trabajo "
    "de personas y agentes."
)
APPROVED_IDENTITY_BLOCK = f"# Handbook\n\n{HERO}\n\n{SUPPORT}"
REMOVE_GENTLE_CONTEXT_LINK = "[`skills/remove-gentle-context/`](skills/remove-gentle-context/)"
LINK_PATTERN = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
REQUIRED_AGENT_CLAUSES = (
    "portable working handbook",
    "Every top-level artifact family must be globally useful, portable, publicly distributable, and explicitly owned.",
    "Give each artifact one explicit owner and keep its runtime dependencies with it.",
    "Add a top-level artifact family only when real content exists; do not scaffold empty categories.",
    "Document how each new family contributes to the handbook, how it is verified, and where its portability boundary lies.",
    "Treat agent runtimes and external tools as integrations, not as the handbook's category.",
    "Keep every skill self-contained under `skills/<name>/` and avoid dependencies between sibling skills.",
    "Treat inventory and planning as read-only operations.",
    "Require explicit, digest-bound approval before destructive actions.",
    "Support macOS, Linux, and Windows without hard-coded user paths.",
    "Prefer the Python standard library for helpers.",
    "Before implementation, identify and review the accepted ADR that governs the change.",
    "Validate each new or modified ADR with `rootline validate docs/adr/<record>.md --strict`.",
    "Keep documentation synchronized with executable behavior.",
    "Run the complete test suite before committing.",
    "Integrate changes through pull requests.",
)


class HandbookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README_PATH.read_text(encoding="utf-8")
        cls.agents = AGENTS_PATH.read_text(encoding="utf-8")

    def assert_readme_leads_with_approved_identity(self, text: str) -> None:
        self.assertTrue(
            text.startswith(APPROVED_IDENTITY_BLOCK),
            "README must begin with the approved Handbook identity before category, vendor, or runtime branding.",
        )

    def assert_agents_contract(self, text: str) -> None:
        for clause in REQUIRED_AGENT_CLAUSES:
            self.assertIn(clause, text)
        self.assertNotIn(
            "This repository publishes independent, portable Agent Skills.",
            text,
        )

    def assert_remove_gentle_context_portability(self, text: str) -> None:
        bullet = next(
            (
                line
                for line in text.splitlines()
                if line.startswith(f"- {REMOVE_GENTLE_CONTEXT_LINK}")
            ),
            "",
        )
        self.assertTrue(bullet, "README must expose the exact remove-gentle-context discovery link.")
        self.assertIn("Python 3.11+ executable", bullet)
        self.assertIn("`python`", bullet)
        self.assertIn("`python3`", bullet)
        self.assertIn("equivalent", bullet)
        self.assertNotIn("with `python3`", bullet)

    def test_readme_leads_with_approved_identity(self) -> None:
        self.assert_readme_leads_with_approved_identity(self.readme)

    def test_readme_rejects_prepended_category_or_vendor_branding(self) -> None:
        for branding in (
            "# Agent Skills\n\nPublic collection of portable Agent Skills.\n\n",
            "# Pi Handbook\n\nVendor-specific agent runtime guidance.\n\n",
        ):
            with self.subTest(branding=branding.splitlines()[0]):
                with self.assertRaises(AssertionError):
                    self.assert_readme_leads_with_approved_identity(
                        f"{branding}{APPROVED_IDENTITY_BLOCK}\n"
                    )

    def test_every_published_skill_is_linked(self) -> None:
        skills = sorted(
            path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")
        )
        self.assertTrue(skills)
        for name in skills:
            with self.subTest(skill=name):
                self.assertIn(f"(skills/{name}/)", self.readme)

    def test_existing_artifact_families_are_linked(self) -> None:
        for target in (
            "AGENTS.md",
            "skills/",
            "output-styles/",
            "docs/adr/",
            "docs/superpowers/",
        ):
            with self.subTest(target=target):
                self.assertIn(f"({target})", self.readme)

    def test_relative_markdown_links_resolve(self) -> None:
        for raw_target in LINK_PATTERN.findall(self.readme):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith("#"):
                continue
            relative = unquote(parsed.path)
            with self.subTest(target=target):
                self.assertTrue((ROOT / relative).exists(), target)

    def test_stale_identity_claims_are_absent(self) -> None:
        stale = (
            "Public collection of portable Agent Skills",
            "https://github.com/pablontiv/gentle-ai",
            "Pull requests are disabled",
            "## Planned skills",
        )
        for claim in stale:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, self.readme)

    def test_agent_contract_uses_handbook_identity(self) -> None:
        self.assert_agents_contract(self.agents)

    def test_agent_contract_rejects_removal_of_required_clauses(self) -> None:
        for clause in REQUIRED_AGENT_CLAUSES:
            with self.subTest(clause=clause):
                mutated = self.agents.replace(clause, "", 1)
                with self.assertRaises(AssertionError):
                    self.assert_agents_contract(mutated)

    def test_remove_gentle_context_readme_discovery_is_portable(self) -> None:
        self.assert_remove_gentle_context_portability(self.readme)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the contract and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tests -p 'test_*.py' -v
```

Expected on the original pre-implementation baseline with this strengthened contract: 9 tests run, with failures naming the old README title/identity, missing `systemic-issue-triage`, absent top-level links, stale claims, old AGENTS purpose, and the hard-coded remove-gentle-context Python invocation. Link resolution and negative mutation probes may already pass.

- [ ] **Step 3: Add the test to the existing OS matrix**

Insert this step in `.github/workflows/ci.yml` immediately after `actions/setup-python` and before skill-specific tests:

```yaml
      - name: Run handbook documentation contract
        run: >-
          python -m unittest discover
          -s tests
          -p "test_*.py"
          -v
```

- [ ] **Step 4: Re-run RED through the CI command**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tests -p 'test_*.py' -v
```

Expected: the same contract failures remain; adding CI wiring does not make the behavior pass.

- [ ] **Step 5: Commit the executable acceptance boundary**

```bash
git add tests/test_handbook_contract.py .github/workflows/ci.yml
git commit -m "test(handbook): enforce repository identity"
```

---

### Task 2: Replace the skills catalog opening with the handbook entry

**Files:**
- Modify: `README.md`
- Test: `tests/test_handbook_contract.py`

**Interfaces:**
- Consumes: exact `HERO`, `SUPPORT`, and filesystem-derived skill names from Task 1.
- Produces: the root handbook navigation contract and relative links consumed by readers and the test suite.

- [ ] **Step 1: Replace README with the approved hierarchy**

Write `README.md` with this content:

```markdown
# Handbook

Un handbook para convertir el trabajo de desarrollo improvisado en un método reproducible, verificable y adaptable.

Reúne reglas, skills, herramientas y memoria para orientar el trabajo de personas y agentes.

## What exists today

This repository is the handbook itself. Its current, versioned building blocks are:

- repository-wide operating rules in [`AGENTS.md`](AGENTS.md);
- portable agent workflows under [`skills/`](skills/);
- deterministic helpers, assets, references, fixtures, and tests bundled with their owning skills;
- cross-session memory guidance in [`context-save`](skills/context-save/);
- interaction contracts under [`output-styles/`](output-styles/);
- architecture decisions in [`docs/adr/`](docs/adr/) and design history in [`docs/superpowers/`](docs/superpowers/).

The integrated workspace method, workspace controller, and end-to-end delivery lifecycle are outside the current repository contract.

## Core model

The handbook organizes portable working artifacts around development needs rather than one agent runtime.

- **Rules** define repository-wide invariants and contribution boundaries.
- **Skills** provide self-contained workflows that agents can discover and follow.
- **Tools** provide deterministic evidence or guarded execution inside the artifact that owns them.
- **Memory** preserves context and decisions across sessions.
- **Records** preserve architecture and design history without rewriting past decisions.

Every published artifact must be globally useful, portable, publicly distributable, and explicitly owned. Product-coupled and repository-local workflows stay with their owning product or repository.

## Capabilities

### Make and preserve decisions

- [`adr`](skills/adr/) records, accepts, and supersedes architecture decisions through Rootline-governed records.
- [`decision-calibrator`](skills/decision-calibrator/) focuses rigor after corrections, context loss, stalled research, or high-operating-cost choices.

### Keep continuity across sessions

- [`context-save`](skills/context-save/) saves, restores, and lists structured session state with Rootline validation.

### Inspect repositories and portfolios

- [`systemic-issue-triage`](skills/systemic-issue-triage/) classifies a repository's issue backlog by verified systemic root causes and stops before design or delivery.
- [`sweep`](skills/sweep/) inventories and classifies stale worktrees, branches, and pull requests before any separately approved mutation.

### Optimize agent configuration with evidence

- [`model-optimizer`](skills/model-optimizer/) evaluates Pi and OpenCode model assignments with runtime-local evidence and explicit approval before native configuration edits.

### Remove active generated context safely

- [`skills/remove-gentle-context/`](skills/remove-gentle-context/) inventories, plans, applies, verifies, and restores supported Gentle AI context through digest-bound authority and verified backups. See its [`SKILL.md`](skills/remove-gentle-context/SKILL.md). Use a Python 3.11+ executable as `python`, `python3`, or an equivalent platform command.

### Shape agent interaction

- [`mentor-telemetria`](output-styles/mentor-telemetria.md) defines operating modes, decision telemetry, root-cause reporting, and post-task learning.

## Optional integrations

Individual artifacts may integrate with Pi, Claude Code, OpenCode, GitHub CLI, Rootline, Backscroll, or other tools. Those integrations are capability-specific; the linked artifact is the authority for supported runtimes, dependencies, and safety gates.

## References

- To use a skill capability, open its linked skill directory and read `SKILL.md`; for interaction style, open the linked output-style document.
- To contribute, follow [`AGENTS.md`](AGENTS.md).
- To understand current decisions, browse [`docs/adr/`](docs/adr/).
- To inspect approved designs and implementation history, browse [`docs/superpowers/`](docs/superpowers/).
- Repository content is available under the [`MIT License`](LICENSE), except where an artifact bundles and declares a different license.
```

- [ ] **Step 2: Run the contract and isolate remaining failures**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tests -p 'test_*.py' -v
```

Expected: README tests pass, including the positional identity and remove-gentle-context portability probes. `test_agent_contract_uses_handbook_identity` still fails because `AGENTS.md` retains the old purpose.

- [ ] **Step 3: Run the README ghost and quantifier probes**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
import re

root = Path('.')
readme = (root / 'README.md').read_text(encoding='utf-8')
skills = sorted(path.parent.name for path in (root / 'skills').glob('*/SKILL.md'))
missing = [name for name in skills if f'(skills/{name}/)' not in readme]
print({'skills': skills, 'missing': missing})
for number, line in enumerate(readme.splitlines(), 1):
    if re.search(r'\b(all|always|never|every|only|none|no)\b', line, re.I):
        print(f'{number}: {line}')
PY
```

Expected: `missing` is empty. Review every printed quantified claim against the repository tree or narrow it before proceeding.

- [ ] **Step 4: Commit the handbook entry**

```bash
git add README.md
git commit -m "docs(handbook): add outcome-led entry"
```

---

### Task 3: Synchronize the executable contributor contract

**Files:**
- Modify: `AGENTS.md`
- Test: `tests/test_handbook_contract.py`

**Interfaces:**
- Consumes: ADR 0022 inclusion boundaries and the existing safety, portability, and delivery rules.
- Produces: repository guidance that permits multiple portable artifact families while retaining skill self-containment.

- [ ] **Step 1: Replace the Purpose section**

Replace the current `## Purpose` section with:

```markdown
## Purpose

This repository publishes a portable working handbook: rules, Agent Skills, deterministic tools, memory workflows, output styles, and governed documentation that help people and agents replace ad hoc development with repeatable, verifiable, adaptable practice.

Every top-level artifact family must be globally useful, portable, publicly distributable, and explicitly owned. Product-coupled and repository-local artifacts stay with their owning product or repository. Keep every skill self-contained under `skills/<name>/` and avoid dependencies between sibling skills.

## Artifact boundaries

- Give each artifact one explicit owner and keep its runtime dependencies with it.
- Add a top-level artifact family only when real content exists; do not scaffold empty categories.
- Document how each new family contributes to the handbook, how it is verified, and where its portability boundary lies.
- Treat agent runtimes and external tools as integrations, not as the handbook's category.
- Preserve historical ADRs, specs, plans, and completed records; supersede decisions instead of rewriting them.
```

Keep the existing `## Safety`, `## Portability`, and `## Delivery` sections byte-for-byte unchanged.

- [ ] **Step 2: Run the handbook contract and verify GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tests -p 'test_*.py' -v
```

Expected: 9 tests pass, 0 failures.

- [ ] **Step 3: Verify the preserved AGENTS sections**

Run:

```bash
git diff --word-diff=porcelain origin/main -- AGENTS.md
```

Expected: changes are confined to the old Purpose span plus the new Artifact boundaries section; Safety, Portability, and Delivery have no changed lines.

- [ ] **Step 4: Commit the synchronized contract**

```bash
git add AGENTS.md
git commit -m "docs(handbook): broaden artifact guidance"
```

---

### Task 4: Run complete local acceptance and review

**Files:**
- Verify: `README.md`
- Verify: `AGENTS.md`
- Verify: `tests/test_handbook_contract.py`
- Verify: `.github/workflows/ci.yml`
- Verify: `docs/adr/0016-gobernar-propiedad-y-distribucion-de-skills-globales.md`
- Verify: `docs/adr/0022-ampliar-repositorio-a-handbook-de-trabajo.md`

**Interfaces:**
- Consumes: all local deliverables from Tasks 1–3.
- Produces: reviewable evidence for pull-request delivery; no new runtime interface.

- [ ] **Step 1: Validate governance records strictly**

```bash
rootline validate \
  docs/adr/0016-gobernar-propiedad-y-distribucion-de-skills-globales.md \
  --strict
rootline validate \
  docs/adr/0022-ampliar-repositorio-a-handbook-de-trabajo.md \
  --strict
```

Expected: both records valid with zero errors and zero warnings.

- [ ] **Step 2: Run all Python contract and skill suites**

```bash
set -e
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover \
  -s skills/systemic-issue-triage/tests \
  -t skills/systemic-issue-triage -p 'test_*.py' -v
python3 -m unittest discover \
  -s skills/context-save/tests \
  -t skills/context-save -p 'test_*.py' -v
python3 -m unittest discover \
  -s skills/sweep/tests \
  -t skills/sweep -p 'test_*.py' -v
(
  cd skills/remove-gentle-context
  python3 -m unittest discover -s tests -t . -v
)
python3 -m unittest discover \
  -s skills/model-optimizer/tests \
  -t skills/model-optimizer -p 'test_*.py' -v
```

Expected: 530 Python tests pass: 9 handbook + 521 existing baseline tests.

- [ ] **Step 3: Run portable shell checks**

```bash
sh skills/sweep/assets/test-assets.sh
```

Expected: 5 passed, 0 failed.

- [ ] **Step 4: Run diagnostics before any build or delivery claim**

Use Pi diagnostics on the changed source/test surfaces:

```text
lsp_diagnostics(paths=["tests/test_handbook_contract.py"], serverScope="primary")
lens_diagnostics(mode="all", paths=["README.md", "AGENTS.md", ".github/workflows/ci.yml", "tests/test_handbook_contract.py", "docs/adr/0016-gobernar-propiedad-y-distribucion-de-skills-globales.md", "docs/adr/0022-ampliar-repositorio-a-handbook-de-trabajo.md"])
```

Expected: no blocking errors.

- [ ] **Step 5: Verify diff scope and historical integrity**

```bash
git diff --check origin/main...HEAD
git diff --name-status origin/main...HEAD
git diff origin/main...HEAD -- \
  docs/adr/0016-gobernar-propiedad-y-distribucion-de-skills-globales.md
```

Expected: only approved surfaces are changed; ADR 0016 has status metadata changes only.

- [ ] **Step 6: Request independent code review**

Invoke `superpowers:requesting-code-review` against the complete branch diff. Require the reviewer to check spec coverage, claim-versus-behavior truth, test quality, historical integrity, and external-mutation gating.

Expected: no unresolved high- or medium-severity findings before pull-request preparation.

---

### Task 5: Prepare and open the pull request

**Files:**
- No repository content changes expected.

**Interfaces:**
- Consumes: green local verification and independent review from Task 4.
- Produces: a pull request targeting `main`; does not rename the repository.

- [ ] **Step 1: Confirm branch and remote state**

```bash
git status --short --branch
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
gh repo view pablontiv/skills \
  --json name,url,defaultBranchRef,description
```

Expected: clean `docs/handbook-identity` branch, only planned commits, GitHub repository still named `skills`, default branch `main`.

- [ ] **Step 2: Push the feature branch**

```bash
git push -u origin docs/handbook-identity
```

Expected: remote branch created without changing `main`.

- [ ] **Step 3: Present the exact PR payload for human approval**

Use this title:

```text
docs(handbook): establish repository identity
```

Use a PR body containing:

```markdown
## Summary

- Reframes the repository as a portable working handbook.
- Organizes current rules, skills, tools, memory, output styles, and records by development need.
- Adds a cross-platform documentation contract to prevent identity and inventory drift.

## Verification

- Handbook contract: 9 tests
- Existing Python suites: 521 tests
- Sweep asset checks: 5 checks
- Rootline strict validation: ADR 0016 and ADR 0022
- Primary Python LSP clean; no branch-introduced blocking diagnostics. Pre-existing unpinned GitHub Actions findings are disclosed as inherited debt.

## Governance

- Reviewed: ADR 0014, ADR 0016
- Created and accepted: ADR 0022
- Modified: ADR 0016 status metadata only
- Governing spec: `docs/superpowers/specs/2026-09-02-handbook-identity-design.md`
- Known conflict: the active Waywarden branch must renumber its divergent ADR 0019/0020 records and reconcile its ADR 0016 supersession when rebased.

## Scope boundary

This PR does not implement the proposed `.workspace/` method, rename the local checkout directory, or mutate the GitHub repository name. The public rename remains a separate post-merge, explicitly authorized operation.
```

Stop and obtain explicit approval before opening the PR.

- [ ] **Step 4: Open the approved pull request**

```bash
gh pr create \
  --repo pablontiv/skills \
  --base main \
  --head docs/handbook-identity \
  --title 'docs(handbook): establish repository identity' \
  --body-file /tmp/handbook-pr-body.md
```

Expected: one open PR URL targeting `main`.

- [ ] **Step 5: Verify PR checks and report without merging**

```bash
gh pr view --repo pablontiv/skills --json number,url,state,mergeStateStatus,reviewDecision

gh pr checks --repo pablontiv/skills
```

Expected: report exact check states. Do not merge without a separate integration decision under `superpowers:finishing-a-development-branch`.

---

### Task 6: Rename the public repository after merge

**Files:**
- Mutate after verified rename: local Git configuration for `origin` only.
- Do not rename: `/Users/Shared/harness/skills`.

**Interfaces:**
- Consumes: merged identity commit on GitHub `main` and explicit digest-like approval of the displayed live mutation payload.
- Produces: public repository `pablontiv/handbook`, synchronized description, and verified local `origin` URL.

- [ ] **Step 1: Re-observe the live repository read-only**

```bash
gh repo view pablontiv/skills \
  --json name,url,description,defaultBranchRef,isPrivate

pr_number=$(gh pr list --repo pablontiv/skills \
  --head docs/handbook-identity --state merged \
  --json number --jq '.[0].number')
test -n "$pr_number"
gh pr view "$pr_number" --repo pablontiv/skills \
  --json state,mergedAt,mergeCommit,url

git ls-remote https://github.com/pablontiv/skills.git HEAD refs/heads/main
```

Expected: repository name `skills`, default branch `main`, the feature branch resolves to one merged pull request with state `MERGED`, and remote refs remain reachable.

- [ ] **Step 2: Present the exact live mutation payload and stop**

Present these commands and the observed repository identity:

```bash
gh repo rename -R pablontiv/skills handbook -y
gh repo edit pablontiv/handbook \
  --description 'Un handbook para convertir el trabajo de desarrollo improvisado en un método reproducible, verificable y adaptable.'
git remote set-url origin https://github.com/pablontiv/handbook.git
```

Require explicit authorization that binds to the observed old URL, target name, exact description, and local remote update. Do not infer authorization from approval of the spec, plan, PR, or merge.

- [ ] **Step 3: Apply only the authorized GitHub rename**

```bash
gh repo rename -R pablontiv/skills handbook -y
```

Expected: exit 0. Any failure requires renewed read-only observation, a reproduced local acceptance case where applicable, independent review, and renewed user authorization before retrying.

- [ ] **Step 4: Verify the renamed remote before further mutation**

```bash
gh repo view pablontiv/handbook \
  --json name,url,description,defaultBranchRef,isPrivate

git ls-remote https://github.com/pablontiv/handbook.git HEAD refs/heads/main
git ls-remote https://github.com/pablontiv/skills.git HEAD refs/heads/main
```

Expected: new name and URL resolve, `main` remains the default branch, and the old Git URL redirects to the same refs.

- [ ] **Step 5: Update and verify the GitHub description**

```bash
gh repo edit pablontiv/handbook \
  --description 'Un handbook para convertir el trabajo de desarrollo improvisado en un método reproducible, verificable y adaptable.'
gh repo view pablontiv/handbook --json description,url
```

Expected: description exactly matches the approved hero.

- [ ] **Step 6: Update the local remote only after GitHub verification**

```bash
git remote set-url origin https://github.com/pablontiv/handbook.git
git remote -v
git ls-remote origin HEAD refs/heads/main
```

Expected: fetch and push URLs both use `pablontiv/handbook.git`; remote refs remain reachable. The checkout directory remains `/Users/Shared/harness/skills`.

- [ ] **Step 7: Verify issue and pull-request continuity**

```bash
gh issue list --repo pablontiv/handbook --limit 5
gh pr list --repo pablontiv/handbook --state all --limit 5
```

Expected: existing tracker records remain accessible. Report the observed counts and URLs without generalizing beyond the queried limit.
