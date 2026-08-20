from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from helper.canonical import canonical_bytes, digest_json
from helper.engine import build_inventory, build_plan, validate_approval, verify_receipt
from helper.transaction import execute_plan
from helper.models import (
    ArtifactClass,
    Candidate,
    Check,
    Inventory,
    LifecycleOutcome,
    Operation,
    OperationKind,
    Ownership,
    Plan,
    PlatformProfile,
    Preimage,
    Receipt,
    ReceiptStatus,
    RuntimeContext,
)


class FakeAdapter:
    def __init__(
        self,
        client: str,
        *,
        version: str = "1",
        layout_version: str = "layout-1",
        candidates: tuple[Candidate, ...] = (),
        operations: tuple[Operation, ...] = (),
        error: Exception | None = None,
        verify_error: Exception | None = None,
    ) -> None:
        self.client = client
        self.version = version
        self.layout_version = layout_version
        self._candidates = candidates
        self._operations = operations
        self._error = error
        self._verify_error = verify_error
        self.inventory_calls = 0
        self.compile_calls: list[str] = []
        self.verify_calls = 0

    def inventory(self, context: RuntimeContext) -> tuple[Candidate, ...]:
        self.inventory_calls += 1
        if self._error is not None:
            raise self._error
        return self._candidates

    def compile(self, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]:
        self.compile_calls.append(candidate.candidate_id)
        return self._operations or (Operation(kind=OperationKind.DELETE_FILE, path=candidate.path),)

    def verify(self, receipt, context):
        self.verify_calls += 1
        if self._verify_error is not None:
            raise self._verify_error
        return ()


class FileBackedAdapter(FakeAdapter):
    def __init__(self, client: str, target: Path) -> None:
        super().__init__(client)
        self.target = target

    def inventory(self, context: RuntimeContext) -> tuple[Candidate, ...]:
        self.inventory_calls += 1
        if not self.target.exists():
            return ()
        return (candidate(self.client, f"{self.client}-file", str(self.target)),)


class NoopLifecycle:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def preflight(self, actions, context):
        self.calls.append("preflight")
        return ()


def candidate(
    client: str,
    candidate_id: str,
    path: str,
    ownership: Ownership = Ownership.PROVEN,
    proposed_action: str = "delete_file",
    dependencies: tuple[str, ...] = (),
    details: dict[str, object] | None = None,
) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        client=client,
        path=path,
        artifact_class=ArtifactClass.ACTIVE_SOURCE,
        evidence=({"kind": "test"},),
        ownership=ownership,
        proposed_action=proposed_action,
        preimage=Preimage(path),
        dependencies=dependencies,
        reason="test candidate",
        details={} if details is None else details,
    )


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.context = RuntimeContext(PlatformProfile("linux", self.home, {}))

    def test_inventory_is_stable_across_adapter_order(self):
        pi_candidate = candidate("pi", "pi", str(self.home / ".pi" / "config.json"))
        claude_candidate = candidate("claude", "claude", str(self.home / ".claude" / "config.json"))
        first_pi = FakeAdapter("pi", candidates=(pi_candidate,))
        first_claude = FakeAdapter("claude", candidates=(claude_candidate,))
        second_pi = FakeAdapter("pi", candidates=(pi_candidate,))
        second_claude = FakeAdapter("claude", candidates=(claude_candidate,))

        first = build_inventory(self.context, (first_pi, first_claude))
        second = build_inventory(self.context, (second_claude, second_pi))

        self.assertEqual(first.digest, second.digest)
        self.assertEqual([c.client for c in first.candidates], ["claude", "pi"])
        self.assertEqual(first_claude.inventory_calls, 1)
        self.assertEqual(first_pi.inventory_calls, 1)
        self.assertEqual(first.adapter_versions, {"claude": "1", "pi": "1"})
        self.assertEqual(first.home, str(self.home.resolve()))

    def test_inventory_reports_adapter_read_or_layout_errors(self):
        inventory = build_inventory(self.context, (FakeAdapter("bad", error=OSError("cannot read")),))

        self.assertEqual(inventory.candidates, ())
        self.assertEqual(len(inventory.findings), 1)
        self.assertEqual(inventory.findings[0].code, "inventory_io_or_layout")
        self.assertEqual(inventory.findings[0].client, "bad")
        self.assertIsNotNone(inventory.digest)

    def test_inventory_rejects_duplicate_candidate_ids(self):
        duplicate = "sha256:" + "1" * 64
        with self.assertRaisesRegex(ValueError, "inventory_duplicate_candidate_id"):
            build_inventory(
                self.context,
                (
                    FakeAdapter("a", candidates=(candidate("a", duplicate, str(self.home / "a")),)),
                    FakeAdapter("b", candidates=(candidate("b", duplicate, str(self.home / "b")),)),
                ),
            )

    def test_plan_excludes_ambiguous_and_preserved_candidates(self):
        proven = candidate(
            "client",
            "proven",
            str(self.home / "proven"),
            Ownership.PROVEN,
            dependencies=("after", "before"),
            details={"lifecycle_actions": [{"action": "stop", "target": "client-daemon", "reason": "quiesce before edit"}]},
        )
        proven_report_only = candidate("client", "proven-report", str(self.home / "proven-report"), Ownership.PROVEN, "report_only")
        ambiguous = candidate("client", "ambiguous", str(self.home / "ambiguous"), Ownership.AMBIGUOUS, "report_only")
        preserved_path = self.home / "preserved"
        preserved_path.write_text("baseline")
        preserved = candidate("client", "preserved", str(preserved_path), Ownership.PRESERVED, "report_only")
        inventory = build_inventory(self.context, (FakeAdapter("client", candidates=(proven, proven_report_only, ambiguous, preserved)),))
        adapter = FakeAdapter("client")

        plan = build_plan(inventory, self.context, (adapter,))

        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.operations[0].candidate_id, "proven")
        self.assertEqual(plan.blocked_candidate_ids, ("ambiguous",))
        self.assertEqual(plan.dependencies, {"proven": ("after", "before")})
        self.assertEqual([a.action for a in plan.lifecycle_actions], ["stop"])
        self.assertEqual([a.candidate_id for a in plan.preservation_assertions], ["preserved"])
        self.assertEqual(adapter.compile_calls, ["proven"])

    def test_plan_rejects_cross_machine_inventory(self):
        inventory = build_inventory(self.context, (FakeAdapter("client"),))
        other_home = self.home.parent / "other-home"
        other_home.mkdir()

        with self.assertRaisesRegex(ValueError, "plan_inventory_home_mismatch"):
            build_plan(inventory, RuntimeContext(PlatformProfile("linux", other_home, {})), (FakeAdapter("client"),))

        with self.assertRaisesRegex(ValueError, "plan_inventory_os_mismatch"):
            build_plan(inventory, RuntimeContext(PlatformProfile("macos", self.home, {})), (FakeAdapter("client"),))

        with self.assertRaisesRegex(ValueError, "plan_inventory_layout_mismatch"):
            build_plan(inventory, self.context, (FakeAdapter("client", layout_version="layout-2"),))

    def test_inventory_and_plan_digest_bind_exact_root_map(self):
        first_project = self.home.parent / "project-a"
        second_project = self.home.parent / "project-b"
        first_project.mkdir()
        second_project.mkdir()
        first_context = RuntimeContext(PlatformProfile("linux", self.home, {}), project_roots=(first_project,))
        second_context = RuntimeContext(PlatformProfile("linux", self.home, {}), project_roots=(second_project,))
        reordered_context = RuntimeContext(PlatformProfile("linux", self.home, {}), project_roots=(second_project, first_project))
        stable_context = RuntimeContext(PlatformProfile("linux", self.home, {}), project_roots=(first_project, second_project))

        first_inventory = build_inventory(first_context, (FakeAdapter("client"),))
        second_inventory = build_inventory(second_context, (FakeAdapter("client"),))
        stable_inventory = build_inventory(stable_context, (FakeAdapter("client"),))
        reordered_inventory = build_inventory(reordered_context, (FakeAdapter("client"),))

        self.assertIn("root_map", first_inventory.to_unsigned_dict())
        self.assertIn("environment", first_inventory.to_unsigned_dict())
        self.assertNotEqual(first_inventory.digest, second_inventory.digest)
        self.assertEqual(stable_inventory.digest, reordered_inventory.digest)
        first_plan = build_plan(first_inventory, first_context, (FakeAdapter("client"),))
        second_plan = build_plan(second_inventory, second_context, (FakeAdapter("client"),))
        stable_plan = build_plan(stable_inventory, stable_context, (FakeAdapter("client"),))
        reordered_plan = build_plan(reordered_inventory, reordered_context, (FakeAdapter("client"),))
        self.assertEqual(first_plan.root_map, first_inventory.root_map)
        self.assertEqual(first_plan.to_unsigned_dict()["root_map"], first_inventory.to_unsigned_dict()["root_map"])
        self.assertNotEqual(first_plan.digest, second_plan.digest)
        self.assertEqual(stable_plan.digest, reordered_plan.digest)

        with self.assertRaisesRegex(ValueError, "plan_inventory_roots_mismatch"):
            build_plan(first_inventory, second_context, (FakeAdapter("client"),))

    def test_inventory_environment_binds_semantic_env_keys_and_xdg_state(self):
        xdg_state = self.home.parent / "state"
        xdg_config = self.home.parent / "xdg-config"
        appdata = self.home.parent / "appdata"
        localappdata = self.home.parent / "localappdata"
        for path in (xdg_state, xdg_config, appdata, localappdata):
            path.mkdir()
        context = RuntimeContext(
            PlatformProfile(
                "windows",
                self.home,
                {
                    "LOCALAPPDATA": str(localappdata.resolve()),
                    "APPDATA": str(appdata.resolve()),
                    "XDG_CONFIG_HOME": str(xdg_config.resolve()),
                    "XDG_STATE_HOME": str(xdg_state.resolve()),
                },
            )
        )

        inventory = build_inventory(context, (FakeAdapter("client"),))
        swapped_by_root_hash = dict(inventory.environment)
        swapped_by_root_hash["APPDATA"], swapped_by_root_hash["LOCALAPPDATA"] = swapped_by_root_hash["LOCALAPPDATA"], swapped_by_root_hash["APPDATA"]
        tampered = Inventory(
            os_name=inventory.os_name,
            home=inventory.home,
            root_map=inventory.root_map,
            environment=swapped_by_root_hash,
            adapter_versions=inventory.adapter_versions,
            adapter_layouts=inventory.adapter_layouts,
            candidates=inventory.candidates,
            findings=inventory.findings,
            digest=inventory.digest,
        )

        self.assertEqual(inventory.environment["APPDATA"], str(appdata.resolve()))
        self.assertEqual(inventory.environment["LOCALAPPDATA"], str(localappdata.resolve()))
        self.assertEqual(inventory.environment["XDG_STATE_HOME"], str(xdg_state.resolve()))
        self.assertNotEqual(inventory.digest, digest_json(tampered.to_unsigned_dict()))
        with self.assertRaisesRegex(ValueError, "plan_inventory_environment_mismatch"):
            build_plan(inventory, RuntimeContext(PlatformProfile("windows", self.home, swapped_by_root_hash)), (FakeAdapter("client"),))

    def test_inventory_environment_allows_explicit_duplicate_alias_values(self):
        shared = self.home.parent / "shared-config"
        shared.mkdir()
        context = RuntimeContext(PlatformProfile("windows", self.home, {"APPDATA": str(shared.resolve()), "LOCALAPPDATA": str(shared.resolve())}))

        inventory = build_inventory(context, (FakeAdapter("client"),))

        self.assertEqual(inventory.environment, {"APPDATA": str(shared.resolve()), "LOCALAPPDATA": str(shared.resolve())})

    def test_inventory_environment_ignores_unapproved_keys_and_rejects_relative_authority_roots(self):
        inventory = build_inventory(RuntimeContext(PlatformProfile("linux", self.home, {"HOME": str(self.home)})), (FakeAdapter("client"),))
        self.assertEqual(inventory.environment, {})

        with self.assertRaisesRegex(ValueError, "environment_root_invalid"):
            build_inventory(RuntimeContext(PlatformProfile("linux", self.home, {"XDG_STATE_HOME": "relative-state"})), (FakeAdapter("client"),))

    def test_write_operation_embeds_postimage_and_digest_changes_when_a_byte_changes(self):
        target = self.home / "config.json"
        target.write_bytes(b"old")
        item = candidate("client", "candidate", str(target), Ownership.PROVEN, "write_file")
        inventory = build_inventory(self.context, (FakeAdapter("client", candidates=(item,)),))

        first_postimage = b'{"enabled":true}\n'
        second_postimage = b'{"enabled":false}\n'
        first_plan = build_plan(inventory, self.context, (FakeAdapter("client", operations=(write_operation(target, first_postimage),)),))
        second_plan = build_plan(inventory, self.context, (FakeAdapter("client", operations=(write_operation(target, second_postimage),)),))

        self.assertNotEqual(first_plan.digest, second_plan.digest)
        self.assertEqual(first_plan.operations[0].postimage_base64, base64.b64encode(first_postimage).decode("ascii"))
        self.assertEqual(first_plan.operations[0].postimage_sha256, "sha256:" + hashlib.sha256(first_postimage).hexdigest())
        self.assertEqual(first_plan.operations[0].preimage_base64, base64.b64encode(b"old").decode("ascii"))

    def test_plan_rejects_duplicate_operation_targets(self):
        target = self.home / "same"
        first = candidate("client", "first", str(target), Ownership.PROVEN)
        second = candidate("client", "second", str(target), Ownership.PROVEN)
        inventory = build_inventory(self.context, (FakeAdapter("client", candidates=(first, second)),))

        with self.assertRaisesRegex(ValueError, "plan_duplicate_operation_target"):
            build_plan(inventory, self.context, (FakeAdapter("client"),))

    def test_approval_is_exact_and_content_bound(self):
        inventory = build_inventory(self.context, (FakeAdapter("client"),))
        plan = build_plan(inventory, self.context, (FakeAdapter("client"),))

        validate_approval(plan, plan.digest)
        with self.assertRaisesRegex(ValueError, "plan_approval_mismatch"):
            validate_approval(plan, "sha256:" + "0" * 64)
        with self.assertRaisesRegex(ValueError, "plan_approval_mismatch"):
            validate_approval(plan, str(plan.digest) + "\n")

    def test_preserved_candidate_missing_baseline_fails_closed_during_plan_build(self):
        missing = self.home / ".codex" / "config.toml"
        inventory = build_inventory(
            self.context,
            (FakeAdapter("codex", candidates=(candidate("codex", "missing-mcp", str(missing), Ownership.PRESERVED, "report_only", details={"kind": "mcp"}),)),),
        )

        with self.assertRaisesRegex(ValueError, "plan_preservation_baseline_unavailable"):
            build_plan(inventory, self.context, (FakeAdapter("codex"),))

    def test_duplicate_adapter_clients_are_rejected_before_inventory_calls(self):
        first = FakeAdapter("client")
        second = FakeAdapter("client")

        with self.assertRaisesRegex(ValueError, "adapter_duplicate_client"):
            build_inventory(self.context, (first, second))

        self.assertEqual(first.inventory_calls, 0)
        self.assertEqual(second.inventory_calls, 0)


class VerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)
        self.home = self.temp_root / "home"
        self.home.mkdir()
        self.project = self.temp_root / "project"
        self.project.mkdir()
        self.context = RuntimeContext(PlatformProfile("linux", self.home, {"XDG_STATE_HOME": str((self.temp_root / "state").resolve(strict=False))}), project_roots=(self.project,))

    def completed_receipt(self, plan: Plan, inventory: Inventory) -> Receipt:
        return Receipt(status=ReceiptStatus.COMPLETED, plan=plan, inventory=inventory)

    def plan_receipt_for(self, adapters: tuple[FakeAdapter, ...]) -> tuple[Inventory, Plan, Receipt]:
        inventory = build_inventory(self.context, adapters)
        plan = build_plan(inventory, self.context, adapters)
        return inventory, plan, self.completed_receipt(plan, inventory)

    def check_codes(self, result) -> list[str]:
        return [check.code for check in result.checks if check.status == "failed"]

    def test_execute_plan_receipt_verifies_end_to_end_with_bound_inventory(self):
        target = self.home / ".client" / "owned.txt"
        target.parent.mkdir(parents=True)
        target.write_text("remove me")
        adapter = FileBackedAdapter("client", target)
        inventory = build_inventory(self.context, (adapter,))
        plan = build_plan(inventory, self.context, (adapter,))

        receipt = execute_plan(plan, plan.digest or "", self.context, NoopLifecycle(), inventory=inventory)
        result = verify_receipt(receipt, self.context, (adapter,))

        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertEqual(receipt.inventory, inventory)
        self.assertFalse(target.exists())
        self.assertEqual(result.status, "passed")

    def test_verify_receipt_fails_stably_when_inventory_is_absent(self):
        inventory = build_inventory(self.context, (FakeAdapter("client"),))
        plan = build_plan(inventory, self.context, (FakeAdapter("client"),))
        receipt = Receipt(status=ReceiptStatus.COMPLETED, plan=plan)

        result = verify_receipt(receipt, self.context, (FakeAdapter("client"),))

        self.assertEqual(result.status, "failed")
        self.assertIn("verify_artifact_digest", self.check_codes(result))
        self.assertTrue(any(check.evidence.get("error") == "missing_inventory" for check in result.checks))

    def test_verifier_duplicate_adapter_clients_fail_before_verify_calls(self):
        inventory, _plan, receipt = self.plan_receipt_for((FakeAdapter("client"),))
        first = FakeAdapter("client")
        second = FakeAdapter("client")

        result = verify_receipt(receipt, self.context, (first, second))

        self.assertEqual(result.status, "failed")
        self.assertIn("verify_adapter_live", self.check_codes(result))
        self.assertEqual(first.verify_calls, 0)
        self.assertEqual(second.verify_calls, 0)
        self.assertEqual(inventory.candidates, ())

    def test_failed_adapter_check_does_not_also_emit_adapter_pass(self):
        class FailingCheckAdapter(FakeAdapter):
            def verify(self, receipt, context):
                self.verify_calls += 1
                return (Check(code="verify_adapter_live", status="failed", severity="error", evidence={"client": self.client}),)

        _inventory, _plan, receipt = self.plan_receipt_for((FakeAdapter("client"),))

        result = verify_receipt(receipt, self.context, (FailingCheckAdapter("client"),))

        adapter_checks = [check for check in result.checks if check.code == "verify_adapter_live" and check.evidence.get("client") == "client"]
        self.assertEqual([(check.status, check.severity) for check in adapter_checks], [("failed", "error")])

    def test_verification_reads_live_state_not_apply_outcomes(self):
        inventory, plan, receipt = self.plan_receipt_for((FakeAdapter("codex"),))
        live_target = self.home / ".codex" / "config.toml"
        live_target.parent.mkdir(parents=True)
        live_target.write_text('default_permissions = "gentle-dev"\n')
        live_candidate = candidate("codex", "live-gentle-profile", str(live_target), details={"kind": "config_toml"})

        result = verify_receipt(receipt, self.context, (FakeAdapter("codex", candidates=(live_candidate,)),))

        self.assertEqual(result.status, "failed")
        self.assertIn("verify_active_residue", self.check_codes(result))
        self.assertIn("verify_adapter_live", [check.code for check in result.checks])
        self.assertEqual(inventory.candidates, ())
        self.assertEqual(plan.operations, ())

    def test_mcp_json_and_toml_drift_fails_even_when_receipt_completed(self):
        json_config = self.home / ".config" / "opencode" / "opencode.json"
        json_config.parent.mkdir(parents=True)
        json_config.write_text(json.dumps({"mcp": {"approved": {"command": "ok"}}, "agent": {}}, indent=2) + "\n")
        toml_config = self.home / ".codex" / "config.toml"
        toml_config.parent.mkdir(parents=True)
        toml_config.write_text('[mcp_servers.approved]\ncommand = "ok"\n')
        adapters = (
            FakeAdapter("codex", candidates=(candidate("codex", "codex-mcp", str(toml_config), Ownership.PRESERVED, "report_only", details={"kind": "mcp"}),)),
            FakeAdapter("opencode", candidates=(candidate("opencode", "opencode-mcp", str(json_config), Ownership.PRESERVED, "report_only", details={"kind": "mcp"}),)),
        )
        inventory, plan, receipt = self.plan_receipt_for(adapters)

        json_config.write_text(json.dumps({"mcp": {"unexpected": {"command": "x"}}, "agent": {}}, indent=2) + "\n")
        toml_config.write_text('[mcp_servers.unexpected]\ncommand = "x"\n')
        result = verify_receipt(receipt, self.context, adapters)

        self.assertEqual(result.status, "failed")
        self.assertIn("verify_preservation_mismatch", self.check_codes(result))
        self.assertEqual(len(plan.preservation_assertions), 2)

    def test_success_report_is_byte_stable_and_sorted(self):
        package = self.home / ".pi" / "node_modules" / "gentle-pi"
        binary = self.home / ".pi" / "node_modules" / ".bin" / "gentle-pi"
        history = self.home / ".codex" / "sessions" / "session.jsonl"
        cosmetic = self.home / ".pi" / "gentle-ai"
        package.mkdir(parents=True)
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/bin/sh\n")
        history.parent.mkdir(parents=True)
        history.write_text('{"prompt":"historical gentle mention only"}\n')
        cosmetic.mkdir(parents=True)
        adapters = (
            FakeAdapter("codex", candidates=(candidate("codex", "history", str(history), Ownership.PRESERVED, "report_only", details={"kind": "historical_jsonl"}),)),
            FakeAdapter("pi", candidates=(
                candidate("pi", "package", str(package), Ownership.PRESERVED, "report_only", details={"kind": "installed_package"}),
                candidate("pi", "binary", str(binary), Ownership.PRESERVED, "report_only", details={"kind": "installed_binary"}),
                candidate("pi", "cosmetic", str(cosmetic), Ownership.PRESERVED, "report_only", details={"kind": "cosmetic_empty_directory"}),
            )),
        )
        _inventory, _plan, receipt = self.plan_receipt_for(adapters)

        first = verify_receipt(receipt, self.context, tuple(reversed(adapters)))
        second = verify_receipt(receipt, self.context, adapters)

        self.assertEqual(first.status, "passed")
        self.assertEqual(first.to_json_bytes(), second.to_json_bytes())
        self.assertEqual(first.to_json_bytes(), canonical_bytes(first.to_dict()))
        self.assertEqual([check.code for check in first.checks], sorted(check.code for check in first.checks))

    def test_each_injected_failure_class_has_stable_failed_code(self):
        target = self.home / "settings.json"
        target.write_text('{"clean": true}\n')
        before_b64, before_digest = image(b'{"clean": true}\n')
        after_b64, after_digest = image(b'{"clean": false}\n')
        plan = Plan(
            os_name="linux",
            home=str(self.home),
            root_map={},
            operations=(Operation(kind=OperationKind.WRITE_FILE, path=str(target), preimage_base64=before_b64, preimage_sha256=before_digest, postimage_base64=after_b64, postimage_sha256=after_digest, details={"content_type": "application/json"}),),
        ).with_digest()
        receipt = Receipt(status=ReceiptStatus.COMPLETED, plan=plan, operation_outcomes=())

        result = verify_receipt(receipt, self.context, (FakeAdapter("client"),))

        self.assertEqual(result.status, "failed")
        self.assertIn("verify_planned_postcondition", self.check_codes(result))
        self.assertIn("verify_backup_evidence", self.check_codes(result))

        target.write_text("not json")
        malformed_receipt = Receipt(status=ReceiptStatus.COMPLETED, plan=plan, operation_outcomes=())
        malformed = verify_receipt(malformed_receipt, self.context, (FakeAdapter("client"),))
        self.assertIn("verify_structured_parse", self.check_codes(malformed))

    def test_package_history_registry_root_lifecycle_and_adapter_failures_are_stable(self):
        package = self.home / ".pi" / "node_modules" / "gentle-pi"
        history = self.home / ".codex" / "sessions" / "session.jsonl"
        registry = self.project / ".atl" / "skill-registry.md"
        package.mkdir(parents=True)
        history.parent.mkdir(parents=True)
        history.write_text("before\n")
        adapters = (
            FakeAdapter("codex", candidates=(candidate("codex", "history", str(history), Ownership.PRESERVED, "report_only", details={"kind": "historical_jsonl"}),)),
            FakeAdapter("pi", candidates=(candidate("pi", "package", str(package), Ownership.PRESERVED, "report_only", details={"kind": "installed_package"}),)),
        )
        _inventory, plan, receipt = self.plan_receipt_for(adapters)
        package.rmdir()
        history.write_text("after\n")
        registry.parent.mkdir(parents=True)
        registry.write_text("<!-- Auto-generated by gentle-pi extensions/skill-registry.ts. -->\n# Skill Registry\n\n| Skill | Path |\n| --- | --- |\n")
        drifted_plan = Plan(os_name=plan.os_name, home=plan.home, root_map={"home": str(self.temp_root / "other")}, preservation_assertions=plan.preservation_assertions, digest=plan.digest)
        failed_receipt = Receipt(
            status=ReceiptStatus.COMPLETED,
            plan=drifted_plan,
            lifecycle_outcomes=(LifecycleOutcome(action="restart", client="pi", target="Pi", status="failed", code="lifecycle_restart_failed", pid=7),),
        )

        result = verify_receipt(failed_receipt, self.context, (FakeAdapter("codex", verify_error=ValueError("codex_toml_malformed")), FakeAdapter("pi", candidates=(candidate("pi", "regrown", str(registry), details={"kind": "generated_registry"}),))))

        failures = self.check_codes(result)
        self.assertIn("verify_root_binding", failures)
        self.assertIn("verify_lifecycle_state", failures)
        self.assertIn("verify_package_presence", failures)
        self.assertIn("verify_history_preservation", failures)
        self.assertIn("verify_generated_regrowth", failures)
        self.assertIn("verify_structured_parse", failures)

    def test_receipt_success_with_live_postimage_drift_still_fails(self):
        target = self.home / "config.json"
        target.write_text('{"enabled": false}\n')
        plan = write_plan(target, b'{"enabled": true}\n', b'{"enabled": false}\n')
        receipt = Receipt(
            status=ReceiptStatus.COMPLETED,
            plan=plan,
            operation_outcomes=(type("Outcome", (), {"operation_index": 0, "kind": str(OperationKind.WRITE_FILE), "path": str(target), "status": "completed"})(),),
        )
        target.write_text('{"enabled": true}\n')

        result = verify_receipt(receipt, self.context, (FakeAdapter("client"),))

        self.assertEqual(result.status, "failed")
        self.assertIn("verify_planned_postcondition", self.check_codes(result))


def write_plan(path: Path, before: bytes, after: bytes) -> Plan:
    pre_b64, pre_digest = image(before)
    post_b64, post_digest = image(after)
    return Plan(
        os_name="linux",
        home=str(path.parents[0]),
        operations=(Operation(kind=OperationKind.WRITE_FILE, path=str(path), preimage_base64=pre_b64, preimage_sha256=pre_digest, postimage_base64=post_b64, postimage_sha256=post_digest, details={"content_type": "application/json"}),),
    ).with_digest()


def image(content: bytes) -> tuple[str, str]:
    return base64.b64encode(content).decode("ascii"), "sha256:" + hashlib.sha256(content).hexdigest()


def write_operation(path: Path, postimage: bytes) -> Operation:
    return Operation(
        kind=OperationKind.WRITE_FILE,
        path=str(path),
        postimage_base64=base64.b64encode(postimage).decode("ascii"),
        postimage_sha256="sha256:" + hashlib.sha256(postimage).hexdigest(),
    )
