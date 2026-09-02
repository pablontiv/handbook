# Context Save and Sweep Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt `context-save` and `sweep` as canonical portable skills, deliver both in one PR, then remove chezmoi ownership and distribute direct runtime symlinks safely.

**Architecture:** Each skill is self-contained under `skills/<name>/` with deterministic contract tests. `context-save` is a licensed adaptation of Praxis; `sweep` bundles portable assets, references, and separate Claude/Pi agent adapters. Runtime paths become symlinks only after the skills PR is merged.

**Tech Stack:** Markdown Agent Skills, Python 3.11 `unittest`, POSIX shell, Git, GitHub CLI, Rootline, chezmoi.

**Spec:** `docs/superpowers/specs/2026-09-02-context-save-sweep-migration-design.md`

## Global Constraints

- Preserve `source: pablontiv/praxis` and bundle PolyForm Noncommercial 1.0.0 for `context-save`.
- Use Rootline v2 `values`, never legacy `enum`, in generated `.stem` guidance.
- Preserve sweep's read-only inspection default and require explicit `--apply` for mutations.
- Keep Claude and Pi agent adapters separate; do not ship OpenCode agents.
- Never point global links at a temporary worktree.
- Never run global `chezmoi apply`.
- Inventory, back up, hash, approve, and verify every live-path mutation.
- Deliver both skills in one pull request and disclose ADRs 0018 and 0019.

---

### Task 1: Add the context-save contract tests

**Files:**
- Create: `skills/context-save/tests/test_contract.py`
- Create: `skills/context-save/tests/__init__.py`

**Interfaces:**
- Consumes: the approved design and the future `skills/context-save/SKILL.md`.
- Produces: deterministic checks for frontmatter, provenance, license, Rootline schema, and harness-neutral wording.

- [ ] **Step 1: Write the failing test**

Create a `unittest.TestCase` that resolves `SKILL.md` and `LICENSE`, then asserts:

```python
self.assertIn("name: context-save", skill)
self.assertIn("source: pablontiv/praxis", skill)
self.assertIn("values: [session-state]", skill)
self.assertIn("values: [saved, restored, archived]", skill)
self.assertNotIn("        enum:", skill)
self.assertNotIn("$ARGUMENTS", skill)
self.assertIn("PolyForm Noncommercial License 1.0.0", license_text)
```

Also assert the skill documents `save`, `restore`, and `list`, requires `rootline`, treats `backscroll` as optional, and contains no absolute `/Users/` or `/home/` path.

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m unittest discover -s skills/context-save/tests -t skills/context-save -v
```

Expected: FAIL because `skills/context-save/SKILL.md` and `LICENSE` do not exist.

- [ ] **Step 3: Commit the RED test**

```bash
git add skills/context-save/tests
git commit -m "test(context-save): define portable migration contract"
```

### Task 2: Implement context-save minimally

**Files:**
- Create: `skills/context-save/SKILL.md`
- Create: `skills/context-save/LICENSE`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1 tests and current Praxis `.openclaw/skills/context-save/SKILL.md`.
- Produces: a self-contained Agent Skill discoverable from shared global roots.

- [ ] **Step 1: Import the current upstream source and license**

Fetch the exact current Praxis files through `gh api`; do not use the stale copies under `/Users/Shared/infra/docs` or `/Users/Shared/infra/factory`.

- [ ] **Step 2: Apply the minimal portability adaptation**

Preserve the three modes and body structure. Change only:

```yaml
# schema examples
values: [session-state]
values: [saved, restored, archived]
```

Replace `$ARGUMENTS` and `/context-save`-only assumptions with “the arguments supplied when invoking this skill”. Keep `.claude/session-state/` as the compatibility data path. State that Backscroll enrichment is optional.

- [ ] **Step 3: Verify GREEN**

```bash
python3 -m unittest discover -s skills/context-save/tests -t skills/context-save -v
```

Expected: all context-save contract tests PASS.

- [ ] **Step 4: Update the repository inventory**

Add `context-save` to the canonical-skills list in `README.md`, noting Praxis provenance and bundled noncommercial license.

- [ ] **Step 5: Commit context-save**

```bash
git add skills/context-save README.md
git commit -m "feat(context-save): adopt portable Praxis skill"
```

### Task 3: Add sweep contract tests

**Files:**
- Create: `skills/sweep/tests/test_contract.py`
- Create: `skills/sweep/tests/__init__.py`
- Create: `skills/sweep/assets/test-assets.sh`

**Interfaces:**
- Consumes: ADR 0018 and the existing live sweep bundle.
- Produces: deterministic checks for complete bundle shape, portability, executable helpers, and runtime-specific agents.

- [ ] **Step 1: Write the failing Python contract test**

Assert all required files exist and contain no `/Users/Shared`, `/Users/pones`, or `/home/pones` strings. Verify:

```python
required_agents = {"sweep-scout.md", "sweep-triage.md", "pr-investigator.md"}
self.assertEqual(required_agents, names("agents/claude"))
self.assertEqual(required_agents, names("agents/pi"))
```

Assert Claude definitions use `Bash`/`Read` and their parent-visible delivery contract; Pi definitions use lowercase `bash`/`read`, contain no `SendMessage`, `color`, or hard-coded model, and instruct the subagent to return the final response directly.

- [ ] **Step 2: Import the existing asset test as the RED fixture harness**

Copy the current `test-assets.sh` test logic only. Do not copy production helpers yet. Update `.orca/worktrees` fixture expectations to `.worktrees`.

- [ ] **Step 3: Verify RED**

```bash
python3 -m unittest discover -s skills/sweep/tests -t skills/sweep -v
sh skills/sweep/assets/test-assets.sh
```

Expected: FAIL because production helpers, references, and adapters are absent.

- [ ] **Step 4: Commit the RED tests**

```bash
git add skills/sweep/tests skills/sweep/assets/test-assets.sh
git commit -m "test(sweep): define portable bundle contract"
```

### Task 4: Implement the sweep bundle

**Files:**
- Create: `skills/sweep/SKILL.md`
- Create: `skills/sweep/assets/enumerate.sh`
- Create: `skills/sweep/assets/facts.sh`
- Create: `skills/sweep/assets/preflight.sh`
- Create: `skills/sweep/references/apply.md`
- Create: `skills/sweep/references/evidence.md`
- Create: `skills/sweep/references/fanout.md`
- Create: `skills/sweep/references/fork-mirrors.md`
- Create: `skills/sweep/references/tiers.md`
- Create: `skills/sweep/agents/claude/{sweep-scout,sweep-triage,pr-investigator}.md`
- Create: `skills/sweep/agents/pi/{sweep-scout,sweep-triage,pr-investigator}.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 3 tests and the live sweep source bundle.
- Produces: one self-contained skill plus runtime-specific subagent definitions.

- [ ] **Step 1: Copy the skill, helpers, and references**

Preserve behavior and executable modes. Replace only stale `.orca/worktrees` fixture wording with `.worktrees`; keep helper root discovery argument-driven.

- [ ] **Step 2: Create Claude adapters**

Start from the three live Claude definitions. Point sibling references to `~/.claude/skills/sweep/`. Preserve narrow `Bash, Read` tools and parent-visible result delivery.

- [ ] **Step 3: Create Pi adapters**

Translate tool frontmatter to:

```yaml
tools:
  - bash
  - read
```

Remove `model`, `color`, and Claude `SendMessage` instructions. End each definition with: “Return the complete evidence or TSV as your final response; `subagent_run` delivers it to the orchestrator.” Point sibling references to `~/.agents/skills/sweep/`.

- [ ] **Step 4: Verify GREEN**

```bash
python3 -m unittest discover -s skills/sweep/tests -t skills/sweep -v
sh skills/sweep/assets/test-assets.sh
```

Expected: all sweep tests PASS.

- [ ] **Step 5: Update repository inventory and commit**

Add `sweep` and its Claude/Pi adapter boundary to `README.md`, then:

```bash
git add skills/sweep README.md
git commit -m "feat(sweep): add portable runtime adapters"
```

### Task 5: Verify and open the single skills PR

**Files:**
- Verify: all files changed in Tasks 1–4
- Modify if required: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: both complete skills.
- Produces: one reviewed PR referencing issue #11 and ADRs 0018/0019.

- [ ] **Step 1: Add new deterministic suites to CI if discovery is not automatic**

Add explicit `python -m unittest discover` steps for `context-save` and `sweep`, plus `sh skills/sweep/assets/test-assets.sh` on macOS/Linux. Keep Windows limited to Python contract tests because the helper suite is POSIX shell.

- [ ] **Step 2: Run all tests**

Run the existing 230 systemic-triage tests, existing 281 model-optimizer tests, remove-gentle-context tests, both new suites, shell asset tests, compile check, and CLI help check.

- [ ] **Step 3: Validate governance and diagnostics**

```bash
rootline validate docs/adr/0019-adoptar-context-save-globalmente.md --strict
```

Run LSP/repository diagnostics on changed files and verify `git diff --check`.

- [ ] **Step 4: Request independent review**

Review spec compliance first, then code/skill quality. Resolve every blocking finding and rerun affected tests.

- [ ] **Step 5: Commit governance and CI**

```bash
git add docs/adr docs/superpowers .github/workflows README.md
git commit -m "docs(skills): govern context-save and sweep migration"
```

- [ ] **Step 6: Push and open one PR**

The PR body must list ADRs 0018 and 0019, issue #11, provenance/license, RED/GREEN evidence, OpenCode boundary, test counts, and the separate post-merge live migration.

### Task 6: Remove dotfiles ownership safely

**Files:**
- Move: `/Users/Shared/infra/dotfiles/dot_claude/skills/chezmoi-drift/SKILL.md` → `/Users/Shared/infra/dotfiles/.agents/skills/chezmoi-drift/SKILL.md`
- Modify: `/Users/Shared/infra/dotfiles/.chezmoiignore`
- Delete: `/Users/Shared/infra/dotfiles/dot_claude/skills/sweep/`
- Delete: `/Users/Shared/infra/dotfiles/dot_gemini/skills/symlink_context-save.tmpl`
- Modify: `/Users/Shared/infra/dotfiles/.githooks/pre-push`
- Modify: `/Users/Shared/infra/dotfiles/.githooks/post-merge`
- Modify: current architecture documentation that claims global skill ownership

**Interfaces:**
- Consumes: merged canonical skills checkout.
- Produces: dotfiles with one repository-local skill and no ownership of the two global skills.

- [ ] **Step 1: Create an isolated dotfiles worktree from the current remote base**

Do not disturb the dirty main checkout. Record the existing pending deletions so the cleanup does not silently lose them.

- [ ] **Step 2: Write a failing repository-boundary check**

In a temporary check script, assert `.agents/skills/chezmoi-drift/SKILL.md` exists, `.agents/` is excluded by `.chezmoiignore`, and no current hook synchronizes `.claude/skills`.

- [ ] **Step 3: Move and remove the governed sources**

Use Git-aware moves/removals in the isolated worktree. Historical plans remain unchanged; update only current architecture documents.

- [ ] **Step 4: Verify chezmoi boundary without applying**

Use `chezmoi source-path`/`managed` checks and `chezmoi diff` scoped to affected targets. Confirm no target is unexpectedly scheduled for recreation. Do not run `chezmoi apply`.

- [ ] **Step 5: Commit and open the dotfiles PR**

Use a conventional commit and disclose that live migration occurs separately with backup and restore evidence.

### Task 7: Distribute from merged canonical sources

**Files:**
- Replace approved runtime paths under `~/.agents/skills`, `~/.claude/skills`, `~/.claude/agents`, `~/.pi/agent/subagents`, and the broken `~/.gemini/skills/context-save` link.
- Create: backup manifest outside runtime discovery roots.

**Interfaces:**
- Consumes: merged PRs and exact canonical paths on `main`.
- Produces: direct runtime symlinks and a verified restore bundle.

- [ ] **Step 1: Inventory and hash all paths**

Capture path type, link target, resolved target, mode, SHA-256, and chezmoi source mapping. Unexpected drift blocks mutation.

- [ ] **Step 2: Create and verify backups**

Back up real skill/agent files and verify recursive hashes. Store the manifest outside all skill roots.

- [ ] **Step 3: Produce the exact operation-plan digest**

List every forget, unlink, move, and symlink operation in deterministic order and hash the plan. Apply only the approved digest represented by this plan and current observed state.

- [ ] **Step 4: Remove confirmed chezmoi ownership**

Run `chezmoi forget` only for paths proven managed. Do not apply other dotfiles changes.

- [ ] **Step 5: Create canonical symlinks**

Create the topology from the approved design. Confirm every resolved target is under `/Users/Shared/harness/skills/skills/`, never `.worktrees/`.

- [ ] **Step 6: Verify discovery safely**

Use Pi RPC/skill discovery, `subagent_list_agents`, Claude path/frontmatter checks, and Gemini shared-root discovery where available. Do not run sweep with `--apply`.

- [ ] **Step 7: Perform restore drill**

Restore the backed-up preimage into a temporary home and compare hashes. Keep the live canonical installation after the drill succeeds.
