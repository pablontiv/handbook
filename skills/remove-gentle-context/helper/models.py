from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Sequence, Tuple


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
class Plan: ...
@dataclass(frozen=True)
class Check: ...
@dataclass(frozen=True)
class BackupManifest: ...
@dataclass(frozen=True)
class OperationOutcome: ...
@dataclass(frozen=True)
class CompletedCommand: ...
@dataclass(frozen=True)
class ProcessSnapshot: ...
@dataclass(frozen=True)
class LifecycleOutcome: ...
@dataclass(frozen=True)
class VerificationResult: ...
@dataclass(frozen=True)
class Receipt: ...
