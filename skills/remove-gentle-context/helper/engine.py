from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Mapping

from helper.paths import root_map
from helper.models import (
    Candidate,
    Inventory,
    InventoryFinding,
    LifecycleAction,
    Operation,
    OperationKind,
    Ownership,
    Plan,
    PreservationAssertion,
    RuntimeContext,
)


INVENTORY_BLOCKED_CODE = "inventory_io_or_layout"


def build_inventory(context: RuntimeContext, adapters: object) -> Inventory:
    ordered_adapters = _ordered_adapters(adapters)
    candidates: list[Candidate] = []
    findings: list[InventoryFinding] = []
    adapter_versions: dict[str, str] = {}
    adapter_layouts: dict[str, str] = {}
    seen_candidate_ids: set[str] = set()

    for adapter in ordered_adapters:
        client = _adapter_client(adapter)
        adapter_versions[client] = _adapter_version(adapter)
        adapter_layouts[client] = _adapter_layout(adapter)
        try:
            adapter_candidates = adapter.inventory(context)
        except (OSError, ValueError) as exc:
            findings.append(InventoryFinding(client=client, code=INVENTORY_BLOCKED_CODE, message=str(exc)))
            continue
        for candidate in adapter_candidates:
            if candidate.candidate_id in seen_candidate_ids:
                raise ValueError("inventory_duplicate_candidate_id")
            seen_candidate_ids.add(candidate.candidate_id)
            candidates.append(candidate)

    inventory = Inventory(
        os_name=context.profile.os_name,
        home=str(context.profile.home.resolve(strict=False)),
        root_map=dict(sorted(root_map(context).items())),
        adapter_versions=dict(sorted(adapter_versions.items())),
        adapter_layouts=dict(sorted(adapter_layouts.items())),
        candidates=tuple(sorted(candidates, key=lambda candidate: (candidate.client, candidate.path, candidate.candidate_id))),
        findings=tuple(sorted(findings, key=lambda finding: (finding.client, finding.code, finding.message))),
    )
    return inventory.with_digest()


def build_plan(inventory: Inventory, context: RuntimeContext, adapters: object) -> Plan:
    _assert_inventory_matches_context(inventory, context)
    adapter_by_client = {adapter.client: adapter for adapter in _ordered_adapters(adapters)}
    current_versions = {client: _adapter_version(adapter) for client, adapter in adapter_by_client.items()}
    current_layouts = {client: _adapter_layout(adapter) for client, adapter in adapter_by_client.items()}
    if dict(sorted(current_layouts.items())) != dict(sorted(inventory.adapter_layouts.items())):
        raise ValueError("plan_inventory_layout_mismatch")
    if dict(sorted(current_versions.items())) != dict(sorted(inventory.adapter_versions.items())):
        raise ValueError("plan_inventory_adapter_version_mismatch")

    operations: list[Operation] = []
    operation_targets: set[str] = set()
    blocked_candidate_ids: list[str] = []
    dependencies: dict[str, tuple[str, ...]] = {}
    lifecycle_actions: list[LifecycleAction] = []
    preservation_assertions: list[PreservationAssertion] = []

    for candidate in inventory.candidates:
        if candidate.dependencies:
            dependencies[candidate.candidate_id] = tuple(sorted(candidate.dependencies))
        lifecycle_actions.extend(_candidate_lifecycle_actions(candidate))

        if candidate.ownership == Ownership.AMBIGUOUS:
            blocked_candidate_ids.append(candidate.candidate_id)
            continue
        if candidate.ownership == Ownership.PRESERVED:
            preservation_assertions.append(_preservation_assertion(candidate))
            continue
        if candidate.ownership != Ownership.PROVEN or candidate.proposed_action == "report_only":
            continue

        try:
            adapter = adapter_by_client[candidate.client]
        except KeyError as exc:
            raise ValueError("adapter_unknown_client") from exc
        compiled = adapter.compile(candidate, context)
        for raw_operation in compiled:
            operation = _complete_operation(raw_operation, candidate)
            target_key = operation.path
            if target_key in operation_targets:
                raise ValueError("plan_duplicate_operation_target")
            operation_targets.add(target_key)
            operations.append(operation)

    plan = Plan(
        inventory_digest=inventory.digest,
        os_name=inventory.os_name,
        home=inventory.home,
        root_map=dict(sorted(inventory.root_map.items())),
        adapter_versions=dict(sorted(inventory.adapter_versions.items())),
        adapter_layouts=dict(sorted(inventory.adapter_layouts.items())),
        operations=tuple(sorted(operations, key=lambda operation: (operation.path, operation.candidate_id or "", str(operation.kind)))),
        blocked_candidate_ids=tuple(sorted(blocked_candidate_ids)),
        dependencies=dict(sorted(dependencies.items())),
        lifecycle_actions=tuple(sorted(lifecycle_actions, key=lambda action: (action.candidate_id, action.action, action.target))),
        preservation_assertions=tuple(sorted(preservation_assertions, key=lambda assertion: (assertion.candidate_id, assertion.path))),
    )
    return plan.with_digest()


def validate_approval(plan: Plan, supplied: str) -> None:
    if plan.digest is None or supplied != plan.digest:
        raise ValueError("plan_approval_mismatch")


def _assert_inventory_matches_context(inventory: Inventory, context: RuntimeContext) -> None:
    if inventory.home != str(context.profile.home.resolve(strict=False)):
        raise ValueError("plan_inventory_home_mismatch")
    if inventory.os_name != context.profile.os_name:
        raise ValueError("plan_inventory_os_mismatch")
    if dict(sorted(inventory.root_map.items())) != dict(sorted(root_map(context).items())):
        raise ValueError("plan_inventory_roots_mismatch")


def _complete_operation(operation: Operation, candidate: Candidate) -> Operation:
    path = operation.path or candidate.path
    candidate_id = operation.candidate_id or candidate.candidate_id
    completed = replace(operation, path=path, candidate_id=candidate_id)

    if _operation_kind(completed) in {OperationKind.WRITE_FILE, OperationKind.DELETE_FILE} and completed.preimage_base64 is None and completed.preimage_sha256 is None:
        completed = _embed_preimage(completed)
    else:
        _validate_embedded_image(completed.preimage_base64, completed.preimage_sha256, "plan_preimage_digest_mismatch")

    if _operation_kind(completed) == OperationKind.WRITE_FILE:
        if completed.postimage_base64 is None or completed.postimage_sha256 is None:
            raise ValueError("plan_write_file_missing_postimage")
        _validate_embedded_image(completed.postimage_base64, completed.postimage_sha256, "plan_postimage_digest_mismatch")
    return completed


def _embed_preimage(operation: Operation) -> Operation:
    path = Path(operation.path)
    if not path.is_file():
        return operation
    content = path.read_bytes()
    return replace(
        operation,
        preimage_base64=base64.b64encode(content).decode("ascii"),
        preimage_sha256=_sha256(content),
    )


def _validate_embedded_image(encoded: str | None, declared_digest: str | None, mismatch_code: str) -> None:
    if encoded is None and declared_digest is None:
        return
    if encoded is None or declared_digest is None:
        raise ValueError(mismatch_code)
    try:
        content = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("plan_invalid_embedded_image") from exc
    if _sha256(content) != declared_digest:
        raise ValueError(mismatch_code)


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _operation_kind(operation: Operation) -> OperationKind:
    return OperationKind(str(operation.kind))


def _preservation_assertion(candidate: Candidate) -> PreservationAssertion:
    return PreservationAssertion(
        candidate_id=candidate.candidate_id,
        client=candidate.client,
        path=candidate.path,
        reason=candidate.reason,
        evidence=tuple(candidate.evidence),
        details=dict(candidate.details),
    )


def _candidate_lifecycle_actions(candidate: Candidate) -> list[LifecycleAction]:
    raw_actions = candidate.details.get("lifecycle_actions")
    if not isinstance(raw_actions, Iterable) or isinstance(raw_actions, (str, bytes, dict)):
        return []
    actions: list[LifecycleAction] = []
    for item in raw_actions:
        if isinstance(item, LifecycleAction):
            actions.append(item)
        elif isinstance(item, Mapping):
            actions.append(
                LifecycleAction(
                    candidate_id=str(item.get("candidate_id", candidate.candidate_id)),
                    client=str(item.get("client", candidate.client)),
                    action=str(item.get("action", "")),
                    target=str(item.get("target", candidate.path)),
                    reason=str(item.get("reason", "")),
                    details=dict(item.get("details", {})) if isinstance(item.get("details", {}), Mapping) else {},
                )
            )
    return actions


def _ordered_adapters(adapters: object) -> tuple[object, ...]:
    if hasattr(adapters, "_adapters"):
        values = list(getattr(adapters, "_adapters").values())
    elif isinstance(adapters, Mapping):
        values = list(adapters.values())
    else:
        values = list(adapters)  # type: ignore[arg-type]
    seen: set[str] = set()
    for adapter in values:
        client = _adapter_client(adapter)
        if client in seen:
            raise ValueError("adapter_duplicate_client")
        seen.add(client)
    return tuple(sorted(values, key=_adapter_client))


def _adapter_client(adapter: object) -> str:
    client = getattr(adapter, "client", None)
    if not isinstance(client, str) or not client:
        raise ValueError("adapter_invalid_client")
    return client


def _adapter_version(adapter: object) -> str:
    value = getattr(adapter, "version", getattr(adapter, "VERSION", "unknown"))
    return str(value)


def _adapter_layout(adapter: object) -> str:
    value = getattr(adapter, "layout_version", getattr(adapter, "layout", "unknown"))
    return str(value)
