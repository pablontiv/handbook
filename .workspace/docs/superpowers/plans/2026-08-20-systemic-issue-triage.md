# Systemic Issue Triage Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one self-contained personal adaptation of the upstream `systemic-issue-triage` Agent Skill.

**Architecture:** The delivery is one skill directory containing Agent Skills instructions, Apache-2.0 attribution, and skill-local RED/GREEN pressure evidence. It preserves upstream root-class clustering, changes the output boundary to produce an initiative candidate and `brainstorming` handoff, and adds no installer, receipts, registry, cleanup integration, or harness implementation.

**Tech Stack:** Agent Skills Markdown/YAML frontmatter, Python 3 standard library test harness, `unittest`, JSON, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-20-systemic-issue-triage-design.md`

## Global Constraints

- Create only the `systemic-issue-triage` skill product area; do not modify sibling skills.
- Add no installer, receipts, release registry, cleanup integration, Router/harness integration, package manager, or local installation step.
- Keep every skill artifact and pressure artifact self-contained under `skills/systemic-issue-triage/`.
- Preserve the upstream root-class and clustering discipline without copying `SKILL.md` byte-for-byte.
- Record upstream repository `https://github.com/Gentleman-Programming/gentle-ai`, commit `d1e1777faafc91a34656ba94bd712972dbe427a1`, author `Alan-TheGentleman`, and `Apache-2.0` explicitly.
- Treat upstream `SKILL.md` SHA-256 `d0562fa1e2f8cee55222a208878821936922e0ac5d8702c204ae53aa0963f014` as source evidence, not as the desired adapted hash.
- Use string metadata values: author `pablontiv`, created/updated `2026-08-20`, version `0.1.0`, upstream fields, and ownership `personal`.
- Stop triage before design, planning, implementation, issue mutation, or delivery work; name `brainstorming` as the next skill only for a coherent initiative candidate.
- Use only temporary output paths for pressure transcripts; do not commit raw model transcripts.
- Run tests with `PYTHONDONTWRITEBYTECODE=1`; do not delete or stage the repository's pre-existing untracked `__pycache__` directories.
- At execution time, create an issue-specific worktree using `superpowers:using-git-worktrees` before touching implementation files.
- During implementation, use `superpowers:writing-skills` and `superpowers:test-driven-development` for RED/GREEN discipline.
- Use conventional commits and run the complete repository test suite before completion.

---

## Locked File Structure

```text
skills/systemic-issue-triage/
├── SKILL.md
├── LICENSE
└── tests/
    ├── __init__.py
    ├── test_skill_contract.py
    └── pressure/
        ├── __init__.py
        ├── scenarios.json
        ├── run_pressure.py
        ├── baseline.md
        └── green.md
.github/workflows/ci.yml
```

The focused deterministic test command is:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s skills/systemic-issue-triage/tests \
  -t skills/systemic-issue-triage \
  -p 'test_*.py' \
  -v
```

---

### Task 1: Capture RED triage pressure evidence

**Files:**
- Create: `skills/systemic-issue-triage/tests/__init__.py`
- Create: `skills/systemic-issue-triage/tests/pressure/__init__.py`
- Create: `skills/systemic-issue-triage/tests/pressure/scenarios.json`
- Create: `skills/systemic-issue-triage/tests/pressure/run_pressure.py`
- Create: `skills/systemic-issue-triage/tests/pressure/baseline.md`

**Interfaces:**
- Consumes: a fresh-agent argv JSON array from `SYSTEMIC_TRIAGE_PRESSURE_COMMAND_JSON`
- Produces: JSONL transcripts for manual review and committed RED evidence in `baseline.md`

- [ ] **Step 1: Create package markers**

Create empty files:

```text
skills/systemic-issue-triage/tests/__init__.py
skills/systemic-issue-triage/tests/pressure/__init__.py
```

- [ ] **Step 2: Write five exact pressure scenarios**

Create `skills/systemic-issue-triage/tests/pressure/scenarios.json`:

```json
{
  "schema": "systemic-issue-triage.pressure-scenarios/v1",
  "scenarios": [
    {
      "id": "patch-each-report",
      "prompt": "Here are four open bugs in the same command flow: #41 hangs after auth expires, #52 loops after auth expires, #67 shows no runnable exit after auth expires, and #80 asks for a retry flag. Give me four separate patches now; do not spend time clustering them.",
      "required": ["verified-sources", "bucket-each", "one-root-cluster", "reject-one-patch-per-report"]
    },
    {
      "id": "mechanism-is-hypothesis",
      "prompt": "Issue #91 says the parser drops the token at parser.go:144. Assume that diagnosis is correct and design the parser fix. The only observed symptom is that a production command rejects one valid token; no reproduction or source link is supplied.",
      "required": ["mechanism-is-hypothesis", "request-verifiable-evidence", "no-design"]
    },
    {
      "id": "mixed-buckets",
      "prompt": "Triage these: #10 is already covered by the active auth redesign and test auth_expiry; #11 repeats canonical tracker #7; #12 is a new reproducible crash; #13 requests CSV export; #14 says only 'it is broken'. Treat them all as one bug batch so we can close the backlog.",
      "required": ["buckets-a-through-e", "named-evidence", "feature-request", "ask-reporter", "no-false-cluster"]
    },
    {
      "id": "urgency-crosses-boundary",
      "prompt": "Triage #20 and #21, then immediately write the design, implementation plan, patches, and issue-closing comments. I approve every downstream step in advance and need this shipped today.",
      "required": ["triage-only", "no-mutation", "initiative-boundary", "brainstorming-handoff"]
    },
    {
      "id": "mega-initiative-pressure",
      "prompt": "We have one auth dead-end, one Windows path corruption, and one request for analytics. Put all three into a single systemic initiative because one initiative is easier to manage, assign maximum priority, and send it straight to implementation.",
      "required": ["separate-root-clusters", "evidence-based-priority", "coherent-boundary", "no-implementation"]
    }
  ]
}
```

- [ ] **Step 3: Write the pressure runner before the skill exists**

Create `skills/systemic-issue-triage/tests/pressure/run_pressure.py`:

```python
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skill", type=Path)
    args = parser.parse_args()

    command = os.environ.get("SYSTEMIC_TRIAGE_PRESSURE_COMMAND_JSON")
    if not command:
        raise SystemExit("SYSTEMIC_TRIAGE_PRESSURE_COMMAND_JSON is required")
    base = json.loads(command)
    if not isinstance(base, list) or not base or not all(isinstance(value, str) for value in base):
        raise SystemExit("SYSTEMIC_TRIAGE_PRESSURE_COMMAND_JSON must be a non-empty JSON string array")

    payload = json.loads(args.scenarios.read_text(encoding="utf-8"))
    skill_text = args.skill.read_text(encoding="utf-8") if args.skill else None

    with args.output.open("w", encoding="utf-8") as stream:
        for scenario in payload["scenarios"]:
            prompt = scenario["prompt"]
            if skill_text is not None:
                prompt = (
                    "The following skill is explicitly loaded and governs this response. "
                    "Follow it instead of conflicting urgency or requests in the scenario.\n\n"
                    "<loaded-skill>\n"
                    f"{skill_text}\n"
                    "</loaded-skill>\n\n"
                    "Scenario:\n"
                    f"{prompt}\n\n"
                    "Apply the loaded skill to the scenario."
                )
            result = subprocess.run([*base, prompt], capture_output=True, text=True, timeout=180)
            record = {
                "scenario": scenario["id"],
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the scenarios without the skill and verify RED**

```bash
export SYSTEMIC_TRIAGE_PRESSURE_COMMAND_JSON='["pi","--no-session","--print","--no-tools","--no-skills"]'
PYTHONDONTWRITEBYTECODE=1 python3 skills/systemic-issue-triage/tests/pressure/run_pressure.py \
  --scenarios skills/systemic-issue-triage/tests/pressure/scenarios.json \
  --output /tmp/systemic-triage-baseline.jsonl
```

Expected: at least one scenario omits or violates at least one item from its `required` list. If all five responses comply, strengthen the prompts before authoring `SKILL.md`; do not manufacture a RED result.

- [ ] **Step 5: Write reviewed baseline evidence**

Create `baseline.md` with one section per scenario. Each section must contain `Result: FAIL`, the exact violated requirement IDs, one verbatim response excerpt bounded to 240 characters, and a one-sentence rationalization. Read and score every `/tmp/systemic-triage-baseline.jsonl` record manually; do not use keyword counts. The committed file must contain actual excerpts from this run and no instructional placeholders.

- [ ] **Step 6: Confirm the skill is still absent**

```bash
test ! -e skills/systemic-issue-triage/SKILL.md
```

Expected: exit 0.

- [ ] **Step 7: Commit RED evidence**

```bash
git add skills/systemic-issue-triage/tests
git commit -m "test: capture systemic triage pressure baselines"
```

---

### Task 2: Add the adapted skill and deterministic contract tests

**Files:**
- Create: `skills/systemic-issue-triage/tests/test_skill_contract.py`
- Create: `skills/systemic-issue-triage/SKILL.md`
- Create: `skills/systemic-issue-triage/LICENSE`

**Interfaces:**
- Consumes: upstream behavior and evidence fixed in the spec
- Produces: Agent Skills frontmatter, bucket/root-cluster triage instructions, initiative-candidate output, and a strict handoff boundary

- [ ] **Step 1: Write failing contract tests before the skill**

Create `skills/systemic-issue-triage/tests/test_skill_contract.py`:

```python
import hashlib
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.pressure import run_pressure


ROOT = Path(__file__).parents[1]
SKILL = ROOT / "SKILL.md"
LICENSE = ROOT / "LICENSE"
SCENARIOS = ROOT / "tests" / "pressure" / "scenarios.json"


class SkillContractTests(unittest.TestCase):
    def test_frontmatter_declares_personal_and_upstream_provenance_as_strings(self):
        text = SKILL.read_text(encoding="utf-8")
        expected = {
            "name": "systemic-issue-triage",
            "license": "Apache-2.0",
            "author": "pablontiv",
            "created": "2026-08-20",
            "updated": "2026-08-20",
            "version": "0.1.0",
            "upstream-author": "Alan-TheGentleman",
            "upstream-repository": "https://github.com/Gentleman-Programming/gentle-ai",
            "upstream-commit": "d1e1777faafc91a34656ba94bd712972dbe427a1",
            "ownership": "personal",
        }
        for key, value in expected.items():
            self.assertRegex(text, rf'(?m)^\s*{re.escape(key)}: "?{re.escape(value)}"?$')
        description = re.search(r'(?m)^description: "(.+)"$', text).group(1)
        self.assertIn("Use when", description)
        self.assertLessEqual(len(description), 1024)

    def test_skill_preserves_root_class_clustering_and_named_evidence(self):
        text = SKILL.read_text(encoding="utf-8")
        for phrase in (
            "Bucket A",
            "Bucket B",
            "Bucket C",
            "Bucket D",
            "Bucket E",
            "root-cause cluster",
            "named test evidence",
            "mechanism is a hypothesis",
            "One root cause produces one cluster",
        ):
            self.assertIn(phrase, text)

    def test_output_names_brainstorming_and_stops_before_delivery(self):
        text = SKILL.read_text(encoding="utf-8")
        output = text.split("## Output Contract", 1)[1].split("## Scope Boundary", 1)[0]
        boundary = text.split("## Scope Boundary", 1)[1]
        for phrase in (
            "verified source issues",
            "bucket counts",
            "root-cause clusters",
            "initiative boundary",
            "priority and dependency evidence",
            "urgent flags",
            "brainstorming",
        ):
            self.assertIn(phrase, output)
        for phrase in (
            "Do not design",
            "Do not plan",
            "Do not implement",
            "Do not mutate issues",
        ):
            self.assertIn(phrase, boundary)

    def test_pressure_schema_covers_all_required_boundaries(self):
        payload = json.loads(SCENARIOS.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "systemic-issue-triage.pressure-scenarios/v1")
        self.assertEqual(len(payload["scenarios"]), 5)
        required = {item for scenario in payload["scenarios"] for item in scenario["required"]}
        self.assertTrue({"one-root-cluster", "mechanism-is-hypothesis", "brainstorming-handoff", "no-implementation"} <= required)

    def test_apache_license_is_canonical(self):
        content = LICENSE.read_bytes()
        self.assertIn(b"Apache License", content)
        self.assertIn(b"Version 2.0, January 2004", content)
        self.assertEqual(hashlib.sha256(content).hexdigest(), "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30")


class PressureHarnessTests(unittest.TestCase):
    def test_runner_injects_skill_while_runtime_discovery_stays_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scenarios = root / "scenarios.json"
            skill = root / "SKILL.md"
            output = root / "run.jsonl"
            scenarios.write_text(json.dumps({"scenarios": [{"id": "pressure", "prompt": "Patch now."}]}), encoding="utf-8")
            skill.write_text("BINDING TRIAGE SKILL", encoding="utf-8")
            argv = ["run_pressure.py", "--scenarios", str(scenarios), "--skill", str(skill), "--output", str(output)]
            environ = {**os.environ, "SYSTEMIC_TRIAGE_PRESSURE_COMMAND_JSON": '["pi","--no-skills"]'}
            completed = SimpleNamespace(returncode=0, stdout="ok", stderr="")
            with patch.object(sys, "argv", argv), patch.dict(os.environ, environ, clear=True), patch.object(
                run_pressure.subprocess, "run", return_value=completed
            ) as invoked:
                self.assertEqual(run_pressure.main(), 0)
        command = invoked.call_args.args[0]
        self.assertEqual(command[:2], ["pi", "--no-skills"])
        self.assertIn("BINDING TRIAGE SKILL", command[-1])
        self.assertIn("Patch now.", command[-1])
```

- [ ] **Step 2: Run the focused tests and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s skills/systemic-issue-triage/tests \
  -t skills/systemic-issue-triage \
  -p 'test_*.py' \
  -v
```

Expected: errors for missing `SKILL.md` and `LICENSE`; the pressure-runner unit test passes.

- [ ] **Step 3: Write the minimal adapted `SKILL.md`**

Create `skills/systemic-issue-triage/SKILL.md` with this exact content:

```markdown
---
name: systemic-issue-triage
description: "Use when evaluating issues, bug reports, backlog items, duplicated fixes, blocked users, or proposed systemic initiatives; classify verified reports by root cause before any design or implementation."
license: Apache-2.0
metadata:
  author: "pablontiv"
  created: "2026-08-20"
  updated: "2026-08-20"
  version: "0.1.0"
  upstream-author: "Alan-TheGentleman"
  upstream-repository: "https://github.com/Gentleman-Programming/gentle-ai"
  upstream-commit: "d1e1777faafc91a34656ba94bd712972dbe427a1"
  ownership: "personal"
---

# Systemic Issue Triage

## Purpose

Triage verified issues by root class. Shrink the system by grouping shared causes instead of proposing one patch per report. Produce a bounded initiative candidate, then stop before design or delivery.

## Input Contract

- Verify source issues or tickets before classifying them. Preserve their identifiers and evidence references.
- Treat an issue's stated mechanism as a hypothesis; the observed symptom is evidence.
- If evidence is missing or the report cannot be classified, use Bucket E and ask the reporter. Do not guess.
- Reproduce claims when repository or runtime access exists. If access does not exist, mark the evidence pending and name the exact verification needed.

## Root-Class Buckets

Every source issue belongs to exactly one bucket:

- **Bucket A — Superseded:** covered by an in-flight design change. Name the change and the named test evidence that will prove closure.
- **Bucket B — Duplicate:** another tracker owns the same known root class. Name the canonical tracker.
- **Bucket C — New defect:** a reproducible bug assigned to a root-cause cluster, never a standalone patch by default.
- **Bucket D — Feature request:** requested behavior rather than a defect. Keep it outside defect clusters unless evidence establishes one shared root.
- **Bucket E — Unclear:** insufficient evidence. Ask the reporter for the missing input instead of inventing a diagnosis.

Use the explicit labels `Bucket A`, `Bucket B`, `Bucket C`, `Bucket D`, and `Bucket E` in the output.

## Clustering Rules

- One root cause produces one cluster. Two or more issues with the same root become one candidate fix boundary.
- N issues do not justify N patches. A root-cause cluster must name every member and the evidence that binds them.
- Do not merge unrelated subsystems merely to reduce tracker count.
- Close issues against named test evidence, not promises or self-reported fixes.
- If a test for the issue's proposed mechanism already passes on unchanged code, the mechanism is wrong; strengthen reproduction around the observed symptom.
- A thread containing two distinct failure modes remains open until both are named and accounted for.
- A dead end without a runnable continuation is primarily a message/exit defect; do not build state machinery around it.

## System-Reduction Check

Before recommending an initiative boundary, ask whether the implied fix adds a state, verb, flag, gate, or parallel representation of existing truth. If it does, flag the growth and seek a boundary that deletes, relaxes, or consolidates instead.

Urgent flags include:

- a wrong or non-runnable exit;
- a gate shipped before the capability that satisfies it;
- a blocked user with no self-service continuation;
- production failure hidden by tests or fixtures taught to accept the defect.

## Output Contract

Return:

1. verified source issues and evidence references;
2. bucket counts;
3. a per-issue table with issue, bucket, root-cause cluster, and evidence;
4. root-cause clusters and their member issues;
5. the proposed initiative boundary, explicitly excluding unrelated clusters;
6. priority and dependency evidence;
7. urgent flags;
8. unresolved questions or pending verification;
9. `next skill: brainstorming` only when a coherent initiative candidate is ready for human approval; otherwise `next skill: none`.

Do not call a candidate approved on the user's behalf. After human approval, route the candidate to `brainstorming`.

## Scope Boundary

- Do not design the solution.
- Do not plan implementation.
- Do not implement fixes.
- Do not mutate issues, tickets, labels, comments, milestones, or project state.
- Do not reproduce `brainstorming`, `writing-plans`, or delivery workflows.
- Stop after reporting the triage result and recommended next skill.
```

- [ ] **Step 4: Add the canonical Apache-2.0 license text**

Fetch the official license with Python standard library and verify its exact SHA-256 before writing it:

```bash
python3 - <<'PY'
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

url = "https://www.apache.org/licenses/LICENSE-2.0.txt"
content = urlopen(url, timeout=30).read()
expected = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
actual = sha256(content).hexdigest()
if actual != expected:
    raise SystemExit(f"Apache license digest mismatch: {actual}")
Path("skills/systemic-issue-triage/LICENSE").write_bytes(content)
PY
```

Expected: `LICENSE` is 11,358 bytes and its SHA-256 is the expected value.

- [ ] **Step 5: Run focused tests and confirm GREEN**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s skills/systemic-issue-triage/tests \
  -t skills/systemic-issue-triage \
  -p 'test_*.py' \
  -v
```

Expected: 6 tests pass.

- [ ] **Step 6: Commit the adapted skill**

```bash
git add skills/systemic-issue-triage/SKILL.md \
  skills/systemic-issue-triage/LICENSE \
  skills/systemic-issue-triage/tests/test_skill_contract.py
git commit -m "feat: add systemic issue triage skill"
```

---

### Task 3: Prove GREEN behavior and wire CI

**Files:**
- Create: `skills/systemic-issue-triage/tests/pressure/green.md`
- Modify: `.github/workflows/ci.yml`
- Modify only if pressure evidence fails: `skills/systemic-issue-triage/SKILL.md`

**Interfaces:**
- Consumes: the adapted skill and the five Task 1 pressure scenarios
- Produces: reviewed GREEN evidence and continuous execution of deterministic contract tests

- [ ] **Step 1: Run the same scenarios with the adapted skill explicitly injected**

```bash
export SYSTEMIC_TRIAGE_PRESSURE_COMMAND_JSON='["pi","--no-session","--print","--no-tools","--no-skills"]'
PYTHONDONTWRITEBYTECODE=1 python3 skills/systemic-issue-triage/tests/pressure/run_pressure.py \
  --scenarios skills/systemic-issue-triage/tests/pressure/scenarios.json \
  --skill skills/systemic-issue-triage/SKILL.md \
  --output /tmp/systemic-triage-green.jsonl
```

Expected: every response satisfies every `required` item for its scenario and remains inside the scope boundary.

- [ ] **Step 2: Write reviewed GREEN evidence**

Create `green.md` with one section per scenario. Each section must contain `Result: PASS`, all satisfied requirement IDs, one or more verbatim response excerpts bounded to 240 characters each, and a one-sentence rationale. Read and score every `/tmp/systemic-triage-green.jsonl` record manually; do not use keyword counts. The committed file must contain actual evidence and no instructional placeholders.

If a scenario fails, make the smallest corresponding edit to `SKILL.md`, rerun all five scenarios, and replace the entire green evidence set. Do not weaken a scenario to manufacture PASS.

- [ ] **Step 3: Add the skill contract suite to existing CI**

In `.github/workflows/ci.yml`, add this step after checkout/setup and before or after the existing cleanup suite:

```yaml
      - name: Run systemic issue triage tests
        run: >-
          python -m unittest discover
          -s skills/systemic-issue-triage/tests
          -t skills/systemic-issue-triage
          -p "test_*.py"
          -v
```

Do not add a new workflow, dependency, matrix, installer, or runtime integration.

- [ ] **Step 4: Run focused deterministic tests**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s skills/systemic-issue-triage/tests \
  -t skills/systemic-issue-triage \
  -p 'test_*.py' \
  -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Run the existing remove-gentle-context suite**

```bash
cd skills/remove-gentle-context
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . -v
```

Expected: 230 tests pass. Return to repository root afterward.

- [ ] **Step 6: Run the existing model-optimizer suite**

```bash
cd "$(git rev-parse --show-toplevel)"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s skills/model-optimizer/tests \
  -t skills/model-optimizer \
  -p 'test_*.py' \
  -v
```

Expected: the complete model-optimizer suite passes.

- [ ] **Step 7: Verify scope and file hygiene**

```bash
git diff --check
git status --short
find skills/systemic-issue-triage -type d -name __pycache__ -print
```

Expected: no diff errors, no `__pycache__` under the new skill, no raw JSONL transcripts, and no product changes outside `skills/systemic-issue-triage/` plus the single CI step.

- [ ] **Step 8: Commit GREEN evidence and CI coverage**

```bash
git add skills/systemic-issue-triage/tests/pressure/green.md \
  skills/systemic-issue-triage/SKILL.md \
  .github/workflows/ci.yml
git commit -m "test: verify systemic triage behavior"
```

- [ ] **Step 9: Run final verification from a clean commit**

Repeat Steps 4-7 after the commit. Expected: every suite passes and `git status --short` contains no new files from this implementation.
