from __future__ import annotations

import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from helper.engine import build_inventory, build_plan, validate_approval
from helper.models import (
    ArtifactClass,
    Candidate,
    Operation,
    OperationKind,
    Ownership,
    PlatformProfile,
    Preimage,
    RuntimeContext,
)


class FakeAdapter:
    def __init__(self, client: str, *, version: str = "1", layout_version: str = "layout-1", candidates: tuple[Candidate, ...] = (), operations: tuple[Operation, ...] = (), error: Exception | None = None) -> None:
        self.client = client
        self.version = version
        self.layout_version = layout_version
        self._candidates = candidates
        self._operations = operations
        self._error = error
        self.inventory_calls = 0
        self.compile_calls: list[str] = []

    def inventory(self, context: RuntimeContext) -> tuple[Candidate, ...]:
        self.inventory_calls += 1
        if self._error is not None:
            raise self._error
        return self._candidates

    def compile(self, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]:
        self.compile_calls.append(candidate.candidate_id)
        return self._operations or (Operation(kind=OperationKind.DELETE_FILE, path=candidate.path),)

    def verify(self, receipt, context):
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
        preserved = candidate("client", "preserved", str(self.home / "preserved"), Ownership.PRESERVED, "report_only")
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


def write_operation(path: Path, postimage: bytes) -> Operation:
    return Operation(
        kind=OperationKind.WRITE_FILE,
        path=str(path),
        postimage_base64=base64.b64encode(postimage).decode("ascii"),
        postimage_sha256="sha256:" + hashlib.sha256(postimage).hexdigest(),
    )
