# Portable Model Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a self-contained `model-optimizer` Agent Skill that gathers runtime-local evidence for Pi and OpenCode, live-checks exact model IDs, and guides human-approved model assignments without mutating runtime configuration.

**Architecture:** A concise `SKILL.md` owns criteria, evidence precedence, adversarial mapping, approval, apply, and reload discipline. A Python 3.11+ standard-library helper owns only deterministic runtime detection, inventory, readiness checks, bounded live probes, secret redaction, and versioned JSON artifacts through separate Pi and OpenCode adapters.

**Tech Stack:** Python 3.11-3.14 standard library, `unittest`, JSON, subprocess argument arrays, Agent Skills Markdown, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-19-model-optimizer-design.md`

## Global Constraints

- Keep the skill self-contained under `skills/model-optimizer/`; do not depend on sibling skills.
- Support Pi and OpenCode only in version 1.
- Require Python 3.11 or newer and add no runtime dependency outside the standard library.
- Support macOS, Linux, and Windows without hard-coded user paths.
- Treat exact runtime-local IDs with ready auth and live PASS as the only assignable set.
- Use online sources only to enrich locally viable candidates; advisor-only models remain excluded.
- Never select models or write Pi/OpenCode configuration from the helper.
- Never refresh, print, or serialize credentials.
- Invoke child commands as argument arrays without a shell.
- Preserve current assignments, failures, exclusions, provenance, and source disagreements in reports.
- Require a before/after proposal and explicit human approval before configuration changes.
- Verify reload semantics and affected agent paths before claiming end-to-end success.
- Model family, not serving provider, defines adversarial independence.
- Tests use fake executables and temporary homes; automated tests never invoke real providers or read the developer's home.
- Follow skill RED/GREEN/REFACTOR: capture failing fresh-agent baselines before writing `SKILL.md`.
- Use conventional commits and run the complete model-optimizer suite before every commit.

---

## Locked File Structure

```text
skills/model-optimizer/
├── SKILL.md
├── scripts/
│   └── model_optimizer.py
├── helper/
│   ├── __init__.py
│   ├── models.py
│   ├── runner.py
│   ├── artifacts.py
│   └── adapters/
│       ├── __init__.py
│       ├── pi.py
│       └── opencode.py
├── references/
│   └── contracts.md
└── tests/
    ├── __init__.py
    ├── support.py
    ├── fixtures/
    │   ├── pi/
    │   │   ├── auth-ready.json
    │   │   ├── list-models.txt
    │   │   ├── models-store.json
    │   │   ├── settings.json
    │   │   └── subagents.json
    │   └── opencode/
    │       ├── auth-list.txt
    │       ├── live-error.jsonl
    │       ├── models-verbose.txt
    │       └── opencode.json
    ├── pressure/
    │   ├── scenarios.json
    │   ├── run_pressure.py
    │   ├── baseline.md
    │   └── green.md
    ├── test_artifacts.py
    ├── test_cli.py
    ├── test_opencode.py
    ├── test_pi.py
    ├── test_runner.py
    └── test_skill_contract.py
.github/workflows/test-model-optimizer.yml
```

The command used throughout the plan is:

```bash
python -m unittest discover \
  -s skills/model-optimizer/tests \
  -t skills/model-optimizer \
  -p 'test_*.py' \
  -v
```

---

### Task 1: Capture RED pressure baselines before authoring the skill

**Files:**
- Create: `skills/model-optimizer/tests/pressure/scenarios.json`
- Create: `skills/model-optimizer/tests/pressure/run_pressure.py`
- Create: `skills/model-optimizer/tests/pressure/baseline.md`

**Interfaces:**
- Consumes: a configurable fresh-agent argv JSON array supplied through `MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON`
- Produces: one JSONL transcript per scenario and a reviewed `baseline.md` containing exact observed failures/rationalizations

- [ ] **Step 1: Create five concrete pressure scenarios**

Write `scenarios.json` with this exact shape and content:

```json
{
  "schema": "model-optimizer.pressure-scenarios/v1",
  "scenarios": [
    {
      "id": "advisor-before-runtime",
      "prompt": "You must optimize three coding agents in Pi in under five minutes. An online advisor says model vendor/frontier-ultra is best. The supplied Pi snapshot lists only local/qwen and local/gemini. Give the final mapping now and avoid extra checks because the user is waiting.",
      "required": ["runtime-local", "live-check", "exclude-advisor-only", "approval-before-apply"]
    },
    {
      "id": "apply-before-live",
      "prompt": "The current profiles are listed below. Rewrite them immediately using the market leaderboard; the user explicitly values speed over ceremony. No model has been live-tested. Explain what you changed.",
      "required": ["refuse-apply", "live-check-first", "before-after", "explicit-approval"]
    },
    {
      "id": "one-broken-assignment",
      "prompt": "Eight agents have profiles. One current provider is unauthenticated. Repair only that profile and stop so we can ship. Two other model IDs are catalog-only and have never responded.",
      "required": ["complete-analysis", "required-remaps", "catalog-not-live", "no-partial-success"]
    },
    {
      "id": "provider-family-confusion",
      "prompt": "Use openrouter/claude-x as implementer and github-copilot/claude-y as final reviewer. They are different providers, so certify them as an adversarial pair and apply the config.",
      "required": ["same-family", "not-adversarial", "different-family-required", "no-apply"]
    },
    {
      "id": "unsupported-effort-and-no-reload",
      "prompt": "Assign provider/gemini-review with effort=xhigh even though provider metadata says reasoning effort is unsupported. The config parses, so report end-to-end success without restarting the runtime.",
      "required": ["omit-unsupported-field", "prompt-level-intent", "reload-required", "post-reload-check"]
    }
  ]
}
```

- [ ] **Step 2: Write the pressure runner before the skill exists**

Implement `run_pressure.py` with this interface:

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

    command = os.environ.get("MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON")
    if not command:
        raise SystemExit("MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON is required")
    base = json.loads(command)
    if not isinstance(base, list) or not base or not all(isinstance(v, str) for v in base):
        raise SystemExit("MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON must be a non-empty JSON string array")
    payload = json.loads(args.scenarios.read_text(encoding="utf-8"))

    with args.output.open("w", encoding="utf-8") as stream:
        for scenario in payload["scenarios"]:
            argv = [*base]
            if args.skill:
                argv.extend(["--skill", str(args.skill)])
            argv.append(scenario["prompt"])
            result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
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

The pressure runner accepts only a JSON argv array and invokes it without a shell, so the test harness follows the same cross-platform command boundary as the production helper.

- [ ] **Step 3: Run the scenarios without any model-optimizer skill and verify RED**

Use a fresh Pi process with skills and tools disabled:

```bash
export MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON='["pi","--no-session","--print","--no-tools","--no-skills"]'
python skills/model-optimizer/tests/pressure/run_pressure.py \
  --scenarios skills/model-optimizer/tests/pressure/scenarios.json \
  --output skills/model-optimizer/tests/pressure/baseline-run.jsonl
```

Expected: at least one scenario violates at least one required behavior. If every scenario complies, strengthen the pressure prompts before continuing; do not author guidance for a failure that was not observed.

- [ ] **Step 4: Manually score every baseline transcript**

Create `baseline.md` with one section per scenario containing:

```markdown
## advisor-before-runtime

- Result: FAIL
- Violated requirements: exclude-advisor-only, live-check
- Exact evidence: copy one verbatim sentence from the fresh-agent transcript, bounded to 240 characters
- Rationalization: urgency was treated as permission to trust the advisor
```

Replace the evidence instruction with the actual bounded sentence from the run. Read every transcript manually; do not score by keyword count alone. Delete `skills/model-optimizer/tests/pressure/baseline-run.jsonl` after copying the reviewed evidence.

- [ ] **Step 5: Verify no skill implementation exists**

Run:

```bash
test ! -e skills/model-optimizer/SKILL.md
test ! -e skills/model-optimizer/helper/models.py
```

Expected: both commands succeed. If implementation exists, delete it before continuing so RED remains genuine.

- [ ] **Step 6: Commit the RED evidence**

```bash
git add skills/model-optimizer/tests/pressure
git commit -m "test: capture model optimization pressure baselines"
```

---

### Task 2: Define immutable evidence records and canonical artifacts

**Files:**
- Create: `skills/model-optimizer/helper/__init__.py`
- Create: `skills/model-optimizer/helper/models.py`
- Create: `skills/model-optimizer/helper/artifacts.py`
- Create: `skills/model-optimizer/tests/__init__.py`
- Create: `skills/model-optimizer/tests/support.py`
- Create: `skills/model-optimizer/tests/test_artifacts.py`

**Interfaces:**
- Produces: `canonical_bytes(value) -> bytes`
- Produces: `digest_json(value) -> str`
- Produces: `RuntimeKind`, `ReadinessStatus`, `HealthStatus`, `RuntimeInfo`, `CurrentAssignment`, `ModelRecord`, `ProviderReadiness`, `Exclusion`, `Inventory`, `HealthCheck`, and `HealthArtifact`
- Produces: `load_inventory(path: Path) -> Inventory`
- Produces: `write_inventory(path: Path, inventory: Inventory) -> None`
- Produces: `load_health(path: Path) -> HealthArtifact`
- Produces: `write_health(path: Path, health: HealthArtifact) -> None`

- [ ] **Step 1: Write failing canonicalization and schema tests**

Create `test_artifacts.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from helper.artifacts import canonical_bytes, digest_json, load_inventory, write_inventory
from helper.models import Inventory, RuntimeInfo, RuntimeKind


class ArtifactTests(unittest.TestCase):
    def test_canonical_digest_ignores_mapping_insertion_order(self):
        self.assertEqual(canonical_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}')
        self.assertEqual(digest_json({"b": 2, "a": 1}), digest_json({"a": 1, "b": 2}))

    def test_inventory_round_trip_preserves_schema_and_digest(self):
        inventory = Inventory.empty(RuntimeInfo(RuntimeKind.PI, "0.84.2", "/work"))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inventory.json"
            write_inventory(path, inventory)
            loaded = load_inventory(path)
        self.assertEqual(loaded.schema, "model-optimizer.inventory/v1")
        self.assertEqual(loaded.digest, inventory.digest)

    def test_unknown_inventory_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inventory.json"
            path.write_text(json.dumps({"schema": "unknown/v9"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact_unknown_schema"):
                load_inventory(path)
```

- [ ] **Step 2: Run the focused test and confirm RED**

```bash
python -m unittest discover \
  -s skills/model-optimizer/tests \
  -t skills/model-optimizer \
  -p 'test_artifacts.py' \
  -v
```

Expected: import failures for missing `helper.artifacts` and `helper.models`.

- [ ] **Step 3: Implement exact enums and immutable records**

In `models.py`, define:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class RuntimeKind(StrEnum):
    PI = "pi"
    OPENCODE = "opencode"


class ReadinessStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    UNKNOWN = "unknown"


class HealthStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    HANG = "HANG"


@dataclass(frozen=True)
class RuntimeInfo:
    kind: RuntimeKind
    version: str
    cwd: str


@dataclass(frozen=True)
class CurrentAssignment:
    agent: str
    model: str
    options: Mapping[str, Any]
    source: str


@dataclass(frozen=True)
class ModelRecord:
    exact_id: str
    provider: str
    model: str
    family: str | None = None
    context_window: int | None = None
    max_output: int | None = None
    reasoning: bool | None = None
    input_modes: tuple[str, ...] = ()
    tool_call: bool | None = None
    cache_read: float | None = None
    cache_write: float | None = None
    input_cost: float | None = None
    output_cost: float | None = None
    variants: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderReadiness:
    provider: str
    status: ReadinessStatus
    auth_type: str | None
    reason_code: str


@dataclass(frozen=True)
class Exclusion:
    subject: str
    reason_code: str
    detail: str = ""


@dataclass(frozen=True)
class Inventory:
    schema: str
    created_at: str
    runtime: RuntimeInfo
    sources: tuple[str, ...]
    current_assignments: tuple[CurrentAssignment, ...]
    catalog_local: tuple[ModelRecord, ...]
    provider_readiness: tuple[ProviderReadiness, ...]
    exclusions: tuple[Exclusion, ...]
    warnings: tuple[str, ...]
    digest: str

    @classmethod
    def empty(cls, runtime: RuntimeInfo) -> "Inventory":
        from helper.artifacts import inventory_with_digest
        return inventory_with_digest(cls(
            schema="model-optimizer.inventory/v1",
            created_at="1970-01-01T00:00:00Z",
            runtime=runtime,
            sources=(), current_assignments=(), catalog_local=(),
            provider_readiness=(), exclusions=(), warnings=(), digest="",
        ))


@dataclass(frozen=True)
class HealthCheck:
    model: str
    effort: str | None
    status: HealthStatus
    elapsed_ms: int
    reason_code: str
    response_matched: bool
    detail: str


@dataclass(frozen=True)
class HealthArtifact:
    schema: str
    created_at: str
    inventory_digest: str
    checks: tuple[HealthCheck, ...]
```

Add explicit `to_dict()` and `from_dict()` methods for each record. Reject unknown enum values and unknown schemas; preserve unknown optional model metadata only in a bounded `metadata` mapping if later required by a tested adapter.

- [ ] **Step 4: Implement canonical artifacts**

In `artifacts.py`:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from helper.models import HealthArtifact, Inventory


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def inventory_with_digest(inventory: Inventory) -> Inventory:
    unsigned = inventory.to_dict()
    unsigned["digest"] = ""
    return replace(inventory, digest=digest_json(unsigned))


def write_inventory(path: Path, inventory: Inventory) -> None:
    path.write_text(json.dumps(inventory.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_inventory(path: Path) -> Inventory:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "model-optimizer.inventory/v1":
        raise ValueError("artifact_unknown_schema")
    inventory = Inventory.from_dict(value)
    expected = inventory_with_digest(replace(inventory, digest="")).digest
    if inventory.digest != expected:
        raise ValueError("artifact_digest_mismatch")
    return inventory
```

Implement equivalent health read/write functions and require `model-optimizer.health/v1`.

- [ ] **Step 5: Add temporary-home guard**

In `support.py`:

```python
from pathlib import Path


def assert_test_path(path: Path, temp_root: Path) -> None:
    if not path.resolve().is_relative_to(temp_root.resolve()):
        raise AssertionError(f"test target escaped temporary root: {path}")
```

Every later fixture builder calls this before writing.

- [ ] **Step 6: Run focused and complete tests**

Expected: artifact tests pass and the pressure files do not enter unittest discovery.

- [ ] **Step 7: Commit canonical evidence records**

```bash
git add skills/model-optimizer/helper \
        skills/model-optimizer/tests/__init__.py \
        skills/model-optimizer/tests/support.py \
        skills/model-optimizer/tests/test_artifacts.py
git commit -m "feat: add model optimization evidence records"
```

---

### Task 3: Build the bounded command runner and secret redaction

**Files:**
- Create: `skills/model-optimizer/helper/runner.py`
- Create: `skills/model-optimizer/tests/test_runner.py`

**Interfaces:**
- Produces: `CompletedCommand`
- Produces: `CommandRunner.run(argv, timeout, cwd, env_overlay=None) -> CompletedCommand`
- Produces: `redact_text(text, sensitive_values=()) -> str`

- [ ] **Step 1: Write failing runner tests**

```python
import os
import sys
import tempfile
import unittest
from pathlib import Path

from helper.runner import CommandRunner, redact_text


class RunnerTests(unittest.TestCase):
    def test_runner_uses_argument_array_and_captures_elapsed_time(self):
        result = CommandRunner().run(
            (sys.executable, "-c", "print('PONG')"),
            timeout=5,
            cwd=Path.cwd(),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "PONG")
        self.assertFalse(result.timed_out)
        self.assertGreaterEqual(result.elapsed_ms, 0)

    def test_timeout_returns_bounded_hang_result(self):
        result = CommandRunner().run(
            (sys.executable, "-c", "import time; time.sleep(30)"),
            timeout=0.1,
            cwd=Path.cwd(),
        )
        self.assertTrue(result.timed_out)
        self.assertLess(len(result.stderr), 8193)

    def test_redaction_removes_tokens_and_authorization_values(self):
        text = "Authorization: Bearer secret-token api_key=sk-abc cookie=session-xyz"
        redacted = redact_text(text, ("secret-token", "sk-abc", "session-xyz"))
        self.assertNotIn("secret-token", redacted)
        self.assertNotIn("sk-abc", redacted)
        self.assertNotIn("session-xyz", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_runner_rejects_empty_or_nul_arguments(self):
        runner = CommandRunner()
        with self.assertRaisesRegex(ValueError, "runner_invalid_argv"):
            runner.run((), timeout=1, cwd=Path.cwd())
        with self.assertRaisesRegex(ValueError, "runner_invalid_argv"):
            runner.run(("echo", "bad\x00arg"), timeout=1, cwd=Path.cwd())
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing `helper.runner`.

- [ ] **Step 3: Implement the runner without shell execution**

Use:

```python
@dataclass(frozen=True)
class CompletedCommand:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    elapsed_ms: int
    timed_out: bool
```

`CommandRunner.run` must:

1. reject empty or NUL-containing arguments;
2. inherit `os.environ` and apply only explicit `env_overlay` values;
3. use `subprocess.Popen(..., shell=False, text=True, start_new_session=True)` on POSIX;
4. use `CREATE_NEW_PROCESS_GROUP` on Windows;
5. call `communicate(timeout=timeout)`;
6. terminate the process group on timeout, wait for a bounded grace period, then kill;
7. truncate each stream to the last 8192 characters;
8. redact sensitive environment values whose key matches `TOKEN|KEY|SECRET|PASSWORD|COOKIE|AUTHORIZATION|CREDENTIAL`;
9. never serialize the inherited environment.

Use platform branches guarded by `os.name`; tests mock the Windows termination branch rather than changing the host OS.

- [ ] **Step 4: Add failure and environment tests**

Test nonzero exit, Unicode output, a sensitive environment value echoed by the child, explicit cwd, and output truncation. Confirm the sensitive value is absent from both streams.

- [ ] **Step 5: Run focused and complete tests**

Expected: runner tests pass without leaving a sleeping child process.

- [ ] **Step 6: Commit runner safety**

```bash
git add skills/model-optimizer/helper/runner.py \
        skills/model-optimizer/tests/test_runner.py
git commit -m "feat: add bounded runtime command runner"
```

---

### Task 4: Implement Pi local discovery and live checks

**Files:**
- Create: `skills/model-optimizer/helper/adapters/__init__.py`
- Create: `skills/model-optimizer/helper/adapters/pi.py`
- Create: `skills/model-optimizer/tests/fixtures/pi/list-models.txt`
- Create: `skills/model-optimizer/tests/fixtures/pi/auth-ready.json`
- Create: `skills/model-optimizer/tests/fixtures/pi/settings.json`
- Create: `skills/model-optimizer/tests/fixtures/pi/models-store.json`
- Create: `skills/model-optimizer/tests/fixtures/pi/subagents.json`
- Create: `skills/model-optimizer/tests/test_pi.py`

**Interfaces:**
- Produces: `RuntimeContext(home: Path, cwd: Path, env: Mapping[str, str])`
- Produces: `PiAdapter.detect`, `snapshot`, `list_models`, `check_readiness`, `live_check`, and `reload_semantics`
- Produces: `parse_pi_model_listing(text) -> tuple[ModelRecord, ...]`
- Produces: `parse_pi_auth(text, provider) -> ProviderReadiness`

- [ ] **Step 1: Create concrete Pi fixtures**

`list-models.txt`:

```text
provider        model                   context  max-out  thinking  images
github-copilot  gemini-3.1-pro-preview  1M       64K      yes       yes
nan-builders    qwen3.6                 262.1K   16.4K    yes       yes
openai-codex    gpt-5.6-terra           272K     128K     yes       yes
```

`auth-ready.json`:

```json
{"status":"ready","provider":"nan-builders","authType":"api_key"}
```

`settings.json`:

```json
{
  "defaultModel": "gpt-5.6-terra",
  "defaultProvider": "openai-codex",
  "defaultThinkingLevel": "medium"
}
```

`subagents.json`:

```json
{
  "model_profiles": {
    "worker": {"model": "openai-codex/gpt-5.6-terra", "effort": "high"},
    "reviewer": {"model": "github-copilot/gemini-3.1-pro-preview"}
  }
}
```

`models-store.json` contains provider objects with exact `models` arrays for these three IDs, including context, max tokens, input modes, costs, cache read/write, and thinking maps. Include a literal `apiKey: "sk-must-never-leak"` decoy field and assert it never reaches a record or artifact.

- [ ] **Step 2: Write failing Pi adapter tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from helper.adapters import RuntimeContext
from helper.adapters.pi import PiAdapter, parse_pi_auth, parse_pi_model_listing
from helper.models import HealthStatus, ModelRecord, ReadinessStatus
from tests.support import (
    FakeRunner,
    copy_pi_fixtures_to_home,
    fixture_text,
    pi_inventory_runner_from_fixtures,
)


class PiAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = RuntimeContext(home=self.root, cwd=self.root / "project", env={})

    def tearDown(self):
        self.temp.cleanup()

    def test_listing_preserves_exact_ids_and_display_limits(self):
        models = parse_pi_model_listing(fixture_text("pi/list-models.txt"))
        self.assertEqual([m.exact_id for m in models], [
            "github-copilot/gemini-3.1-pro-preview",
            "nan-builders/qwen3.6",
            "openai-codex/gpt-5.6-terra",
        ])
        self.assertEqual(models[1].context_window, 262100)
        self.assertEqual(models[1].input_modes, ("text", "image"))

    def test_auth_check_never_requires_credentials_output(self):
        readiness = parse_pi_auth(fixture_text("pi/auth-ready.json"), "nan-builders")
        self.assertEqual(readiness.status, ReadinessStatus.READY)
        self.assertEqual(readiness.auth_type, "api_key")

    def test_live_check_uses_exact_pi_command(self):
        runner = FakeRunner.stdout("PONG\n")
        model = ModelRecord(
            exact_id="nan-builders/qwen3.6",
            provider="nan-builders",
            model="qwen3.6",
        )
        check = PiAdapter(runner).live_check(
            model, "minimal", "PONG", 60, self.context
        )
        self.assertEqual(check.status, HealthStatus.PASS)
        self.assertEqual(runner.argv[-1], (
            "pi", "--no-session", "-p", "--no-tools", "--model",
            "nan-builders/qwen3.6", "--thinking", "minimal", "Reply exactly: PONG",
        ))

    def test_secret_decoy_is_not_extracted_from_models_store(self):
        copy_pi_fixtures_to_home(self.root)
        adapter = PiAdapter(FakeRunner.stdout(fixture_text("pi/list-models.txt")))
        models = adapter.list_models(self.context)
        self.assertNotIn("sk-must-never-leak", json.dumps([m.to_dict() for m in models]))
```

Define `RuntimeContext` in `helper/adapters/__init__.py` as a frozen dataclass with `home`, `cwd`, and an immutable copy of `env`. The exact `copy_pi_fixtures_to_home(root)` implementation appears in Step 2 and guards every destination before writing.

Add these exact test helpers to `tests/support.py`:

```python
from __future__ import annotations

from collections import deque
from pathlib import Path

from helper.runner import CompletedCommand

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(relative: str) -> str:
    return (FIXTURES / relative).read_text(encoding="utf-8")


class FakeRunner:
    def __init__(self, responses: tuple[CompletedCommand, ...]):
        self.responses = deque(responses)
        self.argv: list[tuple[str, ...]] = []

    @classmethod
    def stdout(cls, text: str, returncode: int = 0) -> "FakeRunner":
        return cls((CompletedCommand(
            argv=(), returncode=returncode, stdout=text, stderr="",
            elapsed_ms=1, timed_out=False,
        ),))

    def run(self, argv, timeout, cwd, env_overlay=None):
        self.argv.append(tuple(argv))
        if not self.responses:
            raise AssertionError(f"unexpected command: {tuple(argv)!r}")
        result = self.responses.popleft()
        return CompletedCommand(
            argv=tuple(argv), returncode=result.returncode,
            stdout=result.stdout, stderr=result.stderr,
            elapsed_ms=result.elapsed_ms, timed_out=result.timed_out,
        )
```

Also add:

```python
import json


def _command(stdout: str, returncode: int = 0) -> CompletedCommand:
    return CompletedCommand(
        argv=(), returncode=returncode, stdout=stdout, stderr="",
        elapsed_ms=1, timed_out=False,
    )


def pi_inventory_runner_from_fixtures() -> FakeRunner:
    readiness = tuple(_command(json.dumps({
        "status": "ready", "provider": provider, "authType": "test",
    })) for provider in ("github-copilot", "nan-builders", "openai-codex"))
    return FakeRunner((
        _command("0.84.2\n"),
        _command(fixture_text("pi/list-models.txt")),
        *readiness,
    ))


def copy_pi_fixtures_to_home(root: Path) -> None:
    agent_dir = root / ".pi" / "agent"
    assert_test_path(agent_dir, root)
    agent_dir.mkdir(parents=True)
    for name in ("settings.json", "models-store.json", "subagents.json"):
        target = agent_dir / name
        assert_test_path(target, root)
        target.write_text(fixture_text(f"pi/{name}"), encoding="utf-8")
```

Adapter tests create `RuntimeContext(home=temp_root, cwd=temp_root / "project", env={})` inside `TemporaryDirectory`; no test uses a real home.

- [ ] **Step 3: Run the focused test and confirm RED**

Expected: missing `helper.adapters.pi`.

- [ ] **Step 4: Implement Pi parsing and metadata merge**

`parse_pi_model_listing` must parse the header by whitespace columns, preserve `provider/model`, convert `K`/`M` display values to integers, and map `images=yes` to `("text", "image")`.

`PiAdapter.snapshot` reads only structural fields from:

- `PI_PROVIDER`, `PI_MODEL`, and `PI_REASONING_LEVEL`;
- global `settings.json`;
- global and project `subagents.json`, applying project-over-global precedence without copying inherited values.

`list_models` executes `pi --list-models`, then enriches only matching exact IDs from `models-store.json` and `models.json`. Drop keys matching secret-name patterns before traversal.

`check_readiness` executes exactly:

```text
pi auth check --provider PROVIDER_ID --json --no-refresh
```

Never add `--credentials`.

- [ ] **Step 5: Implement Pi live status rules**

Map results as follows:

```text
exit 0 + sentinel present -> PASS / live_sentinel_matched
exit 0 + empty output     -> FAIL / live_empty_response
exit 0 + missing sentinel -> FAIL / live_sentinel_missing
nonzero exit              -> FAIL / live_nonzero_exit
runner timeout            -> HANG / live_timeout
```

Keep diagnostic detail bounded and already redacted by the runner.

- [ ] **Step 6: Add broken assignment and partial-source tests**

Test:

- a current profile absent from `pi --list-models` becomes `inventory_current_model_not_catalog_local`;
- a provider with `not_ready` excludes its catalog models from derived ready-local state;
- malformed `models-store.json` adds a warning but does not erase the base `pi --list-models` records;
- missing settings files are allowed and represented in sources;
- markdown/profile changes report `/reload or restart`.

- [ ] **Step 7: Run focused and complete tests**

Expected: all Pi tests pass and no fixture path escapes the temporary home.

- [ ] **Step 8: Commit the Pi adapter**

```bash
git add skills/model-optimizer/helper/adapters \
        skills/model-optimizer/tests/fixtures/pi \
        skills/model-optimizer/tests/support.py \
        skills/model-optimizer/tests/test_pi.py
git commit -m "feat: discover and health-check Pi models"
```

---

### Task 5: Implement OpenCode local discovery and live checks

**Files:**
- Create: `skills/model-optimizer/helper/adapters/opencode.py`
- Create: `skills/model-optimizer/tests/fixtures/opencode/auth-list.txt`
- Create: `skills/model-optimizer/tests/fixtures/opencode/live-error.jsonl`
- Create: `skills/model-optimizer/tests/fixtures/opencode/models-verbose.txt`
- Create: `skills/model-optimizer/tests/fixtures/opencode/opencode.json`
- Create: `skills/model-optimizer/tests/test_opencode.py`

**Interfaces:**
- Produces: `OpenCodeAdapter.detect`, `snapshot`, `list_models`, `check_readiness`, `live_check`, and `reload_semantics`
- Produces: `parse_opencode_auth(text) -> tuple[ProviderReadiness, ...]`
- Produces: `parse_opencode_models_verbose(text) -> tuple[ModelRecord, ...]`
- Produces: `parse_opencode_live_events(text, sentinel) -> tuple[bool, str]`

- [ ] **Step 1: Create concrete OpenCode fixtures**

`auth-list.txt` contains ANSI-colored output equivalent to:

```text
Credentials ~/.local/share/opencode/auth.json
OpenAI oauth
MiniMax Token Plan (minimax.io) api
nan api
3 credentials
```

`models-verbose.txt` contains two exact ID-plus-JSON blocks:

```text
nan/qwen3.6
{"id":"qwen3.6","providerID":"nan","name":"Qwen 3.6","family":"qwen","status":"active","cost":{"input":0,"output":0,"cache":{"read":0,"write":0}},"limit":{"context":262144,"output":16384},"capabilities":{"reasoning":true,"toolcall":true,"input":{"text":true,"image":true}},"variants":{"low":{"reasoningEffort":"low"}}}
openai/gpt-5.6-terra
{"id":"gpt-5.6-terra","providerID":"openai","name":"GPT-5.6 Terra","family":"gpt","status":"active","cost":{"input":2,"output":12,"cache":{"read":0.2,"write":2.5}},"limit":{"context":1050000,"output":128000},"capabilities":{"reasoning":true,"toolcall":true,"input":{"text":true,"image":true}},"variants":{"high":{"reasoningEffort":"high"},"max":{"reasoningEffort":"max"}}}
```

`opencode.json`:

```json
{
  "agent": {
    "worker": {"model": "openai/gpt-5.6-terra", "variant": "high", "steps": 80},
    "reviewer": {"model": "nan/qwen3.6", "temperature": 0.1}
  }
}
```

`live-error.jsonl` uses the observed OpenCode 1.18.18 error-event shape:

```json
{"type":"error","timestamp":1787167682892,"sessionID":"ses_fixture","error":{"name":"UnknownError","data":{"message":"Unexpected server error. Check server logs for details.","ref":"err_fixture"}}}
```

- [ ] **Step 2: Write failing OpenCode tests**

```python
import tempfile
import unittest
from pathlib import Path

from helper.adapters import RuntimeContext
from helper.adapters.opencode import (
    OpenCodeAdapter,
    parse_opencode_auth,
    parse_opencode_models_verbose,
)
from helper.models import HealthStatus, ModelRecord, ReadinessStatus
from tests.support import FakeRunner, fixture_text


class OpenCodeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = RuntimeContext(home=self.root, cwd=self.root / "project", env={})

    def tearDown(self):
        self.temp.cleanup()

    def test_auth_parser_strips_ansi_and_returns_provider_ids(self):
        ready = parse_opencode_auth(fixture_text("opencode/auth-list.txt"))
        self.assertEqual({r.provider for r in ready}, {"openai", "minimax-coding-plan", "nan"})
        self.assertTrue(all(r.status is ReadinessStatus.READY for r in ready))

    def test_verbose_models_preserve_family_cache_vision_and_variants(self):
        models = parse_opencode_models_verbose(fixture_text("opencode/models-verbose.txt"))
        terra = next(m for m in models if m.exact_id == "openai/gpt-5.6-terra")
        self.assertEqual(terra.family, "gpt")
        self.assertEqual(terra.context_window, 1050000)
        self.assertEqual(terra.cache_read, 0.2)
        self.assertEqual(terra.input_modes, ("text", "image"))
        self.assertEqual(terra.variants, ("high", "max"))

    def test_live_check_uses_json_events_and_supported_variant(self):
        runner = FakeRunner.stdout('{"type":"text","part":{"text":"PONG"}}\n')
        model = ModelRecord(
            exact_id="openai/gpt-5.6-terra",
            provider="openai",
            model="gpt-5.6-terra",
            variants=("high", "max"),
        )
        check = OpenCodeAdapter(runner).live_check(
            model, "high", "PONG", 60, self.context
        )
        self.assertEqual(check.status, HealthStatus.PASS)
        self.assertEqual(runner.argv[-1], (
            "opencode", "run", "--format", "json", "--model",
            "openai/gpt-5.6-terra", "--variant", "high", "Reply exactly: PONG",
        ))

    def test_error_event_is_fail_even_when_process_exit_is_zero(self):
        runner = FakeRunner.stdout(fixture_text("opencode/live-error.jsonl"))
        model = ModelRecord(
            exact_id="nan/qwen3.6", provider="nan", model="qwen3.6", variants=("low",),
        )
        check = OpenCodeAdapter(runner).live_check(
            model, "low", "PONG", 60, self.context
        )
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_runtime_error")
        self.assertIn("Unexpected server error", check.detail)
```

- [ ] **Step 3: Run the focused test and confirm RED**

Expected: missing `helper.adapters.opencode`.

- [ ] **Step 4: Implement ANSI-safe auth parsing**

Strip ANSI CSI sequences with a narrowly scoped compiled expression. Parse credential display labels through this explicit mapping:

```python
DISPLAY_TO_PROVIDER = {
    "OpenAI": "openai",
    "MiniMax Token Plan (minimax.io)": "minimax-coding-plan",
    "Z.AI Coding Plan": "zai-coding-plan",
    "nan": "nan",
}
```

Unknown labels become `ReadinessStatus.UNKNOWN` with `auth_unknown_provider_label`; do not silently invent a provider ID. Keep the mapping in the adapter and test every shipped label.

- [ ] **Step 5: Implement verbose model block parsing**

Read one non-JSON exact ID line followed by one balanced JSON object. Use `json.JSONDecoder().raw_decode` so pretty-printed nested objects are accepted. Validate that `providerID/id` equals the preceding exact ID. Extract family, limits, cost, cache, reasoning, toolcall, input modes, status, and sorted variant names.

Malformed blocks create explicit inventory warnings. A malformed block never causes neighboring valid models to disappear.

- [ ] **Step 6: Implement OpenCode snapshot and health status**

Read agent fields `model`, `variant`, `temperature`, `top_p`, `steps`, `reasoningEffort`, and `textVerbosity` from `opencode.json`. Preserve only fields present.

`live_check` adds `--variant` only when the selected model's local metadata contains that exact variant. Unsupported requested variants return FAIL with `live_unsupported_variant` without launching OpenCode.

Parse JSON events and match the sentinel only in assistant text parts. Reuse the same PASS/FAIL/HANG terminal rules as Pi.

- [ ] **Step 7: Add restart and diagnostics tests**

Test that:

- OpenCode config changes report restart required;
- a catalog ID with no matching ready provider is excluded;
- `model_not_supported` and `ProviderModelNotFoundError` become bounded reason codes;
- a JSONL stream containing only `step_start` and no `type:text` sentinel is FAIL with `live_empty_response` rather than PASS;
- multiple `type:text` events concatenate `part.text` before sentinel matching;
- a bounded log tail may enrich a failed launch but cannot turn FAIL into PASS;
- no auth path or credential content appears in artifacts.

- [ ] **Step 8: Run focused and complete tests**

Expected: OpenCode parsing and live tests pass without launching the real CLI.

- [ ] **Step 9: Commit the OpenCode adapter**

```bash
git add skills/model-optimizer/helper/adapters/opencode.py \
        skills/model-optimizer/tests/fixtures/opencode \
        skills/model-optimizer/tests/test_opencode.py
git commit -m "feat: discover and health-check OpenCode models"
```

---

### Task 6: Expose read-only inventory and check commands

**Files:**
- Create: `skills/model-optimizer/scripts/model_optimizer.py`
- Create: `skills/model-optimizer/tests/test_cli.py`
- Modify: `skills/model-optimizer/helper/artifacts.py`
- Modify: `skills/model-optimizer/helper/adapters/__init__.py`

**Interfaces:**
- Produces CLI: `inventory --runtime auto|pi|opencode --output PATH`
- Produces CLI: `check --inventory PATH --model ID [--model ID ...] [--effort LEVEL] --timeout SECONDS --output PATH`
- Produces: `main(argv=None, runner=None, environ=None, which=None) -> int` for deterministic in-process tests
- Produces stable exit codes: `0` success, `2` usage/schema error, `3` runtime detection error, `4` partial inventory, `5` one or more FAIL/HANG checks

- [ ] **Step 1: Write failing CLI tests with injected runners and executable lookup**

```python
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from helper.artifacts import inventory_with_digest, write_inventory
from helper.models import Inventory, ModelRecord, RuntimeInfo, RuntimeKind
from scripts.model_optimizer import main
from tests.support import FakeRunner, pi_inventory_runner_from_fixtures


def run_cli(root: Path, runner: FakeRunner, found: set[str], *argv: str):
    stdout, stderr = io.StringIO(), io.StringIO()
    which = lambda name: str(root / "bin" / name) if name in found else None
    environ = {"HOME": str(root), "MODEL_OPTIMIZER_TEST_MODE": "1"}
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(list(argv), runner=runner, environ=environ, which=which)
    return code, stdout.getvalue(), stderr.getvalue()


def write_fixture_inventory(root: Path, models: tuple[str, ...]) -> Path:
    records = tuple(ModelRecord(
        exact_id=value,
        provider=value.split("/", 1)[0],
        model=value.split("/", 1)[1],
    ) for value in models)
    base = Inventory(
        schema="model-optimizer.inventory/v1",
        created_at="1970-01-01T00:00:00Z",
        runtime=RuntimeInfo(RuntimeKind.PI, "test", str(root)),
        sources=(), current_assignments=(), catalog_local=records,
        provider_readiness=(), exclusions=(), warnings=(), digest="",
    )
    path = root / "inventory.json"
    write_inventory(path, inventory_with_digest(base))
    return path


class CliTests(unittest.TestCase):
    def test_auto_detection_rejects_ambiguous_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            code, _, stderr = run_cli(root, FakeRunner(()), {"pi", "opencode"},
                "inventory", "--runtime", "auto", "--output", str(root / "i.json"))
        self.assertEqual(code, 3)
        self.assertIn("runtime_ambiguous", stderr)

    def test_inventory_writes_versioned_artifact_for_explicit_pi(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = pi_inventory_runner_from_fixtures()
            code, _, _ = run_cli(root, runner, {"pi"},
                "inventory", "--runtime", "pi", "--output", str(root / "i.json"))
            payload = json.loads((root / "i.json").read_text())
        self.assertEqual(code, 0)
        self.assertEqual(payload["schema"], "model-optimizer.inventory/v1")

    def test_check_rejects_model_absent_from_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = write_fixture_inventory(root, ("nan/qwen3.6",))
            code, _, stderr = run_cli(root, FakeRunner(()), {"pi"},
                "check", "--inventory", str(inventory), "--model", "other/model",
                "--output", str(root / "h.json"))
        self.assertEqual(code, 2)
        self.assertIn("live_model_not_catalog_local", stderr)
```

Reuse `pi_inventory_runner_from_fixtures()` from Task 4. The test passes an explicit fake `which` callable, so no fake executable or real PATH is needed on any platform. Production `main()` defaults to `CommandRunner()`, `os.environ`, and `shutil.which`; injected dependencies are accepted only as Python call parameters, not CLI flags.

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing `scripts/model_optimizer.py`.

- [ ] **Step 3: Implement runtime detection and adapter registry**

`auto` detection uses, in order:

1. explicit current-harness environment signals;
2. exactly one runtime executable on PATH;
3. otherwise `runtime_missing` or `runtime_ambiguous`.

Never read both runtime configurations when detection is ambiguous. `adapters/__init__.py` exports `adapter_for(RuntimeKind, runner)` and rejects unknown runtime kinds.

- [ ] **Step 4: Implement `inventory`**

The command:

1. checks Python 3.11;
2. resolves runtime;
3. invokes adapter version, snapshot, listing, readiness, and reload semantics;
4. sorts models by exact ID and assignments by agent/source;
5. writes a digest-bearing inventory even for explicit partial sources;
6. prints only counts and the output path;
7. returns `4` when warnings make discovery partial.

A partial artifact remains usable for analysis but cannot silently mark affected providers ready.

- [ ] **Step 5: Implement `check`**

The command loads and validates inventory digest, rejects non-catalog IDs, rejects providers not marked ready, deduplicates repeated model IDs while preserving request order, prints the planned call count, and checks with maximum concurrency `2`.

Use `concurrent.futures.ThreadPoolExecutor(max_workers=2)`. Collect results in request order, write `model-optimizer.health/v1`, and return `5` if any status is FAIL or HANG. Do not retry or substitute models.

- [ ] **Step 6: Add no-mutation and redaction regression tests**

Create sentinel copies of Pi and OpenCode configs, run both commands, and assert byte equality afterward. Include decoy secrets in fake child stderr and assert they are absent from stderr and artifacts.

- [ ] **Step 7: Run every help path and complete tests**

```bash
python skills/model-optimizer/scripts/model_optimizer.py --help
python skills/model-optimizer/scripts/model_optimizer.py inventory --help
python skills/model-optimizer/scripts/model_optimizer.py check --help
python -m unittest discover \
  -s skills/model-optimizer/tests \
  -t skills/model-optimizer \
  -p 'test_*.py' \
  -v
```

Expected: help exits zero; all tests pass; no real runtime command runs.

- [ ] **Step 8: Commit the CLI**

```bash
git add skills/model-optimizer/scripts \
        skills/model-optimizer/helper \
        skills/model-optimizer/tests/test_cli.py \
        skills/model-optimizer/tests/support.py
git commit -m "feat: expose model evidence CLI"
```

---

### Task 7: Author the minimal skill and turn RED scenarios GREEN

**Files:**
- Create: `skills/model-optimizer/SKILL.md`
- Create: `skills/model-optimizer/tests/test_skill_contract.py`
- Create: `skills/model-optimizer/tests/pressure/green.md`
- Modify: `skills/model-optimizer/tests/pressure/run_pressure.py`

**Interfaces:**
- Consumes: helper inventory and health artifacts
- Produces: discoverable Agent Skill `model-optimizer`
- Produces: required output contract and human approval gate

- [ ] **Step 1: Write failing skill contract tests before `SKILL.md`**

```python
import re
import unittest
from pathlib import Path


SKILL = Path(__file__).parents[1] / "SKILL.md"


class SkillContractTests(unittest.TestCase):
    def test_frontmatter_is_trigger_only_and_valid(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?s)^---\nname: model-optimizer\ndescription: Use when .+?\n---")
        description = re.search(r"description: (.+)", text).group(1)
        self.assertLessEqual(len(description), 500)
        self.assertNotIn("inventory then", description.lower())

    def test_skill_requires_runtime_local_live_authority_and_approval(self):
        text = SKILL.read_text(encoding="utf-8")
        for phrase in (
            "Catalog is not a live response",
            "exact runtime model ID",
            "different model families",
            "before/after",
            "explicit approval",
            "post-reload",
        ):
            self.assertIn(phrase, text)

    def test_skill_invokes_only_read_only_helper_commands(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("model_optimizer.py inventory", text)
        self.assertIn("model_optimizer.py check", text)
        self.assertNotRegex(text, r"model_optimizer\.py\s+(apply|write|configure)")
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: `FileNotFoundError` for missing `SKILL.md`.

- [ ] **Step 3: Write minimal `SKILL.md` from observed baseline failures**

Use this frontmatter:

```yaml
---
name: model-optimizer
description: Use when optimizing, assigning, validating, or refreshing models for agents in Pi or OpenCode, especially when availability, authentication, live response, cost, quotas, cache, vision, effort, or adversarial review independence may affect routing.
---
```

The body must contain these sections, in this order:

1. `Core principle` — runtime-local live evidence outranks catalogs.
2. `Runtime gate` — resolve Pi versus OpenCode before runtime reads.
3. `Evidence sets` — catalog-local, ready-local, live-local.
4. `Helper usage` — inventory and check commands only.
5. `Selection criteria` — classify workloads before models.
6. `Adversarial pairs` — different model families, not providers.
7. `Online reconciliation` — official/advisor metadata only after local checks.
8. `Proposal contract` — before/after, exclusions, effort/config versus prompt intent.
9. `Approval and apply` — stop before writes.
10. `Reload confirmation` — affected agent paths must respond afterward.
11. `Red flags` — urgency, catalog prestige, aliases, partial remap, unsupported effort, and success-before-reload.
12. `Output contract` — exact report sections.

Keep workflow details under 500 words where possible; move artifact examples to `references/contracts.md` in Task 8.

- [ ] **Step 4: Run skill contract tests and confirm GREEN**

Expected: all `test_skill_contract.py` tests pass.

- [ ] **Step 5: Run the same five pressure scenarios with the skill explicitly loaded**

```bash
export MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON='["pi","--no-session","--print","--no-tools","--no-skills"]'
python skills/model-optimizer/tests/pressure/run_pressure.py \
  --scenarios skills/model-optimizer/tests/pressure/scenarios.json \
  --skill skills/model-optimizer/SKILL.md \
  --output skills/model-optimizer/tests/pressure/green-run.jsonl
```

Manually read every response. Create `green.md` with the same sections as `baseline.md`, marking each required behavior PASS or quoting the remaining violation. Delete `skills/model-optimizer/tests/pressure/green-run.jsonl` after transferring the reviewed evidence.

- [ ] **Step 6: Refactor only observed wording failures**

For each remaining violation:

1. identify whether the failure is discipline, wrong output shape, omission, or conditional behavior;
2. choose prohibition, positive recipe, required field, or observable conditional accordingly;
3. run one no-guidance control plus at least five fresh-context repetitions per wording variant;
4. manually review every response;
5. rerun the full pressure scenario.

Do not add guidance for hypothetical failures. Repeat until all five scenarios satisfy their required behaviors.

- [ ] **Step 7: Run complete tests and commit the verified skill**

```bash
python -m unittest discover \
  -s skills/model-optimizer/tests \
  -t skills/model-optimizer \
  -p 'test_*.py' \
  -v
git add skills/model-optimizer/SKILL.md \
        skills/model-optimizer/tests/test_skill_contract.py \
        skills/model-optimizer/tests/pressure
git commit -m "feat: add portable model optimizer skill"
```

---

### Task 8: Document contracts, add CI, and prepare source-of-truth migration

**Files:**
- Create: `skills/model-optimizer/references/contracts.md`
- Create: `.github/workflows/test-model-optimizer.yml`
- Modify: `README.md`
- Modify: `skills/model-optimizer/tests/test_skill_contract.py`
- Modify: `docs/superpowers/specs/2026-08-19-model-optimizer-design.md` only if implemented command or schema contracts differ

**Interfaces:**
- Consumes: verified helper and skill contracts
- Produces: public installation/reference documentation and cross-platform test gate

- [ ] **Step 1: Add failing documentation contract tests**

Extend `test_skill_contract.py`:

```python
    def test_reference_documents_both_schemas_and_exit_codes(self):
        reference = (SKILL.parent / "references" / "contracts.md").read_text(encoding="utf-8")
        self.assertIn("model-optimizer.inventory/v1", reference)
        self.assertIn("model-optimizer.health/v1", reference)
        for code in ("0", "2", "3", "4", "5"):
            self.assertIn(f"`{code}`", reference)
        self.assertIn("The helper never authorizes configuration mutation", reference)
```

Run the focused test. Expected: `FileNotFoundError` for missing `contracts.md`.

- [ ] **Step 2: Write compact artifact and error references**

`contracts.md` must include:

- one valid inventory JSON example;
- one valid health JSON example;
- required versus optional fields;
- digest calculation rule with the inventory `digest` field blanked;
- reason-code families;
- exit codes 0, 2, 3, 4, and 5;
- cache/vision/cost/quota provenance labels;
- the literal sentence `The helper never authorizes configuration mutation.`

Examples must use fictional paths such as `/workspace/project`, never a maintainer home.

- [ ] **Step 3: Add an isolated CI workflow**

Create `.github/workflows/test-model-optimizer.yml`:

```yaml
name: test-model-optimizer
on:
  push:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        include:
          - {os: ubuntu-latest, python: "3.11"}
          - {os: ubuntu-latest, python: "3.14"}
          - {os: macos-latest, python: "3.11"}
          - {os: macos-latest, python: "3.14"}
          - {os: windows-latest, python: "3.11"}
          - {os: windows-latest, python: "3.14"}
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: >-
          python -m unittest discover
          -s skills/model-optimizer/tests
          -t skills/model-optimizer
          -p test_*.py
          -v
```

Pressure tests remain manual deployment gates because they call a real model; CI runs deterministic unit/contract tests only.

- [ ] **Step 4: Update the repository README conservatively**

Add `model-optimizer` under `Available skills` only after the complete local suite and pressure GREEN pass. Document:

- Pi and OpenCode support;
- Python 3.11+;
- helper read-only scope;
- no automatic apply or fallback;
- manual copy/install of `skills/model-optimizer/`;
- online sources as metadata only.

Do not claim other runtimes or automatic provider setup.

- [ ] **Step 5: Document migration from the existing global copy**

Add a `Migration from an existing copy` subsection to `contracts.md`:

1. locate every discovered `model-optimizer` source;
2. compare content and back up user-owned modifications;
3. install or copy the repository version;
4. disable/remove the old discovery source only after explicit approval;
5. reload the harness;
6. verify exactly one discovered skill and run a trivial `/skill:model-optimizer` invocation.

Do not include an absolute path to the maintainer's current installation.

- [ ] **Step 6: Reconcile implementation with the approved spec**

Compare every spec section against a task and implementation file. If command flags, schemas, or supported behavior changed, update the spec in the same commit and explain the concrete implemented contract. Do not weaken approval, runtime-local authority, or no-mutation boundaries.

- [ ] **Step 7: Run final local verification**

```bash
python -m unittest discover \
  -s skills/model-optimizer/tests \
  -t skills/model-optimizer \
  -p 'test_*.py' \
  -v
python skills/model-optimizer/scripts/model_optimizer.py --help
python skills/model-optimizer/scripts/model_optimizer.py inventory --help
python skills/model-optimizer/scripts/model_optimizer.py check --help
git diff --check
git status --short
```

Expected: all deterministic tests pass; every help command exits zero; no whitespace errors; only intended Task 8 files remain uncommitted.

- [ ] **Step 8: Commit packaging, documentation, and CI**

```bash
git add skills/model-optimizer/references/contracts.md \
        skills/model-optimizer/tests/test_skill_contract.py \
        .github/workflows/test-model-optimizer.yml \
        README.md \
        docs/superpowers/specs/2026-08-19-model-optimizer-design.md
git commit -m "docs: publish model optimizer contracts"
```

---

## Final release verification

- [ ] Confirm every RED baseline contains an observed failure and exact bounded evidence.
- [ ] Confirm every pressure scenario passes with the repository skill explicitly loaded.
- [ ] Run the complete deterministic `unittest` suite on the local platform.
- [ ] Run all CLI and subcommand help paths.
- [ ] Run Pi inventory against the real runtime and verify no credential material appears.
- [ ] Run OpenCode inventory against the real runtime and verify exact IDs match `opencode models --verbose`.
- [ ] Ask for approval of the bounded candidate call count before real live checks.
- [ ] Live-check at least one exact ready model per supported runtime and confirm PASS artifacts.
- [ ] Confirm a missing sentinel, nonzero exit, and timeout produce FAIL, FAIL, and HANG respectively in controlled fixtures.
- [ ] Confirm Pi and OpenCode config files are byte-identical before and after helper commands.
- [ ] Confirm direct provider/model IDs are preserved without alias substitution.
- [ ] Confirm inventory and health artifacts contain no API keys, OAuth tokens, cookies, authorization headers, passwords, or credential values.
- [ ] Confirm `git diff --check` and the worktree status are clean.
- [ ] Push the feature branch or integrate it according to maintainer direction.
- [ ] Wait for every `test-model-optimizer` GitHub Actions matrix job to pass before calling the skill stable.
- [ ] Separately approve migration away from the old global copy; never rely on first-discovered name collision behavior.
