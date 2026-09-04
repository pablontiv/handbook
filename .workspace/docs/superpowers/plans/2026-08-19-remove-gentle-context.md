# Remove Gentle Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable Agent Skill that inventories, plans, backs up, removes, verifies, and restores active Gentle AI context without modifying Gentle AI or deleting preserved infrastructure and history.

**Architecture:** A Python 3.11+ standard-library helper provides canonical artifacts, digest-bound approval, a transactional mutation engine, and programmatic adapters for Claude, Codex/ChatGPT, OpenCode, and Pi. Versioned JSON adapters cover simple Gemini, Kimi, Hermes, and VS Code Copilot surfaces; unsupported or ambiguous mutations fail closed.

**Tech Stack:** Python 3.11-3.14 standard library, `unittest`, JSON, `tomllib`, GitHub Actions, Agent Skills Markdown.

**Spec:** `docs/superpowers/specs/2026-08-19-remove-gentle-context-design.md`

## Global Constraints

- Keep every skill self-contained under `skills/<name>/`; sibling skills must not depend on each other.
- Require Python 3.11 or newer and add no runtime dependency outside the standard library.
- Support macOS, Linux, and Windows without hard-coded user paths.
- Core clients are Claude, Codex/ChatGPT, OpenCode, and Pi.
- Declarative clients are Gemini, Kimi, Hermes, and VS Code Copilot.
- Preserve MCP, Engram, packages, binaries, source, backups, `.git/gentle-ai`, messages, and archived sessions.
- Treat historical prompt snapshots as report-only by default.
- Never authorize deletion from a textual match alone.
- Require exact SHA-256 plan approval and a hash-verified backup before mutation.
- Fail closed on ambiguous ownership, preimage drift, unsupported structures, symlinks, junctions, reparse points, or unavailable graceful lifecycle control.
- Tests must use temporary homes and must never read or mutate the real home.
- Use conventional commits and run the complete local test suite before every commit.
- Pull Requests stay disabled; implementation is delivered directly by the maintainer.

---

## Locked File Structure

```text
skills/remove-gentle-context/
├── SKILL.md                         # conversational orchestration contract
├── scripts/cleanup.py               # sole executable entrypoint
├── helper/
│   ├── __init__.py
│   ├── adapter.py                   # adapter protocol and registry
│   ├── canonical.py                 # canonical JSON and SHA-256 digests
│   ├── declarative.py               # constrained JSON adapter loader
│   ├── engine.py                    # inventory, planning, verification orchestration
│   ├── lifecycle.py                 # graceful client stop/restart
│   ├── models.py                    # versioned domain records and enums
│   ├── paths.py                     # platform roots and path safety
│   ├── transaction.py               # backup, apply, rollback, restore
│   └── clients/
│       ├── __init__.py
│       ├── claude.py
│       ├── codex.py
│       ├── opencode.py
│       └── pi.py
├── adapters/
│   ├── gemini.json
│   ├── kimi.json
│   ├── hermes.json
│   └── vscode-copilot.json
├── references/
│   ├── contracts.md                 # human-readable schemas and invariants
│   └── ownership-catalog-v1.json    # versioned names, markers, and signatures
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   ├── claude/
    │   ├── codex/
    │   ├── declarative/
    │   ├── opencode/
    │   └── pi/
    ├── support.py
    ├── test_cli.py
    ├── test_declarative.py
    ├── test_engine.py
    ├── test_lifecycle.py
    ├── test_models_paths.py
    ├── test_transaction.py
    └── clients/
        ├── __init__.py
        ├── test_claude.py
        ├── test_codex.py
        ├── test_opencode.py
        └── test_pi.py
.github/workflows/test.yml            # three-OS Python matrix
```

The command used throughout the plan is:

```bash
python -m unittest discover \
  -s skills/remove-gentle-context/tests \
  -t skills/remove-gentle-context \
  -v
```

---

### Task 1: Establish canonical models and safe platform paths

**Files:**
- Create: `skills/remove-gentle-context/helper/__init__.py`
- Create: `skills/remove-gentle-context/helper/canonical.py`
- Create: `skills/remove-gentle-context/helper/models.py`
- Create: `skills/remove-gentle-context/helper/paths.py`
- Create: `skills/remove-gentle-context/tests/__init__.py`
- Create: `skills/remove-gentle-context/tests/support.py`
- Create: `skills/remove-gentle-context/tests/test_models_paths.py`

**Interfaces:**
- Produces: `canonical_bytes(value: JsonValue) -> bytes`
- Produces: `digest_json(value: JsonValue) -> str`
- Produces: `PlatformProfile`, `RuntimeContext`, `Preimage`, `Candidate`, `Operation`, `LifecycleAction`, `PreservationAssertion`, `Inventory`, `Plan`, `Check`, `BackupManifest`, `OperationOutcome`, `CompletedCommand`, `ProcessSnapshot`, `LifecycleOutcome`, `VerificationResult`, and `Receipt`
- Produces: `resolve_state_root(profile: PlatformProfile) -> Path`
- Produces: `assert_safe_target(path: Path, allowed_roots: tuple[Path, ...]) -> os.stat_result`

- [ ] **Step 1: Write failing canonicalization and path-safety tests**

```python
# tests/test_models_paths.py
import os
import tempfile
import unittest
from pathlib import Path

from helper.canonical import canonical_bytes, digest_json
from helper.models import ArtifactClass, Candidate, Ownership, PlatformProfile
from helper.paths import assert_safe_target, resolve_state_root


class ModelsAndPathsTests(unittest.TestCase):
    def test_canonical_digest_ignores_mapping_insertion_order(self):
        left = {"b": 2, "a": 1}
        right = {"a": 1, "b": 2}
        self.assertEqual(canonical_bytes(left), b'{"a":1,"b":2}')
        self.assertEqual(digest_json(left), digest_json(right))

    def test_candidate_serializes_only_json_values(self):
        candidate = Candidate(
            candidate_id="sha256:abc",
            client="codex",
            path="/tmp/config.toml",
            artifact_class=ArtifactClass.ACTIVE_SOURCE,
            evidence=({"kind": "linked_selector", "value": "gentle-dev"},),
            ownership=Ownership.PROVEN,
            proposed_action="write_file",
            preimage=None,
            dependencies=(),
            reason="profile and selector are linked",
            details={},
        )
        self.assertEqual(candidate.to_dict()["ownership"], "proven")

    def test_state_root_uses_platform_conventions(self):
        self.assertEqual(
            resolve_state_root(PlatformProfile("linux", Path("/home/u"), {"XDG_STATE_HOME": "/state"})),
            Path("/state/remove-gentle-context"),
        )
        self.assertEqual(
            resolve_state_root(PlatformProfile("windows", Path("C:/Users/u"), {"LOCALAPPDATA": "C:/Local"})),
            Path("C:/Local/remove-gentle-context/state"),
        )

    def test_safe_target_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real.json"
            real.write_text("{}")
            link = root / "link.json"
            link.symlink_to(real)
            with self.assertRaisesRegex(ValueError, "preflight_unexpected_link"):
                assert_safe_target(link, (root,))
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```bash
python -m unittest discover \
  -s skills/remove-gentle-context/tests \
  -t skills/remove-gentle-context \
  -p 'test_models_paths.py' \
  -v
```

Expected: import failures for missing `helper.canonical`, `helper.models`, and `helper.paths`.

- [ ] **Step 3: Implement canonical JSON, immutable records, and platform roots**

```python
# helper/canonical.py
from __future__ import annotations

import hashlib
import json
from typing import TypeAlias

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def canonical_bytes(value: JsonValue) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest_json(value: JsonValue) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()
```

Implement the enums with `enum.StrEnum`, immutable records with `@dataclass(frozen=True)`, and explicit `to_dict()` methods. Use these exact enum values:

```python
ArtifactClass: active-source, runtime-state, generated-artifact,
               broken-registration, historical, preserved-infrastructure, ambiguous
Ownership: proven, ambiguous, preserved
OperationKind: write_file, delete_file, remove_empty_directory
ReceiptStatus: completed, rolled_back, manual_recovery_required, failed
```

`Plan.to_unsigned_dict()` must omit only `digest`; `Plan.with_digest()` must compute `digest_json(to_unsigned_dict())`. `Receipt` must carry operation outcomes, backup manifest path, lifecycle outcomes, checks, and status.

Implement `PlatformProfile(os_name: str, home: Path, env: Mapping[str, str])` and resolve state roots exactly as follows:

```python
linux:   $XDG_STATE_HOME/remove-gentle-context
         or ~/.local/state/remove-gentle-context
macos:   ~/Library/Application Support/remove-gentle-context/state
windows: %LOCALAPPDATA%/remove-gentle-context/state
```

`assert_safe_target` must use `os.lstat`, require containment under a caller-provided root, reject symbolic links, reject Windows `FILE_ATTRIBUTE_REPARSE_POINT`, and reject nonexistent parents that escape after `resolve(strict=False)`.

- [ ] **Step 4: Add a real-home test guard**

```python
# tests/support.py
from __future__ import annotations

from pathlib import Path


def assert_test_home(home: Path, temp_root: Path) -> None:
    resolved = home.resolve()
    if not resolved.is_relative_to(temp_root.resolve()):
        raise AssertionError(f"test target escaped temporary root: {resolved}")
```

Every later fixture builder must call `assert_test_home` before writing.

- [ ] **Step 5: Run focused and complete tests**

Run the focused test, then the repository command from the plan header.

Expected: all tests pass; no files are created outside temporary directories.

- [ ] **Step 6: Commit the foundation**

```bash
git add skills/remove-gentle-context/helper \
        skills/remove-gentle-context/tests
git commit -m "feat: add cleanup domain and path safety"
```

---

### Task 2: Define the adapter protocol and constrained declarative format

**Files:**
- Create: `skills/remove-gentle-context/helper/adapter.py`
- Create: `skills/remove-gentle-context/helper/declarative.py`
- Create: `skills/remove-gentle-context/adapters/gemini.json`
- Create: `skills/remove-gentle-context/adapters/kimi.json`
- Create: `skills/remove-gentle-context/adapters/hermes.json`
- Create: `skills/remove-gentle-context/adapters/vscode-copilot.json`
- Create: `skills/remove-gentle-context/references/ownership-catalog-v1.json`
- Create: `skills/remove-gentle-context/tests/fixtures/declarative/valid.json`
- Create: `skills/remove-gentle-context/tests/fixtures/declarative/forbidden-toml.json`
- Create: `skills/remove-gentle-context/tests/test_declarative.py`

**Interfaces:**
- Consumes: Task 1 records and `RuntimeContext`
- Produces: `Adapter` protocol
- Produces: `AdapterRegistry.register(adapter)` and `AdapterRegistry.for_client(client)`
- Produces: `load_declarative_adapter(path: Path) -> DeclarativeAdapter`
- Produces: `DeclarativeAdapter.inventory(context) -> tuple[Candidate, ...]`
- Produces: `DeclarativeAdapter.compile(candidate, context) -> tuple[Operation, ...]`
- Produces: `DeclarativeAdapter.verify(receipt, context) -> tuple[Check, ...]`

- [ ] **Step 1: Write failing capability-boundary tests**

```python
# tests/test_declarative.py
import json
import tempfile
import unittest
from pathlib import Path

from helper.declarative import load_declarative_adapter


class DeclarativeAdapterTests(unittest.TestCase):
    def test_loads_exact_file_and_json_array_rules(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "adapter.json"
            path.write_text(json.dumps({
                "schema": "remove-gentle-context.adapter/v1",
                "client": "gemini",
                "roots": {"config": {"kind": "home_relative", "path": ".gemini"}},
                "rules": [
                    {"id": "agent", "kind": "exact_file", "root": "config", "path": "agents/sdd-init.md"},
                    {"id": "hook", "kind": "json_array_value", "root": "config", "path": "settings.json", "pointer": "/hooks", "value": "gentle-hook"},
                ],
            }))
            adapter = load_declarative_adapter(path)
            self.assertEqual(adapter.client, "gemini")
            self.assertEqual(len(adapter.rules), 2)

    def test_rejects_toml_sqlite_runtime_and_arbitrary_text_rules(self):
        forbidden = ["toml_edit", "sqlite_update", "runtime_state", "regex_replace"]
        for kind in forbidden:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                path = Path(td) / "adapter.json"
                path.write_text(json.dumps({
                    "schema": "remove-gentle-context.adapter/v1",
                    "client": "bad",
                    "roots": {"config": {"kind": "home_relative", "path": ".bad"}},
                    "rules": [{"id": "bad", "kind": kind, "root": "config", "path": "state"}],
                }))
                with self.assertRaisesRegex(ValueError, "adapter_forbidden_capability"):
                    load_declarative_adapter(path)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing `helper.declarative`.

- [ ] **Step 3: Implement the protocol and schema validator**

```python
# helper/adapter.py
from typing import Protocol
from helper.models import Candidate, Check, Operation, Receipt, RuntimeContext


class Adapter(Protocol):
    client: str

    def inventory(self, context: RuntimeContext) -> tuple[Candidate, ...]: ...
    def compile(self, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]: ...
    def verify(self, receipt: Receipt, context: RuntimeContext) -> tuple[Check, ...]: ...
```

Implement `AdapterRegistry` as an insertion-ordered mapping keyed by the unique `adapter.client` value. `register` rejects duplicate clients with `adapter_duplicate_client`; `for_client` rejects missing clients with `adapter_unknown_client`.

The declarative loader must reject unknown top-level keys and accept only these rule kinds:

```text
exact_file
empty_directory
balanced_marker_block
json_key
json_array_value
```

`exact_file` and `empty_directory` require exact relative paths. JSON rules require RFC 6901 pointers. Marker rules require distinct literal open and close markers. No rule may contain regex, glob, recursive deletion, shell commands, TOML, SQLite, or lifecycle instructions.

- [ ] **Step 4: Add versioned adapters and ownership catalog**

Use this shared Gentle agent-name catalog in `ownership-catalog-v1.json`:

```json
{
  "schema": "remove-gentle-context.ownership-catalog/v1",
  "agent_names": [
    "jd-fix-agent", "jd-judge-a", "jd-judge-b",
    "review-readability", "review-refuter", "review-reliability",
    "review-resilience", "review-risk", "sdd-apply", "sdd-archive",
    "sdd-design", "sdd-explore", "sdd-init", "sdd-onboard",
    "sdd-propose", "sdd-spec", "sdd-tasks", "sdd-validator", "sdd-verify"
  ],
  "marker_prefix": "gentle-ai:",
  "generated_registry_signature": "Auto-generated by gentle-pi extensions/skill-registry.ts"
}
```

Each declarative adapter must use exact client roots and exact catalog-backed file names. A matching name without a recognized marker, generated signature, or adapter-specific content signature must produce `Ownership.AMBIGUOUS` and `report_only`.

Hermes rules report `state.db`, `state.db-wal`, and archived prompt snapshots as historical; they do not mutate SQLite. Gemini, Kimi, and VS Code Copilot rules remove only exact proven files, balanced marker blocks, or exact JSON registrations.

- [ ] **Step 5: Test all shipped adapter files**

Add a test that loads every `adapters/*.json`, asserts unique client names and rule IDs, and confirms the four forbidden capabilities are absent from serialized JSON.

Run the complete suite. Expected: all adapters validate on every platform profile.

- [ ] **Step 6: Commit declarative adapters**

```bash
git add skills/remove-gentle-context/helper/adapter.py \
        skills/remove-gentle-context/helper/declarative.py \
        skills/remove-gentle-context/adapters \
        skills/remove-gentle-context/references/ownership-catalog-v1.json \
        skills/remove-gentle-context/tests
git commit -m "feat: add constrained client adapters"
```

---

### Task 3: Build read-only inventory and digest-bound planning

**Files:**
- Create: `skills/remove-gentle-context/helper/engine.py`
- Create: `skills/remove-gentle-context/tests/test_engine.py`
- Modify: `skills/remove-gentle-context/helper/models.py`

**Interfaces:**
- Consumes: `Adapter`, `Candidate`, `Operation`, `Inventory`, `Plan`, and canonical digest functions
- Produces: `build_inventory(context, adapters) -> Inventory`
- Produces: `build_plan(inventory, context, adapters) -> Plan`
- Produces: `validate_approval(plan: Plan, supplied: str) -> None`

- [ ] **Step 1: Write failing inventory and approval tests**

```python
class EngineTests(unittest.TestCase):
    def test_inventory_is_stable_across_adapter_order(self):
        first = build_inventory(self.context, (FakeAdapter("pi"), FakeAdapter("claude")))
        second = build_inventory(self.context, (FakeAdapter("claude"), FakeAdapter("pi")))
        self.assertEqual(first.digest, second.digest)
        self.assertEqual([c.client for c in first.candidates], ["claude", "pi"])

    def test_plan_excludes_ambiguous_and_preserved_candidates(self):
        inventory = inventory_with(Ownership.PROVEN, Ownership.AMBIGUOUS, Ownership.PRESERVED)
        plan = build_plan(inventory, self.context, self.registry)
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.blocked_candidate_ids, ("ambiguous",))

    def test_approval_is_exact_and_content_bound(self):
        plan = make_plan().with_digest()
        validate_approval(plan, plan.digest)
        with self.assertRaisesRegex(ValueError, "plan_approval_mismatch"):
            validate_approval(plan, "sha256:" + "0" * 64)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing `build_inventory`, `build_plan`, and `validate_approval`.

- [ ] **Step 3: Implement deterministic inventory**

`build_inventory` must:

1. invoke every adapter in client-name order;
2. reject duplicate candidate IDs;
3. sort candidates by `(client, path, candidate_id)`;
4. record platform, resolved home, and adapter versions;
5. compute an inventory digest over the unsigned canonical record.

An adapter read error becomes a blocked inventory finding with code `inventory_io_or_layout`; it must not disappear from output.

- [ ] **Step 4: Implement plan compilation**

`build_plan` must include only `Ownership.PROVEN` candidates with non-`report_only` actions. It calls the owning adapter's `compile` method, rejects duplicate target operations, groups dependencies, captures lifecycle actions and preservation assertions, and computes a digest over `Plan.to_unsigned_dict()`.

Every `write_file` operation embeds the exact approved postimage as base64 plus its SHA-256. Apply must not rerun semantic transforms.

- [ ] **Step 5: Add drift and machine-binding tests**

Test that planning rejects an inventory created for another home or OS and that changing an operation byte changes the plan digest. Run the full suite.

- [ ] **Step 6: Commit inventory and planning**

```bash
git add skills/remove-gentle-context/helper/engine.py \
        skills/remove-gentle-context/helper/models.py \
        skills/remove-gentle-context/tests/test_engine.py
git commit -m "feat: add inventory and cleanup planning"
```

---

### Task 4: Implement backup, atomic apply, rollback, and restore

**Files:**
- Create: `skills/remove-gentle-context/helper/transaction.py`
- Create: `skills/remove-gentle-context/tests/test_transaction.py`
- Modify: `skills/remove-gentle-context/helper/models.py`
- Modify: `skills/remove-gentle-context/helper/paths.py`

**Interfaces:**
- Consumes: approved `Plan`, `Operation`, `RuntimeContext`
- Produces: `create_backup(plan, context) -> BackupManifest`
- Produces: `apply_operations(plan, manifest, context) -> tuple[OperationOutcome, ...]`
- Produces: `rollback(manifest, outcomes, context) -> tuple[OperationOutcome, ...]`
- Produces: `execute_plan(plan, approval, context, lifecycle) -> Receipt`
- Produces: `restore(manifest_path, approval, context) -> Receipt`

- [ ] **Step 1: Write failing transaction tests**

```python
class TransactionTests(unittest.TestCase):
    def test_preimage_drift_aborts_before_backup_or_mutation(self):
        target = self.home / ".codex" / "config.toml"
        target.parent.mkdir(parents=True)
        target.write_text("before")
        plan = plan_for_write(target, before=b"before", after=b"after")
        target.write_text("drift")
        with self.assertRaisesRegex(ValueError, "preflight_preimage_drift"):
            create_backup(plan, self.context)
        self.assertEqual(target.read_text(), "drift")

    def test_second_write_failure_rolls_back_first_write(self):
        first = self.make_file("one", "before-one")
        second = self.make_file("two", "before-two")
        plan = plan_for_two_writes(first, second)
        with injected_replace_failure(second):
            receipt = execute_plan(plan, plan.digest, self.context, NoopLifecycle())
        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), "before-two")

    def test_restore_rejects_manifest_path_escape(self):
        manifest = manifest_with_original_path("../../outside")
        with self.assertRaisesRegex(ValueError, "restore_path_escape"):
            restore(manifest.path, manifest.digest, self.context)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing transaction functions.

- [ ] **Step 3: Implement verified backup creation**

Backups must live under `resolve_state_root(profile)/backups/<UTC timestamp>-<plan digest prefix>/`. Store payloads beneath `rootfs/` using paths relative to independently known allowed roots. The manifest records original path, root ID, relative path, type, mode, size, and SHA-256.

Read each regular file once, write the payload, flush it, and verify its hash. Reject a target if `lstat` differs from the plan preimage or if the path becomes a link/reparse point.

- [ ] **Step 4: Implement atomic operations and journal**

For `write_file`, decode the approved postimage, verify its declared hash, create a same-directory temporary file, flush, preserve mode, parse when the operation declares JSON or TOML, then call `os.replace`.

For `delete_file`, require the exact preimage and use `os.unlink` only on a regular non-link file. For `remove_empty_directory`, require an adapter-approved directory and `os.rmdir`; never recurse.

Write a journal transition before and after each operation. On failure, restore completed operations in reverse order.

- [ ] **Step 5: Implement digest-bound restore**

Restore must recompute the canonical manifest digest, require exact `--approve`, derive destination paths from caller-known roots plus manifest-relative paths, reject collisions and path escapes, back up any current replacement preimages, and restore atomically.

- [ ] **Step 6: Run failure-injection and complete tests**

Cover backup write failure, postimage hash mismatch, parser failure, unlink failure, rollback failure, idempotent no-op, symlink, Windows reparse-point metadata, and nonempty-directory refusal. Expected: no test leaves partial target state.

- [ ] **Step 7: Commit the transaction engine**

```bash
git add skills/remove-gentle-context/helper/transaction.py \
        skills/remove-gentle-context/helper/models.py \
        skills/remove-gentle-context/helper/paths.py \
        skills/remove-gentle-context/tests/test_transaction.py
git commit -m "feat: add transactional cleanup and restore"
```

---

### Task 5: Add graceful cross-platform client lifecycle control

**Files:**
- Create: `skills/remove-gentle-context/helper/lifecycle.py`
- Create: `skills/remove-gentle-context/tests/test_lifecycle.py`
- Modify: `skills/remove-gentle-context/helper/models.py`

**Interfaces:**
- Produces: `CommandRunner.run(argv: tuple[str, ...], timeout: float) -> CompletedCommand`
- Produces: `LifecycleController.inspect(action, context) -> ProcessSnapshot`
- Produces: `LifecycleController.preflight(actions, context) -> tuple[ProcessSnapshot, ...]`
- Produces: `LifecycleController.stop(snapshot) -> LifecycleOutcome`
- Produces: `LifecycleController.restart(snapshot) -> LifecycleOutcome`

- [ ] **Step 1: Write failing lifecycle tests with a fake runner**

```python
class LifecycleTests(unittest.TestCase):
    def test_preflight_rejects_running_client_without_graceful_stop(self):
        controller = LifecycleController(FakeRunner(running=True, stoppable=False))
        with self.assertRaisesRegex(ValueError, "preflight_lifecycle_unavailable"):
            controller.preflight((codex_action(),), windows_context())

    def test_restart_only_applies_to_clients_stopped_by_transaction(self):
        controller = LifecycleController(FakeRunner(running=True, stoppable=True))
        snapshot = controller.preflight((codex_action(),), mac_context())[0]
        controller.stop(snapshot)
        controller.restart(snapshot)
        self.assertEqual(controller.runner.commands[-1], ("open", "-b", "com.openai.codex"))
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing `helper.lifecycle`.

- [ ] **Step 3: Implement discovery and graceful actions**

Use argument arrays, never shell strings. Implement these version-1 strategies:

```text
macOS:   inspect with pgrep/ps metadata; quit an app with osascript by bundle ID;
         confirm exit by condition polling; restart with open -b <bundle-id>.
Linux:   inspect with pgrep and /proc metadata; send SIGTERM to the exact recorded PID;
         confirm exit by condition polling; restart the discovered executable argv.
Windows: inspect with tasklist/PowerShell process metadata; use taskkill /PID without /F;
         confirm exit by condition polling; restart the recorded executable argv.
```

Reject ambiguous multiple process matches, missing executable metadata, changed PID identity, forced termination, and unconfirmed exit.

- [ ] **Step 4: Integrate lifecycle preflight into transaction execution**

`execute_plan` must run lifecycle preflight before backup, validate the approved preimages, stop approved running clients, and revalidate every preimage after shutdown. If any byte changed, restart clients stopped by the transaction and fail with `preflight_preimage_drift_after_shutdown`; the user must inventory and approve a new plan while the client is closed. Only unchanged approved preimages proceed to stable backup and mutation. Restart only snapshots actually stopped by the transaction.

- [ ] **Step 5: Test shutdown drift and restart failure**

Simulate a client writing state during graceful shutdown. Assert that apply performs no backup or mutation, reports `preflight_preimage_drift_after_shutdown`, and restarts the client before returning. The next plan created while the client is closed must bind the stable bytes. A restart failure yields `manual_recovery_required`, not `completed`.

- [ ] **Step 6: Commit lifecycle support**

```bash
git add skills/remove-gentle-context/helper/lifecycle.py \
        skills/remove-gentle-context/helper/models.py \
        skills/remove-gentle-context/helper/transaction.py \
        skills/remove-gentle-context/tests/test_lifecycle.py \
        skills/remove-gentle-context/tests/test_transaction.py
git commit -m "feat: add safe client lifecycle control"
```

---

### Task 6: Implement the Claude adapter

**Files:**
- Create: `skills/remove-gentle-context/helper/clients/__init__.py`
- Create: `skills/remove-gentle-context/helper/clients/claude.py`
- Create: `skills/remove-gentle-context/tests/clients/__init__.py`
- Create: `skills/remove-gentle-context/tests/clients/test_claude.py`
- Create: `skills/remove-gentle-context/tests/fixtures/claude/settings.json`
- Create: `skills/remove-gentle-context/tests/fixtures/claude/CLAUDE.md`
- Create: `skills/remove-gentle-context/tests/fixtures/claude/gentleman.json`

**Interfaces:**
- Implements: `ClaudeAdapter.inventory`, `ClaudeAdapter.compile`, `ClaudeAdapter.verify`
- Consumes: ownership catalog, marker parser, operation compiler

- [ ] **Step 1: Write failing Claude incident tests**

```python
class ClaudeAdapterTests(unittest.TestCase):
    def test_finds_theme_and_balanced_blocks(self):
        home = build_claude_fixture(self.temp_root)
        candidates = ClaudeAdapter(self.catalog).inventory(context_for(home))
        by_path = {Path(c.path).name: c for c in candidates}
        self.assertEqual(by_path["gentleman.json"].ownership, Ownership.PROVEN)
        self.assertTrue(any(c.details.get("marker") == "gentle-ai:sdd-orchestrator" for c in candidates))
        self.assertFalse(any(Path(c.path).name == "skill-registry.md" for c in candidates))

    def test_preserves_usage_counters_engram_marketplace_and_unrelated_skills(self):
        candidates = ClaudeAdapter(self.catalog).inventory(context_for(self.home))
        mutated = {c.path for c in candidates if c.ownership is Ownership.PROVEN}
        self.assertNotIn(str(self.home / ".claude.json"), mutated)
        self.assertFalse(any("plugins/marketplaces/engram" in path for path in mutated))
        self.assertFalse(any("model-optimizer" in path for path in mutated))
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing `ClaudeAdapter`.

- [ ] **Step 3: Implement bounded Claude discovery**

Resolve only documented Claude roots. Inventory exact catalog paths, balanced `<!-- gentle-ai:<id> -->` blocks, and the exact `themes/gentleman.json` path with recognized JSON content. Do not inventory `.atl/skill-registry.md`; Pi is the sole owner of generated Gentle Pi registries.

A known skill/agent/command name without marker, content signature, or managed-state corroboration is ambiguous. `.claude.json` project paths and skill usage counters are historical metadata. Engram marketplaces and plugin caches are preserved infrastructure.

- [ ] **Step 4: Compile postimages and exact deletes**

Balanced marker removal must require exactly one open/close pair and preserve all surrounding bytes. Theme and exact owned files compile to `delete_file`; Claude never compiles operations for generated `.atl` registries.

- [ ] **Step 5: Add malformed-marker and idempotency tests**

Test missing close, duplicate pair, nested marker, changed theme content, and already-clean files. Malformed or changed content must be ambiguous. Applying twice must produce no second mutation plan.

- [ ] **Step 6: Commit the Claude adapter**

```bash
git add skills/remove-gentle-context/helper/clients \
        skills/remove-gentle-context/tests/clients \
        skills/remove-gentle-context/tests/fixtures/claude
git commit -m "feat: clean Claude Gentle context"
```

---

### Task 7: Implement the Codex and ChatGPT adapter

**Files:**
- Create: `skills/remove-gentle-context/helper/clients/codex.py`
- Create: `skills/remove-gentle-context/tests/clients/test_codex.py`
- Create: `skills/remove-gentle-context/tests/fixtures/codex/config.toml`
- Create: `skills/remove-gentle-context/tests/fixtures/codex/global-state.json`
- Create: `skills/remove-gentle-context/tests/fixtures/codex/archived-session.jsonl`

**Interfaces:**
- Implements: `CodexAdapter.inventory`, `CodexAdapter.compile`, `CodexAdapter.verify`
- Produces: `remove_toml_table_family(text: str, family: str) -> str`
- Produces: `sanitize_runtime_profile(value: JsonValue, profile_id: str) -> tuple[JsonValue, int]`

- [ ] **Step 1: Write the failing `gentle-dev` regression tests**

```python
class CodexAdapterTests(unittest.TestCase):
    def test_removes_noncontiguous_profile_tables_and_selector(self):
        text = fixture("codex/config.toml")
        cleaned = remove_toml_table_family(text, "permissions.gentle-dev")
        parsed = tomllib.loads(cleaned)
        self.assertNotEqual(parsed.get("default_permissions"), "gentle-dev")
        self.assertNotIn("gentle-dev", parsed.get("permissions", {}))
        self.assertEqual(parsed["mcp_servers"], tomllib.loads(text)["mcp_servers"])

    def test_sanitizes_runtime_profiles_without_deleting_threads(self):
        before = json.loads(fixture("codex/global-state.json"))
        after, count = sanitize_runtime_profile(before, "gentle-dev")
        self.assertEqual(count, 2)
        self.assertEqual(set(thread_ids(after)), set(thread_ids(before)))
        self.assertEqual(message_metadata(after), message_metadata(before))
        self.assertFalse(any_profile_id(after, "gentle-dev"))

    def test_archived_sessions_are_report_only(self):
        candidates = CodexAdapter().inventory(self.context)
        archived = [c for c in candidates if "archived_sessions" in c.path]
        self.assertTrue(archived)
        self.assertTrue(all(c.proposed_action == "report_only" for c in archived))
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing Codex functions.

- [ ] **Step 3: Implement lossless bounded TOML removal**

Use line-preserving section recognition plus `tomllib` validation. Remove the root `default_permissions = "gentle-dev"` assignment and every table whose parsed header is exactly `permissions.gentle-dev` or begins `permissions.gentle-dev.`. Do not reserialize unrelated TOML.

Reject malformed TOML, duplicate conflicting selectors, quoted headers the parser cannot classify safely, or a profile without the exact recognized description/signature unless linked managed-state evidence proves ownership.

- [ ] **Step 4: Implement runtime and recovery sanitization**

Walk JSON objects recursively. Replace only:

```json
"activePermissionProfile": {"id": "gentle-dev", "extends": null}
```

with:

```json
"activePermissionProfile": null
```

Preserve all sibling keys, thread IDs, messages, sandbox policy, approvals, and ordering semantics. Include current state, `.bak`, and atomic-write temporary recovery files. Classify session and archived-session JSONL as historical.

- [ ] **Step 5: Add lifecycle and recovery assertions**

If any current or recovery runtime postimage changes and ChatGPT/Codex is running, compile one lifecycle action with bundle/process identities. `config.toml.bak` is recovery state and must be sanitized; rollback bundles and archived sessions remain preserved.

- [ ] **Step 6: Test null profiles, dynamic shutdown writes, and parser smoke behavior**

Cover existing `null`, unknown custom profiles, state files added after inventory, state writes during shutdown, missing ChatGPT executable, and a successful `codex --version` smoke runner. New state files after inventory must invalidate the plan rather than remain silently dirty.

- [ ] **Step 7: Commit the Codex adapter**

```bash
git add skills/remove-gentle-context/helper/clients/codex.py \
        skills/remove-gentle-context/tests/clients/test_codex.py \
        skills/remove-gentle-context/tests/fixtures/codex
git commit -m "feat: remove Codex Gentle permission state"
```

---

### Task 8: Implement the OpenCode adapter

**Files:**
- Create: `skills/remove-gentle-context/helper/clients/opencode.py`
- Create: `skills/remove-gentle-context/tests/clients/test_opencode.py`
- Create: `skills/remove-gentle-context/tests/fixtures/opencode/opencode.json`
- Create: `skills/remove-gentle-context/tests/fixtures/opencode/tui.json`
- Create: `skills/remove-gentle-context/tests/fixtures/opencode/package.json`

**Interfaces:**
- Implements: `OpenCodeAdapter.inventory`, `OpenCodeAdapter.compile`, `OpenCodeAdapter.verify`
- Produces: exact JSON postimages for default-agent and plugin registration cleanup

- [ ] **Step 1: Write failing OpenCode regression tests**

```python
class OpenCodeAdapterTests(unittest.TestCase):
    def test_finds_broken_logo_and_sdd_plugin_registrations(self):
        candidates = OpenCodeAdapter(self.catalog).inventory(self.context)
        kinds = {(c.details.get("plugin"), c.artifact_class) for c in candidates}
        self.assertIn(("gentle-logo.tsx", ArtifactClass.BROKEN_REGISTRATION), kinds)
        self.assertIn(("opencode-sdd-engram-manage", ArtifactClass.ACTIVE_SOURCE), kinds)

    def test_compile_preserves_package_and_mcp(self):
        plan = plan_for(self.context, OpenCodeAdapter(self.catalog))
        apply_to_fixture(plan)
        tui = json.loads(self.tui.read_text())
        package = json.loads(self.package.read_text())
        config = json.loads(self.config.read_text())
        self.assertEqual(tui["plugin"], ["opencode-subagent-statusline"])
        self.assertIn("opencode-sdd-engram-manage", package["dependencies"])
        self.assertEqual(config["mcp"], self.original_mcp)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing `OpenCodeAdapter`.

- [ ] **Step 3: Implement structured OpenCode inventory**

Inspect only `opencode.json`, `tui.json`, exact agent/command/skill roots, and exact local plugin paths. Classify a registered missing Gentle logo path as broken. Classify `opencode-sdd-engram-manage` registration as active context but its dependency and `node_modules` directory as preserved package infrastructure.

Change `default_agent: gentle-orchestrator` to `general` only when `general` exists or is the documented built-in fallback. Remove catalog-proven Gentle agents, prompts, commands, and skills. Preserve unrelated statusline and third-party plugins.

- [ ] **Step 4: Compile JSON postimages without package removal**

Use parsed JSON and deterministic indented output. Preservation assertions must cover `mcp`, dependencies, and unrelated plugin order. Local Gentle plugin files compile to exact deletes only with recognized fingerprints.

- [ ] **Step 5: Test malformed JSON, absent plugin files, duplicates, and idempotency**

A duplicate registration removes every exact duplicate but leaves relative and unrelated paths unchanged. Invalid JSON blocks the client. A second plan after apply contains no OpenCode mutations.

- [ ] **Step 6: Commit the OpenCode adapter**

```bash
git add skills/remove-gentle-context/helper/clients/opencode.py \
        skills/remove-gentle-context/tests/clients/test_opencode.py \
        skills/remove-gentle-context/tests/fixtures/opencode
git commit -m "feat: unregister OpenCode Gentle context"
```

---

### Task 9: Implement the Pi adapter and regeneration detection

**Files:**
- Create: `skills/remove-gentle-context/helper/clients/pi.py`
- Create: `skills/remove-gentle-context/tests/clients/test_pi.py`
- Create: `skills/remove-gentle-context/tests/fixtures/pi/settings.json`
- Create: `skills/remove-gentle-context/tests/fixtures/pi/skill-registry.md`

**Interfaces:**
- Implements: `PiAdapter.inventory`, `PiAdapter.compile`, `PiAdapter.verify`
- Produces: package-registration JSON postimage and generated-registry deletes

- [ ] **Step 1: Write failing Pi preservation tests**

```python
class PiAdapterTests(unittest.TestCase):
    def test_disables_registration_but_preserves_installed_package(self):
        candidates = PiAdapter(self.catalog).inventory(self.context)
        registration = one(c for c in candidates if c.details.get("package") == "npm:gentle-pi")
        self.assertEqual(registration.ownership, Ownership.PROVEN)
        plan = plan_for(self.context, PiAdapter(self.catalog))
        apply_to_fixture(plan)
        settings = json.loads(self.settings.read_text())
        self.assertNotIn("npm:gentle-pi", settings["packages"])
        self.assertTrue(self.node_modules_package.is_dir())

    def test_registry_requires_full_generator_signature(self):
        signed = self.make_registry("<!-- Auto-generated by gentle-pi extensions/skill-registry.ts. -->")
        unsigned = self.make_registry("Gentle registry notes", name="other.md")
        candidates = PiAdapter(self.catalog).inventory(self.context)
        self.assertEqual(candidate_for(signed, candidates).ownership, Ownership.PROVEN)
        self.assertEqual(candidate_for(unsigned, candidates).ownership, Ownership.AMBIGUOUS)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing `PiAdapter`.

- [ ] **Step 3: Implement settings and registry inventory**

Parse Pi settings JSON, remove only exact `npm:gentle-pi` entries, and preserve the installed `node_modules/gentle-pi` directory and all other packages. Discover `.atl/skill-registry.md` only under approved project roots supplied to inventory; do not crawl an unrestricted filesystem.

Require the full generator signature and a recognized registry schema before proven deletion. An empty `.pi/gentle-ai` directory is cosmetic and report-only in version 1.

- [ ] **Step 4: Detect regeneration risk**

If Pi processes that loaded Gentle Pi are running, compile lifecycle actions or block generated-registry deletion when safe restart metadata is unavailable. Verification waits by condition polling for the configured quiet interval, then confirms governed registries have not reappeared.

- [ ] **Step 5: Test stale sessions, package aliases, and quiet-period verification**

Cover `npm:gentle-pi@version`, unrelated `npm:gentle-engram`, a registry regenerated during the quiet interval, and a process that cannot be restarted. Versioned Gentle Pi aliases are active registrations; Gentle Engram remains preserved.

- [ ] **Step 6: Commit the Pi adapter**

```bash
git add skills/remove-gentle-context/helper/clients/pi.py \
        skills/remove-gentle-context/tests/clients/test_pi.py \
        skills/remove-gentle-context/tests/fixtures/pi
git commit -m "feat: disable Pi Gentle context safely"
```

---

### Task 10: Implement independent verification and machine-readable receipts

**Files:**
- Modify: `skills/remove-gentle-context/helper/engine.py`
- Modify: `skills/remove-gentle-context/helper/transaction.py`
- Modify: `skills/remove-gentle-context/helper/models.py`
- Modify: `skills/remove-gentle-context/tests/test_engine.py`
- Modify: `skills/remove-gentle-context/tests/test_transaction.py`

**Interfaces:**
- Produces: `verify_receipt(receipt: Receipt, context: RuntimeContext, adapters: AdapterRegistry) -> VerificationResult`
- Produces: terminal statuses `passed` and `failed` with stable check codes

- [ ] **Step 1: Write failing independent-verification tests**

```python
class VerificationTests(unittest.TestCase):
    def test_verification_reads_live_state_not_apply_outcomes(self):
        receipt = completed_receipt_claiming_clean()
        self.codex_config.write_text(gentle_dev_toml())
        result = verify_receipt(receipt, self.context, self.registry)
        self.assertEqual(result.status, "failed")
        self.assertIn("verify_active_residue", [c.code for c in result.checks])

    def test_mcp_drift_fails_even_when_cleanup_postconditions_pass(self):
        receipt = receipt_with_mcp_assertion(self.original_mcp)
        rewrite_mcp(self.config, {"unexpected": {"command": "x"}})
        result = verify_receipt(receipt, self.context, self.registry)
        self.assertIn("verify_preservation_mismatch", [c.code for c in result.checks])
```

- [ ] **Step 2: Run focused tests and confirm RED**

Expected: missing `verify_receipt` or false success from receipt-only checks.

- [ ] **Step 3: Implement live verification**

Re-run adapter verification from disk. Required checks are:

```text
verify_planned_postcondition
verify_active_residue
verify_structured_parse
verify_preservation_mismatch
verify_package_presence
verify_history_preservation
verify_lifecycle_state
verify_generated_regrowth
verify_ambiguous_untouched
```

A single failed required check makes the result `failed` and the command exit nonzero. Verification must not mutate or repair.

- [ ] **Step 4: Add preservation and regrowth fixtures**

Test MCP deep equality for JSON and TOML, package and binary sentinels, unchanged archived-session hashes, preserved ambiguous files, and a regenerated Pi registry. Store normalized preservation values in the plan and receipt rather than comparing textual formatting.

- [ ] **Step 5: Commit verification**

```bash
git add skills/remove-gentle-context/helper \
        skills/remove-gentle-context/tests/test_engine.py \
        skills/remove-gentle-context/tests/test_transaction.py
git commit -m "feat: verify cleanup from live state"
```

---

### Task 11: Expose the five-command CLI and end-to-end flow

**Files:**
- Create: `skills/remove-gentle-context/scripts/cleanup.py`
- Create: `skills/remove-gentle-context/tests/test_cli.py`
- Modify: `skills/remove-gentle-context/helper/engine.py`
- Modify: `skills/remove-gentle-context/helper/transaction.py`

**Interfaces:**
- Produces CLI commands: `inventory`, `plan`, `apply`, `verify`, `restore`
- Produces stable JSON artifacts and nonzero exit codes on blocked/failed terminal states

- [ ] **Step 1: Write failing CLI contract tests**

```python
class CliTests(unittest.TestCase):
    def test_apply_requires_exact_approval(self):
        result = run_cli("apply", "--plan", str(self.plan))
        self.assertEqual(result.returncode, 2)
        self.assertIn("--approve", result.stderr)

    def test_full_flow_is_idempotent_in_temporary_home(self):
        inventory = run_cli_ok("inventory", "--home", str(self.home), "--platform", "linux")
        plan = run_cli_ok("plan", "--inventory", inventory.output_path)
        applied = run_cli_ok("apply", "--plan", plan.output_path, "--approve", plan.digest)
        verification = run_cli_ok("verify", "--receipt", applied.json["receipt_path"])
        self.assertEqual(verification.json["status"], "passed")
        second = run_cli_ok("inventory", "--home", str(self.home), "--platform", "linux")
        self.assertEqual(second.json["counts"]["active"], 0)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Expected: missing executable script.

- [ ] **Step 3: Implement argparse commands and artifact defaults**

The entrypoint inserts its skill root into `sys.path`, checks Python 3.11, registers core and shipped declarative adapters, and maps exceptions to stable phase codes.

Use these exact required arguments:

```text
inventory [--output PATH] [--project-root PATH ...]
plan --inventory PATH [--output PATH]
apply --plan PATH --approve sha256:<digest> [--receipt PATH]
verify --receipt PATH [--output PATH]
restore --manifest PATH --approve sha256:<digest> [--receipt PATH]
```

`--home` and `--platform` are accepted only with `REMOVE_GENTLE_CONTEXT_TEST_MODE=1`; production use derives real platform roots. Default artifacts live under the platform state directory.

- [ ] **Step 4: Implement human and machine output separation**

Write artifacts to files and concise summaries to stdout. Errors go to stderr with stable code, phase, path when safe, and next action. Never print full file contents or environment values.

- [ ] **Step 5: Add cross-client end-to-end fixtures**

Build one temporary home containing Claude, Codex, OpenCode, Pi, and declarative-client fixtures. Assert the full five-command flow, rollback restore, preserved history hashes, package presence, MCP equality, exact approval rejection, and second-run idempotency.

- [ ] **Step 6: Run the full local suite**

Run the plan-header command on the minimum locally available Python 3.11+ interpreter. Expected: all tests pass with no network and no real-home access.

- [ ] **Step 7: Commit the CLI**

```bash
git add skills/remove-gentle-context/scripts/cleanup.py \
        skills/remove-gentle-context/helper \
        skills/remove-gentle-context/tests/test_cli.py \
        skills/remove-gentle-context/tests/fixtures
git commit -m "feat: expose cleanup transaction CLI"
```

---

### Task 12: Write the skill contract, repository docs, and platform CI

**Files:**
- Create: `skills/remove-gentle-context/SKILL.md`
- Create: `skills/remove-gentle-context/references/contracts.md`
- Create: `.github/workflows/test.yml`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-19-remove-gentle-context-design.md` only if executable names or contracts changed during implementation

**Interfaces:**
- Consumes: completed CLI and artifact contracts
- Produces: installable Agent Skill and three-OS verification gate

- [ ] **Step 1: Write a failing documentation-contract test**

Add to `tests/test_cli.py`:

```python
def test_skill_mentions_every_phase_and_never_authorizes_freeform_delete(self):
    text = (SKILL_ROOT / "SKILL.md").read_text()
    for command in ("inventory", "plan", "apply", "verify", "restore"):
        self.assertIn(f"cleanup.py {command}", text)
    self.assertIn("--approve", text)
    self.assertIn("Never improvise deletion commands", text)
```

Run it. Expected: FAIL because `SKILL.md` does not exist.

- [ ] **Step 2: Write `SKILL.md`**

Frontmatter:

```yaml
---
name: remove-gentle-context
description: >-
  Inventory, back up, remove, and verify active Gentle AI context across
  Claude, Codex/ChatGPT, OpenCode, Pi, and supported declarative clients
  while preserving MCP, Engram, packages, binaries, source, backups, and history.
---
```

The body must require this sequence:

1. check Python 3.11;
2. explain preserved scope;
3. run inventory;
4. summarize active, runtime, generated, broken, historical, preserved, ambiguous, and blocked counts;
5. run plan;
6. show every mutation and lifecycle action;
7. ask the user to approve the exact digest;
8. run apply with only that digest;
9. run independent verify;
10. report backup/receipt paths and any manual recovery.

Include the literal rule: `Never improvise deletion commands outside scripts/cleanup.py.`

- [ ] **Step 3: Document artifact contracts**

`references/contracts.md` must show compact valid examples of inventory, plan, manifest, receipt, and verification JSON. Document every stable error-code family and explain that plan and manifest digests omit their own digest field.

- [ ] **Step 4: Add the GitHub Actions matrix**

```yaml
name: test
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
          - os: ubuntu-latest
            python: "3.11"
          - os: ubuntu-latest
            python: "3.12"
          - os: ubuntu-latest
            python: "3.13"
          - os: ubuntu-latest
            python: "3.14"
          - os: macos-latest
            python: "3.11"
          - os: macos-latest
            python: "3.14"
          - os: windows-latest
            python: "3.11"
          - os: windows-latest
            python: "3.14"
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: >-
          python -m unittest discover
          -s skills/remove-gentle-context/tests
          -t skills/remove-gentle-context
          -v
```

- [ ] **Step 5: Update the README without claiming unreleased support**

Move `remove-gentle-context` from “Planned skills” to “Available skills” only after local tests pass. Document Python 3.11+, manual copy installation, the public repository URL, preserved scope, and the five-command safety flow.

- [ ] **Step 6: Run documentation and full verification**

Run:

```bash
python -m unittest discover \
  -s skills/remove-gentle-context/tests \
  -t skills/remove-gentle-context \
  -v
git diff --check
git status --short
```

Expected: all tests pass; no whitespace errors; only intended Task 12 files are changed.

- [ ] **Step 7: Commit skill packaging and CI**

```bash
git add skills/remove-gentle-context/SKILL.md \
        skills/remove-gentle-context/references/contracts.md \
        skills/remove-gentle-context/tests/test_cli.py \
        .github/workflows/test.yml \
        README.md \
        docs/superpowers/specs/2026-08-19-remove-gentle-context-design.md
git commit -m "feat: publish remove-gentle-context skill"
```

---

## Final release verification

- [ ] Run the complete `unittest` suite on the local platform.
- [ ] Run `python skills/remove-gentle-context/scripts/cleanup.py --help` and every subcommand's `--help`.
- [ ] Run the full inventory → plan → apply → verify → restore flow against the cross-client temporary fixture.
- [ ] Confirm a plan with one changed byte rejects the original approval digest.
- [ ] Confirm a changed preimage aborts before backup or mutation.
- [ ] Confirm rollback restores byte-identical preimages after injected failure.
- [ ] Confirm MCP deep equality, package presence, and archived-history hashes.
- [ ] Confirm symlink, junction/reparse-point, and path-traversal tests pass.
- [ ] Push `main` and wait for every GitHub Actions matrix job to pass.
- [ ] Verify repository settings through GitHub API: public, Issues enabled, Pull Requests disabled, default branch `main`.
- [ ] Record the release commit and CI run URL in the implementation summary.
