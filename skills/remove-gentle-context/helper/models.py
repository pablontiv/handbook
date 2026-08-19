from __future__ import annotations

from dataclasses import dataclass, field
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


# Minimal placeholders for required exports
@dataclass(frozen=True)
class Operation: ...
@dataclass(frozen=True)
class LifecycleAction: ...
@dataclass(frozen=True)
class PreservationAssertion: ...
@dataclass(frozen=True)
class Inventory: ...
@dataclass(frozen=True)
class Plan:
    digest: str | None = None

    def to_unsigned_dict(self) -> dict[str, object]:
        return {}

    def to_dict(self) -> dict[str, object]:
        data = self.to_unsigned_dict()
        if self.digest is not None:
            data["digest"] = self.digest
        return data

    def with_digest(self) -> "Plan":
        return Plan(digest=digest_json(self.to_unsigned_dict()))


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
