from __future__ import annotations

import base64
import hashlib
import json
import tomllib
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .canonical import digest_json
from .models import (
    ArtifactClass,
    BackupManifest,
    Check,
    Inventory,
    Operation,
    OperationKind,
    Plan,
    PreservationAssertion,
    Receipt,
    ReceiptStatus,
    RuntimeContext,
    VerificationResult,
)
from .paths import root_map

REQUIRED_CODES = (
    "verify_active_residue",
    "verify_ambiguous_untouched",
    "verify_generated_regrowth",
    "verify_history_preservation",
    "verify_lifecycle_state",
    "verify_package_presence",
    "verify_planned_postcondition",
    "verify_preservation_mismatch",
    "verify_structured_parse",
)
SUPPORT_CODES = (
    "verify_adapter_live",
    "verify_artifact_digest",
    "verify_backup_evidence",
    "verify_root_binding",
)


def verify_receipt(receipt: Receipt, context: RuntimeContext, adapters: object) -> VerificationResult:
    """Independently verify a cleanup receipt against live state.

    The verifier treats the receipt as evidence to validate, not as proof of
    success. All checks are read-only and deterministic; adapter exceptions are
    converted into stable failed checks.
    """

    checks: list[Check] = []
    plan = getattr(receipt, "plan", None)
    inventory = getattr(receipt, "inventory", None)

    if not isinstance(plan, Plan):
        checks.append(_failed("verify_artifact_digest", {"artifact": "plan", "error": "missing_plan"}))
        plan = None
    else:
        checks.extend(_verify_plan_artifact(plan, context))

    if inventory is None:
        checks.append(_failed("verify_artifact_digest", {"artifact": "inventory", "error": "missing_inventory"}))
    elif isinstance(inventory, Inventory):
        checks.extend(_verify_inventory_artifact(inventory, context, plan))
    else:
        checks.append(_failed("verify_artifact_digest", {"artifact": "inventory", "error": "invalid_inventory"}))

    checks.extend(_verify_receipt_status_and_lifecycle(receipt))

    if plan is not None:
        checks.extend(_verify_backup_evidence(plan, receipt))
        checks.extend(_verify_operations(plan, receipt))
        checks.extend(_verify_preservations(plan.preservation_assertions))

    checks.extend(_run_adapter_live_verification(receipt, context, adapters))
    checks.extend(_verify_live_reinventory(plan, inventory, context, adapters))

    checks = _with_default_passes(checks)
    checks = tuple(sorted(checks, key=_check_sort_key))
    status = "failed" if any(check.status == "failed" and check.severity == "error" for check in checks) else "passed"
    return VerificationResult(status=status, checks=checks)


def _verify_plan_artifact(plan: Plan, context: RuntimeContext) -> tuple[Check, ...]:
    checks: list[Check] = []
    expected = digest_json(plan.to_unsigned_dict())
    if plan.digest != expected:
        checks.append(_failed("verify_artifact_digest", {"artifact": "plan", "expected": expected, "actual": plan.digest}))
    if plan.home and plan.home != str(context.profile.home.resolve(strict=False)):
        checks.append(_failed("verify_root_binding", {"artifact": "plan", "field": "home", "expected": plan.home, "actual": str(context.profile.home.resolve(strict=False))}))
    if plan.os_name and plan.os_name != context.profile.os_name:
        checks.append(_failed("verify_root_binding", {"artifact": "plan", "field": "os_name", "expected": plan.os_name, "actual": context.profile.os_name}))
    if plan.root_map and dict(sorted(plan.root_map.items())) != dict(sorted(root_map(context).items())):
        checks.append(_failed("verify_root_binding", {"artifact": "plan", "field": "root_map", "expected": dict(sorted(plan.root_map.items())), "actual": dict(sorted(root_map(context).items()))}))
    return tuple(checks)


def _verify_inventory_artifact(inventory: Inventory, context: RuntimeContext, plan: Plan | None) -> tuple[Check, ...]:
    checks: list[Check] = []
    expected = digest_json(inventory.to_unsigned_dict())
    if inventory.digest != expected:
        checks.append(_failed("verify_artifact_digest", {"artifact": "inventory", "expected": expected, "actual": inventory.digest}))
    if plan is not None and plan.inventory_digest and inventory.digest != plan.inventory_digest:
        checks.append(_failed("verify_artifact_digest", {"artifact": "inventory", "field": "plan_binding", "expected": plan.inventory_digest, "actual": inventory.digest}))
    if inventory.home and inventory.home != str(context.profile.home.resolve(strict=False)):
        checks.append(_failed("verify_root_binding", {"artifact": "inventory", "field": "home", "expected": inventory.home, "actual": str(context.profile.home.resolve(strict=False))}))
    if inventory.os_name and inventory.os_name != context.profile.os_name:
        checks.append(_failed("verify_root_binding", {"artifact": "inventory", "field": "os_name", "expected": inventory.os_name, "actual": context.profile.os_name}))
    if inventory.root_map and dict(sorted(inventory.root_map.items())) != dict(sorted(root_map(context).items())):
        checks.append(_failed("verify_root_binding", {"artifact": "inventory", "field": "root_map", "expected": dict(sorted(inventory.root_map.items())), "actual": dict(sorted(root_map(context).items()))}))
    return tuple(checks)


def _verify_receipt_status_and_lifecycle(receipt: Receipt) -> tuple[Check, ...]:
    checks: list[Check] = []
    if receipt.status != ReceiptStatus.COMPLETED:
        checks.append(_failed("verify_lifecycle_state", {"artifact": "receipt", "field": "status", "actual": None if receipt.status is None else str(receipt.status)}))
    stopped = {
        getattr(outcome, "pid", None)
        for outcome in receipt.lifecycle_outcomes
        if getattr(outcome, "action", "") == "stop" and getattr(outcome, "status", "") == "stopped"
    }
    restarted = {
        getattr(outcome, "pid", None)
        for outcome in receipt.lifecycle_outcomes
        if getattr(outcome, "action", "") == "restart" and getattr(outcome, "status", "") == "restarted"
    }
    failed = [outcome for outcome in receipt.lifecycle_outcomes if getattr(outcome, "status", "") == "failed"]
    if failed:
        checks.append(_failed("verify_lifecycle_state", {"error": "lifecycle_failed_outcome", "count": len(failed), "codes": sorted(str(getattr(outcome, "code", "")) for outcome in failed)}))
    missing = sorted(pid for pid in stopped - restarted if pid is not None)
    if missing:
        checks.append(_failed("verify_lifecycle_state", {"error": "restart_missing", "pids": missing}))
    return tuple(checks)


def _verify_backup_evidence(plan: Plan, receipt: Receipt) -> tuple[Check, ...]:
    if not plan.operations:
        return ()
    path = receipt.backup_manifest_path
    if path is None:
        return (_failed("verify_backup_evidence", {"error": "missing_backup_manifest"}),)
    try:
        data = json.loads(Path(path).read_text())
        if not isinstance(data, Mapping):
            raise ValueError("manifest_not_object")
        manifest = BackupManifest.from_dict(data, Path(path))
        computed = digest_json(manifest.to_unsigned_dict())
        if manifest.digest != computed:
            return (_failed("verify_backup_evidence", {"error": "manifest_digest_mismatch", "expected": computed, "actual": manifest.digest}),)
        if manifest.plan_digest != plan.digest:
            return (_failed("verify_backup_evidence", {"error": "manifest_plan_mismatch", "expected": plan.digest, "actual": manifest.plan_digest}),)
        if len(manifest.entries) != len(plan.operations):
            return (_failed("verify_backup_evidence", {"error": "manifest_entry_count_mismatch", "expected": len(plan.operations), "actual": len(manifest.entries)}),)
    except BaseException as exc:
        return (_failed("verify_backup_evidence", {"error": _stable_error(exc)}),)
    return ()


def _verify_operations(plan: Plan, receipt: Receipt) -> tuple[Check, ...]:
    checks: list[Check] = []
    completed_indexes = {
        int(getattr(outcome, "operation_index", -1))
        for outcome in receipt.operation_outcomes
        if getattr(outcome, "status", "") == "completed"
    }
    if len(completed_indexes) < len(plan.operations):
        checks.append(_failed("verify_planned_postcondition", {"error": "operation_receipt_incomplete", "expected": len(plan.operations), "actual": len(completed_indexes)}))
    for index, operation in enumerate(plan.operations):
        checks.extend(_verify_operation(index, operation))
    return tuple(checks)


def _verify_operation(index: int, operation: Operation) -> tuple[Check, ...]:
    checks: list[Check] = []
    path = Path(operation.path)
    try:
        kind = OperationKind(str(operation.kind))
    except ValueError as exc:
        return (_failed("verify_planned_postcondition", {"operation_index": index, "path": operation.path, "error": _stable_error(exc)}),)

    for label, encoded, declared in (("preimage", operation.preimage_base64, operation.preimage_sha256), ("postimage", operation.postimage_base64, operation.postimage_sha256)):
        if encoded is None and declared is None:
            continue
        try:
            _decode_image(encoded, declared)
        except ValueError as exc:
            checks.append(_failed("verify_artifact_digest", {"operation_index": index, "path": operation.path, "image": label, "error": str(exc)}))

    if kind == OperationKind.DELETE_FILE:
        if path.exists() or path.is_symlink():
            checks.append(_failed("verify_planned_postcondition", {"operation_index": index, "path": operation.path, "error": "delete_target_present"}))
        return tuple(checks)
    if kind == OperationKind.REMOVE_EMPTY_DIRECTORY:
        if path.exists() or path.is_symlink():
            checks.append(_failed("verify_planned_postcondition", {"operation_index": index, "path": operation.path, "error": "directory_target_present"}))
        return tuple(checks)
    if kind == OperationKind.WRITE_FILE:
        try:
            content = path.read_bytes()
        except BaseException as exc:
            checks.append(_failed("verify_planned_postcondition", {"operation_index": index, "path": operation.path, "error": _stable_error(exc)}))
            return tuple(checks)
        if operation.postimage_sha256 and _sha256(content) != operation.postimage_sha256:
            checks.append(_failed("verify_planned_postcondition", {"operation_index": index, "path": operation.path, "expected": operation.postimage_sha256, "actual": _sha256(content)}))
        checks.extend(_verify_declared_structure(index, operation, content))
    return tuple(checks)


def _verify_declared_structure(index: int, operation: Operation, content: bytes) -> tuple[Check, ...]:
    content_type = str(operation.details.get("content_type") or operation.details.get("parse") or "")
    if not content_type:
        return ()
    try:
        if content_type in {"application/json", "json"}:
            json.loads(content.decode("utf-8"))
        elif content_type in {"text/toml", "toml"}:
            tomllib.loads(content.decode("utf-8"))
    except BaseException as exc:
        return (_failed("verify_structured_parse", {"operation_index": index, "path": operation.path, "content_type": content_type, "error": _stable_error(exc)}),)
    return ()


def _verify_preservations(assertions: Sequence[PreservationAssertion]) -> tuple[Check, ...]:
    checks: list[Check] = []
    for assertion in assertions:
        preservation = assertion.details.get("preservation") if isinstance(assertion.details, Mapping) else None
        if not isinstance(preservation, Mapping):
            checks.append(_failed("verify_preservation_mismatch", {"candidate_id": assertion.candidate_id, "path": assertion.path, "error": "missing_preservation_baseline"}))
            continue
        checks.extend(_verify_one_preservation(assertion, preservation))
    return tuple(checks)


def _verify_one_preservation(assertion: PreservationAssertion, preservation: Mapping[str, object]) -> tuple[Check, ...]:
    path = Path(assertion.path)
    kind = str(preservation.get("kind", ""))
    try:
        if kind in {"json_value", "toml_value"}:
            value = _load_structured_value(path, kind, _string_sequence(preservation.get("pointer", ())))
            expected = preservation.get("value")
            expected_digest = str(preservation.get("digest", ""))
            actual_digest = digest_json(value)  # type: ignore[arg-type]
            if value != expected or actual_digest != expected_digest:
                return (_failed("verify_preservation_mismatch", {"candidate_id": assertion.candidate_id, "path": assertion.path, "expected_digest": expected_digest, "actual_digest": actual_digest}),)
            return ()
        if kind == "file_sha256":
            digest = _sha256(path.read_bytes())
            expected = str(preservation.get("sha256", ""))
            code = "verify_history_preservation" if preservation.get("semantic") == "history" else "verify_preservation_mismatch"
            if digest != expected:
                return (_failed(code, {"candidate_id": assertion.candidate_id, "path": assertion.path, "expected": expected, "actual": digest}),)
            return ()
        if kind == "directory_exists":
            if not path.is_dir():
                return (_failed("verify_package_presence", {"candidate_id": assertion.candidate_id, "path": assertion.path, "expected": "directory"}),)
            return ()
        if kind == "path_exists":
            if not path.exists() and not path.is_symlink():
                return (_failed("verify_package_presence", {"candidate_id": assertion.candidate_id, "path": assertion.path, "expected": "path"}),)
            return ()
        if kind == "empty_directory":
            if not path.is_dir() or any(path.iterdir()):
                return (_failed("verify_ambiguous_untouched", {"candidate_id": assertion.candidate_id, "path": assertion.path, "expected": "empty_directory"}),)
            return ()
        if kind == "json_array_order":
            values = _string_sequence(preservation.get("values", ()))
            actual = _load_structured_value(path, "json_value", _string_sequence(preservation.get("pointer", ())))
            if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)):
                return (_failed("verify_preservation_mismatch", {"candidate_id": assertion.candidate_id, "path": assertion.path, "error": "array_missing"}),)
            if _relative_order(tuple(str(item) for item in actual if isinstance(item, str) and item in values), values) != values:
                return (_failed("verify_preservation_mismatch", {"candidate_id": assertion.candidate_id, "path": assertion.path, "expected": list(values)}),)
            return ()
    except BaseException as exc:
        code = "verify_structured_parse" if kind in {"json_value", "toml_value"} else "verify_preservation_mismatch"
        if kind == "file_sha256" and preservation.get("semantic") == "history":
            code = "verify_history_preservation"
        if kind in {"directory_exists", "path_exists"}:
            code = "verify_package_presence"
        return (_failed(code, {"candidate_id": assertion.candidate_id, "path": assertion.path, "error": _stable_error(exc)}),)
    return (_failed("verify_preservation_mismatch", {"candidate_id": assertion.candidate_id, "path": assertion.path, "error": "unknown_preservation_kind", "kind": kind}),)


def _run_adapter_live_verification(receipt: Receipt, context: RuntimeContext, adapters: object) -> tuple[Check, ...]:
    checks: list[Check] = []
    try:
        ordered = _ordered_adapters(adapters)
    except BaseException as exc:
        return (_failed("verify_adapter_live", {"error": _stable_error(exc)}),)
    for adapter in ordered:
        client = str(getattr(adapter, "client", ""))
        adapter_failed = False
        try:
            returned = tuple(adapter.verify(receipt, context))  # type: ignore[attr-defined]
            for check in returned:
                if isinstance(check, Check) and check.status == "failed":
                    adapter_failed = True
                    checks.append(check)
        except BaseException as exc:
            checks.append(_failed(_adapter_error_code(exc), {"client": client, "error": _stable_error(exc)}))
            continue
        if not adapter_failed:
            checks.append(_passed("verify_adapter_live", {"client": client}))
    return tuple(checks)


def _verify_live_reinventory(plan: Plan | None, inventory: Inventory | None, context: RuntimeContext, adapters: object) -> tuple[Check, ...]:
    from .engine import build_inventory, build_plan

    checks: list[Check] = []
    try:
        live_inventory = build_inventory(context, adapters)
    except BaseException as exc:
        return (_failed(_adapter_error_code(exc), {"stage": "inventory", "error": _stable_error(exc)}),)

    for finding in live_inventory.findings:
        checks.append(_failed(_adapter_error_code(ValueError(finding.message)), {"client": finding.client, "code": finding.code, "error": finding.message}))

    try:
        live_plan = build_plan(live_inventory, context, adapters)
    except BaseException as exc:
        checks.append(_failed(_adapter_error_code(exc), {"stage": "plan", "error": _stable_error(exc)}))
        return tuple(checks)

    active_operations = tuple(operation for operation in live_plan.operations if _is_relevant_operation(operation))
    if active_operations:
        checks.append(_failed("verify_active_residue", {"operation_count": len(active_operations), "targets": sorted(operation.path for operation in active_operations)}))

    generated = tuple(
        candidate
        for candidate in live_inventory.candidates
        if (candidate.artifact_class == ArtifactClass.GENERATED_ARTIFACT or candidate.details.get("kind") == "generated_registry")
        and str(candidate.ownership) == "proven"
        and candidate.proposed_action != "report_only"
    )
    if generated:
        checks.append(_failed("verify_generated_regrowth", {"candidate_ids": sorted(candidate.candidate_id for candidate in generated), "paths": sorted(candidate.path for candidate in generated)}))

    original_blocked = set(plan.blocked_candidate_ids if plan is not None else ())
    live_blocked = set(live_plan.blocked_candidate_ids)
    unexpected_blocked = sorted(live_blocked - original_blocked)
    if unexpected_blocked:
        checks.append(_failed("verify_ambiguous_untouched", {"error": "unapproved_blockers", "candidate_ids": unexpected_blocked}))

    if plan is not None and original_blocked:
        live_candidate_ids = {candidate.candidate_id for candidate in live_inventory.candidates}
        missing = sorted(original_blocked - live_candidate_ids)
        if missing:
            checks.append(_failed("verify_ambiguous_untouched", {"error": "original_blocker_missing_or_changed", "candidate_ids": missing}))

    return tuple(checks)


def _is_relevant_operation(operation: Operation) -> bool:
    return bool(operation.path)


def _with_default_passes(checks: Iterable[Check]) -> list[Check]:
    result = list(checks)
    failed_codes = {check.code for check in result if check.status == "failed"}
    seen_codes = {check.code for check in result}
    for code in sorted(set(REQUIRED_CODES + SUPPORT_CODES)):
        if code not in failed_codes and code not in seen_codes:
            result.append(_passed(code, {}))
    return result


def _failed(code: str, evidence: Mapping[str, object]) -> Check:
    return Check(code=code, status="failed", severity="error", evidence=dict(evidence))


def _passed(code: str, evidence: Mapping[str, object]) -> Check:
    return Check(code=code, status="passed", severity="info", evidence=dict(evidence))


def _check_sort_key(check: Check) -> tuple[str, str, str, bytes]:
    return (check.code, check.status, check.severity, json.dumps(check.to_dict()["evidence"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _adapter_error_code(exc: BaseException) -> str:
    text = _stable_error(exc)
    if any(token in text for token in ("malformed", "invalid_layout", "invalid_packages", "not_object", "unreadable")):
        return "verify_structured_parse"
    if "registry_regrew" in text:
        return "verify_generated_regrowth"
    if "package_missing" in text or "binary_missing" in text:
        return "verify_package_presence"
    if "restart" in text or "lifecycle" in text:
        return "verify_lifecycle_state"
    if "present" in text or "residue" in text:
        return "verify_active_residue"
    return "verify_adapter_live"


def _stable_error(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    return text.replace(str(Path.home()), "~")


def _ordered_adapters(adapters: object) -> tuple[object, ...]:
    if hasattr(adapters, "_adapters"):
        values = list(getattr(adapters, "_adapters").values())
    elif isinstance(adapters, Mapping):
        values = list(adapters.values())
    else:
        values = list(adapters)  # type: ignore[arg-type]
    seen: set[str] = set()
    for adapter in values:
        client = getattr(adapter, "client", None)
        if not isinstance(client, str) or not client:
            raise ValueError("adapter_invalid_client")
        if client in seen:
            raise ValueError("adapter_duplicate_client")
        seen.add(client)
    return tuple(sorted(values, key=lambda adapter: str(getattr(adapter, "client", ""))))


def _decode_image(encoded: str | None, declared_digest: str | None) -> bytes:
    if encoded is None or declared_digest is None:
        raise ValueError("embedded_image_incomplete")
    try:
        content = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("embedded_image_invalid") from exc
    if _sha256(content) != declared_digest:
        raise ValueError("embedded_image_digest_mismatch")
    return content


def _load_structured_value(path: Path, kind: str, pointer: Sequence[str]) -> object:
    if kind == "json_value":
        data = json.loads(path.read_text())
    elif kind == "toml_value":
        data = tomllib.loads(path.read_text())
    else:
        raise ValueError("unknown_structured_kind")
    value: object = data
    for part in pointer:
        if not isinstance(value, Mapping) or part not in value:
            raise ValueError("structured_pointer_missing")
        value = value[part]
    return value


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


def _relative_order(actual_values: tuple[str, ...], expected_values: tuple[str, ...]) -> tuple[str, ...]:
    expected_set = set(expected_values)
    return tuple(value for value in actual_values if value in expected_set)


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()
