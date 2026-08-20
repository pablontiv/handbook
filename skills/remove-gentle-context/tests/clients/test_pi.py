from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helper.clients.pi import PiAdapter
from helper.engine import build_inventory, build_plan
from helper.models import LifecycleOutcome, OperationKind, Ownership, PlatformProfile, ProcessSnapshot, ReceiptStatus, RuntimeContext
from helper.ownership import load_ownership_catalog
from helper.transaction import apply_operations, create_backup, execute_plan, restore, rollback
from tests.support import assert_test_home

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pi"


def context_for(home: Path, *, project_roots: tuple[Path, ...] = (), os_name: str = "linux", **env: str) -> RuntimeContext:
    authority_keys = {"XDG_STATE_HOME", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA"}
    normalized = {key: (str(Path(value).resolve(strict=False)) if key in authority_keys else value) for key, value in env.items()}
    return RuntimeContext(PlatformProfile(os_name, home, normalized), project_roots=project_roots)


def one(items):
    values = list(items)
    if len(values) != 1:
        raise AssertionError(f"expected exactly one item, got {len(values)}")
    return values[0]


def plan_for(context: RuntimeContext, adapter: PiAdapter):
    return build_plan(build_inventory(context, (adapter,)), context, (adapter,))


def apply_to_fixture(plan, context: RuntimeContext) -> None:
    manifest = create_backup(plan, context)
    apply_operations(plan, manifest, context)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now


class FakeSleeper:
    def __init__(self, clock: FakeClock, *, on_sleep=None) -> None:
        self.clock = clock
        self.on_sleep = on_sleep
        self.calls: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.now += seconds
        if self.on_sleep is not None:
            self.on_sleep(len(self.calls))


class FakePiProbe:
    def __init__(self, *sessions: dict[str, object]) -> None:
        self.sessions = sessions
        self.calls = 0

    def inspect_pi_processes(self, context: RuntimeContext) -> tuple[dict[str, object], ...]:
        self.calls += 1
        return tuple(dict(session) for session in self.sessions)


class FakeLifecycle:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def preflight(self, actions, context):
        self.calls.append("preflight")
        return tuple(
            ProcessSnapshot(
                action=action,
                platform=context.profile.os_name,
                running=True,
                pid=123,
                process_name=str(action.details.get("process_name", "Pi")),
                executable="/usr/bin/pi",
                argv=("/usr/bin/pi", "--foreground"),
                identity="linux:123:/usr/bin/pi",
            )
            for action in actions
        )

    def stop(self, snapshot):
        self.calls.append("stop")
        return LifecycleOutcome(action="stop", client=snapshot.action.client, target=snapshot.action.target, status="stopped", pid=snapshot.pid)

    def restart(self, snapshot):
        self.calls.append("restart")
        return LifecycleOutcome(action="restart", client=snapshot.action.client, target=snapshot.action.target, status="restarted", pid=snapshot.pid)


class PiAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)
        self.home = self.temp_root / "home"
        self.home.mkdir()
        self.pi_dir = self.home / ".pi"
        self.pi_dir.mkdir()
        self.settings = self.pi_dir / "settings.json"
        shutil.copy2(FIXTURE_ROOT / "settings.json", self.settings)
        self.node_modules_package = self.pi_dir / "node_modules" / "gentle-pi"
        self.node_modules_package.mkdir(parents=True)
        self.node_modules_bin = self.pi_dir / "node_modules" / ".bin"
        self.node_modules_bin.mkdir()
        (self.node_modules_bin / "gentle-pi").write_text("#!/usr/bin/env node\n")
        self.project = self.temp_root / "project"
        self.project.mkdir()
        self.registry = self.project / ".atl" / "skill-registry.md"
        self.registry.parent.mkdir()
        shutil.copy2(FIXTURE_ROOT / "skill-registry.md", self.registry)
        assert_test_home(self.home, self.temp_root)
        self.context = context_for(self.home, project_roots=(self.project,), XDG_STATE_HOME=str(self.temp_root / "state"))
        self.project = self.context.project_roots[0]
        self.registry = self.project / ".atl" / "skill-registry.md"
        self.catalog = load_ownership_catalog()

    def make_registry(self, body: str, *, project: Path | None = None) -> Path:
        target_project = self.project if project is None else project
        target = target_project / ".atl" / "skill-registry.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
        return target

    def exercise_external_platform_config_settings(self, *, os_name: str, env_key: str, settings_relative: Path) -> None:
        self.registry.unlink()
        self.settings.write_text(json.dumps({"packages": ["npm:gentle-engram"]}, indent=2) + "\n")
        external_config = self.temp_root / f"external-{env_key.lower()}"
        external_settings = external_config / settings_relative
        external_settings.parent.mkdir(parents=True)
        shutil.copy2(FIXTURE_ROOT / "settings.json", external_settings)
        context = context_for(
            self.home,
            os_name=os_name,
            XDG_STATE_HOME=str(self.temp_root / f"state-{env_key.lower()}"),
            **{env_key: str(external_config)},
        )
        adapter = PiAdapter(self.catalog, process_probe=FakePiProbe())

        inventory = build_inventory(context, (adapter,))
        plan = build_plan(inventory, context, (adapter,))
        resolved_external_settings = external_settings.resolve(strict=False)
        registration = one(candidate for candidate in inventory.candidates if candidate.path == str(resolved_external_settings))
        platform_root_ids = [root_id for root_id, root in inventory.root_map.items() if root == str(external_config.resolve(strict=False))]
        self.assertEqual(len(platform_root_ids), 1)
        self.assertTrue(platform_root_ids[0].startswith("platform-config-"))
        self.assertEqual(registration.details["root_id"], platform_root_ids[0])
        self.assertEqual(registration.details["relative_path"], settings_relative.as_posix())
        self.assertEqual(plan.root_map, inventory.root_map)
        self.assertIn(str(resolved_external_settings), {operation.path for operation in plan.operations})

        manifest = create_backup(plan, context)
        apply_operations(plan, manifest, context)
        self.assertNotIn("npm:gentle-pi", json.loads(external_settings.read_text())["packages"])
        receipt = restore(manifest.path, manifest.digest or "", context)
        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertIn("npm:gentle-pi", json.loads(external_settings.read_text())["packages"])

        absent_context = context_for(self.home, os_name=os_name, XDG_STATE_HOME=str(self.temp_root / f"state-absent-{env_key.lower()}"))
        with self.assertRaisesRegex(ValueError, "apply_plan_roots_mismatch"):
            apply_operations(plan, manifest, absent_context)
        with self.assertRaisesRegex(ValueError, "restore_path_escape"):
            restore(manifest.path, manifest.digest or "", absent_context)

        drifted_context = context_for(
            self.home,
            os_name=os_name,
            XDG_STATE_HOME=str(self.temp_root / f"state-drifted-{env_key.lower()}"),
            **{env_key: str(self.temp_root / f"drifted-{env_key.lower()}")},
        )
        with self.assertRaisesRegex(ValueError, "apply_plan_roots_mismatch"):
            apply_operations(plan, manifest, drifted_context)
        with self.assertRaisesRegex(ValueError, "restore_path_escape"):
            restore(manifest.path, manifest.digest or "", drifted_context)

    def test_linux_xdg_config_home_pi_settings_external_root_apply_restore_and_drift_rejection(self) -> None:
        self.exercise_external_platform_config_settings(os_name="linux", env_key="XDG_CONFIG_HOME", settings_relative=Path("pi") / "settings.json")

    def test_windows_appdata_pi_settings_external_root_apply_restore_and_drift_rejection(self) -> None:
        self.exercise_external_platform_config_settings(os_name="windows", env_key="APPDATA", settings_relative=Path("Pi") / "settings.json")

    def test_disables_registration_but_preserves_installed_package(self) -> None:
        adapter = PiAdapter(self.catalog, process_probe=FakePiProbe())
        candidates = adapter.inventory(self.context)
        registration = one(c for c in candidates if c.details.get("package") == "npm:gentle-pi")
        self.assertEqual(registration.ownership, Ownership.PROVEN)
        plan = plan_for(self.context, adapter)
        apply_to_fixture(plan, self.context)
        adapter.verify(type("ReceiptLike", (), {"operation_outcomes": (), "checks": ()})(), self.context)

        settings = json.loads(self.settings.read_text())
        self.assertNotIn("npm:gentle-pi", settings["packages"])
        self.assertNotIn("npm:gentle-pi@1.2.3", settings["packages"])
        self.assertIn("npm:gentle-pi@latest", settings["packages"])
        self.assertIn("npm:gentle-engram", settings["packages"])
        self.assertTrue(self.node_modules_package.is_dir())
        self.assertTrue((self.node_modules_bin / "gentle-pi").is_file())

    def test_registry_requires_full_generator_signature_and_schema(self) -> None:
        adapter = PiAdapter(self.catalog, process_probe=FakePiProbe())
        signed = self.make_registry(FIXTURE_ROOT.joinpath("skill-registry.md").read_text())
        candidates = adapter.inventory(self.context)
        self.assertEqual(one(c for c in candidates if c.path == str(signed)).ownership, Ownership.PROVEN)

        vague = self.make_registry("Gentle registry notes\n# Skill Registry\n\n| Skill | Path |\n| --- | --- |\n")
        candidates = adapter.inventory(self.context)
        self.assertEqual(one(c for c in candidates if c.path == str(vague)).ownership, Ownership.AMBIGUOUS)

        malformed = self.make_registry("<!-- Auto-generated by gentle-pi extensions/skill-registry.ts. -->\nGentle text only\n")
        candidates = adapter.inventory(self.context)
        self.assertEqual(one(c for c in candidates if c.path == str(malformed)).ownership, Ownership.AMBIGUOUS)

    def test_registry_inventory_uses_only_runtime_project_roots_no_crawl(self) -> None:
        sibling = self.temp_root / "sibling"
        self.make_registry(FIXTURE_ROOT.joinpath("skill-registry.md").read_text(), project=sibling)
        candidates = PiAdapter(self.catalog).inventory(self.context)
        self.assertNotIn(str(sibling / ".atl" / "skill-registry.md"), {candidate.path for candidate in candidates})

    def test_empty_pi_gentle_ai_is_report_only_and_package_sentinel_preserved(self) -> None:
        cosmetic = self.pi_dir / "gentle-ai"
        cosmetic.mkdir()
        inventory = build_inventory(self.context, (PiAdapter(self.catalog),))
        plan = build_plan(inventory, self.context, (PiAdapter(self.catalog),))

        cosmetic_candidate = one(candidate for candidate in inventory.candidates if candidate.path == str(cosmetic))
        package_candidate = one(candidate for candidate in inventory.candidates if candidate.path == str(self.node_modules_package))
        self.assertEqual(cosmetic_candidate.proposed_action, "report_only")
        self.assertEqual(package_candidate.ownership, Ownership.PRESERVED)
        self.assertNotIn(str(cosmetic), {operation.path for operation in plan.operations})
        self.assertNotIn(str(self.node_modules_package), {operation.path for operation in plan.operations})

    def test_running_restartable_pi_compiles_lifecycle_action_and_executes_delete(self) -> None:
        adapter = PiAdapter(
            self.catalog,
            process_probe=FakePiProbe(
                {
                    "running": True,
                    "loaded_gentle_pi": True,
                    "restartable": True,
                    "process_name": "Pi",
                    "restart_argv": ("/usr/bin/pi", "--foreground"),
                }
            ),
        )
        inventory = build_inventory(self.context, (adapter,))
        plan = build_plan(inventory, self.context, (adapter,))

        self.assertEqual(len(plan.lifecycle_actions), 1)
        self.assertEqual(plan.lifecycle_actions[0].client, "pi")
        self.assertIn(str(self.registry), {operation.path for operation in plan.operations if operation.kind is OperationKind.DELETE_FILE})
        lifecycle = FakeLifecycle()
        receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle=lifecycle, inventory=inventory)

        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertFalse(self.registry.exists())

    def test_missing_process_probe_marks_signed_registry_ambiguous_but_allows_settings_cleanup(self) -> None:
        for adapter in (PiAdapter(self.catalog), PiAdapter(self.catalog, process_probe=object())):
            with self.subTest(adapter=type(adapter.process_probe).__name__ if adapter.process_probe is not None else "none"):
                inventory = build_inventory(self.context, (adapter,))
                plan = build_plan(inventory, self.context, (adapter,))
                registry_candidate = one(candidate for candidate in inventory.candidates if candidate.path == str(self.registry))

                self.assertEqual(registry_candidate.ownership, Ownership.AMBIGUOUS)
                self.assertEqual(registry_candidate.proposed_action, "report_only")
                self.assertTrue(any(isinstance(item, dict) and item.get("kind") == "process_probe_unavailable" for item in registry_candidate.evidence))
                self.assertIn(registry_candidate.candidate_id, plan.blocked_candidate_ids)
                self.assertIn(str(self.settings), {operation.path for operation in plan.operations})
                self.assertNotIn(str(self.registry), {operation.path for operation in plan.operations})

    def test_running_unrestartable_pi_blocks_registry_but_allows_settings_cleanup(self) -> None:
        adapter = PiAdapter(
            self.catalog,
            process_probe=FakePiProbe({"running": True, "loaded_gentle_pi": True, "restartable": False, "process_name": "Pi"}),
        )
        inventory = build_inventory(self.context, (adapter,))
        plan = build_plan(inventory, self.context, (adapter,))
        registry_candidate = one(candidate for candidate in inventory.candidates if candidate.path == str(self.registry))

        self.assertEqual(registry_candidate.ownership, Ownership.AMBIGUOUS)
        self.assertIn(registry_candidate.candidate_id, plan.blocked_candidate_ids)
        self.assertIn(str(self.settings), {operation.path for operation in plan.operations})
        self.assertNotIn(str(self.registry), {operation.path for operation in plan.operations})

    def test_stale_or_unaffected_pi_session_does_not_create_lifecycle_authority(self) -> None:
        adapter = PiAdapter(
            self.catalog,
            process_probe=FakePiProbe(
                {"running": False, "loaded_gentle_pi": True, "restartable": False},
                {"running": True, "loaded_gentle_pi": False, "restartable": False},
            ),
        )
        plan = plan_for(self.context, adapter)

        self.assertEqual(plan.lifecycle_actions, ())
        self.assertIn(str(self.registry), {operation.path for operation in plan.operations})

    def test_quiet_period_verification_fails_if_registry_regrows(self) -> None:
        data = json.loads(self.settings.read_text())
        data["packages"] = ["npm:gentle-engram"]
        self.settings.write_text(json.dumps(data, indent=2) + "\n")
        self.registry.unlink()
        clock = FakeClock()

        def regrow(call_count: int) -> None:
            if call_count == 1:
                self.registry.parent.mkdir(exist_ok=True)
                self.registry.write_text(FIXTURE_ROOT.joinpath("skill-registry.md").read_text())

        adapter = PiAdapter(self.catalog, clock=clock, sleeper=FakeSleeper(clock, on_sleep=regrow), quiet_interval=2.0, poll_interval=0.5)

        with self.assertRaisesRegex(ValueError, "verify_pi_registry_regrew"):
            adapter.verify(type("ReceiptLike", (), {"operation_outcomes": (), "checks": ()})(), self.context)

    def test_project_root_registry_delete_can_apply_and_restore(self) -> None:
        plan = plan_for(self.context, PiAdapter(self.catalog, process_probe=FakePiProbe()))
        registry_operation = one(operation for operation in plan.operations if operation.path == str(self.registry))
        self.assertEqual(registry_operation.kind, OperationKind.DELETE_FILE)

        manifest = create_backup(plan, self.context)
        outcomes = apply_operations(plan, manifest, self.context)
        self.assertFalse(self.registry.exists())
        rollback(manifest, outcomes, self.context)
        self.assertTrue(self.registry.is_file())

    def test_invalid_settings_json_blocks_inventory_and_no_mutation(self) -> None:
        self.settings.write_text('{"packages": [')
        inventory = build_inventory(self.context, (PiAdapter(self.catalog),))
        plan = build_plan(inventory, self.context, (PiAdapter(self.catalog),))

        self.assertEqual(inventory.candidates, ())
        self.assertEqual(len(inventory.findings), 1)
        self.assertIn("pi_settings_json_malformed", inventory.findings[0].message)
        self.assertEqual(plan.operations, ())

    def test_second_inventory_plan_after_apply_is_idempotent(self) -> None:
        adapter = PiAdapter(self.catalog, process_probe=FakePiProbe())
        first_plan = plan_for(self.context, adapter)
        self.assertTrue(first_plan.operations)
        apply_to_fixture(first_plan, self.context)

        second_inventory = build_inventory(self.context, (PiAdapter(self.catalog),))
        second_plan = build_plan(second_inventory, self.context, (PiAdapter(self.catalog),))

        self.assertEqual(second_plan.operations, ())
        self.assertFalse(any(candidate.ownership is Ownership.PROVEN and candidate.proposed_action != "report_only" for candidate in second_inventory.candidates))


if __name__ == "__main__":
    unittest.main()
