from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import stat
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from helper.artifacts import digest_json, write_json_atomic
from helper.models import Inventory, RuntimeKind
from helper.optimizer import AgentContract, PermissionRule, RouteKey

_STATE_SCHEMA = "model-optimizer.state/v1"
_FRESH_SECONDS = 7 * 24 * 60 * 60
_MAX_STATE_BYTES = 1024 * 1024
_LOCK_TIMEOUT_SECONDS = 5.0
_LOCK_RETRY_SECONDS = 0.01
_TRANSACTION_LOCK_STRIPES = 64
_TRANSACTION_LOCKS = tuple(threading.Lock() for _ in range(_TRANSACTION_LOCK_STRIPES))

try:  # pragma: no cover - exercised on POSIX platforms by the transaction tests.
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback.
    fcntl = None  # type: ignore[assignment]

try:  # pragma: no cover - exercised only on Windows.
    import msvcrt
except ImportError:  # pragma: no cover - POSIX fallback.
    msvcrt = None  # type: ignore[assignment]


@dataclass(frozen=True)
class SemanticSnapshot:
    runtime_fingerprint: str
    model_fingerprints: Mapping[str, str]
    readiness_fingerprints: Mapping[str, str]
    assignment_fingerprints: Mapping[str, str]
    agent_fingerprints: Mapping[str, str]


@dataclass(frozen=True)
class EvaluationKey:
    route: RouteKey
    agent_digest: str
    tool_digest: str
    fixture_id: str
    fixture_version: str
    model_fingerprint: str


@dataclass(frozen=True)
class EvaluationSummary:
    key: EvaluationKey
    created_at: str
    success: bool
    role_score: float
    contract_success: bool
    elapsed_ms: int
    metered_cost: float | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkKey:
    route: RouteKey
    source_name: str
    benchmark: str
    benchmark_version: str
    evaluated_model_identity: str
    reasoning_mode: str | None


@dataclass(frozen=True)
class BenchmarkSummary:
    route: RouteKey
    identity: str
    source_name: str
    source_url: str
    benchmark: str
    benchmark_version: str
    harness_or_agent: str | None
    evaluated_model_identity: str
    reasoning_mode: str | None
    observed_at: str
    cached_at: str
    metric_name: str
    metric_value: float | None


@dataclass(frozen=True)
class OptimizerState:
    schema: str
    snapshot: SemanticSnapshot | None
    evaluations: tuple[EvaluationSummary, ...]
    benchmarks: tuple[BenchmarkSummary, ...]
    warnings: tuple[str, ...] = ()


class _StateLockError(Exception):
    def __init__(self, warning: str) -> None:
        super().__init__(warning)
        self.warning = warning


@dataclass(frozen=True)
class InventoryDelta:
    first_run: bool
    runtime_changed: bool
    new_models: tuple[str, ...]
    removed_models: tuple[str, ...]
    changed_models: tuple[str, ...]
    new_readiness: tuple[str, ...]
    removed_readiness: tuple[str, ...]
    changed_readiness: tuple[str, ...]
    new_agents: tuple[str, ...]
    removed_agents: tuple[str, ...]
    changed_agents: tuple[str, ...]
    new_assignments: tuple[str, ...]
    removed_assignments: tuple[str, ...]
    changed_assignments: tuple[str, ...]
    unassigned_agents: tuple[str, ...]
    missing_incumbents: tuple[str, ...]
    full_cartesian_required: bool = False

    @property
    def has_changes(self) -> bool:
        return any((
            self.first_run,
            self.runtime_changed,
            self.new_models,
            self.removed_models,
            self.changed_models,
            self.new_readiness,
            self.removed_readiness,
            self.changed_readiness,
            self.new_agents,
            self.removed_agents,
            self.changed_agents,
            self.new_assignments,
            self.removed_assignments,
            self.changed_assignments,
            self.unassigned_agents,
            self.missing_incumbents,
        ))


def state_path(environ: Mapping[str, str], home: Path, config_trees: Sequence[Path]) -> Path:
    cache_home_value = environ.get("XDG_CACHE_HOME")
    if cache_home_value:
        cache_home = Path(cache_home_value).expanduser()
        if not cache_home.is_absolute():
            raise ValueError("state_cache_home_not_absolute")
    else:
        cache_home = Path(home).expanduser() / ".cache"
    target = cache_home / "model-optimizer" / "state.json"
    resolved_target = _resolved(target)
    for tree in config_trees:
        if _is_relative_to(resolved_target, _resolved(tree)):
            raise ValueError("state_path_forbidden")
    return target


def semantic_snapshot(inventory: Inventory, agents: Sequence[AgentContract]) -> SemanticSnapshot:
    model_ids = frozenset(model.exact_id for model in inventory.catalog_local)
    return SemanticSnapshot(
        runtime_fingerprint=_fingerprint({
            "kind": inventory.runtime.kind.value,
            "version": inventory.runtime.version,
        }),
        model_fingerprints=dict(sorted(
            (model.exact_id, _fingerprint(_model_semantics(model.to_dict())))
            for model in inventory.catalog_local
        )),
        readiness_fingerprints=dict(sorted(
            (readiness.provider, _fingerprint({
                "provider": readiness.provider,
                "status": readiness.status.value,
                "reason_code": readiness.reason_code,
            }))
            for readiness in inventory.provider_readiness
        )),
        assignment_fingerprints=dict(sorted(
            (assignment.agent, _assignment_fingerprint(assignment.to_dict(), assignment.model not in model_ids))
            for assignment in inventory.current_assignments
        )),
        agent_fingerprints=dict(sorted(
            (agent.name, _fingerprint(_agent_semantics(agent)))
            for agent in agents
        )),
    )


def load_state(path: Path) -> OptimizerState:
    payload = _read_state_payload(path)
    if isinstance(payload, OptimizerState):
        return payload
    try:
        value = json.loads(payload.decode("utf-8"), parse_constant=_reject_json_constant)
    except UnicodeDecodeError:
        return _empty_state("state_invalid_encoding")
    except json.JSONDecodeError:
        return _empty_state("state_invalid_json")
    except ValueError as exc:
        if str(exc) == "state_invalid_number":
            return _empty_state("state_invalid_number")
        return _empty_state("state_invalid_json")
    if not isinstance(value, dict):
        return _empty_state("state_invalid_shape")
    try:
        if value.get("schema") != _STATE_SCHEMA:
            return _empty_state("state_unknown_schema")
        return _state_from_dict(value)
    except (KeyError, TypeError, ValueError, AttributeError):
        return _empty_state("state_invalid_shape")


def update_state(path: Path, transform: Callable[[OptimizerState], OptimizerState]) -> OptimizerState:
    thread_lock = _transaction_lock_for_target(path)
    try:
        with thread_lock, _process_file_lock(path):
            current = load_state(path)
            if "state_path_symlink" in current.warnings:
                return _transform_without_persisting(transform, current, "state_path_symlink")
            transformed = _sanitize_state(transform(current))
            transformed = replace(transformed, warnings=_merge_warnings(current.warnings, transformed.warnings))
            try:
                write_json_atomic(path, _state_to_dict(transformed))
            except (OSError, ValueError):
                return replace(transformed, warnings=_append_warning(transformed.warnings, "state_write_failed"))
            return transformed
    except _StateLockError as exc:
        return _transform_without_persisting(transform, _empty_state(exc.warning), exc.warning)


def inventory_delta(previous: SemanticSnapshot | None, current: SemanticSnapshot) -> InventoryDelta:
    current_unassigned = _unassigned_agents(current)
    current_missing = _missing_incumbents(current)
    if previous is None:
        return InventoryDelta(
            first_run=True,
            runtime_changed=False,
            new_models=tuple(sorted(current.model_fingerprints)),
            removed_models=(),
            changed_models=(),
            new_readiness=tuple(sorted(current.readiness_fingerprints)),
            removed_readiness=(),
            changed_readiness=(),
            new_agents=tuple(sorted(current.agent_fingerprints)),
            removed_agents=(),
            changed_agents=(),
            new_assignments=tuple(sorted(current.assignment_fingerprints)),
            removed_assignments=(),
            changed_assignments=(),
            unassigned_agents=current_unassigned,
            missing_incumbents=current_missing,
            full_cartesian_required=False,
        )
    return InventoryDelta(
        first_run=False,
        runtime_changed=previous.runtime_fingerprint != current.runtime_fingerprint,
        new_models=_added(previous.model_fingerprints, current.model_fingerprints),
        removed_models=_removed(previous.model_fingerprints, current.model_fingerprints),
        changed_models=_changed(previous.model_fingerprints, current.model_fingerprints),
        new_readiness=_added(previous.readiness_fingerprints, current.readiness_fingerprints),
        removed_readiness=_removed(previous.readiness_fingerprints, current.readiness_fingerprints),
        changed_readiness=_changed(previous.readiness_fingerprints, current.readiness_fingerprints),
        new_agents=_added(previous.agent_fingerprints, current.agent_fingerprints),
        removed_agents=_removed(previous.agent_fingerprints, current.agent_fingerprints),
        changed_agents=_changed(previous.agent_fingerprints, current.agent_fingerprints),
        new_assignments=_added(previous.assignment_fingerprints, current.assignment_fingerprints),
        removed_assignments=_removed(previous.assignment_fingerprints, current.assignment_fingerprints),
        changed_assignments=_changed(previous.assignment_fingerprints, current.assignment_fingerprints),
        unassigned_agents=current_unassigned,
        missing_incumbents=current_missing,
        full_cartesian_required=False,
    )


def fresh_evaluation(state: OptimizerState, key: EvaluationKey, now: datetime) -> EvaluationSummary | None:
    for summary in state.evaluations:
        if summary.key == key and _is_fresh(summary.created_at, now):
            return summary
    return None


def fresh_benchmark(state: OptimizerState, key: BenchmarkKey, now: datetime) -> BenchmarkSummary | None:
    for summary in state.benchmarks:
        if _benchmark_key(summary) == key and _is_fresh(summary.cached_at, now):
            return summary
    return None


def _empty_state(warning: str | None = None) -> OptimizerState:
    return OptimizerState(
        schema=_STATE_SCHEMA,
        snapshot=None,
        evaluations=(),
        benchmarks=(),
        warnings=(warning,) if warning else (),
    )


def _read_state_payload(path: Path) -> bytes | OptimizerState:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return _empty_state()
    except OSError:
        return _empty_state("state_read_failed")
    if stat.S_ISLNK(info.st_mode):
        return _empty_state("state_path_symlink")
    if _has_unsafe_posix_permissions(info.st_mode):
        return _empty_state("state_unsafe_permissions")
    if info.st_size > _MAX_STATE_BYTES:
        return _empty_state("state_file_too_large")
    try:
        payload = path.read_bytes()
    except OSError:
        return _empty_state("state_read_failed")
    if len(payload) > _MAX_STATE_BYTES:
        return _empty_state("state_file_too_large")
    return payload


def _has_unsafe_posix_permissions(mode: int) -> bool:
    if os.name == "nt":
        return False
    return bool(stat.S_IMODE(mode) & (stat.S_IRWXG | stat.S_IRWXO))


def _transform_without_persisting(
    transform: Callable[[OptimizerState], OptimizerState],
    state: OptimizerState,
    warning: str,
) -> OptimizerState:
    transformed = _sanitize_state(transform(state))
    return replace(transformed, warnings=_append_warning(_merge_warnings(state.warnings, transformed.warnings), warning))


def _state_to_dict(state: OptimizerState) -> dict[str, Any]:
    return {
        "schema": state.schema,
        "snapshot": _snapshot_to_dict(state.snapshot) if state.snapshot is not None else None,
        "evaluations": [_evaluation_summary_to_dict(summary) for summary in state.evaluations],
        "benchmarks": [_benchmark_summary_to_dict(summary) for summary in state.benchmarks],
        "warnings": list(state.warnings),
    }


def _state_from_dict(value: Mapping[str, Any]) -> OptimizerState:
    snapshot_value = value.get("snapshot")
    return OptimizerState(
        schema=_expect_string(value["schema"]),
        snapshot=_snapshot_from_dict(snapshot_value) if snapshot_value is not None else None,
        evaluations=tuple(_evaluation_summary_from_dict(item) for item in _expect_list(value.get("evaluations", []))),
        benchmarks=tuple(_benchmark_summary_from_dict(item) for item in _expect_list(value.get("benchmarks", []))),
        warnings=tuple(_expect_string(item) for item in _expect_list(value.get("warnings", []))),
    )


def _snapshot_to_dict(snapshot: SemanticSnapshot) -> dict[str, Any]:
    return {
        "runtime_fingerprint": snapshot.runtime_fingerprint,
        "model_fingerprints": dict(sorted(snapshot.model_fingerprints.items())),
        "readiness_fingerprints": dict(sorted(snapshot.readiness_fingerprints.items())),
        "assignment_fingerprints": dict(sorted(snapshot.assignment_fingerprints.items())),
        "agent_fingerprints": dict(sorted(snapshot.agent_fingerprints.items())),
    }


def _snapshot_from_dict(value: Any) -> SemanticSnapshot:
    if not isinstance(value, Mapping):
        raise ValueError("state_invalid_shape")
    return SemanticSnapshot(
        runtime_fingerprint=_expect_string(value["runtime_fingerprint"]),
        model_fingerprints=_string_mapping(value["model_fingerprints"]),
        readiness_fingerprints=_string_mapping(value["readiness_fingerprints"]),
        assignment_fingerprints=_string_mapping(value["assignment_fingerprints"]),
        agent_fingerprints=_string_mapping(value["agent_fingerprints"]),
    )


def _evaluation_summary_to_dict(summary: EvaluationSummary) -> dict[str, Any]:
    return {
        "key": _evaluation_key_to_dict(summary.key),
        "created_at": summary.created_at,
        "success": summary.success,
        "role_score": summary.role_score,
        "contract_success": summary.contract_success,
        "elapsed_ms": summary.elapsed_ms,
        "metered_cost": summary.metered_cost,
        "reason_codes": list(summary.reason_codes),
    }


def _evaluation_summary_from_dict(value: Any) -> EvaluationSummary:
    if not isinstance(value, Mapping):
        raise ValueError("state_invalid_shape")
    return EvaluationSummary(
        key=_evaluation_key_from_dict(value["key"]),
        created_at=_expect_string(value["created_at"]),
        success=_expect_bool(value["success"]),
        role_score=_expect_number(value["role_score"]),
        contract_success=_expect_bool(value["contract_success"]),
        elapsed_ms=_expect_int(value["elapsed_ms"]),
        metered_cost=_expect_optional_number(value.get("metered_cost")),
        reason_codes=tuple(_expect_string(item) for item in _expect_list(value.get("reason_codes", []))),
    )


def _benchmark_summary_to_dict(summary: BenchmarkSummary) -> dict[str, Any]:
    return {
        "route": _route_to_dict(summary.route),
        "identity": summary.identity,
        "source_name": summary.source_name,
        "source_url": _sanitize_url(summary.source_url),
        "benchmark": summary.benchmark,
        "benchmark_version": summary.benchmark_version,
        "harness_or_agent": summary.harness_or_agent,
        "evaluated_model_identity": summary.evaluated_model_identity,
        "reasoning_mode": summary.reasoning_mode,
        "observed_at": summary.observed_at,
        "cached_at": summary.cached_at,
        "metric_name": summary.metric_name,
        "metric_value": summary.metric_value,
    }


def _benchmark_summary_from_dict(value: Any) -> BenchmarkSummary:
    if not isinstance(value, Mapping):
        raise ValueError("state_invalid_shape")
    return BenchmarkSummary(
        route=_route_from_dict(value["route"]),
        identity=_expect_string(value["identity"]),
        source_name=_expect_string(value["source_name"]),
        source_url=_sanitize_url(_expect_string(value.get("source_url", ""))),
        benchmark=_expect_string(value["benchmark"]),
        benchmark_version=_expect_string(value["benchmark_version"]),
        harness_or_agent=_expect_optional_string(value.get("harness_or_agent")),
        evaluated_model_identity=_expect_string(value["evaluated_model_identity"]),
        reasoning_mode=_expect_optional_string(value.get("reasoning_mode")),
        observed_at=_expect_string(value["observed_at"]),
        cached_at=_expect_string(value["cached_at"]),
        metric_name=_expect_string(value["metric_name"]),
        metric_value=_expect_optional_number(value.get("metric_value")),
    )


def _evaluation_key_to_dict(key: EvaluationKey) -> dict[str, Any]:
    return {
        "route": _route_to_dict(key.route),
        "agent_digest": key.agent_digest,
        "tool_digest": key.tool_digest,
        "fixture_id": key.fixture_id,
        "fixture_version": key.fixture_version,
        "model_fingerprint": key.model_fingerprint,
    }


def _evaluation_key_from_dict(value: Any) -> EvaluationKey:
    if not isinstance(value, Mapping):
        raise ValueError("state_invalid_shape")
    return EvaluationKey(
        route=_route_from_dict(value["route"]),
        agent_digest=_expect_string(value["agent_digest"]),
        tool_digest=_expect_string(value["tool_digest"]),
        fixture_id=_expect_string(value["fixture_id"]),
        fixture_version=_expect_string(value["fixture_version"]),
        model_fingerprint=_expect_string(value["model_fingerprint"]),
    )


def _benchmark_key(summary: BenchmarkSummary) -> BenchmarkKey:
    return BenchmarkKey(
        route=summary.route,
        source_name=summary.source_name,
        benchmark=summary.benchmark,
        benchmark_version=summary.benchmark_version,
        evaluated_model_identity=summary.evaluated_model_identity,
        reasoning_mode=summary.reasoning_mode,
    )


def _route_to_dict(route: RouteKey) -> dict[str, Any]:
    return {
        "runtime_kind": route.runtime_kind.value,
        "runtime_version": route.runtime_version,
        "model": route.model,
        "effort": route.effort,
    }


def _route_from_dict(value: Any) -> RouteKey:
    if not isinstance(value, Mapping):
        raise ValueError("state_invalid_shape")
    return RouteKey(
        runtime_kind=RuntimeKind(_expect_string(value["runtime_kind"])),
        runtime_version=_expect_string(value["runtime_version"]),
        model=_expect_string(value["model"]),
        effort=_expect_optional_string(value.get("effort")),
    )


def _sanitize_state(state: OptimizerState) -> OptimizerState:
    return OptimizerState(
        schema=state.schema,
        snapshot=state.snapshot,
        evaluations=tuple(state.evaluations),
        benchmarks=tuple(replace(summary, source_url=_sanitize_url(summary.source_url)) for summary in state.benchmarks),
        warnings=tuple(state.warnings),
    )


def _sanitize_url(url: str) -> str:
    if not url:
        return url
    parts = urlsplit(url)
    if not parts.query and not parts.fragment:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _model_semantics(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    for key in ("input_modes", "variants", "provenance"):
        result[key] = sorted(str(item) for item in result.get(key, ()))
    return result


def _agent_semantics(agent: AgentContract) -> dict[str, Any]:
    return {
        "name": agent.name,
        "description_digest": _text_digest(agent.description),
        "mode": agent.mode,
        "model": agent.model,
        "effort": agent.effort,
        "tools": sorted(agent.tools),
        "permissions": sorted(_permission_to_tuple(rule) for rule in agent.permissions),
        "mutation_authority": agent.mutation_authority,
        "body_digest": _text_digest(agent.body),
        "scope": agent.scope,
        "definition_source_digest": _text_digest(agent.definition_source),
        "assignment_source_digest": _text_digest(agent.assignment_source or ""),
        "inheritance_source_digests": sorted(_text_digest(source) for source in agent.inheritance_sources),
        "apply_target_digest": _text_digest(agent.apply_target or ""),
    }


def _permission_to_tuple(rule: PermissionRule) -> tuple[str, str, str]:
    return (rule.capability, rule.pattern, rule.action)


def _assignment_fingerprint(value: Mapping[str, Any], missing_model: bool) -> str:
    digest = _fingerprint({
        "agent": value["agent"],
        "model": value["model"],
        "options": _normalize_json(value.get("options", {})),
        "source_digest": _text_digest(value.get("source", "")),
        "missing_model": missing_model,
    })
    return f"{digest}:missing" if missing_model else digest


def _fingerprint(value: Any) -> str:
    return digest_json(_normalize_json(value))


def _text_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_json(value[key]) for key in sorted(value.keys(), key=str)}
    if isinstance(value, tuple):
        return [_normalize_json(item) for item in value]
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    return value


def _added(previous: Mapping[str, str], current: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(sorted(set(current) - set(previous)))


def _removed(previous: Mapping[str, str], current: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(sorted(set(previous) - set(current)))


def _changed(previous: Mapping[str, str], current: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(sorted(key for key in set(previous) & set(current) if previous[key] != current[key]))


def _unassigned_agents(snapshot: SemanticSnapshot) -> tuple[str, ...]:
    return tuple(sorted(set(snapshot.agent_fingerprints) - set(snapshot.assignment_fingerprints)))


def _missing_incumbents(snapshot: SemanticSnapshot) -> tuple[str, ...]:
    return tuple(sorted(agent for agent, fingerprint in snapshot.assignment_fingerprints.items() if fingerprint.endswith(":missing")))


def _is_fresh(timestamp: str, now: datetime) -> bool:
    created = _parse_timestamp(timestamp)
    if created is None:
        return False
    comparable_now = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    return (comparable_now.astimezone(timezone.utc) - created).total_seconds() < _FRESH_SECONDS


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _reject_json_constant(_constant: str) -> None:
    raise ValueError("state_invalid_number")


def _expect_string(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("state_invalid_shape")
    return value


def _expect_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return _expect_string(value)


def _expect_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("state_invalid_shape")
    return value


def _expect_int(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("state_invalid_shape")
    return value


def _expect_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("state_invalid_shape")
    return float(value)


def _expect_optional_number(value: Any) -> float | None:
    if value is None:
        return None
    return _expect_number(value)


def _expect_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("state_invalid_shape")
    return value


def _string_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("state_invalid_shape")
    return {str(_expect_string(key)): _expect_string(item) for key, item in value.items()}


def _append_warning(warnings: tuple[str, ...], warning: str) -> tuple[str, ...]:
    if warning in warnings:
        return warnings
    return warnings + (warning,)


def _merge_warnings(*warning_groups: tuple[str, ...]) -> tuple[str, ...]:
    merged: tuple[str, ...] = ()
    for warnings in warning_groups:
        for warning in warnings:
            merged = _append_warning(merged, warning)
    return merged


@contextlib.contextmanager
def _process_file_lock(path: Path) -> Iterator[None]:
    backend = _lock_backend()
    if backend is None:
        raise _StateLockError("state_lock_unsupported")
    lock_path = Path(f"{path}.lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            _prepare_lock_file(handle, backend)
            if not _acquire_portable_lock(handle, backend, time.monotonic() + _LOCK_TIMEOUT_SECONDS):
                raise _StateLockError("state_lock_timeout")
            try:
                yield
            finally:
                _release_portable_lock(handle, backend)
    except _StateLockError:
        raise
    except OSError:
        raise _StateLockError("state_lock_failed") from None


def _lock_backend() -> str | None:
    if fcntl is not None:
        return "fcntl"
    if msvcrt is not None:
        return "msvcrt"
    return None


def _prepare_lock_file(handle: Any, backend: str) -> None:
    if backend != "msvcrt":
        return
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)


def _acquire_portable_lock(handle: Any, backend: str, deadline: float) -> bool:
    while True:
        if _try_acquire_portable_lock(handle, backend):
            return True
        now = time.monotonic()
        if now >= deadline:
            return False
        time.sleep(min(_LOCK_RETRY_SECONDS, max(0.0, deadline - now)))


def _try_acquire_portable_lock(handle: Any, backend: str) -> bool:
    if backend == "fcntl":
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                return False
            raise
    if backend == "msvcrt":
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                return False
            raise
    raise _StateLockError("state_lock_unsupported")


def _release_portable_lock(handle: Any, backend: str) -> None:
    if backend == "fcntl":
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    if backend == "msvcrt":
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    raise _StateLockError("state_lock_unsupported")


def _transaction_lock_for_target(path: Path) -> threading.Lock:
    resolved = str(_resolved(path))
    digest = hashlib.blake2b(resolved.encode("utf-8"), digest_size=8).digest()
    stripe_index = int.from_bytes(digest, "big") % _TRANSACTION_LOCK_STRIPES
    return _TRANSACTION_LOCKS[stripe_index]


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
