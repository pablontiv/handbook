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
    project_roots: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        home = self.profile.home.expanduser().resolve(strict=False)
        normalized: list[Path] = []
        seen: set[str] = {str(home)}
        for raw_root in self.project_roots:
            root = Path(raw_root).expanduser().resolve(strict=False)
            key = str(root)
            if key in seen:
                raise ValueError("project_root_duplicate")
            seen.add(key)
            normalized.append(root)
        object.__setattr__(self, "project_roots", tuple(sorted(normalized, key=lambda path: str(path))))


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
    root_map: Mapping[str, str] = field(default_factory=dict)
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
        if self.root_map:
            data["root_map"] = dict(self.root_map)
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
    root_map: Mapping[str, str] = field(default_factory=dict)
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
        if self.root_map:
            data["root_map"] = dict(self.root_map)
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
    code: str = ""
    status: str = "passed"
    severity: str = "info"
    evidence: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "status": self.status,
            "severity": self.severity,
            "evidence": _json_safe(self.evidence),
        }


@dataclass(frozen=True)
class BackupEntry:
    operation_index: int
    kind: str
    original_path: str
    root_id: str
    relative_path: str
    target_type: str
    mode: int | None = None
    size: int | None = None
    sha256: str | None = None
    payload_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "operation_index": self.operation_index,
            "kind": self.kind,
            "original_path": self.original_path,
            "root_id": self.root_id,
            "relative_path": self.relative_path,
            "target_type": self.target_type,
        }
        if self.mode is not None:
            data["mode"] = self.mode
        if self.size is not None:
            data["size"] = self.size
        if self.sha256 is not None:
            data["sha256"] = self.sha256
        if self.payload_path is not None:
            data["payload_path"] = self.payload_path
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "BackupEntry":
        return cls(
            operation_index=int(data["operation_index"]),
            kind=str(data["kind"]),
            original_path=str(data["original_path"]),
            root_id=str(data["root_id"]),
            relative_path=str(data["relative_path"]),
            target_type=str(data["target_type"]),
            mode=None if "mode" not in data else int(data["mode"]),
            size=None if "size" not in data else int(data["size"]),
            sha256=None if data.get("sha256") is None else str(data["sha256"]),
            payload_path=None if data.get("payload_path") is None else str(data["payload_path"]),
        )


@dataclass(frozen=True)
class BackupManifest:
    path: Path
    root: Path
    plan_digest: str
    entries: tuple[BackupEntry, ...] = ()
    digest: str | None = None

    def to_unsigned_dict(self) -> dict[str, object]:
        return {
            "schema": "remove-gentle-context.backup/v1",
            "plan_digest": self.plan_digest,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def to_dict(self) -> dict[str, object]:
        data = self.to_unsigned_dict()
        if self.digest is not None:
            data["digest"] = self.digest
        return data

    def with_digest(self) -> "BackupManifest":
        return replace(self, digest=digest_json(self.to_unsigned_dict()))

    @classmethod
    def from_dict(cls, data: Mapping[str, object], path: Path) -> "BackupManifest":
        entries_data = data.get("entries", ())
        if not isinstance(entries_data, Sequence) or isinstance(entries_data, (str, bytes)):
            raise ValueError("manifest_invalid_entries")
        entries = tuple(BackupEntry.from_dict(item) for item in entries_data if isinstance(item, Mapping))
        if len(entries) != len(entries_data):
            raise ValueError("manifest_invalid_entries")
        return cls(
            path=path,
            root=path.parent,
            plan_digest=str(data["plan_digest"]),
            entries=entries,
            digest=None if data.get("digest") is None else str(data["digest"]),
        )


@dataclass(frozen=True)
class OperationOutcome:
    operation_index: int
    kind: str
    path: str
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "operation_index": self.operation_index,
            "kind": self.kind,
            "path": self.path,
            "status": self.status,
        }
        if self.error is not None:
            data["error"] = self.error
        return data


@dataclass(frozen=True)
class CompletedCommand:
    argv: tuple[str, ...] = ()
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class ProcessSnapshot:
    action: LifecycleAction = field(default_factory=LifecycleAction)
    platform: str = ""
    running: bool = False
    pid: int | None = None
    process_name: str = ""
    executable: str | None = None
    argv: tuple[str, ...] = ()
    bundle_id: str | None = None
    identity: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "action": self.action.to_dict(),
            "platform": self.platform,
            "running": self.running,
            "argv": list(self.argv),
            "details": dict(self.details),
        }
        if self.pid is not None:
            data["pid"] = self.pid
        if self.process_name:
            data["process_name"] = self.process_name
        if self.executable is not None:
            data["executable"] = self.executable
        if self.bundle_id is not None:
            data["bundle_id"] = self.bundle_id
        if self.identity is not None:
            data["identity"] = self.identity
        return data


@dataclass(frozen=True)
class LifecycleOutcome:
    action: str = ""
    client: str = ""
    target: str = ""
    status: str = ""
    code: str | None = None
    pid: int | None = None
    argv: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "action": self.action,
            "client": self.client,
            "target": self.target,
            "status": self.status,
            "argv": list(self.argv),
        }
        if self.code is not None:
            data["code"] = self.code
        if self.pid is not None:
            data["pid"] = self.pid
        return data


@dataclass(frozen=True)
class VerificationResult:
    status: str = "failed"
    checks: tuple[Check, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "checks": [check.to_dict() for check in self.checks],
            "status": self.status,
        }

    def to_json_bytes(self) -> bytes:
        return digestable_json_bytes(self.to_dict())


@dataclass(frozen=True)
class Receipt:
    operation_outcomes: tuple[OperationOutcome, ...] = ()
    backup_manifest_path: Path | None = None
    lifecycle_outcomes: tuple[LifecycleOutcome, ...] = ()
    checks: tuple[Check, ...] = ()
    status: ReceiptStatus | None = None
    plan: Plan | None = None
    inventory: Inventory | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_outcomes": [_to_dict(o) for o in self.operation_outcomes],
            "backup_manifest_path": None if self.backup_manifest_path is None else str(self.backup_manifest_path),
            "lifecycle_outcomes": [_to_dict(o) for o in self.lifecycle_outcomes],
            "checks": [c.to_dict() if hasattr(c, "to_dict") else _json_safe(getattr(c, "__dict__", {})) for c in self.checks],
            "status": None if self.status is None else str(self.status),
            "plan": None if self.plan is None else self.plan.to_dict(),
            "inventory": None if self.inventory is None else self.inventory.to_dict(),
        }


def digestable_json_bytes(value: object) -> bytes:
    from .canonical import canonical_bytes

    return canonical_bytes(_json_safe(value))


def _to_dict(value: object) -> dict[str, object]:
    if hasattr(value, "to_dict"):
        data = value.to_dict()  # type: ignore[no-any-return, attr-defined]
        return _json_safe(data) if isinstance(data, dict) else {"value": _json_safe(data)}
    raw = getattr(value, "__dict__", {})
    return _json_safe(raw) if isinstance(raw, dict) else {"value": _json_safe(raw)}


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
