from __future__ import annotations

import base64
import hashlib
import json
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

from helper.clients.codex import CodexAdapter, remove_toml_table_family, sanitize_runtime_profile
from helper.engine import build_inventory, build_plan
from helper.models import CompletedCommand, LifecycleOutcome, PlatformProfile, ProcessSnapshot, ReceiptStatus, RuntimeContext
from helper.paths import resolve_state_root
from helper.transaction import create_backup, execute_plan

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "codex"


def fixture(relative: str) -> str:
    return (Path(__file__).resolve().parents[1] / "fixtures" / relative).read_text()


def context_for(home: Path, **env: str) -> RuntimeContext:
    return RuntimeContext(PlatformProfile("linux", home, dict(env)))


def build_codex_fixture(temp_root: Path, *, include_archives: bool = True) -> Path:
    home = temp_root / "home"
    home.mkdir(parents=True)
    codex = home / ".codex"
    codex.mkdir()
    shutil.copy2(FIXTURE_ROOT / "config.toml", codex / "config.toml")
    shutil.copy2(FIXTURE_ROOT / "config.toml", codex / "config.toml.bak")
    shutil.copy2(FIXTURE_ROOT / "global-state.json", codex / "global-state.json")
    shutil.copy2(FIXTURE_ROOT / "global-state.json", codex / "global-state.json.bak")
    shutil.copy2(FIXTURE_ROOT / "global-state.json", codex / ".global-state.json.atomic.tmp")
    if include_archives:
        archived = codex / "archived_sessions"
        archived.mkdir()
        shutil.copy2(FIXTURE_ROOT / "archived-session.jsonl", archived / "archived-session.jsonl")
        sessions = codex / "sessions"
        sessions.mkdir()
        shutil.copy2(FIXTURE_ROOT / "archived-session.jsonl", sessions / "session.jsonl")
    return home


def thread_ids(value: object) -> list[str]:
    if isinstance(value, dict):
        ids: list[str] = []
        if isinstance(value.get("id"), str) and "messages" in value:
            ids.append(value["id"])
        for child in value.values():
            ids.extend(thread_ids(child))
        return ids
    if isinstance(value, list):
        ids = []
        for child in value:
            ids.extend(thread_ids(child))
        return ids
    return []


def message_metadata(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        items: list[dict[str, object]] = []
        if "role" in value and isinstance(value.get("metadata"), dict):
            items.append(value["metadata"])
        for child in value.values():
            items.extend(message_metadata(child))
        return items
    if isinstance(value, list):
        items = []
        for child in value:
            items.extend(message_metadata(child))
        return items
    return []


def any_active_profile_id(value: object, profile_id: str) -> bool:
    if isinstance(value, dict):
        profile = value.get("activePermissionProfile")
        if isinstance(profile, dict) and profile.get("id") == profile_id:
            return True
        return any(any_active_profile_id(child, profile_id) for child in value.values())
    if isinstance(value, list):
        return any(any_active_profile_id(child, profile_id) for child in value)
    return False


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class SmokeRunner:
    def __init__(self, *, missing: bool = False, returncode: int = 0) -> None:
        self.missing = missing
        self.returncode = returncode
        self.commands: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], timeout: float) -> CompletedCommand:
        self.commands.append(argv)
        if self.missing:
            raise FileNotFoundError(argv[0])
        return CompletedCommand(argv=argv, returncode=self.returncode, stdout="codex 1.2.3\n")


class ShutdownWritesRecoveryLifecycle:
    def __init__(self, recovery_path: Path, content: str) -> None:
        self.recovery_path = recovery_path
        self.content = content
        self.calls: list[str] = []

    def preflight(self, actions, context):
        self.calls.append("preflight")
        return tuple(
            ProcessSnapshot(
                action=action,
                platform=context.profile.os_name,
                running=True,
                pid=123,
                process_name="Codex",
                executable="/usr/bin/codex",
                argv=("/usr/bin/codex", "--foreground"),
                identity="linux:123:/usr/bin/codex",
            )
            for action in actions
        )

    def stop(self, snapshot):
        self.calls.append("stop")
        self.recovery_path.write_text(self.content)
        return LifecycleOutcome(action="stop", client=snapshot.action.client, target=snapshot.action.target, status="stopped", pid=snapshot.pid)

    def restart(self, snapshot):
        self.calls.append("restart")
        return LifecycleOutcome(action="restart", client=snapshot.action.client, target=snapshot.action.target, status="restarted", pid=snapshot.pid)


class CodexAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)

    def test_removes_noncontiguous_profile_tables_and_selector(self) -> None:
        text = fixture("codex/config.toml")
        cleaned = remove_toml_table_family(text, "permissions.gentle-dev")
        parsed = tomllib.loads(cleaned)
        self.assertNotEqual(parsed.get("default_permissions"), "gentle-dev")
        self.assertNotIn("gentle-dev", parsed.get("permissions", {}))
        self.assertEqual(parsed["mcp_servers"], tomllib.loads(text)["mcp_servers"])
        self.assertIn("# Codex configuration fixture\n", cleaned)
        self.assertIn("[permissions.other.nested]\nallow = [\"keep\"]\n", cleaned)

    def test_toml_parser_fail_closed_cases(self) -> None:
        with self.assertRaisesRegex(ValueError, "codex_toml_malformed"):
            remove_toml_table_family("default_permissions = [\n", "permissions.gentle-dev")
        with self.assertRaisesRegex(ValueError, "codex_toml_unsafe_quoted_header"):
            remove_toml_table_family('["permissions"."gentle-dev"]\ndescription = "Gentle development permissions managed by gentle-ai"\n', "permissions.gentle-dev")
        with self.assertRaisesRegex(ValueError, "codex_profile_ownership_unproven"):
            remove_toml_table_family('[permissions.gentle-dev]\ndescription = "User profile"\n', "permissions.gentle-dev")

    def test_sanitizes_runtime_profiles_without_deleting_threads(self) -> None:
        before = json.loads(fixture("codex/global-state.json"))
        after, count = sanitize_runtime_profile(before, "gentle-dev")
        self.assertEqual(count, 2)
        self.assertEqual(set(thread_ids(after)), set(thread_ids(before)))
        self.assertEqual(message_metadata(after), message_metadata(before))
        self.assertFalse(any_active_profile_id(after, "gentle-dev"))
        self.assertIsNone(after["threads"][1]["activePermissionProfile"])
        self.assertEqual(after["profiles"], before["profiles"])

    def test_archived_sessions_are_report_only_and_hash_preserved(self) -> None:
        home = build_codex_fixture(self.temp_root)
        archived = home / ".codex" / "archived_sessions" / "archived-session.jsonl"
        session = home / ".codex" / "sessions" / "session.jsonl"
        before_hashes = {archived: sha256_file(archived), session: sha256_file(session)}

        inventory = build_inventory(context_for(home), (CodexAdapter(),))
        candidates = [c for c in inventory.candidates if "archived_sessions" in c.path or "/sessions/" in c.path]
        self.assertTrue(candidates)
        self.assertTrue(all(c.proposed_action == "report_only" for c in candidates))
        plan = build_plan(inventory, context_for(home), (CodexAdapter(),))

        self.assertFalse(any(operation.path in {str(archived), str(session)} for operation in plan.operations))
        self.assertEqual({archived: sha256_file(archived), session: sha256_file(session)}, before_hashes)

    def test_inventory_plan_apply_sanitizes_current_and_recovery_then_is_idempotent(self) -> None:
        home = build_codex_fixture(self.temp_root)
        config_recovery = home / ".codex" / ".config.toml.atomic.tmp"
        config_recovery.write_text(fixture("codex/config.toml"))
        context = context_for(home, XDG_STATE_HOME=str(self.temp_root / "state"))
        adapter = CodexAdapter()
        original_recovery_mcp = tomllib.loads(config_recovery.read_text())["mcp_servers"]

        first_inventory = build_inventory(context, (adapter,))
        self.assertEqual(first_inventory.findings, ())
        first_plan = build_plan(first_inventory, context, (adapter,))
        operation_paths = {Path(operation.path).name for operation in first_plan.operations}

        self.assertIn("config.toml", operation_paths)
        self.assertIn("config.toml.bak", operation_paths)
        self.assertIn(".config.toml.atomic.tmp", operation_paths)
        self.assertIn("global-state.json", operation_paths)
        self.assertIn("global-state.json.bak", operation_paths)
        self.assertIn(".global-state.json.atomic.tmp", operation_paths)
        self.assertEqual(len(first_plan.lifecycle_actions), 1)
        self.assertEqual(first_plan.lifecycle_actions[0].details["process_name"], "Codex")
        self.assertEqual(first_plan.lifecycle_actions[0].details["bundle_id"], "com.openai.codex")

        receipt = execute_plan(first_plan, first_plan.digest or "", context, lifecycle=ShutdownWritesRecoveryLifecycle(home / ".codex" / "never-created", ""))
        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        adapter.verify(receipt, context)
        self.assertFalse(any_active_profile_id(json.loads((home / ".codex" / "global-state.json").read_text()), "gentle-dev"))
        self.assertNotIn("gentle-dev", tomllib.loads((home / ".codex" / "config.toml.bak").read_text()).get("permissions", {}))
        cleaned_recovery = tomllib.loads(config_recovery.read_text())
        self.assertNotEqual(cleaned_recovery.get("default_permissions"), "gentle-dev")
        self.assertNotIn("gentle-dev", cleaned_recovery.get("permissions", {}))
        self.assertEqual(cleaned_recovery["mcp_servers"], original_recovery_mcp)

        second_inventory = build_inventory(context, (CodexAdapter(),))
        second_plan = build_plan(second_inventory, context, (CodexAdapter(),))
        self.assertEqual(second_plan.operations, ())

    def test_malformed_config_recovery_temp_fails_closed_as_toml_not_json(self) -> None:
        home = build_codex_fixture(self.temp_root, include_archives=False)
        (home / ".codex" / ".config.toml.bad.tmp").write_text("default_permissions = [\n")
        context = context_for(home, XDG_STATE_HOME=str(self.temp_root / "state"))

        inventory = build_inventory(context, (CodexAdapter(),))

        self.assertEqual([finding.message for finding in inventory.findings], ["codex_toml_malformed"])

    def test_governed_recovery_member_sets_invalidate_on_appearance_removal_or_change(self) -> None:
        cases = (
            ("config_appearance", ".config.toml.late.tmp", "appear", fixture("codex/config.toml")),
            ("runtime_appearance", ".global-state.json.late.tmp", "appear", fixture("codex/global-state.json")),
            ("config_removal", ".config.toml.present.tmp", "remove", fixture("codex/config.toml")),
            ("runtime_removal", ".global-state.json.atomic.tmp", "remove", fixture("codex/global-state.json")),
            ("config_change", ".config.toml.present.tmp", "change", fixture("codex/config.toml") + "\n# shutdown write\n"),
            ("runtime_change", ".global-state.json.atomic.tmp", "change", "{}\n"),
        )
        for case_name, file_name, mutation, mutated_content in cases:
            with self.subTest(case=case_name):
                home = build_codex_fixture(self.temp_root / case_name, include_archives=False)
                context = context_for(home, XDG_STATE_HOME=str(self.temp_root / "state" / case_name))
                target = home / ".codex" / file_name
                if mutation in {"remove", "change"} and not target.exists():
                    target.write_text(fixture("codex/config.toml") if "config" in file_name else fixture("codex/global-state.json"))
                adapter = CodexAdapter()
                inventory = build_inventory(context, (adapter,))
                self.assertEqual(inventory.findings, ())
                plan = build_plan(inventory, context, (adapter,))

                if mutation == "appear":
                    target.write_text(mutated_content)
                elif mutation == "remove":
                    target.unlink()
                else:
                    target.write_text(mutated_content)

                with self.assertRaisesRegex(ValueError, "preflight_directory_members_drift"):
                    create_backup(plan, context)

                self.assertFalse((resolve_state_root(context.profile) / "backups").exists())

    def test_shutdown_recovery_write_invalidates_plan_before_backup_or_mutation(self) -> None:
        home = build_codex_fixture(self.temp_root, include_archives=False)
        context = context_for(home, XDG_STATE_HOME=str(self.temp_root / "state"))
        adapter = CodexAdapter()
        inventory = build_inventory(context, (adapter,))
        plan = build_plan(inventory, context, (adapter,))
        current = home / ".codex" / "global-state.json"
        before = current.read_text()
        late = home / ".codex" / ".global-state.json.shutdown.tmp"

        receipt = execute_plan(plan, plan.digest or "", context, ShutdownWritesRecoveryLifecycle(late, fixture("codex/global-state.json")))

        self.assertEqual(receipt.status, ReceiptStatus.FAILED)
        self.assertIsNone(receipt.backup_manifest_path)
        self.assertEqual(current.read_text(), before)
        self.assertTrue(late.exists())
        self.assertEqual(receipt.operation_outcomes[0].error, "preflight_preimage_drift_after_shutdown")
        self.assertFalse((resolve_state_root(context.profile) / "backups").exists())

    def test_verify_reads_live_state_and_uses_argv_only_smoke_runner(self) -> None:
        home = build_codex_fixture(self.temp_root, include_archives=False)
        context = context_for(home)
        inventory = build_inventory(context, (CodexAdapter(),))
        plan = build_plan(inventory, context, (CodexAdapter(),))
        manifest = create_backup(plan, context)
        from helper.transaction import apply_operations

        outcomes = apply_operations(plan, manifest, context)
        runner = SmokeRunner()
        CodexAdapter(runner=runner).verify(type("ReceiptLike", (), {"operation_outcomes": outcomes, "checks": ()})(), context)

        self.assertEqual(runner.commands, [("codex", "--version")])

    def test_verify_reports_missing_smoke_executable(self) -> None:
        home = self.temp_root / "home"
        home.mkdir()
        runner = SmokeRunner(missing=True)
        with self.assertRaisesRegex(ValueError, "codex_smoke_missing_executable"):
            CodexAdapter(runner=runner).verify(type("ReceiptLike", (), {"operation_outcomes": (), "checks": ()})(), context_for(home))
        self.assertEqual(runner.commands, [("codex", "--version")])


if __name__ == "__main__":
    unittest.main()
