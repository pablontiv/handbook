import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import helper
from helper import Plan, Receipt, ReceiptStatus
from helper.canonical import canonical_bytes, digest_json
from helper.models import ArtifactClass, Candidate, Ownership, PlatformProfile, RuntimeContext
from helper.paths import _is_windows_reparse_point, assert_safe_target, known_roots, resolve_state_root, root_relative_path


APPROVED_HELPER_PUBLIC_NAMES = (
    "canonical_bytes",
    "digest_json",
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
    "resolve_state_root",
)


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
        with self.subTest("helper.__all__"):
            self.assertEqual(tuple(getattr(helper, "__all__", ())), APPROVED_HELPER_PUBLIC_NAMES)

        with self.subTest("from helper import *"):
            namespace = {}
            exec("from helper import *", namespace)
            public_names = {name for name in namespace if not name.startswith("_")}
            self.assertEqual(public_names, set(APPROVED_HELPER_PUBLIC_NAMES))

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

    def test_known_roots_include_stable_external_project_root_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            project_a = root / "projects" / "alpha"
            project_b = root / "projects" / "beta"
            home.mkdir()
            project_a.mkdir(parents=True)
            project_b.mkdir(parents=True)
            first = RuntimeContext(PlatformProfile("linux", home, {}), project_roots=(project_b, project_a))
            second = RuntimeContext(PlatformProfile("linux", home, {}), project_roots=(project_a, project_b))

            first_roots = known_roots(first)
            second_roots = known_roots(second)

            self.assertEqual(first_roots, second_roots)
            self.assertEqual(first_roots["home"], home)
            project_root_ids = [root_id for root_id in first_roots if root_id != "home"]
            self.assertEqual(project_root_ids, sorted(project_root_ids))
            self.assertEqual({first_roots[root_id] for root_id in project_root_ids}, {project_a.resolve(), project_b.resolve()})
            self.assertTrue(all(root_id.startswith("project-") for root_id in project_root_ids))
            self.assertEqual(root_relative_path(project_a / "CLAUDE.md", first)[1], "CLAUDE.md")

    def test_known_roots_include_stable_external_platform_config_roots(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            xdg = root / "xdg-config"
            appdata = root / "appdata"
            home.mkdir()
            xdg.mkdir()
            appdata.mkdir()
            context = RuntimeContext(
                PlatformProfile(
                    "linux",
                    home,
                    {"XDG_CONFIG_HOME": str(xdg), "APPDATA": str(appdata), "LOCALAPPDATA": str(xdg)},
                )
            )

            roots = known_roots(context)
            platform_root_ids = [root_id for root_id in roots if root_id.startswith("platform-config-")]

            self.assertEqual(platform_root_ids, sorted(platform_root_ids))
            self.assertEqual({roots[root_id] for root_id in platform_root_ids}, {xdg.resolve(), appdata.resolve()})
            root_id, relative = root_relative_path(xdg / "pi" / "settings.json", context)
            self.assertTrue(root_id.startswith("platform-config-"))
            self.assertEqual(relative, "pi/settings.json")

    def test_known_roots_deduplicates_platform_config_roots_inside_home(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            in_home_config = home / ".config"
            in_home_config.mkdir(parents=True)
            context = RuntimeContext(PlatformProfile("linux", home, {"XDG_CONFIG_HOME": str(in_home_config)}))

            roots = known_roots(context)

            self.assertEqual([root_id for root_id in roots if root_id.startswith("platform-config-")], [])
            self.assertEqual(root_relative_path(in_home_config / "pi" / "settings.json", context), ("home", ".config/pi/settings.json"))

    def test_known_roots_rejects_relative_platform_config_env_roots(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            context = RuntimeContext(PlatformProfile("linux", home, {"XDG_CONFIG_HOME": "relative-config"}))

            with self.assertRaisesRegex(ValueError, "platform_config_root_invalid"):
                known_roots(context)

    def test_runtime_context_rejects_duplicate_project_roots_after_normalization(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            project = root / "project"
            home.mkdir()
            project.mkdir()

            with self.assertRaisesRegex(ValueError, "project_root_duplicate"):
                RuntimeContext(PlatformProfile("linux", home, {}), project_roots=(project, project / ".." / "project"))
