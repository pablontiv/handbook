import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helper import Plan, Receipt, ReceiptStatus
from helper.canonical import canonical_bytes, digest_json
from helper.models import ArtifactClass, Candidate, Ownership, PlatformProfile
from helper.paths import _is_windows_reparse_point, assert_safe_target, resolve_state_root


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

    def test_plan_digest_round_trips_without_digest_field(self):
        plan = Plan().with_digest()
        self.assertEqual(plan.to_unsigned_dict(), {})
        self.assertEqual(plan.digest, digest_json({}))
        self.assertNotIn("digest", plan.to_unsigned_dict())

    def test_package_public_api_matches_deliberate_contract(self):
        namespace = {}
        exec("from helper import *", namespace)
        public_names = {name for name in namespace if not name.startswith("_")}
        self.assertEqual(
            public_names,
            {
                "ArtifactClass",
                "BackupManifest",
                "Candidate",
                "Check",
                "CompletedCommand",
                "Inventory",
                "LifecycleAction",
                "LifecycleOutcome",
                "Operation",
                "OperationKind",
                "OperationOutcome",
                "Ownership",
                "Plan",
                "PlatformProfile",
                "Preimage",
                "PreservationAssertion",
                "ProcessSnapshot",
                "Receipt",
                "ReceiptStatus",
                "RuntimeContext",
                "VerificationResult",
                "assert_safe_target",
                "canonical_bytes",
                "digest_json",
                "resolve_state_root",
            },
        )

    def test_receipt_serializes_stage_fields(self):
        receipt = Receipt(status=ReceiptStatus.COMPLETED)
        self.assertEqual(receipt.to_dict()["status"], "completed")
        self.assertIn("operation_outcomes", receipt.to_dict())
        self.assertIn("backup_manifest_path", receipt.to_dict())
        self.assertIn("lifecycle_outcomes", receipt.to_dict())
        self.assertIn("checks", receipt.to_dict())

    def test_safe_target_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real.json"
            real.write_text("{}")
            link = root / "link.json"
            link.symlink_to(real)
            with self.assertRaisesRegex(ValueError, "preflight_unexpected_link"):
                assert_safe_target(link, (root,))

    def test_windows_reparse_predicate_uses_st_file_attributes(self):
        self.assertTrue(_is_windows_reparse_point(type("Stat", (), {"st_file_attributes": 0x400})()))
        self.assertFalse(_is_windows_reparse_point(type("Stat", (), {"st_file_attributes": 0})()))
        self.assertFalse(_is_windows_reparse_point(type("Stat", (), {})()))

    def test_safe_target_rejects_windows_reparse_point(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "reparse.json"
            target.write_text("{}")
            fake_stat = type("Stat", (), {"st_file_attributes": 0x400, "st_mode": 0})()
            with patch("helper.paths.os.lstat", return_value=fake_stat), patch.object(Path, "resolve", return_value=target), patch.object(Path, "is_symlink", return_value=False):
                with self.assertRaisesRegex(ValueError, "preflight_unexpected_link"):
                    assert_safe_target(target, (root,))

    def test_safe_target_rejects_nonexistent_parent_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "allowed"
            root.mkdir()
            path = root / "missing" / ".." / ".." / "escape.json"
            with self.assertRaisesRegex(ValueError, "preflight_path_escape"):
                assert_safe_target(path, (root,))
