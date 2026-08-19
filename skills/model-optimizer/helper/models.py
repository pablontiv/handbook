from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class RuntimeKind(StrEnum):
    PI = "pi"
    OPENCODE = "opencode"


class ReadinessStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    UNKNOWN = "unknown"


class HealthStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    HANG = "HANG"


@dataclass(frozen=True)
class RuntimeInfo:
    kind: RuntimeKind
    version: str
    cwd: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "version": self.version,
            "cwd": self.cwd,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RuntimeInfo":
        return cls(
            kind=RuntimeKind(value["kind"]),
            version=value["version"],
            cwd=value["cwd"],
        )


@dataclass(frozen=True)
class CurrentAssignment:
    agent: str
    model: str
    options: Mapping[str, Any]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "model": self.model,
            "options": dict(self.options),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CurrentAssignment":
        return cls(
            agent=value["agent"],
            model=value["model"],
            options=dict(value.get("options", {})),
            source=value["source"],
        )


@dataclass(frozen=True)
class ModelRecord:
    exact_id: str
    provider: str
    model: str
    family: str | None = None
    context_window: int | None = None
    max_output: int | None = None
    reasoning: bool | None = None
    input_modes: tuple[str, ...] = ()
    tool_call: bool | None = None
    cache_read: float | None = None
    cache_write: float | None = None
    input_cost: float | None = None
    output_cost: float | None = None
    variants: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "exact_id": self.exact_id,
            "provider": self.provider,
            "model": self.model,
            "family": self.family,
            "context_window": self.context_window,
            "max_output": self.max_output,
            "reasoning": self.reasoning,
            "input_modes": list(self.input_modes),
            "tool_call": self.tool_call,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
            "input_cost": self.input_cost,
            "output_cost": self.output_cost,
            "variants": list(self.variants),
            "provenance": list(self.provenance),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ModelRecord":
        return cls(
            exact_id=value["exact_id"],
            provider=value["provider"],
            model=value["model"],
            family=value.get("family"),
            context_window=value.get("context_window"),
            max_output=value.get("max_output"),
            reasoning=value.get("reasoning"),
            input_modes=tuple(value.get("input_modes", ())),
            tool_call=value.get("tool_call"),
            cache_read=value.get("cache_read"),
            cache_write=value.get("cache_write"),
            input_cost=value.get("input_cost"),
            output_cost=value.get("output_cost"),
            variants=tuple(value.get("variants", ())),
            provenance=tuple(value.get("provenance", ())),
        )


@dataclass(frozen=True)
class ProviderReadiness:
    provider: str
    status: ReadinessStatus
    auth_type: str | None
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status.value,
            "auth_type": self.auth_type,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProviderReadiness":
        return cls(
            provider=value["provider"],
            status=ReadinessStatus(value["status"]),
            auth_type=value.get("auth_type"),
            reason_code=value["reason_code"],
        )


@dataclass(frozen=True)
class Exclusion:
    subject: str
    reason_code: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "reason_code": self.reason_code,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Exclusion":
        return cls(
            subject=value["subject"],
            reason_code=value["reason_code"],
            detail=value.get("detail", ""),
        )


@dataclass(frozen=True)
class Inventory:
    schema: str
    created_at: str
    runtime: RuntimeInfo
    sources: tuple[str, ...]
    current_assignments: tuple[CurrentAssignment, ...]
    catalog_local: tuple[ModelRecord, ...]
    provider_readiness: tuple[ProviderReadiness, ...]
    exclusions: tuple[Exclusion, ...]
    warnings: tuple[str, ...]
    digest: str

    @classmethod
    def empty(cls, runtime: RuntimeInfo) -> "Inventory":
        from helper.artifacts import inventory_with_digest
        return inventory_with_digest(cls(
            schema="model-optimizer.inventory/v1",
            created_at="1970-01-01T00:00:00Z",
            runtime=runtime,
            sources=(), current_assignments=(), catalog_local=(),
            provider_readiness=(), exclusions=(), warnings=(), digest="",
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "created_at": self.created_at,
            "runtime": self.runtime.to_dict(),
            "sources": list(self.sources),
            "current_assignments": [assignment.to_dict() for assignment in self.current_assignments],
            "catalog_local": [record.to_dict() for record in self.catalog_local],
            "provider_readiness": [readiness.to_dict() for readiness in self.provider_readiness],
            "exclusions": [exclusion.to_dict() for exclusion in self.exclusions],
            "warnings": list(self.warnings),
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Inventory":
        if value.get("schema") != "model-optimizer.inventory/v1":
            raise ValueError("artifact_unknown_schema")
        return cls(
            schema=value["schema"],
            created_at=value["created_at"],
            runtime=RuntimeInfo.from_dict(value["runtime"]),
            sources=tuple(value.get("sources", ())),
            current_assignments=tuple(
                CurrentAssignment.from_dict(assignment)
                for assignment in value.get("current_assignments", ())
            ),
            catalog_local=tuple(
                ModelRecord.from_dict(record)
                for record in value.get("catalog_local", ())
            ),
            provider_readiness=tuple(
                ProviderReadiness.from_dict(readiness)
                for readiness in value.get("provider_readiness", ())
            ),
            exclusions=tuple(
                Exclusion.from_dict(exclusion)
                for exclusion in value.get("exclusions", ())
            ),
            warnings=tuple(value.get("warnings", ())),
            digest=value["digest"],
        )


@dataclass(frozen=True)
class HealthCheck:
    model: str
    effort: str | None
    status: HealthStatus
    elapsed_ms: int
    reason_code: str
    response_matched: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "effort": self.effort,
            "status": self.status.value,
            "elapsed_ms": self.elapsed_ms,
            "reason_code": self.reason_code,
            "response_matched": self.response_matched,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HealthCheck":
        return cls(
            model=value["model"],
            effort=value.get("effort"),
            status=HealthStatus(value["status"]),
            elapsed_ms=value["elapsed_ms"],
            reason_code=value["reason_code"],
            response_matched=value["response_matched"],
            detail=value["detail"],
        )


@dataclass(frozen=True)
class HealthArtifact:
    schema: str
    created_at: str
    inventory_digest: str
    checks: tuple[HealthCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "created_at": self.created_at,
            "inventory_digest": self.inventory_digest,
            "checks": [check.to_dict() for check in self.checks],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HealthArtifact":
        if value.get("schema") != "model-optimizer.health/v1":
            raise ValueError("artifact_unknown_schema")
        return cls(
            schema=value["schema"],
            created_at=value["created_at"],
            inventory_digest=value["inventory_digest"],
            checks=tuple(HealthCheck.from_dict(check) for check in value.get("checks", ())),
        )
