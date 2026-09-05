# Handbook Skill Author Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `metadata.author: pablontiv` an enforced contract for every Agent Skill published by the handbook.

**Architecture:** Extend the root handbook contract test so it enumerates every `skills/*/SKILL.md`, parses YAML frontmatter with the repository's pinned test-only PyYAML dependency, and verifies the author field. Add the missing metadata to the seven current skills while preserving all existing provenance fields and behavior.

**Tech Stack:** Markdown Agent Skills, YAML frontmatter, Python 3.11 `unittest`, PyYAML 6.0.3, Rootline, Git.

**Spec:** `.workspace/docs/superpowers/specs/2026-09-04-federated-skill-ownership-and-distribution-design.md`

## Global Constraints

- Read `.workspace/docs/adr/*-distribuir-skills-sin-registro-inicial.md` and the linked spec before implementation; exactly one matching ADR must exist and be accepted.
- Use the `writing-skills` skill before editing any `SKILL.md`.
- Add only adaptation authorship; do not remove or rewrite existing upstream attribution, license, version, source, ownership, or provenance fields.
- Discover published skills dynamically through `skills/*/SKILL.md`; do not maintain a second hard-coded skill list.
- PyYAML remains a pinned test-only dependency under ADR 0023 and must not be imported by runtime code.
- Do not create `skills/registry.json` or other unused registry infrastructure.
- Do not modify user runtime directories, symlinks, or `.skill-lock.json` in this plan.
- Deliver through a pull request and disclose the governing and superseded ADRs.

---

### Task 1: Enforce and apply handbook skill authorship

**Files:**

- Modify: `tests/test_handbook_contract.py`
- Modify: `skills/adr/SKILL.md`
- Modify: `skills/context-save/SKILL.md`
- Modify: `skills/decision-calibrator/SKILL.md`
- Modify: `skills/evidence-driven-development/SKILL.md`
- Modify: `skills/model-optimizer/SKILL.md`
- Modify: `skills/remove-gentle-context/SKILL.md`
- Modify: `skills/sweep/SKILL.md`

**Interfaces:**

- Consumes: every YAML frontmatter document matched by `skills/*/SKILL.md` and the pinned `PyYAML==6.0.3` test dependency.
- Produces: `load_skill_frontmatter(path: Path) -> dict[str, object]` and a repository contract that rejects any published skill whose `metadata.author` is not exactly `pablontiv`.

- [ ] **Step 1: Add the frontmatter parser and failing contract test**

Add the import:

```python
import yaml
```

Add this helper after `REQUIRED_AGENT_CLAUSES`:

```python
def load_skill_frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"{path} must begin with YAML frontmatter")
    _, raw_frontmatter, _ = text.split("---", 2)
    parsed = yaml.safe_load(raw_frontmatter)
    if not isinstance(parsed, dict):
        raise AssertionError(f"{path} frontmatter must be a mapping")
    return parsed
```

Add this test to `HandbookContractTests` immediately after `test_every_published_skill_is_linked`:

```python
def test_every_published_skill_declares_pablontiv_author(self) -> None:
    skill_paths = sorted((ROOT / "skills").glob("*/SKILL.md"))
    self.assertTrue(skill_paths)
    for path in skill_paths:
        with self.subTest(skill=path.parent.name):
            frontmatter = load_skill_frontmatter(path)
            metadata = frontmatter.get("metadata")
            self.assertIsInstance(metadata, dict, path.relative_to(ROOT))
            if not isinstance(metadata, dict):
                continue
            self.assertEqual(
                metadata.get("author"),
                "pablontiv",
                path.relative_to(ROOT),
            )
```

- [ ] **Step 2: Run the handbook contract and verify RED**

Run:

```bash
python -m unittest discover \
  -s tests \
  -p "test_handbook_contract.py" \
  -v
```

Expected: FAIL for exactly these seven skills because their current frontmatter has no `metadata.author`:

```text
adr
context-save
decision-calibrator
evidence-driven-development
model-optimizer
remove-gentle-context
sweep
```

`systemic-issue-triage` must already pass with its existing `metadata.author: "pablontiv"` and its upstream provenance unchanged.

- [ ] **Step 3: Add the minimum metadata to the seven skills**

For each listed `SKILL.md`, add this mapping inside the existing frontmatter without changing the `name`, `description`, `source`, or any other field:

```yaml
metadata:
  author: pablontiv
```

For `context-save`, retain `source: pablontiv/praxis`. Do not remove or reinterpret that provenance when adding the metadata mapping.

- [ ] **Step 4: Run the handbook contract and verify GREEN**

Run:

```bash
python -m unittest discover \
  -s tests \
  -p "test_handbook_contract.py" \
  -v
```

Expected: PASS for all eight published skills.

- [ ] **Step 5: Run repository verification**

Install the already-pinned test dependency without transitive packages:

```bash
python -m pip install --disable-pip-version-check --no-deps -r requirements-test.txt
```

Run the repository checks represented by both workflows:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
python -m unittest discover -s profiles/pablontiv/tests -t profiles/pablontiv -p "test_*.py" -v
python -m unittest discover -s skills/adr/tests -t skills/adr -p "test_*.py" -v
python -m unittest discover -s skills/evidence-driven-development/tests -t skills/evidence-driven-development -p "test_*.py" -v
python -m unittest discover -s skills/systemic-issue-triage/tests -t skills/systemic-issue-triage -p "test_*.py" -v
python -m unittest discover -s skills/context-save/tests -t skills/context-save -p "test_*.py" -v
python -m unittest discover -s skills/sweep/tests -t skills/sweep -p "test_*.py" -v
sh skills/sweep/assets/test-assets.sh
(
  cd skills/remove-gentle-context
  python -m unittest discover -s tests -t . -v
  python -m py_compile scripts/cleanup.py
  python scripts/cleanup.py --help
)
python -m unittest discover -s skills/model-optimizer/tests -t skills/model-optimizer -p "test_*.py" -v
rootline validate --all .workspace/docs/adr -o json
rootline validate --all .workspace/docs/superpowers -o json
rootline validate --all profiles/pablontiv -o json
git diff --check
```

Expected: every command exits zero. On Windows, skip only the POSIX shell asset test exactly as CI does.

- [ ] **Step 6: Review the complete diff**

Run:

```bash
git diff -- \
  tests/test_handbook_contract.py \
  skills/adr/SKILL.md \
  skills/context-save/SKILL.md \
  skills/decision-calibrator/SKILL.md \
  skills/evidence-driven-development/SKILL.md \
  skills/model-optimizer/SKILL.md \
  skills/remove-gentle-context/SKILL.md \
  skills/sweep/SKILL.md
```

Expected: one test helper, one contract test, and only the seven frontmatter additions. No skill body, provenance, source, license, runtime path, or registry change is present.

- [ ] **Step 7: Commit the independently verified unit**

```bash
git add \
  tests/test_handbook_contract.py \
  skills/adr/SKILL.md \
  skills/context-save/SKILL.md \
  skills/decision-calibrator/SKILL.md \
  skills/evidence-driven-development/SKILL.md \
  skills/model-optimizer/SKILL.md \
  skills/remove-gentle-context/SKILL.md \
  skills/sweep/SKILL.md
git commit -m "chore(skills): declare handbook author metadata"
```

## Subsequent Independent Plans

This plan implements only Stage 1 of the federated ownership specification. Create separately reviewed plans before changing behavior for:

1. `naming-brief` migration;
2. `docs-northstar` migration;
3. `rule-audit` migration;
4. generalized `gh-communication-style`;
5. the portable MarkItDown adaptation;
6. `context-save` and `session-handover` convergence;
7. canonical `poness` and `qmd` skills in their owner repositories;
8. `opensrc` manager convergence;
9. digest-bound live symlink replacement and cleanup.

No later plan may treat this plan, the specification, or a skill name as authority to mutate a user runtime path.
