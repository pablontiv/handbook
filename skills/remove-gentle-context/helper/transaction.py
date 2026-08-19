from __future__ import annotations

import base64
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
from .models import BackupEntry, BackupManifest, Operation, OperationKind, OperationOutcome, Plan, Receipt, ReceiptStatus, RuntimeContext
from .paths import _is_windows_reparse_point, path_from_root_relative, resolve_state_root, root_relative_path


class OperationApplyError(RuntimeError):
    def __init__(self, code: str, outcomes: tuple[OperationOutcome, ...]) -> None:
        super().__init__(code)
        self.code = code
        self.outcomes = outcomes


def create_backup(plan: Plan, context: RuntimeContext) -> BackupManifest:
    plan_digest = _require_digest(plan.digest, "backup_plan_missing_digest")
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
    if manifest.plan_digest != _require_digest(plan.digest, "apply_plan_missing_digest"):
        raise ValueError("apply_manifest_plan_mismatch")
    outcomes: list[OperationOutcome] = []
    entries_by_index = {entry.operation_index: entry for entry in manifest.entries}
    for index, operation in enumerate(plan.operations):
        entry = entries_by_index.get(index)
        if entry is None:
            raise ValueError("apply_manifest_missing_entry")
        _append_journal(manifest, "before", index, operation)
        try:
            _apply_one(index, operation, entry, context)
        except BaseException as exc:
            code = _error_code(exc, "operation_failed")
            failed = OperationOutcome(index, str(operation.kind), operation.path, "failed", code)
            _append_journal(manifest, "after", index, operation, status="failed", error=code)
            raise OperationApplyError(code, tuple(outcomes + [failed])) from exc
        outcome = OperationOutcome(index, str(operation.kind), operation.path, "completed")
        outcomes.append(outcome)
        _append_journal(manifest, "after", index, operation, status="completed")
    return tuple(outcomes)


def rollback(manifest: BackupManifest, outcomes: Iterable[OperationOutcome], context: RuntimeContext) -> tuple[OperationOutcome, ...]:
    completed = [outcome for outcome in outcomes if outcome.status == "completed"]
    entries_by_index = {entry.operation_index: entry for entry in manifest.entries}
    rollback_outcomes: list[OperationOutcome] = []
    for outcome in reversed(completed):
        entry = entries_by_index[outcome.operation_index]
        _append_journal(manifest, "rollback_before", outcome.operation_index, None)
        try:
            _restore_entry(entry, manifest, context)
        except BaseException as exc:
            code = _error_code(exc, "rollback_failed")
            rollback_outcomes.append(OperationOutcome(outcome.operation_index, outcome.kind, outcome.path, "failed", code))
            _append_journal(manifest, "rollback_after", outcome.operation_index, None, status="failed", error=code)
            continue
        rollback_outcomes.append(OperationOutcome(outcome.operation_index, outcome.kind, outcome.path, "rolled_back"))
        _append_journal(manifest, "rollback_after", outcome.operation_index, None, status="rolled_back")
    return tuple(rollback_outcomes)


def execute_plan(plan: Plan, approval: str, context: RuntimeContext, lifecycle: object) -> Receipt:
    validate_approval(plan, approval)
    if not plan.operations:
        return Receipt(status=ReceiptStatus.COMPLETED)
    manifest = create_backup(plan, context)
    try:
        outcomes = apply_operations(plan, manifest, context)
    except OperationApplyError as exc:
        rollback_outcomes = rollback(manifest, exc.outcomes, context)
        status = ReceiptStatus.ROLLED_BACK
        if any(outcome.status == "failed" for outcome in rollback_outcomes):
            status = ReceiptStatus.MANUAL_RECOVERY_REQUIRED
        return Receipt(operation_outcomes=tuple(exc.outcomes + rollback_outcomes), backup_manifest_path=manifest.path, status=status)
    return Receipt(operation_outcomes=outcomes, backup_manifest_path=manifest.path, status=ReceiptStatus.COMPLETED)


def restore(manifest_path: Path, approval: str, context: RuntimeContext) -> Receipt:
    manifest = _load_manifest(manifest_path)
    computed = digest_json(manifest.to_unsigned_dict())
    if manifest.digest != computed:
        raise ValueError("restore_manifest_digest_mismatch")
    if approval != computed:
        raise ValueError("restore_approval_mismatch")
    replacement_manifest = _backup_restore_replacements(manifest, context)
    outcomes: list[OperationOutcome] = []
    seen: set[Path] = set()
    for entry in manifest.entries:
        destination = path_from_root_relative(entry.root_id, entry.relative_path, context, error_code="restore_path_escape")
        resolved = destination.resolve(strict=False)
        if resolved in seen:
            raise ValueError("restore_path_collision")
        seen.add(resolved)
        _restore_entry(entry, manifest, context)
        outcomes.append(OperationOutcome(entry.operation_index, entry.kind, str(destination), "completed"))
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

    st = _safe_lstat(target)
    if not stat.S_ISREG(st.st_mode):
        raise ValueError("preflight_not_regular_file")
    if st.st_size != len(expected):
        raise ValueError("preflight_preimage_drift")
    content = target.read_bytes()
    if _sha256(content) != operation.preimage_sha256 or content != expected:
        raise ValueError("preflight_preimage_drift")
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
    st = _safe_lstat(target)
    if not stat.S_ISREG(st.st_mode) or st.st_size != len(expected) or (entry.mode is not None and stat.S_IMODE(st.st_mode) != entry.mode):
        raise ValueError("preflight_preimage_drift")
    content = target.read_bytes()
    if content != expected or _sha256(content) != entry.sha256:
        raise ValueError("preflight_preimage_drift")


def _restore_entry(entry: BackupEntry, manifest: BackupManifest, context: RuntimeContext) -> None:
    target = path_from_root_relative(entry.root_id, entry.relative_path, context, error_code="restore_path_escape")
    if entry.target_type == "file":
        if entry.payload_path is None or entry.sha256 is None:
            raise ValueError("restore_manifest_missing_payload")
        payload = manifest.root / entry.payload_path
        _assert_payload_contained(payload, manifest.root)
        content = payload.read_bytes()
        if _sha256(content) != entry.sha256:
            raise ValueError("restore_payload_digest_mismatch")
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
            content = destination.read_bytes()
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


def _write_json_atomic(path: Path, data: dict[str, object], *, mode: int) -> None:
    content = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    # Validate the declared JSON before replacement.
    json.loads(content.decode("utf-8"))
    _write_file_atomic(path, content, mode=mode)


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


def _safe_lstat(path: Path) -> os.stat_result:
    try:
        st = os.lstat(path)
    except FileNotFoundError as exc:
        raise ValueError("preflight_preimage_drift") from exc
    if path.is_symlink() or _is_windows_reparse_point(st):
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
