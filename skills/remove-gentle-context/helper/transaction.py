from __future__ import annotations

import base64
import errno
import fnmatch
import json
import os
import stat
import tempfile
import tomllib
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .canonical import digest_json
from .engine import validate_approval
from .models import BackupEntry, BackupManifest, Inventory, LifecycleOutcome, Operation, OperationKind, OperationOutcome, Plan, ProcessSnapshot, Receipt, ReceiptStatus, RuntimeContext
from .paths import _is_windows_reparse_point, canonical_environment_roots, path_from_root_relative, resolve_state_root, root_map, root_relative_path


class OperationApplyError(RuntimeError):
    def __init__(self, code: str, outcomes: tuple[OperationOutcome, ...]) -> None:
        super().__init__(code)
        self.code = code
        self.outcomes = outcomes


def create_backup(plan: Plan, context: RuntimeContext) -> BackupManifest:
    plan_digest = _require_digest(plan.digest, "backup_plan_missing_digest")
    _assert_plan_root_map_matches_context(plan, context, "backup_plan_roots_mismatch")
    _validate_plan_preconditions(plan, context, drift_code="preflight_directory_members_drift")
    prepared = [_prepare_backup_entry(index, operation, context) for index, operation in enumerate(plan.operations)]
    root = _new_transaction_root("backups", plan_digest, context)
    entries: list[BackupEntry] = []
    try:
        for entry, content in prepared:
            payload_path: str | None = None
            if content is not None:
                payload_path = f"rootfs/{entry.root_id}/{entry.relative_path}"
                _write_verified_payload(root / payload_path, content, entry.sha256 or "")
            entries.append(replace(entry, payload_path=payload_path))
        manifest = BackupManifest(path=root / "manifest.json", root=root, plan_digest=plan_digest, entries=tuple(entries)).with_digest()
        _write_json_atomic(manifest.path, manifest.to_dict(), mode=0o600)
        return manifest
    except BaseException:
        # Targets have not been mutated yet. Leave any partial backup directory for forensic inspection.
        raise


def apply_operations(plan: Plan, manifest: BackupManifest, context: RuntimeContext) -> tuple[OperationOutcome, ...]:
    _assert_plan_root_map_matches_context(plan, context, "apply_plan_roots_mismatch")
    if manifest.plan_digest != _require_digest(plan.digest, "apply_plan_missing_digest"):
        raise ValueError("apply_manifest_plan_mismatch")
    outcomes: list[OperationOutcome] = []
    entries_by_index = {entry.operation_index: entry for entry in manifest.entries}
    for index, operation in enumerate(plan.operations):
        entry = entries_by_index.get(index)
        if entry is None:
            failed = OperationOutcome(index, str(operation.kind), operation.path, "failed", "apply_manifest_missing_entry")
            raise OperationApplyError("apply_manifest_missing_entry", tuple(outcomes + [failed]))
        try:
            _append_journal(manifest, "before", index, operation)
        except BaseException as exc:
            failed = OperationOutcome(index, str(operation.kind), operation.path, "failed", "journal_append_failed")
            raise OperationApplyError("journal_append_failed", tuple(outcomes + [failed])) from exc
        try:
            _apply_one(index, operation, entry, context)
        except BaseException as exc:
            code = _error_code(exc, "operation_failed")
            failed = OperationOutcome(index, str(operation.kind), operation.path, "failed", code)
            _append_journal_best_effort(manifest, "after", index, operation, status="failed", error=code)
            raise OperationApplyError(code, tuple(outcomes + [failed])) from exc
        outcome = OperationOutcome(index, str(operation.kind), operation.path, "completed")
        outcomes.append(outcome)
        try:
            _append_journal(manifest, "after", index, operation, status="completed")
        except BaseException as exc:
            failed = OperationOutcome(index, str(operation.kind), operation.path, "failed", "journal_append_failed")
            raise OperationApplyError("journal_append_failed", tuple(outcomes + [failed])) from exc
    return tuple(outcomes)


def rollback(manifest: BackupManifest, outcomes: Iterable[OperationOutcome], context: RuntimeContext) -> tuple[OperationOutcome, ...]:
    completed = [outcome for outcome in outcomes if outcome.status == "completed"]
    entries_by_index = {entry.operation_index: entry for entry in manifest.entries}
    rollback_outcomes: list[OperationOutcome] = []
    for outcome in reversed(completed):
        entry = entries_by_index[outcome.operation_index]
        _append_journal_best_effort(manifest, "rollback_before", outcome.operation_index, None)
        try:
            _restore_entry(entry, manifest, context)
        except BaseException as exc:
            code = _error_code(exc, "rollback_failed")
            rollback_outcomes.append(OperationOutcome(outcome.operation_index, outcome.kind, outcome.path, "failed", code))
            _append_journal_best_effort(manifest, "rollback_after", outcome.operation_index, None, status="failed", error=code)
            continue
        rollback_outcomes.append(OperationOutcome(outcome.operation_index, outcome.kind, outcome.path, "rolled_back"))
        _append_journal_best_effort(manifest, "rollback_after", outcome.operation_index, None, status="rolled_back")
    return tuple(rollback_outcomes)


def execute_plan(plan: Plan, approval: str, context: RuntimeContext, lifecycle: object, *, inventory: Inventory) -> Receipt:
    _validate_execution_artifacts(plan, inventory, context)
    validate_approval(plan, approval)
    if not plan.operations:
        return Receipt(status=ReceiptStatus.COMPLETED, plan=plan, inventory=inventory)

    lifecycle_outcomes: list[LifecycleOutcome] = []
    stopped: list[ProcessSnapshot] = []
    snapshots = _lifecycle_preflight(plan, context, lifecycle)
    _validate_plan_preimages(plan, context, drift_code="preflight_preimage_drift")

    try:
        for snapshot in snapshots:
            if not snapshot.running:
                continue
            outcome = lifecycle.stop(snapshot)  # type: ignore[attr-defined]
            lifecycle_outcomes.append(outcome)
            if getattr(outcome, "status", None) == "stopped":
                stopped.append(snapshot)
    except BaseException as exc:
        code = _error_code(exc, "preflight_lifecycle_stop_failed")
        restart_outcomes = _restart_stopped(lifecycle, tuple(stopped))
        lifecycle_outcomes.extend(restart_outcomes)
        status = ReceiptStatus.MANUAL_RECOVERY_REQUIRED if _has_restart_failure(restart_outcomes) else ReceiptStatus.FAILED
        return Receipt(operation_outcomes=_failed_preflight_outcomes(plan, code), lifecycle_outcomes=tuple(lifecycle_outcomes), status=status, plan=plan, inventory=inventory)

    try:
        _validate_plan_preimages(plan, context, drift_code="preflight_preimage_drift_after_shutdown")
    except BaseException as exc:
        code = _error_code(exc, "preflight_preimage_drift_after_shutdown")
        restart_outcomes = _restart_stopped(lifecycle, tuple(stopped))
        lifecycle_outcomes.extend(restart_outcomes)
        status = ReceiptStatus.MANUAL_RECOVERY_REQUIRED if _has_restart_failure(restart_outcomes) else ReceiptStatus.FAILED
        return Receipt(operation_outcomes=_failed_preflight_outcomes(plan, code), lifecycle_outcomes=tuple(lifecycle_outcomes), status=status, plan=plan, inventory=inventory)

    manifest: BackupManifest | None = None
    try:
        manifest = create_backup(plan, context)
    except BaseException as exc:
        code = _error_code(exc, "backup_failed")
        restart_outcomes = _restart_stopped(lifecycle, tuple(stopped))
        lifecycle_outcomes.extend(restart_outcomes)
        status = ReceiptStatus.MANUAL_RECOVERY_REQUIRED if _has_restart_failure(restart_outcomes) else ReceiptStatus.NOT_STARTED
        return Receipt(operation_outcomes=_failed_preflight_outcomes(plan, code), lifecycle_outcomes=tuple(lifecycle_outcomes), status=status, plan=plan, inventory=inventory)

    try:
        outcomes = apply_operations(plan, manifest, context)
    except OperationApplyError as exc:
        rollback_outcomes = rollback(manifest, exc.outcomes, context)
        restart_outcomes = _restart_stopped(lifecycle, tuple(stopped))
        lifecycle_outcomes.extend(restart_outcomes)
        status = _failure_status(exc.outcomes, rollback_outcomes, restart_outcomes)
        return Receipt(operation_outcomes=tuple(exc.outcomes + rollback_outcomes), backup_manifest_path=manifest.path, lifecycle_outcomes=tuple(lifecycle_outcomes), status=status, plan=plan, inventory=inventory)
    except BaseException as exc:
        code = _error_code(exc, "transaction_failed")
        restart_outcomes = _restart_stopped(lifecycle, tuple(stopped))
        lifecycle_outcomes.extend(restart_outcomes)
        return Receipt(operation_outcomes=_failed_preflight_outcomes(plan, code), backup_manifest_path=manifest.path, lifecycle_outcomes=tuple(lifecycle_outcomes), status=ReceiptStatus.MANUAL_RECOVERY_REQUIRED, plan=plan, inventory=inventory)

    restart_outcomes = _restart_stopped(lifecycle, tuple(stopped))
    lifecycle_outcomes.extend(restart_outcomes)
    status = ReceiptStatus.MANUAL_RECOVERY_REQUIRED if _has_restart_failure(restart_outcomes) else ReceiptStatus.COMPLETED
    return Receipt(operation_outcomes=outcomes, backup_manifest_path=manifest.path, lifecycle_outcomes=tuple(lifecycle_outcomes), status=status, plan=plan, inventory=inventory)


def _validate_execution_artifacts(plan: Plan, inventory: Inventory, context: RuntimeContext) -> None:
    if not isinstance(inventory, Inventory):
        raise ValueError("execute_inventory_required")
    expected_inventory_digest = digest_json(inventory.to_unsigned_dict())
    if inventory.digest != expected_inventory_digest:
        raise ValueError("execute_inventory_digest_mismatch")
    expected_plan_digest = digest_json(plan.to_unsigned_dict())
    if plan.digest != expected_plan_digest:
        raise ValueError("execute_plan_digest_mismatch")
    if plan.inventory_digest != inventory.digest:
        raise ValueError("execute_plan_inventory_digest_mismatch")

    context_home = str(context.profile.home.resolve(strict=False))
    if inventory.home != context_home:
        raise ValueError("execute_inventory_home_mismatch")
    if plan.home != context_home:
        raise ValueError("execute_plan_home_mismatch")
    if inventory.os_name != context.profile.os_name:
        raise ValueError("execute_inventory_os_mismatch")
    if plan.os_name != context.profile.os_name:
        raise ValueError("execute_plan_os_mismatch")
    context_roots = dict(sorted(root_map(context).items()))
    inventory_roots = dict(sorted(inventory.root_map.items()))
    plan_roots = dict(sorted(plan.root_map.items()))
    if inventory_roots != context_roots:
        raise ValueError("execute_inventory_roots_mismatch")
    if plan_roots != context_roots:
        raise ValueError("execute_plan_roots_mismatch")
    if dict(sorted(inventory.environment.items())) != canonical_environment_roots(context.profile.env):
        raise ValueError("execute_inventory_environment_mismatch")


def _assert_plan_root_map_matches_context(plan: Plan, context: RuntimeContext, code: str) -> None:
    if not plan.root_map:
        return
    if dict(sorted(plan.root_map.items())) != dict(sorted(root_map(context).items())):
        raise ValueError(code)


def _lifecycle_preflight(plan: Plan, context: RuntimeContext, lifecycle: object) -> tuple[ProcessSnapshot, ...]:
    if not plan.lifecycle_actions:
        return ()
    preflight = getattr(lifecycle, "preflight", None)
    if preflight is None:
        raise ValueError("preflight_lifecycle_unavailable")
    return tuple(preflight(plan.lifecycle_actions, context))


def _validate_plan_preimages(plan: Plan, context: RuntimeContext, *, drift_code: str) -> None:
    _validate_plan_preconditions(plan, context, drift_code=drift_code if drift_code != "preflight_preimage_drift" else "preflight_directory_members_drift")
    for index, operation in enumerate(plan.operations):
        try:
            _prepare_backup_entry(index, operation, context)
        except ValueError as exc:
            if drift_code != "preflight_preimage_drift" and _is_preimage_state_error(str(exc)):
                raise ValueError(drift_code) from exc
            raise


def _validate_plan_preconditions(plan: Plan, context: RuntimeContext, *, drift_code: str) -> None:
    for operation in plan.operations:
        raw = operation.details.get("directory_member_preconditions")
        if raw is None:
            continue
        if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes, dict)):
            raise ValueError("preflight_invalid_directory_member_precondition")
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("preflight_invalid_directory_member_precondition")
            if item.get("kind") != "directory_member_set":
                continue
            root_id = item.get("root_id")
            relative_dir = item.get("relative_dir")
            expected_digest = item.get("digest")
            if not isinstance(root_id, str) or not isinstance(relative_dir, str) or not isinstance(expected_digest, str):
                raise ValueError("preflight_invalid_directory_member_precondition")
            names = _string_tuple(item.get("file_names", ()), "preflight_invalid_directory_member_precondition")
            patterns = _string_tuple(item.get("patterns", ()), "preflight_invalid_directory_member_precondition")
            directory = path_from_root_relative(root_id, relative_dir, context, error_code="preflight_path_escape")
            actual_members = _directory_member_set(directory, names, patterns)
            actual_digest = digest_json({"members": actual_members})
            if actual_digest != expected_digest:
                raise ValueError(drift_code)


def _string_tuple(value: object, code: str) -> tuple[str, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        raise ValueError(code)
    items = tuple(value)  # type: ignore[arg-type]
    if not all(isinstance(item, str) for item in items):
        raise ValueError(code)
    return items


def _directory_member_set(directory: Path, names: tuple[str, ...], patterns: tuple[str, ...]) -> list[dict[str, object]]:
    members: list[dict[str, object]] = []
    if not directory.is_dir():
        return members
    governed_names = set(names)
    for child in sorted(directory.iterdir(), key=lambda item: item.name):
        if child.name not in governed_names and not any(fnmatch.fnmatchcase(child.name, pattern) for pattern in patterns):
            continue
        try:
            st = os.lstat(child)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode) or _is_windows_reparse_point(st):
            members.append({"name": child.name, "type": "link_or_reparse"})
            continue
        if not stat.S_ISREG(st.st_mode):
            members.append({"name": child.name, "type": "non_regular"})
            continue
        content = child.read_bytes()
        members.append({"name": child.name, "sha256": _sha256(content), "type": "file"})
    return members


def _is_preimage_state_error(code: str) -> bool:
    return code in {
        "preflight_preimage_drift",
        "preflight_missing_preimage",
        "preflight_unexpected_link",
        "preflight_not_regular_file",
        "preflight_not_directory",
        "preflight_directory_members_drift",
    }


def _failed_preflight_outcomes(plan: Plan, code: str) -> tuple[OperationOutcome, ...]:
    return tuple(OperationOutcome(index, str(operation.kind), operation.path, "failed", code) for index, operation in enumerate(plan.operations))


def _restart_stopped(lifecycle: object, stopped: tuple[ProcessSnapshot, ...]) -> tuple[LifecycleOutcome, ...]:
    outcomes: list[LifecycleOutcome] = []
    for snapshot in reversed(stopped):
        try:
            outcome = lifecycle.restart(snapshot)  # type: ignore[attr-defined]
        except BaseException as exc:
            outcome = LifecycleOutcome(action="restart", client=snapshot.action.client, target=snapshot.action.target, status="failed", code=_error_code(exc, "lifecycle_restart_failed"), pid=snapshot.pid)
        outcomes.append(outcome)
    return tuple(outcomes)


def _has_restart_failure(outcomes: tuple[LifecycleOutcome, ...]) -> bool:
    return any(outcome.action == "restart" and outcome.status == "failed" for outcome in outcomes)


def _failure_status(operation_outcomes: tuple[OperationOutcome, ...], rollback_outcomes: tuple[OperationOutcome, ...], restart_outcomes: tuple[LifecycleOutcome, ...]) -> ReceiptStatus:
    if any(outcome.status == "failed" for outcome in rollback_outcomes) or _has_restart_failure(restart_outcomes):
        return ReceiptStatus.MANUAL_RECOVERY_REQUIRED
    if _is_not_started_operation_failure(operation_outcomes):
        return ReceiptStatus.NOT_STARTED
    return ReceiptStatus.ROLLED_BACK


def _is_not_started_operation_failure(operation_outcomes: tuple[OperationOutcome, ...]) -> bool:
    if any(outcome.status == "completed" for outcome in operation_outcomes):
        return False
    failed = [outcome for outcome in operation_outcomes if outcome.status == "failed"]
    return bool(failed) and all(outcome.error == "journal_append_failed" for outcome in failed)


def restore(manifest_path: Path, approval: str, context: RuntimeContext) -> Receipt:
    manifest = _load_manifest(manifest_path)
    computed = digest_json(manifest.to_unsigned_dict())
    if manifest.digest != computed:
        raise ValueError("restore_manifest_digest_mismatch")
    if approval != computed:
        raise ValueError("restore_approval_mismatch")
    replacement_manifest = _backup_restore_replacements(manifest, context)
    replacement_by_index = {entry.operation_index: entry for entry in replacement_manifest.entries}
    outcomes: list[OperationOutcome] = []
    completed: list[BackupEntry] = []
    seen: set[Path] = set()
    for entry in manifest.entries:
        destination = path_from_root_relative(entry.root_id, entry.relative_path, context, error_code="restore_path_escape")
        resolved = destination.resolve(strict=False)
        if resolved in seen:
            raise ValueError("restore_path_collision")
        seen.add(resolved)
        try:
            _restore_entry(entry, manifest, context)
        except BaseException as exc:
            code = _error_code(exc, "restore_failed")
            outcomes.append(OperationOutcome(entry.operation_index, entry.kind, str(destination), "failed", code))
            rollback_outcomes = _rollback_restore_entries(tuple(completed), manifest, replacement_manifest, replacement_by_index, context)
            status = ReceiptStatus.ROLLED_BACK
            if any(outcome.status == "failed" for outcome in rollback_outcomes):
                status = ReceiptStatus.MANUAL_RECOVERY_REQUIRED
            return Receipt(operation_outcomes=tuple(outcomes + list(rollback_outcomes)), backup_manifest_path=replacement_manifest.path, status=status)
        outcomes.append(OperationOutcome(entry.operation_index, entry.kind, str(destination), "completed"))
        completed.append(entry)
    return Receipt(operation_outcomes=tuple(outcomes), backup_manifest_path=replacement_manifest.path, status=ReceiptStatus.COMPLETED)


def _prepare_backup_entry(index: int, operation: Operation, context: RuntimeContext) -> tuple[BackupEntry, bytes | None]:
    kind = OperationKind(str(operation.kind))
    target = Path(operation.path)
    root_id, relative = root_relative_path(target, context)
    _assert_parent_contained(target, context)

    if kind == OperationKind.REMOVE_EMPTY_DIRECTORY:
        st = _safe_lstat(target)
        if not stat.S_ISDIR(st.st_mode):
            raise ValueError("preflight_not_directory")
        return BackupEntry(index, str(kind), operation.path, root_id, relative, "directory", mode=stat.S_IMODE(st.st_mode)), None

    expected = _decode_optional_image(operation.preimage_base64, operation.preimage_sha256, "preflight_preimage_digest_mismatch")
    exists = target.exists() or target.is_symlink()
    if expected is None:
        if not exists:
            return BackupEntry(index, str(kind), operation.path, root_id, relative, "missing"), None
        raise ValueError("preflight_missing_preimage")

    st, content = _read_regular_file_bound(
        target,
        expected_content=expected,
        expected_sha256=operation.preimage_sha256,
        expected_size=len(expected),
        mismatch_code="preflight_preimage_drift",
        link_code="preflight_unexpected_link",
        not_regular_code="preflight_not_regular_file",
    )
    return BackupEntry(index, str(kind), operation.path, root_id, relative, "file", mode=stat.S_IMODE(st.st_mode), size=len(content), sha256=_sha256(content)), content


def _apply_one(index: int, operation: Operation, entry: BackupEntry, context: RuntimeContext) -> None:
    kind = OperationKind(str(operation.kind))
    if kind == OperationKind.WRITE_FILE:
        _apply_write(operation, entry, context)
    elif kind == OperationKind.DELETE_FILE:
        _apply_delete(operation, entry, context)
    elif kind == OperationKind.REMOVE_EMPTY_DIRECTORY:
        _apply_remove_empty_directory(operation, entry, context)
    else:
        raise ValueError("operation_unknown_kind")


def _apply_write(operation: Operation, entry: BackupEntry, context: RuntimeContext) -> None:
    target = path_from_root_relative(entry.root_id, entry.relative_path, context, error_code="preflight_path_escape")
    _revalidate_entry_preimage(operation, entry, target)
    postimage = _decode_required_image(operation.postimage_base64, operation.postimage_sha256, "operation_postimage_digest_mismatch")
    if _sha256(postimage) != operation.postimage_sha256:
        raise ValueError("operation_postimage_digest_mismatch")
    _validate_declared_parse(operation, postimage)
    mode = entry.mode if entry.mode is not None else 0o600
    _write_file_atomic(target, postimage, mode=mode)


def _apply_delete(operation: Operation, entry: BackupEntry, context: RuntimeContext) -> None:
    target = path_from_root_relative(entry.root_id, entry.relative_path, context, error_code="preflight_path_escape")
    _revalidate_entry_preimage(operation, entry, target)
    if entry.target_type == "missing":
        return
    os.unlink(target)
    _fsync_directory(target.parent)


def _apply_remove_empty_directory(operation: Operation, entry: BackupEntry, context: RuntimeContext) -> None:
    target = path_from_root_relative(entry.root_id, entry.relative_path, context, error_code="preflight_path_escape")
    st = _safe_lstat(target)
    if not stat.S_ISDIR(st.st_mode):
        raise ValueError("operation_not_directory")
    os.rmdir(target)
    _fsync_directory(target.parent)


def _revalidate_entry_preimage(operation: Operation, entry: BackupEntry, target: Path) -> None:
    _assert_parent_contained_for_target(target)
    if entry.target_type == "missing":
        if target.exists() or target.is_symlink():
            raise ValueError("preflight_preimage_drift")
        return
    if entry.target_type != "file":
        return
    expected = _decode_required_image(operation.preimage_base64, operation.preimage_sha256, "preflight_preimage_digest_mismatch")
    _read_regular_file_bound(
        target,
        expected_content=expected,
        expected_sha256=entry.sha256,
        expected_size=len(expected),
        expected_mode=entry.mode,
        mismatch_code="preflight_preimage_drift",
        link_code="preflight_preimage_drift",
        not_regular_code="preflight_preimage_drift",
    )


def _restore_entry(entry: BackupEntry, manifest: BackupManifest, context: RuntimeContext) -> None:
    target = path_from_root_relative(entry.root_id, entry.relative_path, context, error_code="restore_path_escape")
    if entry.target_type == "file":
        if entry.payload_path is None or entry.sha256 is None:
            raise ValueError("restore_manifest_missing_payload")
        payload = manifest.root / entry.payload_path
        _assert_payload_contained(payload, manifest.root)
        content = _read_backup_payload(payload, entry)
        _write_file_atomic(target, content, mode=entry.mode if entry.mode is not None else 0o600)
    elif entry.target_type == "directory":
        if target.exists() and not target.is_dir():
            raise ValueError("restore_directory_collision")
        target.mkdir(mode=entry.mode if entry.mode is not None else 0o700, parents=False, exist_ok=True)
        if entry.mode is not None:
            target.chmod(entry.mode)
        _fsync_directory(target.parent)
    elif entry.target_type == "missing":
        if not target.exists() and not target.is_symlink():
            return
        st = _safe_lstat(target)
        if stat.S_ISREG(st.st_mode):
            os.unlink(target)
        elif stat.S_ISDIR(st.st_mode):
            os.rmdir(target)
        else:
            raise ValueError("restore_refuse_special_file")
        _fsync_directory(target.parent)
    else:
        raise ValueError("restore_manifest_invalid_entry_type")


def _backup_restore_replacements(manifest: BackupManifest, context: RuntimeContext) -> BackupManifest:
    computed = digest_json(manifest.to_unsigned_dict())
    seen: set[Path] = set()
    destinations: list[tuple[BackupEntry, Path]] = []
    for source_entry in manifest.entries:
        destination = path_from_root_relative(source_entry.root_id, source_entry.relative_path, context, error_code="restore_path_escape")
        resolved = destination.resolve(strict=False)
        if resolved in seen:
            raise ValueError("restore_path_collision")
        seen.add(resolved)
        destinations.append((source_entry, destination))

    root = _new_transaction_root("restore-replacements", computed, context)
    entries: list[BackupEntry] = []
    for source_entry, destination in destinations:
        if not destination.exists() and not destination.is_symlink():
            entries.append(BackupEntry(source_entry.operation_index, source_entry.kind, str(destination), source_entry.root_id, source_entry.relative_path, "missing"))
            continue
        st = _safe_lstat(destination)
        if stat.S_ISREG(st.st_mode):
            st, content = _read_regular_file_bound(
                destination,
                mismatch_code="restore_replacement_preimage_drift",
                link_code="preflight_unexpected_link",
                not_regular_code="restore_refuse_special_file",
            )
            digest = _sha256(content)
            payload_path = f"rootfs/{source_entry.root_id}/{source_entry.relative_path}"
            _write_verified_payload(root / payload_path, content, digest)
            entries.append(BackupEntry(source_entry.operation_index, source_entry.kind, str(destination), source_entry.root_id, source_entry.relative_path, "file", mode=stat.S_IMODE(st.st_mode), size=len(content), sha256=digest, payload_path=payload_path))
        elif stat.S_ISDIR(st.st_mode):
            entries.append(BackupEntry(source_entry.operation_index, source_entry.kind, str(destination), source_entry.root_id, source_entry.relative_path, "directory", mode=stat.S_IMODE(st.st_mode)))
        else:
            raise ValueError("restore_refuse_special_file")
    replacement = BackupManifest(path=root / "manifest.json", root=root, plan_digest=computed, entries=tuple(entries)).with_digest()
    _write_json_atomic(replacement.path, replacement.to_dict(), mode=0o600)
    return replacement


def _rollback_restore_entries(
    completed: tuple[BackupEntry, ...],
    source_manifest: BackupManifest,
    replacement_manifest: BackupManifest,
    replacement_by_index: dict[int, BackupEntry],
    context: RuntimeContext,
) -> tuple[OperationOutcome, ...]:
    rollback_outcomes: list[OperationOutcome] = []
    for source_entry in reversed(completed):
        replacement_entry = replacement_by_index[source_entry.operation_index]
        destination = path_from_root_relative(source_entry.root_id, source_entry.relative_path, context, error_code="restore_path_escape")
        try:
            _rollback_restored_entry(source_entry, source_manifest, replacement_entry, replacement_manifest, context)
        except BaseException as exc:
            rollback_outcomes.append(OperationOutcome(source_entry.operation_index, source_entry.kind, str(destination), "failed", _error_code(exc, "restore_rollback_failed")))
            continue
        rollback_outcomes.append(OperationOutcome(source_entry.operation_index, source_entry.kind, str(destination), "rolled_back"))
    return tuple(rollback_outcomes)


def _rollback_restored_entry(source_entry: BackupEntry, source_manifest: BackupManifest, replacement_entry: BackupEntry, replacement_manifest: BackupManifest, context: RuntimeContext) -> None:
    if replacement_entry.target_type != "missing":
        _restore_entry(replacement_entry, replacement_manifest, context)
        return

    target = path_from_root_relative(source_entry.root_id, source_entry.relative_path, context, error_code="restore_path_escape")
    if source_entry.target_type == "file":
        expected = _read_source_entry_payload(source_entry, source_manifest)
        _read_regular_file_bound(
            target,
            expected_content=expected,
            expected_sha256=source_entry.sha256,
            expected_size=len(expected),
            expected_mode=source_entry.mode,
            mismatch_code="restore_rollback_preimage_drift",
            link_code="restore_rollback_preimage_drift",
            not_regular_code="restore_rollback_preimage_drift",
        )
        os.unlink(target)
        _fsync_directory(target.parent)
        return

    if source_entry.target_type == "directory":
        st = _safe_lstat(target)
        if not stat.S_ISDIR(st.st_mode) or (source_entry.mode is not None and stat.S_IMODE(st.st_mode) != source_entry.mode):
            raise ValueError("restore_rollback_preimage_drift")
        os.rmdir(target)
        _fsync_directory(target.parent)
        return

    if source_entry.target_type == "missing":
        if target.exists() or target.is_symlink():
            raise ValueError("restore_rollback_preimage_drift")
        return

    raise ValueError("restore_manifest_invalid_entry_type")


def _read_source_entry_payload(entry: BackupEntry, manifest: BackupManifest) -> bytes:
    if entry.payload_path is None or entry.sha256 is None:
        raise ValueError("restore_manifest_missing_payload")
    payload = manifest.root / entry.payload_path
    _assert_payload_contained(payload, manifest.root)
    return _read_backup_payload(payload, entry)


def _read_backup_payload(payload: Path, entry: BackupEntry) -> bytes:
    if entry.sha256 is None:
        raise ValueError("restore_manifest_missing_payload")
    _, content = _read_regular_file_bound(
        payload,
        expected_sha256=entry.sha256,
        expected_size=entry.size,
        mismatch_code="restore_payload_digest_mismatch",
        link_code="restore_payload_digest_mismatch",
        not_regular_code="restore_payload_digest_mismatch",
    )
    return content


def _load_manifest(path: Path) -> BackupManifest:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError("restore_manifest_invalid_json") from exc
    if not isinstance(data, dict):
        raise ValueError("restore_manifest_invalid_json")
    manifest = BackupManifest.from_dict(data, path)
    if data.get("schema") != "remove-gentle-context.backup/v1":
        raise ValueError("restore_manifest_invalid_schema")
    return manifest


def _new_transaction_root(kind: str, digest: str, context: RuntimeContext) -> Path:
    prefix = digest.removeprefix("sha256:")[:12]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    root = resolve_state_root(context.profile) / kind / f"{timestamp}-{prefix}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _write_verified_payload(path: Path, content: bytes, expected_digest: str) -> None:
    _write_file_atomic(path, content, mode=0o600)
    if _sha256(path.read_bytes()) != expected_digest:
        raise ValueError("backup_payload_digest_mismatch")


def _write_file_atomic(path: Path, content: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            _fsync_file(handle.fileno())
        temp_path.chmod(mode)
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            if temp_path.exists() or temp_path.is_symlink():
                os.unlink(temp_path)
        finally:
            raise


def write_json_atomic(path: Path, data: dict[str, object], *, mode: int = 0o600) -> None:
    """Write a JSON artifact with same-directory temp, fsync, and atomic replace."""

    content = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    # Validate the declared JSON before replacement.
    json.loads(content.decode("utf-8"))
    _write_file_atomic(path, content, mode=mode)


def _write_json_atomic(path: Path, data: dict[str, object], *, mode: int) -> None:
    write_json_atomic(path, data, mode=mode)


def _append_journal(manifest: BackupManifest, transition: str, operation_index: int, operation: Operation | None, *, status: str | None = None, error: str | None = None) -> None:
    manifest.root.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {"transition": transition, "operation_index": operation_index, "timestamp": datetime.now(timezone.utc).isoformat()}
    if operation is not None:
        data["kind"] = str(operation.kind)
        data["path"] = operation.path
    if status is not None:
        data["status"] = status
    if error is not None:
        data["error"] = error
    journal = manifest.root / "journal.jsonl"
    with journal.open("ab") as handle:
        handle.write(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
        handle.flush()
        _fsync_file(handle.fileno())
    _fsync_directory(journal.parent)


def _append_journal_best_effort(manifest: BackupManifest, transition: str, operation_index: int, operation: Operation | None, *, status: str | None = None, error: str | None = None) -> None:
    try:
        _append_journal(manifest, transition, operation_index, operation, status=status, error=error)
    except BaseException:
        return


def _decode_optional_image(encoded: str | None, declared_digest: str | None, mismatch_code: str) -> bytes | None:
    if encoded is None and declared_digest is None:
        return None
    return _decode_required_image(encoded, declared_digest, mismatch_code)


def _decode_required_image(encoded: str | None, declared_digest: str | None, mismatch_code: str) -> bytes:
    if encoded is None or declared_digest is None:
        raise ValueError(mismatch_code)
    try:
        content = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("operation_invalid_embedded_image") from exc
    if _sha256(content) != declared_digest:
        raise ValueError(mismatch_code)
    return content


def _validate_declared_parse(operation: Operation, content: bytes) -> None:
    parse_as = _declared_parse(operation)
    if parse_as is None:
        return
    try:
        text = content.decode("utf-8")
        if parse_as == "json":
            json.loads(text)
        elif parse_as == "toml":
            tomllib.loads(text)
    except Exception as exc:
        raise ValueError("operation_parse_failed") from exc


def _declared_parse(operation: Operation) -> str | None:
    for key in ("parse", "parse_as", "format", "content_type"):
        value = operation.details.get(key)
        if isinstance(value, str):
            lowered = value.lower()
            if "json" in lowered:
                return "json"
            if "toml" in lowered:
                return "toml"
    return None


def _read_regular_file_bound(
    path: Path,
    *,
    expected_content: bytes | None = None,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    expected_mode: int | None = None,
    mismatch_code: str,
    link_code: str,
    not_regular_code: str,
) -> tuple[os.stat_result, bytes]:
    try:
        pre_open_stat = os.lstat(path)
    except FileNotFoundError as exc:
        raise ValueError(mismatch_code) from exc
    if stat.S_ISLNK(pre_open_stat.st_mode) or _is_windows_reparse_point(pre_open_stat):
        raise ValueError(link_code)
    if not stat.S_ISREG(pre_open_stat.st_mode):
        raise ValueError(not_regular_code)

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise ValueError(link_code) from exc
        raise ValueError(mismatch_code) from exc

    try:
        opened_stat = os.fstat(fd)
        if stat.S_ISLNK(opened_stat.st_mode) or _is_windows_reparse_point(opened_stat):
            raise ValueError(link_code)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise ValueError(not_regular_code)
        if not _same_file_identity(pre_open_stat, opened_stat):
            raise ValueError(mismatch_code)
        if expected_mode is not None and stat.S_IMODE(opened_stat.st_mode) != expected_mode:
            raise ValueError(mismatch_code)
        content = _read_all_from_fd(fd)
    finally:
        os.close(fd)

    digest = _sha256(content)
    if len(content) != opened_stat.st_size:
        raise ValueError(mismatch_code)
    if expected_size is not None and len(content) != expected_size:
        raise ValueError(mismatch_code)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(mismatch_code)
    if expected_content is not None and content != expected_content:
        raise ValueError(mismatch_code)
    return opened_stat, content


def _read_all_from_fd(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _same_file_identity(before: os.stat_result, after: os.stat_result) -> bool:
    before_inode = _reliable_stat_integer(getattr(before, "st_ino", None))
    after_inode = _reliable_stat_integer(getattr(after, "st_ino", None))
    if before_inode is None or after_inode is None:
        return False
    if before_inode != after_inode:
        return False

    before_device = _reliable_stat_integer(getattr(before, "st_dev", None))
    after_device = _reliable_stat_integer(getattr(after, "st_dev", None))
    if before_device is not None and after_device is not None and before_device != after_device:
        return False
    return True


def _reliable_stat_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0:
        return None
    return value


def _safe_lstat(path: Path) -> os.stat_result:
    try:
        st = os.lstat(path)
    except FileNotFoundError as exc:
        raise ValueError("preflight_preimage_drift") from exc
    if stat.S_ISLNK(st.st_mode) or _is_windows_reparse_point(st):
        raise ValueError("preflight_unexpected_link")
    return st


def _assert_parent_contained(path: Path, context: RuntimeContext) -> None:
    root_relative_path(path.parent, context)


def _assert_parent_contained_for_target(path: Path) -> None:
    if not path.parent.exists():
        raise ValueError("preflight_parent_missing")


def _assert_payload_contained(path: Path, manifest_root: Path) -> None:
    rootfs = (manifest_root / "rootfs").resolve(strict=False)
    resolved = path.resolve(strict=False)
    if resolved != rootfs and not resolved.is_relative_to(rootfs):
        raise ValueError("restore_payload_path_escape")


def _sha256(content: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(content).hexdigest()


def _require_digest(digest: str | None, code: str) -> str:
    if digest is None:
        raise ValueError(code)
    return digest


def _error_code(exc: BaseException, fallback: str) -> str:
    if isinstance(exc, ValueError) and exc.args and isinstance(exc.args[0], str):
        return exc.args[0]
    return fallback


def _fsync_file(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError:
        pass


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        _fsync_file(fd)
    finally:
        os.close(fd)
