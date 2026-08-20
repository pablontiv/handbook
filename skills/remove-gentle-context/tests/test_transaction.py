from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from helper.canonical import digest_json
from helper.models import Inventory, LifecycleAction, LifecycleOutcome, Operation, OperationKind, Plan, PlatformProfile, ProcessSnapshot, ReceiptStatus, RuntimeContext
from helper.paths import resolve_state_root, root_map
from helper.transaction import OperationApplyError, _read_regular_file_bound, _same_file_identity, apply_operations, create_backup, execute_plan, restore


class NoopLifecycle:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def prepare(self, *args, **kwargs):
        self.calls.append("prepare")
        return ()


class FakeTransactionLifecycle:
    def __init__(self, *, target: Path | None = None, shutdown_content: str | None = None, restart_succeeds: bool = True, running: bool = True) -> None:
        self.target = target
        self.shutdown_content = shutdown_content
        self.restart_succeeds = restart_succeeds
        self.running = running
        self.calls: list[str] = []
        self.stopped: list[ProcessSnapshot] = []
        self.restarted: list[ProcessSnapshot] = []

    def preflight(self, actions, context):
        self.calls.append("preflight")
        if not self.running:
            return ()
        return tuple(
            ProcessSnapshot(
                action=action,
                platform=context.profile.os_name,
                running=True,
                pid=123,
                process_name=action.target or action.client,
                executable="/usr/bin/codex",
                argv=("/usr/bin/codex", "--foreground"),
                identity="linux:123:/usr/bin/codex",
            )
            for action in actions
        )

    def stop(self, snapshot):
        self.calls.append("stop")
        self.stopped.append(snapshot)
        if self.target is not None and self.shutdown_content is not None:
            self.target.write_text(self.shutdown_content)
        return LifecycleOutcome(action="stop", client=snapshot.action.client, target=snapshot.action.target, status="stopped", pid=snapshot.pid)

    def restart(self, snapshot):
        self.calls.append("restart")
        self.restarted.append(snapshot)
        status = "restarted" if self.restart_succeeds else "failed"
        code = None if self.restart_succeeds else "lifecycle_restart_failed"
        return LifecycleOutcome(action="restart", client=snapshot.action.client, target=snapshot.action.target, status=status, code=code, pid=snapshot.pid)


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def image(content: bytes) -> tuple[str, str]:
    return base64.b64encode(content).decode("ascii"), sha256_bytes(content)


def plan_home(home: Path) -> str:
    return str(home.resolve(strict=False))


def write_plan(path: Path, before: bytes | None, after: bytes, *, home: Path, details: dict[str, object] | None = None) -> Plan:
    pre_b64, pre_digest = (None, None) if before is None else image(before)
    post_b64, post_digest = image(after)
    return Plan(
        os_name="linux",
        home=plan_home(home),
        operations=(
            Operation(
                kind=OperationKind.WRITE_FILE,
                path=str(path),
                preimage_base64=pre_b64,
                preimage_sha256=pre_digest,
                postimage_base64=post_b64,
                postimage_sha256=post_digest,
                details={} if details is None else details,
            ),
        ),
    ).with_digest()


def lifecycle_write_plan(path: Path, before: bytes, after: bytes, *, home: Path) -> Plan:
    base = write_plan(path, before, after, home=home)
    return Plan(
        os_name=base.os_name,
        home=base.home,
        operations=base.operations,
        lifecycle_actions=(LifecycleAction(candidate_id="codex-config", client="codex", action="stop", target="codex", reason="quiesce before edit", details={"process_name": "codex", "restart_argv": ["/usr/bin/codex", "--foreground"]}),),
    ).with_digest()


def delete_plan(path: Path, before: bytes, *, home: Path) -> Plan:
    pre_b64, pre_digest = image(before)
    return Plan(
        os_name="linux",
        home=plan_home(home),
        operations=(Operation(kind=OperationKind.DELETE_FILE, path=str(path), preimage_base64=pre_b64, preimage_sha256=pre_digest),),
    ).with_digest()


def delete_plan_for_many(paths_and_preimages: tuple[tuple[Path, bytes], ...], home: Path) -> Plan:
    operations = []
    for path, before in paths_and_preimages:
        pre_b64, pre_digest = image(before)
        operations.append(Operation(kind=OperationKind.DELETE_FILE, path=str(path), preimage_base64=pre_b64, preimage_sha256=pre_digest))
    return Plan(os_name="linux", home=str(home), operations=tuple(operations)).with_digest()


def remove_empty_dir_plan(path: Path, *, home: Path) -> Plan:
    return Plan(os_name="linux", home=plan_home(home), operations=(Operation(kind=OperationKind.REMOVE_EMPTY_DIRECTORY, path=str(path)),)).with_digest()


@contextmanager
def injected_replace_failure(target: Path):
    original = os.replace

    def fail_for_target(src, dst):
        if Path(dst) == target:
            raise OSError("injected replace failure")
        return original(src, dst)

    with patch("helper.transaction.os.replace", side_effect=fail_for_target):
        yield


@contextmanager
def injected_unlink_failure(target: Path):
    original = os.unlink

    def fail_for_target(path, *args, **kwargs):
        if Path(path) == target:
            raise OSError("injected unlink failure")
        return original(path, *args, **kwargs)

    with patch("helper.transaction.os.unlink", side_effect=fail_for_target):
        yield


class SyntheticStat:
    def __init__(self, *, st_mode: int = stat.S_IFREG | 0o600, st_size: int = 0, st_ino: object = 1, st_dev: object = 1) -> None:
        self.st_mode = st_mode
        self.st_size = st_size
        if st_ino != "missing":
            self.st_ino = st_ino
        if st_dev != "missing":
            self.st_dev = st_dev


class FileIdentityTests(unittest.TestCase):
    def test_same_file_identity_requires_reliable_nonzero_inode(self):
        self.assertFalse(_same_file_identity(SyntheticStat(st_ino=0, st_dev=1), SyntheticStat(st_ino=0, st_dev=1)))
        self.assertFalse(_same_file_identity(SyntheticStat(st_ino="missing", st_dev=1), SyntheticStat(st_ino=1, st_dev=1)))
        self.assertFalse(_same_file_identity(SyntheticStat(st_ino="abc", st_dev=1), SyntheticStat(st_ino="abc", st_dev=1)))

    def test_same_file_identity_compares_inode_and_reliable_device(self):
        self.assertTrue(_same_file_identity(SyntheticStat(st_ino=7, st_dev=3), SyntheticStat(st_ino=7, st_dev=3)))
        self.assertFalse(_same_file_identity(SyntheticStat(st_ino=7, st_dev=3), SyntheticStat(st_ino=8, st_dev=3)))
        self.assertFalse(_same_file_identity(SyntheticStat(st_ino=7, st_dev=3), SyntheticStat(st_ino=7, st_dev=4)))

    def test_same_file_identity_accepts_stable_inode_when_device_is_zero(self):
        self.assertTrue(_same_file_identity(SyntheticStat(st_ino=7, st_dev=0), SyntheticStat(st_ino=7, st_dev=0)))
        self.assertTrue(_same_file_identity(SyntheticStat(st_ino=7, st_dev="missing"), SyntheticStat(st_ino=7, st_dev="missing")))

    def test_bound_read_includes_binary_flag_when_available(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "binary-flag.txt"
            target.write_bytes(b"raw\r\nbytes")
            native_binary = getattr(os, "O_BINARY", 0)
            synthetic_binary = 0x800000
            while synthetic_binary & native_binary:
                synthetic_binary <<= 1
            original_open = os.open
            opened_flags: list[int] = []
            forwarded_flags: list[int] = []

            def open_stripping_synthetic_binary(path, flags, *args, **kwargs):
                opened_flags.append(flags)
                real_flags = (flags & ~synthetic_binary) | native_binary
                forwarded_flags.append(real_flags)
                return original_open(path, real_flags, *args, **kwargs)

            with patch("helper.transaction.os.O_BINARY", synthetic_binary, create=True), patch("helper.transaction.os.open", side_effect=open_stripping_synthetic_binary):
                _stat_result, content = _read_regular_file_bound(
                    target,
                    expected_content=b"raw\r\nbytes",
                    expected_sha256=sha256_bytes(b"raw\r\nbytes"),
                    expected_size=len(b"raw\r\nbytes"),
                    mismatch_code="preflight_preimage_drift",
                    link_code="preflight_unexpected_link",
                    not_regular_code="preflight_not_regular_file",
                )

            self.assertEqual(content, b"raw\r\nbytes")
            self.assertEqual(len(opened_flags), 1)
            self.assertEqual(len(forwarded_flags), 1)
            self.assertTrue(opened_flags[0] & synthetic_binary)
            self.assertFalse(forwarded_flags[0] & synthetic_binary)
            if native_binary:
                self.assertTrue(forwarded_flags[0] & native_binary)
            if hasattr(os, "O_NOFOLLOW"):
                self.assertTrue(opened_flags[0] & os.O_NOFOLLOW)

    def test_bound_read_preserves_raw_crlf_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "crlf.txt"
            raw = b"line-one\r\nline-two\r\n"
            target.write_bytes(raw)

            _stat_result, content = _read_regular_file_bound(
                target,
                expected_content=raw,
                expected_sha256=sha256_bytes(raw),
                expected_size=len(raw),
                mismatch_code="preflight_preimage_drift",
                link_code="preflight_unexpected_link",
                not_regular_code="preflight_not_regular_file",
            )

        self.assertEqual(content, raw)


class TransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)
        self.home = self.temp_root / "home"
        self.home.mkdir()
        self.state = self.temp_root / "state"
        self.context = RuntimeContext(PlatformProfile("linux", self.home, {"XDG_STATE_HOME": str(self.state.resolve(strict=False))}))

    def make_file(self, relative: str, content: str, *, mode: int = 0o640) -> Path:
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(mode)
        return path

    def canonical_inventory(self, *, adapter_versions: dict[str, str] | None = None) -> Inventory:
        return Inventory(
            os_name=self.context.profile.os_name,
            home=str(self.home.resolve(strict=False)),
            root_map=dict(sorted(root_map(self.context).items())),
            environment=dict(sorted(self.context.profile.env.items())),
            adapter_versions={} if adapter_versions is None else dict(sorted(adapter_versions.items())),
        ).with_digest()

    def bind_plan(self, plan: Plan, inventory: Inventory | None = None) -> tuple[Inventory, Plan]:
        bound_inventory = self.canonical_inventory() if inventory is None else inventory
        bound_plan = Plan(
            inventory_digest=bound_inventory.digest,
            os_name=bound_inventory.os_name,
            home=bound_inventory.home,
            root_map=dict(sorted(bound_inventory.root_map.items())),
            adapter_versions=dict(sorted(bound_inventory.adapter_versions.items())),
            operations=plan.operations,
            blocked_candidate_ids=plan.blocked_candidate_ids,
            dependencies=plan.dependencies,
            lifecycle_actions=plan.lifecycle_actions,
            preservation_assertions=plan.preservation_assertions,
        ).with_digest()
        return bound_inventory, bound_plan

    def execute_bound(self, plan: Plan, lifecycle: object | None = None):
        inventory, bound_plan = self.bind_plan(plan)
        receipt = execute_plan(bound_plan, bound_plan.digest or "", self.context, NoopLifecycle() if lifecycle is None else lifecycle, inventory=inventory)
        self.assertEqual(receipt.inventory, inventory)
        return inventory, bound_plan, receipt

    def assert_verified_manifest_for_plan(self, manifest_path: Path | None, plan: Plan) -> None:
        self.assertIsNotNone(manifest_path)
        assert manifest_path is not None
        self.assertTrue(manifest_path.exists())
        manifest_data = json.loads(manifest_path.read_text())
        self.assertEqual(manifest_data["plan_digest"], plan.digest)
        self.assertEqual(manifest_data["digest"], digest_json({key: value for key, value in manifest_data.items() if key != "digest"}))

    def execution_artifact_fixture(self) -> tuple[Path, Inventory, Plan, FakeTransactionLifecycle]:
        target = self.make_file("artifact-binding.txt", "before")
        inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        return target, inventory, plan, FakeTransactionLifecycle()

    def assert_execution_artifact_rejected_without_side_effects(self, inventory: Inventory, plan: Plan, lifecycle: FakeTransactionLifecycle, target: Path, code: str) -> None:
        with self.assertRaisesRegex(ValueError, code):
            execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, [])
        self.assertFalse((resolve_state_root(self.context.profile) / "backups").exists())

    def test_tampered_inventory_environment_aborts_before_lifecycle_backup_or_mutation(self):
        target, inventory, plan, lifecycle = self.execution_artifact_fixture()
        other_state = self.temp_root / "other-state"
        tampered_inventory = replace(inventory, environment={"XDG_STATE_HOME": str(other_state.resolve(strict=False))}).with_digest()
        rebound_plan = replace(plan, inventory_digest=tampered_inventory.digest).with_digest()

        self.assert_execution_artifact_rejected_without_side_effects(tampered_inventory, rebound_plan, lifecycle, target, "execute_inventory_environment_mismatch")

    def test_preimage_drift_aborts_before_backup_or_mutation(self):
        target = self.make_file(".codex/config.toml", "before")
        plan = write_plan(target, b"before", b"after", home=self.home)
        target.write_text("drift")

        with self.assertRaisesRegex(ValueError, "preflight_preimage_drift"):
            create_backup(plan, self.context)

        self.assertEqual(target.read_text(), "drift")
        self.assertFalse((resolve_state_root(self.context.profile) / "backups").exists())

    def test_zero_inode_aborts_before_backup_or_mutation(self):
        target = self.make_file("zero-inode.txt", "before")
        plan = write_plan(target, b"before", b"after", home=self.home)
        original_lstat = os.lstat
        original_fstat = os.fstat

        def zero_inode_stat(stat_result: os.stat_result) -> SyntheticStat:
            return SyntheticStat(st_mode=stat_result.st_mode, st_size=stat_result.st_size, st_ino=0, st_dev=stat_result.st_dev)

        def lstat_with_zero_inode(path, *args, **kwargs):
            stat_result = original_lstat(path, *args, **kwargs)
            if Path(path) == target:
                return zero_inode_stat(stat_result)
            return stat_result

        with patch("helper.transaction.os.lstat", side_effect=lstat_with_zero_inode), patch("helper.transaction.os.fstat", side_effect=lambda fd: zero_inode_stat(original_fstat(fd))):
            with self.assertRaisesRegex(ValueError, "preflight_preimage_drift"):
                create_backup(plan, self.context)

        self.assertEqual(target.read_text(), "before")
        self.assertFalse((resolve_state_root(self.context.profile) / "backups").exists())

    def test_execute_plan_missing_inventory_is_rejected_before_lifecycle_backup_or_mutation(self):
        target = self.make_file("missing-inventory.txt", "before")
        _inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        lifecycle = FakeTransactionLifecycle()

        with self.assertRaises(TypeError):
            execute_plan(plan, plan.digest or "", self.context, lifecycle)

        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, [])
        self.assertFalse((resolve_state_root(self.context.profile) / "backups").exists())

    def test_execute_plan_invalid_artifacts_are_rejected_before_lifecycle_backup_or_mutation(self):
        target = self.make_file("mismatched-inventory.txt", "before")
        correct_inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        wrong_inventory = self.canonical_inventory(adapter_versions={"other": "1"})
        lifecycle = FakeTransactionLifecycle()

        with self.assertRaisesRegex(ValueError, "execute_plan_inventory_digest_mismatch"):
            execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=wrong_inventory)

        self.assertNotEqual(correct_inventory.digest, wrong_inventory.digest)
        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, [])
        self.assertFalse((resolve_state_root(self.context.profile) / "backups").exists())

        digest_cases = (
            (
                "execute_inventory_digest_mismatch",
                lambda inventory, plan: (replace(inventory, digest="sha256:" + "0" * 64), plan),
            ),
            (
                "execute_plan_digest_mismatch",
                lambda inventory, plan: (inventory, replace(plan, digest="sha256:" + "0" * 64)),
            ),
        )
        for code, tamper in digest_cases:
            with self.subTest(code=code):
                target, inventory, plan, lifecycle = self.execution_artifact_fixture()
                tampered_inventory, tampered_plan = tamper(inventory, plan)
                self.assert_execution_artifact_rejected_without_side_effects(tampered_inventory, tampered_plan, lifecycle, target, code)

        other_home = self.temp_root / "other-home"
        other_home.mkdir()
        bad_roots = {**dict(root_map(self.context)), "unexpected": str(self.temp_root / "unexpected-root")}
        binding_cases = (
            (
                "execute_inventory_home_mismatch",
                lambda inventory, plan: (
                    (bad_inventory := replace(inventory, home=str(other_home.resolve(strict=False))).with_digest()),
                    replace(plan, inventory_digest=bad_inventory.digest).with_digest(),
                ),
            ),
            (
                "execute_plan_home_mismatch",
                lambda inventory, plan: (inventory, replace(plan, home=str(other_home.resolve(strict=False))).with_digest()),
            ),
            (
                "execute_inventory_os_mismatch",
                lambda inventory, plan: (
                    (bad_inventory := replace(inventory, os_name="darwin").with_digest()),
                    replace(plan, inventory_digest=bad_inventory.digest).with_digest(),
                ),
            ),
            (
                "execute_plan_os_mismatch",
                lambda inventory, plan: (inventory, replace(plan, os_name="darwin").with_digest()),
            ),
            (
                "execute_inventory_roots_mismatch",
                lambda inventory, plan: (
                    (bad_inventory := replace(inventory, root_map=bad_roots).with_digest()),
                    replace(plan, inventory_digest=bad_inventory.digest).with_digest(),
                ),
            ),
            (
                "execute_plan_roots_mismatch",
                lambda inventory, plan: (inventory, replace(plan, root_map=bad_roots).with_digest()),
            ),
        )
        for code, tamper in binding_cases:
            with self.subTest(code=code):
                target, inventory, plan, lifecycle = self.execution_artifact_fixture()
                tampered_inventory, tampered_plan = tamper(inventory, plan)
                self.assert_execution_artifact_rejected_without_side_effects(tampered_inventory, tampered_plan, lifecycle, target, code)

    def test_second_write_failure_rolls_back_first_write(self):
        first = self.make_file("one", "before-one")
        second = self.make_file("two", "before-two")
        first_post_b64, first_post_digest = image(b"after-one")
        second_post_b64, second_post_digest = image(b"after-two")
        first_pre_b64, first_pre_digest = image(b"before-one")
        second_pre_b64, second_pre_digest = image(b"before-two")
        plan = Plan(
            os_name="linux",
            home=str(self.home),
            operations=(
                Operation(kind=OperationKind.WRITE_FILE, path=str(first), preimage_base64=first_pre_b64, preimage_sha256=first_pre_digest, postimage_base64=first_post_b64, postimage_sha256=first_post_digest),
                Operation(kind=OperationKind.WRITE_FILE, path=str(second), preimage_base64=second_pre_b64, preimage_sha256=second_pre_digest, postimage_base64=second_post_b64, postimage_sha256=second_post_digest),
            ),
        ).with_digest()

        with injected_replace_failure(second):
            _inventory, plan, receipt = self.execute_bound(plan)

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), "before-two")
        self.assertTrue(receipt.backup_manifest_path and receipt.backup_manifest_path.exists())

    def test_restore_rejects_manifest_path_escape(self):
        target = self.make_file("safe.txt", "before")
        plan = delete_plan(target, b"before", home=self.home)
        manifest = create_backup(plan, self.context)
        data = json.loads(manifest.path.read_text())
        data["entries"][0]["relative_path"] = "../../outside"
        data["digest"] = digest_json({key: value for key, value in data.items() if key != "digest"})
        manifest.path.write_text(json.dumps(data))

        with self.assertRaisesRegex(ValueError, "restore_path_escape"):
            restore(manifest.path, data["digest"], self.context)

    def test_backup_payload_write_failure_does_not_mutate_target(self):
        target = self.make_file("config.json", "before")
        plan = delete_plan(target, b"before", home=self.home)

        with patch("helper.transaction._write_verified_payload", side_effect=OSError("injected backup failure")):
            with self.assertRaisesRegex(OSError, "injected backup failure"):
                create_backup(plan, self.context)

        self.assertEqual(target.read_text(), "before")

    def test_backup_payload_failure_after_stop_restarts_and_returns_not_started_receipt(self):
        target = self.make_file("stopped-backup.txt", "before")
        inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        lifecycle = FakeTransactionLifecycle()

        with patch("helper.transaction._write_verified_payload", side_effect=OSError("injected backup failure")):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(len(lifecycle.restarted), 1)
        self.assertEqual(lifecycle.restarted, lifecycle.stopped)
        self.assertEqual(receipt.status, ReceiptStatus.NOT_STARTED)
        self.assertIsNone(receipt.backup_manifest_path)
        self.assertEqual(receipt.plan, plan)
        self.assertEqual(receipt.inventory, inventory)
        self.assertEqual(receipt.operation_outcomes[0].status, "failed")
        self.assertEqual(receipt.operation_outcomes[0].error, "backup_failed")

    def test_backup_payload_failure_after_stop_with_restart_failure_requires_manual_recovery(self):
        target = self.make_file("stopped-backup-restart-fails.txt", "before")
        inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        lifecycle = FakeTransactionLifecycle(restart_succeeds=False)

        with patch("helper.transaction._write_verified_payload", side_effect=OSError("injected backup failure")):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertIsNone(receipt.backup_manifest_path)
        self.assertEqual(receipt.operation_outcomes[0].error, "backup_failed")

    def test_first_postimage_hash_mismatch_returns_not_started_with_verified_manifest_and_restart(self):
        target = self.make_file("config.json", "before")
        pre_b64, pre_digest = image(b"before")
        bad_post_b64 = base64.b64encode(b"after").decode("ascii")
        base_plan = Plan(
            os_name="linux",
            home=str(self.home),
            operations=(Operation(kind=OperationKind.WRITE_FILE, path=str(target), preimage_base64=pre_b64, preimage_sha256=pre_digest, postimage_base64=bad_post_b64, postimage_sha256=sha256_bytes(b"different")),),
            lifecycle_actions=(LifecycleAction(candidate_id="codex-config", client="codex", action="stop", target="codex", reason="quiesce before edit", details={"process_name": "codex", "restart_argv": ["/usr/bin/codex", "--foreground"]}),),
        ).with_digest()
        inventory, plan = self.bind_plan(base_plan)
        lifecycle = FakeTransactionLifecycle()

        receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(receipt.status, ReceiptStatus.NOT_STARTED)
        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assert_verified_manifest_for_plan(receipt.backup_manifest_path, plan)
        self.assertEqual(
            [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes],
            [(0, "failed", "operation_postimage_digest_mismatch")],
        )

    def test_postimage_hash_mismatch_after_completed_write_rolls_back_first(self):
        first = self.make_file("postimage-first.txt", "before-one")
        second = self.make_file("postimage-second.txt", "before-two")
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        second_pre_b64, second_pre_digest = image(b"before-two")
        bad_post_b64 = base64.b64encode(b"after-two").decode("ascii")
        second_operation = Operation(kind=OperationKind.WRITE_FILE, path=str(second), preimage_base64=second_pre_b64, preimage_sha256=second_pre_digest, postimage_base64=bad_post_b64, postimage_sha256=sha256_bytes(b"different"))
        plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], second_operation)).with_digest()

        _inventory, plan, receipt = self.execute_bound(plan)

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), "before-two")
        self.assertEqual(
            [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes],
            [(0, "completed", None), (1, "failed", "operation_postimage_digest_mismatch"), (0, "rolled_back", None)],
        )

    def test_first_postimage_hash_mismatch_with_restart_failure_requires_manual_recovery(self):
        target = self.make_file("postimage-restart-failure.txt", "before")
        pre_b64, pre_digest = image(b"before")
        bad_post_b64 = base64.b64encode(b"after").decode("ascii")
        base_plan = Plan(
            os_name="linux",
            home=str(self.home),
            operations=(Operation(kind=OperationKind.WRITE_FILE, path=str(target), preimage_base64=pre_b64, preimage_sha256=pre_digest, postimage_base64=bad_post_b64, postimage_sha256=sha256_bytes(b"different")),),
            lifecycle_actions=(LifecycleAction(candidate_id="codex-config", client="codex", action="stop", target="codex", reason="quiesce before edit", details={"process_name": "codex", "restart_argv": ["/usr/bin/codex", "--foreground"]}),),
        ).with_digest()
        inventory, plan = self.bind_plan(base_plan)
        lifecycle = FakeTransactionLifecycle(restart_succeeds=False)

        receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertEqual(target.read_text(), "before")
        self.assertEqual(receipt.lifecycle_outcomes[-1].status, "failed")
        self.assertEqual(receipt.operation_outcomes[0].error, "operation_postimage_digest_mismatch")

    def test_postimage_hash_mismatch_after_completed_write_with_rollback_failure_requires_manual_recovery(self):
        first = self.make_file("postimage-rollback-failure-first.txt", "before-one")
        second = self.make_file("postimage-rollback-failure-second.txt", "before-two")
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        second_pre_b64, second_pre_digest = image(b"before-two")
        bad_post_b64 = base64.b64encode(b"after-two").decode("ascii")
        second_operation = Operation(kind=OperationKind.WRITE_FILE, path=str(second), preimage_base64=second_pre_b64, preimage_sha256=second_pre_digest, postimage_base64=bad_post_b64, postimage_sha256=sha256_bytes(b"different"))
        plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], second_operation)).with_digest()
        original_replace = os.replace

        def fail_first_rollback(src, dst):
            if Path(dst) == first and first.read_text() == "after-one":
                raise OSError("injected rollback failure")
            return original_replace(src, dst)

        with patch("helper.transaction.os.replace", side_effect=fail_first_rollback):
            _inventory, plan, receipt = self.execute_bound(plan)

        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertEqual(first.read_text(), "after-one")
        self.assertEqual(second.read_text(), "before-two")
        self.assertEqual(receipt.operation_outcomes[-1].status, "failed")

    def test_first_generic_operation_failure_is_not_reported_not_started(self):
        target = self.make_file("generic-replace-failure.txt", "before")
        inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        lifecycle = FakeTransactionLifecycle()

        with injected_replace_failure(target):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertNotEqual(receipt.status, ReceiptStatus.NOT_STARTED)
        self.assertEqual(receipt.operation_outcomes[0].error, "operation_failed")

    def test_first_declared_json_parse_failure_returns_not_started_with_verified_manifest_and_restart(self):
        target = self.home / "settings.json"
        target.write_bytes(b'{"before": true}\n')
        target.chmod(0o640)
        base_plan = lifecycle_write_plan(target, b'{"before": true}\n', b'{"after": ', home=self.home)
        operation = replace(base_plan.operations[0], details={"parse": "json"})
        base_plan = replace(base_plan, operations=(operation,)).with_digest()
        inventory, plan = self.bind_plan(base_plan)
        lifecycle = FakeTransactionLifecycle()

        receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(receipt.status, ReceiptStatus.NOT_STARTED)
        self.assertEqual(target.read_text(), '{"before": true}\n')
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assert_verified_manifest_for_plan(receipt.backup_manifest_path, plan)
        self.assertEqual(receipt.operation_outcomes[0].error, "operation_parse_failed")

    def test_declared_json_parse_failure_after_completed_write_rolls_back_first(self):
        first = self.make_file("parse-first.txt", "before-one")
        second = self.home / "parse-second.json"
        second.write_bytes(b'{"before": true}\n')
        second.chmod(0o640)
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        second_plan = write_plan(second, b'{"before": true}\n', b'{"after": ', home=self.home, details={"parse": "json"})
        plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], second_plan.operations[0])).with_digest()

        _inventory, plan, receipt = self.execute_bound(plan)

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), '{"before": true}\n')
        self.assertEqual(
            [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes],
            [(0, "completed", None), (1, "failed", "operation_parse_failed"), (0, "rolled_back", None)],
        )

    def test_delete_unlink_failure_leaves_file_and_reports_manual_recovery_when_rollback_fails(self):
        first = self.make_file("first", "before-first")
        second = self.make_file("second", "before-second")
        first_plan = write_plan(first, b"before-first", b"after-first", home=self.home)
        second_delete = delete_plan(second, b"before-second", home=self.home).operations[0]
        plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], second_delete)).with_digest()

        original_replace = os.replace

        def replace_fails_during_rollback(src, dst):
            if Path(dst) == first and first.read_text() == "after-first":
                raise OSError("injected rollback failure")
            return original_replace(src, dst)

        with injected_unlink_failure(second), patch("helper.transaction.os.replace", side_effect=replace_fails_during_rollback):
            _inventory, plan, receipt = self.execute_bound(plan)

        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertEqual(first.read_text(), "after-first")
        self.assertEqual(second.read_text(), "before-second")

    def test_idempotent_noop_still_requires_preimage(self):
        target = self.make_file("noop.txt", "same")
        plan = write_plan(target, b"same", b"same", home=self.home)

        _inventory, plan, receipt = self.execute_bound(plan)

        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertEqual(target.read_text(), "same")

        target.write_text("drift")
        with self.assertRaisesRegex(ValueError, "preflight_preimage_drift"):
            create_backup(plan, self.context)

    def test_symlink_and_windows_reparse_targets_are_rejected_before_backup(self):
        real = self.make_file("real.json", "{}")
        link = self.home / "link.json"
        link.symlink_to(real)
        plan = delete_plan(link, b"{}", home=self.home)
        with self.assertRaisesRegex(ValueError, "preflight_unexpected_link"):
            create_backup(plan, self.context)

        target = self.make_file("reparse.json", "{}")
        reparse_plan = delete_plan(target, b"{}", home=self.home)
        fake_stat = type("Stat", (), {"st_file_attributes": 0x400, "st_mode": target.lstat().st_mode, "st_size": 2})()
        with patch("helper.paths.os.lstat", return_value=fake_stat), patch("helper.transaction.os.lstat", return_value=fake_stat):
            with self.assertRaisesRegex(ValueError, "preflight_unexpected_link"):
                create_backup(reparse_plan, self.context)

    def test_backup_read_rejects_same_content_path_identity_swap(self):
        target = self.make_file("race.txt", "before")
        replacement = self.home / "replacement-source.txt"
        replacement.write_text("before")
        plan = delete_plan(target, b"before", home=self.home)
        original_open = os.open
        swapped = False

        def swap_before_guarded_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if Path(path) == target and not swapped:
                swapped = True
                target.unlink()
                replacement.rename(target)
            return original_open(path, flags, *args, **kwargs)

        with patch("helper.transaction.os.open", side_effect=swap_before_guarded_open):
            with self.assertRaisesRegex(ValueError, "preflight_preimage_drift"):
                create_backup(plan, self.context)

        self.assertTrue(swapped)
        self.assertEqual(target.read_text(), "before")
        self.assertFalse((resolve_state_root(self.context.profile) / "backups").exists())

    def test_apply_revalidation_rejects_same_content_path_identity_swap(self):
        target = self.make_file("apply-race.txt", "before")
        replacement = self.home / "apply-replacement-source.txt"
        replacement.write_text("before")
        plan = write_plan(target, b"before", b"after", home=self.home)
        manifest = create_backup(plan, self.context)
        original_open = os.open
        swapped = False

        def swap_before_guarded_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if Path(path) == target and not swapped:
                swapped = True
                target.unlink()
                replacement.rename(target)
            return original_open(path, flags, *args, **kwargs)

        with patch("helper.transaction.os.open", side_effect=swap_before_guarded_open):
            with self.assertRaisesRegex(Exception, "preflight_preimage_drift"):
                apply_operations(plan, manifest, self.context)

        self.assertTrue(swapped)
        self.assertEqual(target.read_text(), "before")

    def test_first_apply_preimage_drift_returns_not_started_with_verified_manifest_and_restart(self):
        target = self.make_file("apply-preimage-drift-first.txt", "before")
        inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        lifecycle = FakeTransactionLifecycle()
        original_create_backup = create_backup

        def drift_after_backup(plan_arg, context_arg):
            manifest = original_create_backup(plan_arg, context_arg)
            target.write_text("drift")
            return manifest

        with patch("helper.transaction.create_backup", side_effect=drift_after_backup):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(receipt.status, ReceiptStatus.NOT_STARTED)
        self.assertEqual(target.read_text(), "drift")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assert_verified_manifest_for_plan(receipt.backup_manifest_path, plan)
        self.assertEqual(receipt.operation_outcomes[0].error, "preflight_preimage_drift")

    def test_apply_preimage_drift_after_completed_write_rolls_back_first(self):
        first = self.make_file("apply-preimage-drift-one.txt", "before-one")
        second = self.make_file("apply-preimage-drift-two.txt", "before-two")
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        second_plan = write_plan(second, b"before-two", b"after-two", home=self.home)
        plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], second_plan.operations[0])).with_digest()
        original_create_backup = create_backup

        def drift_after_backup(plan_arg, context_arg):
            manifest = original_create_backup(plan_arg, context_arg)
            second.write_text("drift")
            return manifest

        with patch("helper.transaction.create_backup", side_effect=drift_after_backup):
            _inventory, plan, receipt = self.execute_bound(plan)

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), "drift")
        self.assertEqual(
            [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes],
            [(0, "completed", None), (1, "failed", "preflight_preimage_drift"), (0, "rolled_back", None)],
        )

    def test_first_remove_directory_type_preguard_returns_not_started_with_verified_manifest_and_restart(self):
        directory = self.home / "remove-dir-type-first"
        directory.mkdir()
        base_plan = Plan(
            os_name="linux",
            home=str(self.home),
            operations=(Operation(kind=OperationKind.REMOVE_EMPTY_DIRECTORY, path=str(directory)),),
            lifecycle_actions=(LifecycleAction(candidate_id="codex-config", client="codex", action="stop", target="codex", reason="quiesce before edit", details={"process_name": "codex", "restart_argv": ["/usr/bin/codex", "--foreground"]}),),
        ).with_digest()
        inventory, plan = self.bind_plan(base_plan)
        lifecycle = FakeTransactionLifecycle()
        original_create_backup = create_backup

        def replace_directory_after_backup(plan_arg, context_arg):
            manifest = original_create_backup(plan_arg, context_arg)
            directory.rmdir()
            directory.write_text("not a directory")
            return manifest

        with patch("helper.transaction.create_backup", side_effect=replace_directory_after_backup):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(receipt.status, ReceiptStatus.NOT_STARTED)
        self.assertEqual(directory.read_text(), "not a directory")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assert_verified_manifest_for_plan(receipt.backup_manifest_path, plan)
        self.assertEqual(receipt.operation_outcomes[0].error, "operation_not_directory")

    def test_remove_directory_type_preguard_after_completed_write_rolls_back_first(self):
        first = self.make_file("remove-dir-type-one.txt", "before-one")
        directory = self.home / "remove-dir-type-two"
        directory.mkdir()
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        remove_operation = remove_empty_dir_plan(directory, home=self.home).operations[0]
        plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], remove_operation)).with_digest()
        original_create_backup = create_backup

        def replace_directory_after_backup(plan_arg, context_arg):
            manifest = original_create_backup(plan_arg, context_arg)
            directory.rmdir()
            directory.write_text("not a directory")
            return manifest

        with patch("helper.transaction.create_backup", side_effect=replace_directory_after_backup):
            _inventory, plan, receipt = self.execute_bound(plan)

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(directory.read_text(), "not a directory")
        self.assertEqual(
            [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes],
            [(0, "completed", None), (1, "failed", "operation_not_directory"), (0, "rolled_back", None)],
        )

    def test_manifest_tamper_is_rejected_by_restore_digest(self):
        target = self.make_file("restore.txt", "before")
        manifest = create_backup(delete_plan(target, b"before", home=self.home), self.context)
        data = json.loads(manifest.path.read_text())
        data["entries"][0]["sha256"] = sha256_bytes(b"tampered")
        manifest.path.write_text(json.dumps(data))

        with self.assertRaisesRegex(ValueError, "restore_manifest_digest_mismatch"):
            restore(manifest.path, manifest.digest or "", self.context)

    def test_restore_is_digest_approved_and_backs_up_replacement_preimage(self):
        target = self.make_file("restore.txt", "before")
        manifest = create_backup(delete_plan(target, b"before", home=self.home), self.context)
        target.write_text("replacement")

        with self.assertRaisesRegex(ValueError, "restore_approval_mismatch"):
            restore(manifest.path, "sha256:" + "0" * 64, self.context)

        receipt = restore(manifest.path, manifest.digest or "", self.context)

        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertEqual(target.read_text(), "before")
        self.assertTrue(receipt.backup_manifest_path and receipt.backup_manifest_path.exists())
        replacement_manifest = json.loads(receipt.backup_manifest_path.read_text())
        self.assertEqual(replacement_manifest["entries"][0]["sha256"], sha256_bytes(b"replacement"))

    def test_external_project_root_file_backup_apply_restore_uses_root_id_not_audit_path(self):
        project = self.temp_root / "external-project"
        project.mkdir()
        target = project / "CLAUDE.md"
        target.write_text("before")
        target.chmod(0o640)
        context = RuntimeContext(self.context.profile, project_roots=(project,))
        plan = write_plan(target, b"before", b"after", home=self.home)

        with self.assertRaisesRegex(ValueError, "preflight_path_escape"):
            create_backup(plan, self.context)

        bound_plan = Plan(os_name="linux", home=str(self.home), root_map=root_map(context), operations=plan.operations).with_digest()
        with self.assertRaisesRegex(ValueError, "backup_plan_roots_mismatch"):
            create_backup(bound_plan, self.context)

        manifest = create_backup(bound_plan, context)
        self.assertTrue(manifest.entries[0].root_id.startswith("project-"))
        self.assertEqual(manifest.entries[0].relative_path, "CLAUDE.md")
        apply_operations(bound_plan, manifest, context)
        self.assertEqual(target.read_text(), "after")

        data = json.loads(manifest.path.read_text())
        data["entries"][0]["original_path"] = str(self.temp_root / "outside-audit-path" / "CLAUDE.md")
        data["digest"] = digest_json({key: value for key, value in data.items() if key != "digest"})
        manifest.path.write_text(json.dumps(data))

        receipt = restore(manifest.path, data["digest"], context)

        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertEqual(target.read_text(), "before")

    def test_restore_replacement_zero_inode_aborts_before_mutation(self):
        target = self.make_file("restore-zero-inode.txt", "before")
        manifest = create_backup(delete_plan(target, b"before", home=self.home), self.context)
        target.write_text("replacement")
        original_lstat = os.lstat
        original_fstat = os.fstat

        def zero_inode_stat(stat_result: os.stat_result) -> SyntheticStat:
            return SyntheticStat(st_mode=stat_result.st_mode, st_size=stat_result.st_size, st_ino=0, st_dev=stat_result.st_dev)

        def lstat_with_zero_inode(path, *args, **kwargs):
            stat_result = original_lstat(path, *args, **kwargs)
            if Path(path) == target:
                return zero_inode_stat(stat_result)
            return stat_result

        with patch("helper.transaction.os.lstat", side_effect=lstat_with_zero_inode), patch("helper.transaction.os.fstat", side_effect=lambda fd: zero_inode_stat(original_fstat(fd))):
            with self.assertRaisesRegex(ValueError, "restore_replacement_preimage_drift"):
                restore(manifest.path, manifest.digest or "", self.context)

        self.assertEqual(target.read_text(), "replacement")

    def test_restore_failure_rolls_back_replacement_file(self):
        first = self.make_file("restore-first.txt", "before-one")
        second = self.make_file("restore-second.txt", "before-two")
        manifest = create_backup(delete_plan_for_many(((first, b"before-one"), (second, b"before-two")), self.home), self.context)
        first.write_text("replacement-one")
        second.write_text("replacement-two")

        with injected_replace_failure(second):
            receipt = restore(manifest.path, manifest.digest or "", self.context)

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(first.read_text(), "replacement-one")
        self.assertEqual(second.read_text(), "replacement-two")
        self.assertTrue(receipt.backup_manifest_path and receipt.backup_manifest_path.exists())

    def test_restore_failure_removes_newly_created_destination(self):
        first = self.make_file("restore-new.txt", "before-one")
        second = self.make_file("restore-existing.txt", "before-two")
        manifest = create_backup(delete_plan_for_many(((first, b"before-one"), (second, b"before-two")), self.home), self.context)
        first.unlink()
        second.write_text("replacement-two")

        with injected_replace_failure(second):
            receipt = restore(manifest.path, manifest.digest or "", self.context)

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertFalse(first.exists())
        self.assertEqual(second.read_text(), "replacement-two")
        self.assertTrue(receipt.backup_manifest_path and receipt.backup_manifest_path.exists())

    def test_restore_rollback_failure_requires_manual_recovery(self):
        first = self.make_file("restore-manual-first.txt", "before-one")
        second = self.make_file("restore-manual-second.txt", "before-two")
        manifest = create_backup(delete_plan_for_many(((first, b"before-one"), (second, b"before-two")), self.home), self.context)
        first.write_text("replacement-one")
        second.write_text("replacement-two")
        original_replace = os.replace

        def fail_second_restore_and_first_rollback(src, dst):
            if Path(dst) == second:
                raise OSError("injected second restore failure")
            if Path(dst) == first and first.read_text() == "before-one":
                raise OSError("injected rollback failure")
            return original_replace(src, dst)

        with patch("helper.transaction.os.replace", side_effect=fail_second_restore_and_first_rollback):
            receipt = restore(manifest.path, manifest.digest or "", self.context)

        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), "replacement-two")
        self.assertTrue(receipt.backup_manifest_path and receipt.backup_manifest_path.exists())

    def test_first_nonempty_directory_refusal_returns_not_started_with_stable_code_verified_manifest_and_restart(self):
        directory = self.home / "dir"
        directory.mkdir()
        (directory / "child").write_text("x")
        base_plan = Plan(
            os_name="linux",
            home=str(self.home),
            operations=(Operation(kind=OperationKind.REMOVE_EMPTY_DIRECTORY, path=str(directory)),),
            lifecycle_actions=(LifecycleAction(candidate_id="codex-config", client="codex", action="stop", target="codex", reason="quiesce before edit", details={"process_name": "codex", "restart_argv": ["/usr/bin/codex", "--foreground"]}),),
        ).with_digest()
        inventory, plan = self.bind_plan(base_plan)
        lifecycle = FakeTransactionLifecycle()

        receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(receipt.status, ReceiptStatus.NOT_STARTED)
        self.assertTrue(directory.exists())
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assert_verified_manifest_for_plan(receipt.backup_manifest_path, plan)
        self.assertEqual(receipt.operation_outcomes[0].error, "operation_directory_not_empty")

        (directory / "child").unlink()
        _inventory, plan, receipt = self.execute_bound(remove_empty_dir_plan(directory, home=self.home))
        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertFalse(directory.exists())

    def test_nonempty_directory_refusal_after_completed_write_rolls_back_first(self):
        first = self.make_file("nonempty-before-dir.txt", "before-one")
        directory = self.home / "nonempty-second-dir"
        directory.mkdir()
        (directory / "child").write_text("x")
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        remove_operation = remove_empty_dir_plan(directory, home=self.home).operations[0]
        plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], remove_operation)).with_digest()

        _inventory, plan, receipt = self.execute_bound(plan)

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(first.read_text(), "before-one")
        self.assertTrue(directory.exists())
        self.assertEqual(receipt.operation_outcomes[1].error, "operation_directory_not_empty")

    def test_shutdown_drift_after_graceful_stop_aborts_before_backup_or_mutation_and_restarts(self):
        target = self.make_file(".codex/config.toml", "before")
        plan = lifecycle_write_plan(target, b"before", b"after", home=self.home)
        lifecycle = FakeTransactionLifecycle(target=target, shutdown_content="shutdown-drift")

        _inventory, plan, receipt = self.execute_bound(plan, lifecycle)

        self.assertEqual(receipt.status, ReceiptStatus.FAILED)
        self.assertEqual(target.read_text(), "shutdown-drift")
        self.assertIsNone(receipt.backup_manifest_path)
        self.assertFalse((resolve_state_root(self.context.profile) / "backups").exists())
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(receipt.operation_outcomes[0].error, "preflight_preimage_drift_after_shutdown")

    def test_next_plan_created_while_client_closed_binds_stable_shutdown_bytes(self):
        target = self.make_file(".codex/config.toml", "before")
        drift_plan = lifecycle_write_plan(target, b"before", b"after", home=self.home)
        drift_lifecycle = FakeTransactionLifecycle(target=target, shutdown_content="shutdown-drift")
        _inventory, drift_plan, drift_receipt = self.execute_bound(drift_plan, drift_lifecycle)
        self.assertEqual(drift_receipt.status, ReceiptStatus.FAILED)

        closed_plan = lifecycle_write_plan(target, b"shutdown-drift", b"after", home=self.home)
        closed_lifecycle = FakeTransactionLifecycle(running=False)
        _inventory, closed_plan, receipt = self.execute_bound(closed_plan, closed_lifecycle)

        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertEqual(target.read_text(), "after")
        self.assertEqual(closed_lifecycle.calls, ["preflight"])

    def test_restart_failure_after_shutdown_drift_requires_manual_recovery(self):
        target = self.make_file(".codex/config.toml", "before")
        plan = lifecycle_write_plan(target, b"before", b"after", home=self.home)
        lifecycle = FakeTransactionLifecycle(target=target, shutdown_content="shutdown-drift", restart_succeeds=False)

        _inventory, plan, receipt = self.execute_bound(plan, lifecycle)

        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertEqual(receipt.operation_outcomes[0].error, "preflight_preimage_drift_after_shutdown")
        self.assertEqual(receipt.lifecycle_outcomes[-1].status, "failed")
        self.assertIsNone(receipt.backup_manifest_path)
        self.assertEqual(target.read_text(), "shutdown-drift")

    def test_journal_failure_before_first_mutation_does_not_mutate_and_restarts(self):
        target = self.make_file("journal-before-first.txt", "before")
        inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        lifecycle = FakeTransactionLifecycle()

        def fail_before_first(manifest, transition, operation_index, operation, **kwargs):
            if transition == "before" and operation_index == 0:
                raise OSError("injected journal failure")

        with patch("helper.transaction._append_journal", side_effect=fail_before_first):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(receipt.status, ReceiptStatus.NOT_STARTED)
        self.assertTrue(receipt.backup_manifest_path and receipt.backup_manifest_path.exists())
        manifest_data = json.loads(receipt.backup_manifest_path.read_text())
        self.assertEqual(manifest_data["plan_digest"], plan.digest)
        self.assertEqual(manifest_data["digest"], digest_json({key: value for key, value in manifest_data.items() if key != "digest"}))
        self.assertEqual(receipt.operation_outcomes[0].status, "failed")
        self.assertEqual(receipt.operation_outcomes[0].error, "journal_append_failed")

    def test_journal_failure_before_second_mutation_rolls_back_first_and_restarts(self):
        first = self.make_file("journal-before-second-one.txt", "before-one")
        second = self.make_file("journal-before-second-two.txt", "before-two")
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        second_plan = write_plan(second, b"before-two", b"after-two", home=self.home)
        base_plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], second_plan.operations[0]), lifecycle_actions=(LifecycleAction(candidate_id="codex-config", client="codex", action="stop", target="codex", reason="quiesce before edit", details={"process_name": "codex", "restart_argv": ["/usr/bin/codex", "--foreground"]}),)).with_digest()
        inventory, plan = self.bind_plan(base_plan)
        lifecycle = FakeTransactionLifecycle()

        def fail_before_second(manifest, transition, operation_index, operation, **kwargs):
            if transition == "before" and operation_index == 1:
                raise OSError("injected journal failure")

        with patch("helper.transaction._append_journal", side_effect=fail_before_second):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), "before-two")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual([(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes], [(0, "completed", None), (1, "failed", "journal_append_failed"), (0, "rolled_back", None)])

    def test_journal_failure_after_completed_mutation_includes_current_in_rollback(self):
        target = self.make_file("journal-after-current.txt", "before")
        inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        lifecycle = FakeTransactionLifecycle()

        def fail_after_completed(manifest, transition, operation_index, operation, **kwargs):
            if transition == "after" and kwargs.get("status") == "completed":
                raise OSError("injected journal failure")

        with patch("helper.transaction._append_journal", side_effect=fail_after_completed):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertIn((0, "completed", None), [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes])
        self.assertIn((0, "failed", "journal_append_failed"), [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes])
        self.assertIn((0, "rolled_back", None), [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes])

    def test_journal_failures_during_error_and_rollback_reporting_do_not_block_safety(self):
        first = self.make_file("journal-reporting-one.txt", "before-one")
        second = self.make_file("journal-reporting-two.txt", "before-two")
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        second_plan = write_plan(second, b"before-two", b"after-two", home=self.home)
        base_plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], second_plan.operations[0]), lifecycle_actions=(LifecycleAction(candidate_id="codex-config", client="codex", action="stop", target="codex", reason="quiesce before edit", details={"process_name": "codex", "restart_argv": ["/usr/bin/codex", "--foreground"]}),)).with_digest()
        inventory, plan = self.bind_plan(base_plan)
        lifecycle = FakeTransactionLifecycle()

        def fail_reporting(manifest, transition, operation_index, operation, **kwargs):
            if transition in {"rollback_before", "rollback_after"} or (transition == "after" and kwargs.get("status") == "failed"):
                raise OSError("injected journal reporting failure")

        with injected_replace_failure(second), patch("helper.transaction._append_journal", side_effect=fail_reporting):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), "before-two")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertIn((1, "failed", "operation_failed"), [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes])
        self.assertIn((0, "rolled_back", None), [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes])

    def test_apply_operations_reports_completed_indices_when_journal_before_second_fails(self):
        first = self.make_file("apply-journal-one.txt", "before-one")
        second = self.make_file("apply-journal-two.txt", "before-two")
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        second_plan = write_plan(second, b"before-two", b"after-two", home=self.home)
        plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], second_plan.operations[0])).with_digest()
        manifest = create_backup(plan, self.context)

        def fail_before_second(manifest, transition, operation_index, operation, **kwargs):
            if transition == "before" and operation_index == 1:
                raise OSError("injected journal failure")

        with patch("helper.transaction._append_journal", side_effect=fail_before_second):
            with self.assertRaises(OperationApplyError) as raised:
                apply_operations(plan, manifest, self.context)

        self.assertEqual([(outcome.operation_index, outcome.status, outcome.error) for outcome in raised.exception.outcomes], [(0, "completed", None), (1, "failed", "journal_append_failed")])
        self.assertEqual(first.read_text(), "after-one")
        self.assertEqual(second.read_text(), "before-two")

    def test_manifest_missing_first_entry_does_not_mutate_and_reports_not_started_with_verified_manifest(self):
        target = self.make_file("manifest-missing-first.txt", "before")
        inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        lifecycle = FakeTransactionLifecycle()

        manifest = create_backup(plan, self.context)
        tampered_manifest = replace(manifest, entries=()).with_digest()
        manifest.path.write_text(json.dumps(tampered_manifest.to_dict(), sort_keys=True, separators=(",", ":")), encoding="utf-8")

        with patch("helper.transaction.create_backup", return_value=tampered_manifest):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(receipt.status, ReceiptStatus.NOT_STARTED)
        self.assertEqual(receipt.backup_manifest_path, tampered_manifest.path)
        self.assertEqual(
            [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes],
            [(0, "failed", "apply_manifest_missing_entry")],
        )
        manifest_data = json.loads(receipt.backup_manifest_path.read_text())
        self.assertEqual(manifest_data["plan_digest"], plan.digest)
        self.assertEqual(manifest_data["digest"], digest_json({key: value for key, value in manifest_data.items() if key != "digest"}))

    def test_manifest_missing_first_entry_restart_failure_requires_manual_recovery(self):
        target = self.make_file("manifest-missing-first-restart.txt", "before")
        inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        lifecycle = FakeTransactionLifecycle(restart_succeeds=False)

        manifest = create_backup(plan, self.context)
        tampered_manifest = replace(manifest, entries=()).with_digest()
        manifest.path.write_text(json.dumps(tampered_manifest.to_dict(), sort_keys=True, separators=(",", ":")), encoding="utf-8")

        with patch("helper.transaction.create_backup", return_value=tampered_manifest):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertEqual(receipt.lifecycle_outcomes[-1].status, "failed")
        self.assertEqual(receipt.lifecycle_outcomes[-1].code, "lifecycle_restart_failed")
        self.assertEqual(receipt.backup_manifest_path, tampered_manifest.path)
        self.assertEqual(
            [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes],
            [(0, "failed", "apply_manifest_missing_entry")],
        )
        manifest_data = json.loads(receipt.backup_manifest_path.read_text())
        self.assertEqual(manifest_data["plan_digest"], plan.digest)
        self.assertEqual(manifest_data["digest"], digest_json({key: value for key, value in manifest_data.items() if key != "digest"}))

    def test_manifest_missing_second_entry_rolls_back_completed_first_and_restarts(self):
        first = self.make_file("manifest-missing-one.txt", "before-one")
        second = self.make_file("manifest-missing-two.txt", "before-two")
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        second_plan = write_plan(second, b"before-two", b"after-two", home=self.home)
        base_plan = Plan(
            os_name="linux",
            home=str(self.home),
            operations=(first_plan.operations[0], second_plan.operations[0]),
            lifecycle_actions=(
                LifecycleAction(
                    candidate_id="codex-config",
                    client="codex",
                    action="stop",
                    target="codex",
                    reason="quiesce before edit",
                    details={"process_name": "codex", "restart_argv": ["/usr/bin/codex", "--foreground"]},
                ),
            ),
        ).with_digest()
        inventory, plan = self.bind_plan(base_plan)
        lifecycle = FakeTransactionLifecycle()

        manifest = create_backup(plan, self.context)
        tampered_manifest = replace(manifest, entries=(manifest.entries[0],)).with_digest()
        manifest.path.write_text(json.dumps(tampered_manifest.to_dict(), sort_keys=True, separators=(",", ":")), encoding="utf-8")

        with patch("helper.transaction.create_backup", return_value=tampered_manifest):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), "before-two")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(receipt.backup_manifest_path, tampered_manifest.path)
        self.assertEqual(
            [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes],
            [(0, "completed", None), (1, "failed", "apply_manifest_missing_entry"), (0, "rolled_back", None)],
        )

    def test_manifest_missing_second_entry_restart_failure_requires_manual_recovery(self):
        first = self.make_file("manifest-missing-restart-one.txt", "before-one")
        second = self.make_file("manifest-missing-restart-two.txt", "before-two")
        first_plan = write_plan(first, b"before-one", b"after-one", home=self.home)
        second_plan = write_plan(second, b"before-two", b"after-two", home=self.home)
        base_plan = Plan(
            os_name="linux",
            home=str(self.home),
            operations=(first_plan.operations[0], second_plan.operations[0]),
            lifecycle_actions=(
                LifecycleAction(
                    candidate_id="codex-config",
                    client="codex",
                    action="stop",
                    target="codex",
                    reason="quiesce before edit",
                    details={"process_name": "codex", "restart_argv": ["/usr/bin/codex", "--foreground"]},
                ),
            ),
        ).with_digest()
        inventory, plan = self.bind_plan(base_plan)
        lifecycle = FakeTransactionLifecycle(restart_succeeds=False)

        manifest = create_backup(plan, self.context)
        tampered_manifest = replace(manifest, entries=(manifest.entries[0],)).with_digest()
        manifest.path.write_text(json.dumps(tampered_manifest.to_dict(), sort_keys=True, separators=(",", ":")), encoding="utf-8")

        with patch("helper.transaction.create_backup", return_value=tampered_manifest):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), "before-two")
        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertEqual(receipt.lifecycle_outcomes[-1].status, "failed")
        self.assertEqual(receipt.lifecycle_outcomes[-1].code, "lifecycle_restart_failed")
        self.assertEqual(
            [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes],
            [(0, "completed", None), (1, "failed", "apply_manifest_missing_entry"), (0, "rolled_back", None)],
        )

    def test_unexpected_apply_exception_before_mutation_uses_manual_fallback_and_restarts(self):
        target = self.make_file("unexpected-apply-fallback.txt", "before")
        inventory, plan = self.bind_plan(lifecycle_write_plan(target, b"before", b"after", home=self.home))
        lifecycle = FakeTransactionLifecycle()

        with patch("helper.transaction.apply_operations", side_effect=RuntimeError("injected unexpected apply failure")):
            receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle, inventory=inventory)

        self.assertEqual(target.read_text(), "before")
        self.assertEqual(lifecycle.calls, ["preflight", "stop", "restart"])
        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertTrue(receipt.backup_manifest_path and receipt.backup_manifest_path.exists())
        self.assertEqual(
            [(outcome.operation_index, outcome.status, outcome.error) for outcome in receipt.operation_outcomes],
            [(0, "failed", "transaction_failed")],
        )

    def test_restart_failure_after_successful_apply_requires_manual_recovery(self):
        target = self.make_file(".codex/config.toml", "before")
        plan = lifecycle_write_plan(target, b"before", b"after", home=self.home)
        lifecycle = FakeTransactionLifecycle(restart_succeeds=False)

        _inventory, plan, receipt = self.execute_bound(plan, lifecycle)

        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertEqual(target.read_text(), "after")
        self.assertTrue(receipt.backup_manifest_path and receipt.backup_manifest_path.exists())
        self.assertEqual(receipt.operation_outcomes[0].status, "completed")
        self.assertEqual(receipt.lifecycle_outcomes[-1].code, "lifecycle_restart_failed")

    def test_zero_operation_plan_does_not_touch_lifecycle(self):
        lifecycle = NoopLifecycle()
        plan = Plan(os_name="linux", home=str(self.home), operations=()).with_digest()

        _inventory, plan, receipt = self.execute_bound(plan, lifecycle)

        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertEqual(lifecycle.calls, [])
