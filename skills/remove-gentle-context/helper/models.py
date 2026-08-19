from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Sequence

from .canonical import digest_json


class ArtifactClass(StrEnum):
    ACTIVE_SOURCE = "active-source"
    RUNTIME_STATE = "runtime-state"
    GENERATED_ARTIFACT = "generated-artifact"
    BROKEN_REGISTRATION = "broken-registration"
    HISTORICAL = "historical"
    PRESERVED_INFRASTRUCTURE = "preserved-infrastructure"
    AMBIGUOUS = "ambiguous"


class Ownership(StrEnum):
    PROVEN = "proven"
    AMBIGUOUS = "ambiguous"
    PRESERVED = "preserved"


class OperationKind(StrEnum):
    WRITE_FILE = "write_file"
    DELETE_FILE = "delete_file"
    REMOVE_EMPTY_DIRECTORY = "remove_empty_directory"


class ReceiptStatus(StrEnum):
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    MANUAL_RECOVERY_REQUIRED = "manual_recovery_required"
    FAILED = "failed"


@dataclass(frozen=True)
class PlatformProfile:
    os_name: str
    home: Path
    env: Mapping[str, str]


@dataclass(frozen=True)
class RuntimeContext:
    profile: PlatformProfile


@dataclass(frozen=True)
class Preimage:
    path: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path}


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    client: str
    path: str
    artifact_class: ArtifactClass
    evidence: Sequence[object]
    ownership: Ownership
    proposed_action: str
    preimage: Preimage | None
    dependencies: Sequence[str]
    reason: str
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "client": self.client,
            "path": self.path,
            "artifact_class": str(self.artifact_class),
            "evidence": list(self.evidence),
            "ownership": str(self.ownership),
            "proposed_action": self.proposed_action,
            "preimage": None if self.preimage is None else self.preimage.to_dict(),
            "dependencies": list(self.dependencies),
            "reason": self.reason,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class Operation:
    kind: OperationKind = OperationKind.DELETE_FILE
    path: str = ""
    candidate_id: str | None = None
    preimage_base64: str | None = None
    preimage_sha256: str | None = None
    postimage_base64: str | None = None
    postimage_sha256: str | None = None
    dependencies: Sequence[str] = ()
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "kind": str(self.kind),
            "path": self.path,
        }
        if self.candidate_id is not None:
            data["candidate_id"] = self.candidate_id
        if self.preimage_base64 is not None:
            data["preimage_base64"] = self.preimage_base64
        if self.preimage_sha256 is not None:
            data["preimage_sha256"] = self.preimage_sha256
        if self.postimage_base64 is not None:
            data["postimage_base64"] = self.postimage_base64
        if self.postimage_sha256 is not None:
            data["postimage_sha256"] = self.postimage_sha256
        if self.dependencies:
            data["dependencies"] = list(self.dependencies)
        if self.details:
            data["details"] = dict(self.details)
        return data


@dataclass(frozen=True)
class LifecycleAction:
    candidate_id: str = ""
    client: str = ""
    action: str = ""
    target: str = ""
    reason: str = ""
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.candidate_id:
            data["candidate_id"] = self.candidate_id
        if self.client:
            data["client"] = self.client
        if self.action:
            data["action"] = self.action
        if self.target:
            data["target"] = self.target
        if self.reason:
            data["reason"] = self.reason
        if self.details:
            data["details"] = dict(self.details)
        return data


@dataclass(frozen=True)
class PreservationAssertion:
    candidate_id: str = ""
    client: str = ""
    path: str = ""
    reason: str = ""
    evidence: Sequence[object] = ()
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.candidate_id:
            data["candidate_id"] = self.candidate_id
        if self.client:
            data["client"] = self.client
        if self.path:
            data["path"] = self.path
        if self.reason:
            data["reason"] = self.reason
        if self.evidence:
            data["evidence"] = list(self.evidence)
        if self.details:
            data["details"] = dict(self.details)
        return data


@dataclass(frozen=True)
class InventoryFinding:
    client: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"client": self.client, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class Inventory:
    os_name: str = ""
    home: str = ""
    adapter_versions: Mapping[str, str] = field(default_factory=dict)
    adapter_layouts: Mapping[str, str] = field(default_factory=dict)
    candidates: tuple[Candidate, ...] = ()
    findings: tuple[InventoryFinding, ...] = ()
    digest: str | None = None

    def to_unsigned_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.os_name:
            data["os_name"] = self.os_name
        if self.home:
            data["home"] = self.home
        if self.adapter_versions:
            data["adapter_versions"] = dict(self.adapter_versions)
        if self.adapter_layouts:
            data["adapter_layouts"] = dict(self.adapter_layouts)
        if self.candidates:
            data["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        if self.findings:
            data["findings"] = [finding.to_dict() for finding in self.findings]
        return data

    def to_dict(self) -> dict[str, object]:
        data = self.to_unsigned_dict()
        if self.digest is not None:
            data["digest"] = self.digest
        return data

    def with_digest(self) -> "Inventory":
        return replace(self, digest=digest_json(self.to_unsigned_dict()))


@dataclass(frozen=True)
class Plan:
    inventory_digest: str | None = None
    os_name: str = ""
    home: str = ""
    adapter_versions: Mapping[str, str] = field(default_factory=dict)
    adapter_layouts: Mapping[str, str] = field(default_factory=dict)
    operations: tuple[Operation, ...] = ()
    blocked_candidate_ids: tuple[str, ...] = ()
    dependencies: Mapping[str, Sequence[str]] = field(default_factory=dict)
    lifecycle_actions: tuple[LifecycleAction, ...] = ()
    preservation_assertions: tuple[PreservationAssertion, ...] = ()
    digest: str | None = None

    def to_unsigned_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.inventory_digest is not None:
            data["inventory_digest"] = self.inventory_digest
        if self.os_name:
            data["os_name"] = self.os_name
        if self.home:
            data["home"] = self.home
        if self.adapter_versions:
            data["adapter_versions"] = dict(self.adapter_versions)
        if self.adapter_layouts:
            data["adapter_layouts"] = dict(self.adapter_layouts)
        if self.operations:
            data["operations"] = [operation.to_dict() for operation in self.operations]
        if self.blocked_candidate_ids:
            data["blocked_candidate_ids"] = list(self.blocked_candidate_ids)
        if self.dependencies:
            data["dependencies"] = {candidate_id: list(dependencies) for candidate_id, dependencies in self.dependencies.items()}
        if self.lifecycle_actions:
            data["lifecycle_actions"] = [action.to_dict() for action in self.lifecycle_actions]
        if self.preservation_assertions:
            data["preservation_assertions"] = [assertion.to_dict() for assertion in self.preservation_assertions]
        return data

    def to_dict(self) -> dict[str, object]:
        data = self.to_unsigned_dict()
        if self.digest is not None:
            data["digest"] = self.digest
        return data

    def with_digest(self) -> "Plan":
        return replace(self, digest=digest_json(self.to_unsigned_dict()))


@dataclass(frozen=True)
class Check:
    pass


@dataclass(frozen=True)
class BackupManifest:
    pass


@dataclass(frozen=True)
class OperationOutcome:
    pass


@dataclass(frozen=True)
class CompletedCommand:
    pass


@dataclass(frozen=True)
class ProcessSnapshot:
    pass


@dataclass(frozen=True)
class LifecycleOutcome:
    pass


@dataclass(frozen=True)
class VerificationResult:
    pass


@dataclass(frozen=True)
class Receipt:
    operation_outcomes: tuple[OperationOutcome, ...] = ()
    backup_manifest_path: Path | None = None
    lifecycle_outcomes: tuple[LifecycleOutcome, ...] = ()
    checks: tuple[Check, ...] = ()
    status: ReceiptStatus | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_outcomes": [o.__dict__ for o in self.operation_outcomes],
            "backup_manifest_path": None if self.backup_manifest_path is None else str(self.backup_manifest_path),
            "lifecycle_outcomes": [o.__dict__ for o in self.lifecycle_outcomes],
            "checks": [c.__dict__ for c in self.checks],
            "status": None if self.status is None else str(self.status),
        }
