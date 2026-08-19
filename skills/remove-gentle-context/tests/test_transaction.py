from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from helper.canonical import digest_json
from helper.models import Operation, OperationKind, Plan, PlatformProfile, ReceiptStatus, RuntimeContext
from helper.paths import resolve_state_root
from helper.transaction import create_backup, execute_plan, restore


class NoopLifecycle:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def prepare(self, *args, **kwargs):
        self.calls.append("prepare")
        return ()


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def image(content: bytes) -> tuple[str, str]:
    return base64.b64encode(content).decode("ascii"), sha256_bytes(content)


def write_plan(path: Path, before: bytes | None, after: bytes, *, details: dict[str, object] | None = None) -> Plan:
    pre_b64, pre_digest = (None, None) if before is None else image(before)
    post_b64, post_digest = image(after)
    return Plan(
        os_name="linux",
        home=str(path.parents[0]),
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


def delete_plan(path: Path, before: bytes) -> Plan:
    pre_b64, pre_digest = image(before)
    return Plan(
        os_name="linux",
        home=str(path.parents[0]),
        operations=(Operation(kind=OperationKind.DELETE_FILE, path=str(path), preimage_base64=pre_b64, preimage_sha256=pre_digest),),
    ).with_digest()


def remove_empty_dir_plan(path: Path) -> Plan:
    return Plan(os_name="linux", home=str(path.parents[0]), operations=(Operation(kind=OperationKind.REMOVE_EMPTY_DIRECTORY, path=str(path)),)).with_digest()


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


class TransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)
        self.home = self.temp_root / "home"
        self.home.mkdir()
        self.state = self.temp_root / "state"
        self.context = RuntimeContext(PlatformProfile("linux", self.home, {"XDG_STATE_HOME": str(self.state)}))

    def make_file(self, relative: str, content: str, *, mode: int = 0o640) -> Path:
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(mode)
        return path

    def test_preimage_drift_aborts_before_backup_or_mutation(self):
        target = self.make_file(".codex/config.toml", "before")
        plan = write_plan(target, b"before", b"after")
        target.write_text("drift")

        with self.assertRaisesRegex(ValueError, "preflight_preimage_drift"):
            create_backup(plan, self.context)

        self.assertEqual(target.read_text(), "drift")
        self.assertFalse((resolve_state_root(self.context.profile) / "backups").exists())

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
            receipt = execute_plan(plan, plan.digest or "", self.context, NoopLifecycle())

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(first.read_text(), "before-one")
        self.assertEqual(second.read_text(), "before-two")
        self.assertTrue(receipt.backup_manifest_path and receipt.backup_manifest_path.exists())

    def test_restore_rejects_manifest_path_escape(self):
        target = self.make_file("safe.txt", "before")
        plan = delete_plan(target, b"before")
        manifest = create_backup(plan, self.context)
        data = json.loads(manifest.path.read_text())
        data["entries"][0]["relative_path"] = "../../outside"
        data["digest"] = digest_json({key: value for key, value in data.items() if key != "digest"})
        manifest.path.write_text(json.dumps(data))

        with self.assertRaisesRegex(ValueError, "restore_path_escape"):
            restore(manifest.path, data["digest"], self.context)

    def test_backup_payload_write_failure_does_not_mutate_target(self):
        target = self.make_file("config.json", "before")
        plan = delete_plan(target, b"before")

        with patch("helper.transaction._write_verified_payload", side_effect=OSError("injected backup failure")):
            with self.assertRaisesRegex(OSError, "injected backup failure"):
                create_backup(plan, self.context)

        self.assertEqual(target.read_text(), "before")

    def test_postimage_hash_mismatch_aborts_before_write(self):
        target = self.make_file("config.json", "before")
        pre_b64, pre_digest = image(b"before")
        bad_post_b64 = base64.b64encode(b"after").decode("ascii")
        plan = Plan(
            os_name="linux",
            home=str(self.home),
            operations=(Operation(kind=OperationKind.WRITE_FILE, path=str(target), preimage_base64=pre_b64, preimage_sha256=pre_digest, postimage_base64=bad_post_b64, postimage_sha256=sha256_bytes(b"different")),),
        ).with_digest()

        receipt = execute_plan(plan, plan.digest or "", self.context, NoopLifecycle())

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(target.read_text(), "before")

    def test_declared_json_parse_failure_aborts_before_replace(self):
        target = self.make_file("settings.json", '{"before": true}\n')
        plan = write_plan(target, b'{"before": true}\n', b'{"after": ', details={"parse": "json"})

        receipt = execute_plan(plan, plan.digest or "", self.context, NoopLifecycle())

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertEqual(target.read_text(), '{"before": true}\n')

    def test_delete_unlink_failure_leaves_file_and_reports_manual_recovery_when_rollback_fails(self):
        first = self.make_file("first", "before-first")
        second = self.make_file("second", "before-second")
        first_plan = write_plan(first, b"before-first", b"after-first")
        second_delete = delete_plan(second, b"before-second").operations[0]
        plan = Plan(os_name="linux", home=str(self.home), operations=(first_plan.operations[0], second_delete)).with_digest()

        original_replace = os.replace

        def replace_fails_during_rollback(src, dst):
            if Path(dst) == first and first.read_text() == "after-first":
                raise OSError("injected rollback failure")
            return original_replace(src, dst)

        with injected_unlink_failure(second), patch("helper.transaction.os.replace", side_effect=replace_fails_during_rollback):
            receipt = execute_plan(plan, plan.digest or "", self.context, NoopLifecycle())

        self.assertEqual(receipt.status, ReceiptStatus.MANUAL_RECOVERY_REQUIRED)
        self.assertEqual(first.read_text(), "after-first")
        self.assertEqual(second.read_text(), "before-second")

    def test_idempotent_noop_still_requires_preimage(self):
        target = self.make_file("noop.txt", "same")
        plan = write_plan(target, b"same", b"same")

        receipt = execute_plan(plan, plan.digest or "", self.context, NoopLifecycle())

        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertEqual(target.read_text(), "same")

        target.write_text("drift")
        with self.assertRaisesRegex(ValueError, "preflight_preimage_drift"):
            create_backup(plan, self.context)

    def test_symlink_and_windows_reparse_targets_are_rejected_before_backup(self):
        real = self.make_file("real.json", "{}")
        link = self.home / "link.json"
        link.symlink_to(real)
        plan = delete_plan(link, b"{}")
        with self.assertRaisesRegex(ValueError, "preflight_unexpected_link"):
            create_backup(plan, self.context)

        target = self.make_file("reparse.json", "{}")
        reparse_plan = delete_plan(target, b"{}")
        fake_stat = type("Stat", (), {"st_file_attributes": 0x400, "st_mode": target.lstat().st_mode, "st_size": 2})()
        with patch("helper.paths.os.lstat", return_value=fake_stat), patch("helper.transaction.os.lstat", return_value=fake_stat):
            with self.assertRaisesRegex(ValueError, "preflight_unexpected_link"):
                create_backup(reparse_plan, self.context)

    def test_manifest_tamper_is_rejected_by_restore_digest(self):
        target = self.make_file("restore.txt", "before")
        manifest = create_backup(delete_plan(target, b"before"), self.context)
        data = json.loads(manifest.path.read_text())
        data["entries"][0]["sha256"] = sha256_bytes(b"tampered")
        manifest.path.write_text(json.dumps(data))

        with self.assertRaisesRegex(ValueError, "restore_manifest_digest_mismatch"):
            restore(manifest.path, manifest.digest or "", self.context)

    def test_restore_is_digest_approved_and_backs_up_replacement_preimage(self):
        target = self.make_file("restore.txt", "before")
        manifest = create_backup(delete_plan(target, b"before"), self.context)
        target.write_text("replacement")

        with self.assertRaisesRegex(ValueError, "restore_approval_mismatch"):
            restore(manifest.path, "sha256:" + "0" * 64, self.context)

        receipt = restore(manifest.path, manifest.digest or "", self.context)

        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertEqual(target.read_text(), "before")
        self.assertTrue(receipt.backup_manifest_path and receipt.backup_manifest_path.exists())
        replacement_manifest = json.loads(receipt.backup_manifest_path.read_text())
        self.assertEqual(replacement_manifest["entries"][0]["sha256"], sha256_bytes(b"replacement"))

    def test_nonempty_directory_refusal_and_empty_directory_removal(self):
        directory = self.home / "dir"
        directory.mkdir()
        (directory / "child").write_text("x")
        plan = remove_empty_dir_plan(directory)

        receipt = execute_plan(plan, plan.digest or "", self.context, NoopLifecycle())

        self.assertEqual(receipt.status, ReceiptStatus.ROLLED_BACK)
        self.assertTrue(directory.exists())

        (directory / "child").unlink()
        receipt = execute_plan(plan, plan.digest or "", self.context, NoopLifecycle())
        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertFalse(directory.exists())

    def test_zero_operation_plan_does_not_touch_lifecycle(self):
        lifecycle = NoopLifecycle()
        plan = Plan(os_name="linux", home=str(self.home), operations=()).with_digest()

        receipt = execute_plan(plan, plan.digest or "", self.context, lifecycle)

        self.assertEqual(receipt.status, ReceiptStatus.COMPLETED)
        self.assertEqual(lifecycle.calls, [])
