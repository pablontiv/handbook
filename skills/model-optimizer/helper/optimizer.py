from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from helper.models import HealthCheck, HealthStatus, ModelRecord, RuntimeKind

_MAX_AGENT_DEFINITION_BYTES = 256 * 1024
_MAX_AGENT_FRONTMATTER_CHARS = 16 * 1024
_MAX_AGENT_BODY_CHARS = 65_536
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_PERMISSION_ACTIONS = frozenset({"allow", "ask", "deny"})


class IdentityMatch(StrEnum):
    EXACT = "EXACT"
    MODEL_EQUIVALENT = "MODEL_EQUIVALENT"
    FAMILY_PROXY = "FAMILY_PROXY"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


@dataclass(frozen=True)
class RouteKey:
    runtime_kind: RuntimeKind
    runtime_version: str
    model: str
    effort: str | None


@dataclass(frozen=True)
class PermissionRule:
    capability: str
    pattern: str
    action: str  # allow | ask | deny


@dataclass(frozen=True)
class AgentContract:
    name: str
    description: str
    mode: str | None
    model: str | None
    effort: str | None
    tools: tuple[str, ...]
    permissions: tuple[PermissionRule, ...]
    mutation_authority: str
    body: str
    scope: str
    definition_source: str
    assignment_source: str | None
    inheritance_sources: tuple[str, ...]
    apply_target: str | None
    digest: str


@dataclass(frozen=True)
class RoleRequirements:
    archetype: str
    required_tools: tuple[str, ...]
    essential_custom_tools: tuple[str, ...]
    requires_vision: bool
    requires_mutation: bool
    min_context: int | None
    min_output: int | None
    allowed_efforts: tuple[str, ...]
    structured_output: bool
    adversarial_against_family: str | None
    priority_order: tuple[str, ...]


@dataclass(frozen=True)
class RunObservation:
    run_id: str
    elapsed_ms: int
    reliable: bool
    intervention_count: int
    metered_cost: float | None


@dataclass(frozen=True)
class FixtureEvidence:
    fixture_id: str
    fixture_version: str
    success: bool
    role_score: float
    contract_success: bool
    runs: tuple[RunObservation, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CandidateEvidence:
    route: RouteKey
    model: ModelRecord
    health: HealthCheck
    identity: IdentityMatch
    fixtures: tuple[FixtureEvidence, ...]
    benchmark_score: float | None
    reliability_rate: float | None
    median_elapsed_ms: int | None
    metered_cost: float | None
    incumbent: bool = False
    infrastructure_status: str = "SAFE"
    infrastructure_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.infrastructure_status not in {"SAFE", "UNSAFE", "UNAVAILABLE", "INCONCLUSIVE"}:
            raise ValueError("candidate_infrastructure_status_invalid")
        if len(self.infrastructure_reasons) > 16 or any(not isinstance(reason, str) or not _SAFE_NAME_RE.fullmatch(reason) for reason in self.infrastructure_reasons):
            raise ValueError("candidate_infrastructure_reasons_invalid")


@dataclass(frozen=True)
class MappingDecision:
    status: str  # CHANGE | NO_CHANGE | NEEDS_MORE_EVIDENCE | ABSTAIN
    selected_route: RouteKey | None
    next_fixture: str | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkObservation:
    exact_id: str | None = None
    model: str | None = None
    family: str | None = None
    effort: str | None = None
    identity_unknown: bool = False


def parse_agent_definition(path: Path, *, scope: str, config_path: Path) -> AgentContract:
    raw = _read_bounded_definition(path)
    text = _decode_definition(raw)
    frontmatter, body = _split_frontmatter(text)
    parsed = _parse_frontmatter(frontmatter)
    name = _required_string(parsed, "name")
    description = _optional_string(parsed, "description") or ""
    tools = _normalize_tools(parsed.get("tools"))
    permissions = _normalize_permissions(parsed.get("permissions", parsed.get("permission")))
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    return AgentContract(
        name=name,
        description=description,
        mode=_optional_string(parsed, "mode"),
        model=_optional_string(parsed, "model"),
        effort=_optional_string(parsed, "variant") or _optional_string(parsed, "effort"),
        tools=tools,
        permissions=permissions,
        mutation_authority=_mutation_authority(tools, permissions),
        body=body,
        scope=scope,
        definition_source=f"{scope}:{path.name}",
        assignment_source=None,
        inheritance_sources=(),
        apply_target=str(config_path),
        digest=digest,
    )


def discover_agent_contracts(runtime: RuntimeKind, home: Path, cwd: Path, environ: Mapping[str, str]) -> tuple[AgentContract, ...]:
    if runtime is RuntimeKind.PI:
        return _discover_pi_agent_contracts(home, cwd, environ)
    if runtime is RuntimeKind.OPENCODE:
        return _discover_opencode_agent_contracts(home, cwd, environ)
    return ()


def classify_identity(runtime_route: RouteKey, observation: BenchmarkObservation | None, source_available: bool) -> IdentityMatch:
    if not source_available:
        return IdentityMatch.SOURCE_UNAVAILABLE
    if observation is None:
        return IdentityMatch.ABSENT
    if observation.identity_unknown:
        return IdentityMatch.UNKNOWN
    if observation.exact_id == runtime_route.model and (observation.effort is None or observation.effort == runtime_route.effort):
        return IdentityMatch.EXACT
    route_model = runtime_route.model.split("/", 1)[-1]
    observed_model = observation.model or (observation.exact_id.split("/", 1)[-1] if observation.exact_id else None)
    if observed_model and observed_model == route_model:
        return IdentityMatch.MODEL_EQUIVALENT
    route_family = _family_from_model_id(route_model)
    if observation.family and route_family and observation.family.lower() == route_family.lower():
        return IdentityMatch.FAMILY_PROXY
    return IdentityMatch.ABSENT


def gate_candidate(requirements: RoleRequirements, route: RouteKey, model: ModelRecord, health: HealthCheck) -> tuple[str, ...]:
    reasons: list[str] = []
    if route.model != model.exact_id or health.model != route.model:
        reasons.append("route_model_mismatch")
    if health.effort != route.effort:
        reasons.append("route_live_effort_mismatch")
    if health.status is not HealthStatus.PASS or not health.response_matched:
        reasons.append("route_live_unavailable")
    if route.effort is not None and (not model.variants or route.effort not in model.variants):
        reasons.append("unsupported_effort")
    if requirements.allowed_efforts and route.effort not in requirements.allowed_efforts:
        reasons.append("disallowed_effort")
    if requirements.requires_vision and "image" not in model.input_modes:
        reasons.append("required_vision_missing")
    if requirements.min_context is not None and (model.context_window is None or model.context_window < requirements.min_context):
        reasons.append("context_window_too_small")
    if requirements.min_output is not None and (model.max_output is None or model.max_output < requirements.min_output):
        reasons.append("max_output_too_small")
    if requirements.required_tools and model.tool_call is not True:
        reasons.append("required_tool_call_missing")
    if requirements.requires_mutation and model.tool_call is not True:
        reasons.append("required_mutation_missing")
    if requirements.essential_custom_tools:
        reasons.append("essential_custom_tools_unverified")
    if requirements.adversarial_against_family and model.family and model.family.lower() == requirements.adversarial_against_family.lower():
        reasons.append("adversarial_family_conflict")
    return tuple(reasons)


def shortlist_candidates(
    requirements: RoleRequirements,
    candidates: Sequence[CandidateEvidence],
    incumbent: RouteKey | None,
    limit: int = 4,
) -> tuple[CandidateEvidence, ...]:
    eligible = [
        candidate for candidate in candidates
        if not gate_candidate(requirements, candidate.route, candidate.model, candidate.health)
    ]
    selected: list[CandidateEvidence] = []
    if incumbent is not None:
        for candidate in eligible:
            if candidate.route == incumbent:
                selected.append(candidate)
                break
    challengers = [candidate for candidate in eligible if candidate.route != incumbent]
    challengers.sort(key=lambda candidate: _shortlist_sort_key(requirements, candidate))
    for candidate in challengers:
        if len(selected) >= max(0, limit):
            break
        selected.append(candidate)
    return tuple(selected[: max(0, limit)])


def choose_mapping(
    requirements: RoleRequirements,
    candidates: Sequence[CandidateEvidence],
    incumbent: RouteKey | None,
) -> MappingDecision:
    eligible = shortlist_candidates(requirements, candidates, incumbent, limit=len(candidates) or 1)
    unsafe_infrastructure = _unsafe_infrastructure_reasons(eligible)
    if unsafe_infrastructure:
        return MappingDecision("ABSTAIN", None, None, unsafe_infrastructure)
    if not eligible:
        return MappingDecision("ABSTAIN", None, None, ("no_eligible_candidates",))
    incumbent_candidate = next((candidate for candidate in eligible if incumbent is not None and candidate.route == incumbent), None)
    challengers = [candidate for candidate in eligible if incumbent is None or candidate.route != incumbent]
    if incumbent_candidate is None:
        best = _best_candidate_without_incumbent(requirements, challengers or list(eligible))
        return best
    needs_more_evidence = False
    for challenger in challengers:
        if _has_higher_mandatory_tier(challenger, incumbent_candidate):
            return MappingDecision("CHANGE", challenger.route, None, ("higher_mandatory_tier",))
        if _has_material_quality_advantage(challenger, incumbent_candidate):
            return MappingDecision("CHANGE", challenger.route, None, ("material_quality_advantage",))
        if _has_material_operational_advantage(requirements, challenger, incumbent_candidate):
            return MappingDecision("CHANGE", challenger.route, None, ("material_operational_advantage",))
        if _needs_more_pairwise_evidence(challenger, incumbent_candidate):
            needs_more_evidence = True
    if needs_more_evidence:
        return MappingDecision("NEEDS_MORE_EVIDENCE", incumbent_candidate.route, None, ("one_fixture_tie",))
    return MappingDecision("NO_CHANGE", incumbent_candidate.route, None, ("incumbent_retained",))


def _unsafe_infrastructure_reasons(candidates: Sequence[CandidateEvidence]) -> tuple[str, ...]:
    reasons: list[str] = []
    for candidate in candidates:
        if candidate.infrastructure_status == "SAFE" and not candidate.infrastructure_reasons:
            continue
        for reason in candidate.infrastructure_reasons or (candidate.infrastructure_status.lower(),):
            if reason not in reasons:
                reasons.append(reason)
    return tuple(reasons)


def _discover_pi_agent_contracts(home: Path, cwd: Path, environ: Mapping[str, str]) -> tuple[AgentContract, ...]:
    from helper.adapters.pi import pi_global_agent_dir, pi_project_subagents_path

    global_root = pi_global_agent_dir(home, environ)
    project_config = pi_project_subagents_path(cwd)
    assignments = _read_pi_assignments((
        ("global", global_root / "subagents.json"),
        ("project", project_config),
    ))
    by_name: dict[str, AgentContract] = {}
    for scope, directory, config_path in (
        ("global", global_root / "agents", global_root / "subagents.json"),
        ("global", global_root / "subagents", global_root / "subagents.json"),
        ("project", cwd / ".pi" / "agents", project_config),
        ("project", cwd / ".pi" / "subagents", project_config),
    ):
        for path in _markdown_files(directory):
            contract = parse_agent_definition(path, scope=scope, config_path=config_path)
            source = f"{scope}:{directory.name}/{path.name}"
            inherited = (by_name[contract.name].definition_source,) if contract.name in by_name else ()
            by_name[contract.name] = replace(contract, definition_source=source, inheritance_sources=inherited)
    for name, assignment in assignments.items():
        if name in by_name:
            contract = by_name[name]
            by_name[name] = replace(
                contract,
                model=_string_from_mapping(assignment["profile"], "model") or contract.model,
                effort=_string_from_mapping(assignment["profile"], "variant") or _string_from_mapping(assignment["profile"], "effort") or _string_from_mapping(assignment["profile"], "thinking") or contract.effort,
                assignment_source=assignment["source"],
                apply_target=str(assignment["path"]),
            )
        else:
            profile = assignment["profile"]
            by_name[name] = _contract_from_json_agent(
                name,
                profile,
                scope=str(assignment["scope"]),
                definition_source=f"{assignment['source']}#model_profiles.{name}",
                assignment_source=str(assignment["source"]),
                apply_target=str(assignment["path"]),
                inherited=(),
            )
    for contract in _pi_current_contracts(global_root, environ):
        inherited = (by_name[contract.name].definition_source,) if contract.name in by_name else ()
        by_name[contract.name] = replace(contract, inheritance_sources=inherited)
    return tuple(by_name[name] for name in sorted(by_name))


def _discover_opencode_agent_contracts(home: Path, cwd: Path, environ: Mapping[str, str]) -> tuple[AgentContract, ...]:
    from helper.adapters.opencode import opencode_global_config_dir, opencode_project_config_path

    global_root = opencode_global_config_dir(home, environ)
    global_config = global_root / "opencode.json"
    project_config = opencode_project_config_path(cwd)
    by_name: dict[str, AgentContract] = {}
    for scope, directory, config_path in (
        ("global", global_root / "agents", global_config),
        ("project", cwd / ".opencode" / "agents", project_config),
    ):
        for path in _markdown_files(directory):
            contract = parse_agent_definition(path, scope=scope, config_path=config_path)
            source = f"{scope}:agents/{path.name}"
            inherited = (by_name[contract.name].definition_source,) if contract.name in by_name else ()
            by_name[contract.name] = replace(contract, definition_source=source, inheritance_sources=inherited)
    for scope, path in (("global", global_config), ("project", project_config)):
        for name, config in _read_opencode_agents(path):
            source = f"{scope}:opencode.json#agent.{name}"
            inherited = (by_name[name].definition_source,) if name in by_name else ()
            if name in by_name:
                contract = by_name[name]
                if scope == "project" and contract.definition_source.startswith("global:opencode.json#"):
                    by_name[name] = _contract_from_json_agent(
                        name,
                        config,
                        scope=scope,
                        definition_source=source,
                        assignment_source=source if _string_from_mapping(config, "model") else None,
                        apply_target=str(path),
                        inherited=inherited,
                    )
                    continue
                tools = _normalize_tools(config.get("tools")) if "tools" in config else contract.tools
                permissions = _normalize_permissions(config.get("permission", config.get("permissions"))) if ("permission" in config or "permissions" in config) else contract.permissions
                by_name[name] = replace(
                    contract,
                    scope=scope if scope == "project" else contract.scope,
                    definition_source=source if contract.definition_source.startswith("global:opencode.json#") else contract.definition_source,
                    description=_string_from_mapping(config, "description") or contract.description,
                    mode=_string_from_mapping(config, "mode") or contract.mode,
                    model=_string_from_mapping(config, "model") or contract.model,
                    effort=_string_from_mapping(config, "variant") or _string_from_mapping(config, "reasoningEffort") or contract.effort,
                    tools=tools,
                    permissions=permissions,
                    mutation_authority=_mutation_authority(tools, permissions),
                    assignment_source=source if _string_from_mapping(config, "model") else contract.assignment_source,
                    inheritance_sources=inherited,
                    apply_target=str(path),
                )
            else:
                by_name[name] = _contract_from_json_agent(
                    name,
                    config,
                    scope=scope,
                    definition_source=source,
                    assignment_source=source if _string_from_mapping(config, "model") else None,
                    apply_target=str(path),
                    inherited=inherited,
                )
    return tuple(by_name[name] for name in sorted(by_name))


def _markdown_files(directory: Path) -> tuple[Path, ...]:
    if not directory.exists() or not directory.is_dir():
        return ()
    return tuple(sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".md"))


def _read_json_object(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, Mapping) else {}


def _read_pi_assignments(sources: Sequence[tuple[str, Path]]) -> dict[str, dict[str, Any]]:
    assignments: dict[str, dict[str, Any]] = {}
    for scope, path in sources:
        value = _read_json_object(path)
        profiles = value.get("model_profiles", value.get("profiles", {}))
        if not isinstance(profiles, Mapping):
            continue
        for name, profile in profiles.items():
            if isinstance(name, str) and isinstance(profile, Mapping):
                assignments[name] = {"scope": scope, "source": f"{scope}:subagents.json", "path": path, "profile": profile}
    return assignments


def _pi_current_contracts(global_root: Path, environ: Mapping[str, str]) -> tuple[AgentContract, ...]:
    contracts: list[AgentContract] = []
    env_model = _exact_model(environ.get("PI_PROVIDER"), environ.get("PI_MODEL"))
    env_effort = _nonempty_string(environ.get("PI_REASONING_LEVEL"))
    if env_model:
        contracts.append(_synthetic_assignment_contract(
            "current",
            model=env_model,
            effort=env_effort,
            definition_source="env#current",
            assignment_source="env",
            apply_target=None,
        ))
    settings_path = global_root / "settings.json"
    settings = _read_json_object(settings_path)
    settings_model = _exact_model(settings.get("defaultProvider"), settings.get("defaultModel"))
    if settings_model:
        contracts.append(_synthetic_assignment_contract(
            "default",
            model=settings_model,
            effort=_nonempty_string(settings.get("defaultThinkingLevel")),
            definition_source="global:settings.json#default",
            assignment_source="global:settings.json",
            apply_target=str(settings_path),
        ))
    return tuple(contracts)


def _synthetic_assignment_contract(
    name: str,
    *,
    model: str,
    effort: str | None,
    definition_source: str,
    assignment_source: str,
    apply_target: str | None,
) -> AgentContract:
    digest_payload = json.dumps({
        "name": name,
        "model": model,
        "effort": effort,
        "definition_source": definition_source,
        "assignment_source": assignment_source,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return AgentContract(
        name=name,
        description="",
        mode=None,
        model=model,
        effort=effort,
        tools=(),
        permissions=(),
        mutation_authority="denied",
        body="",
        scope="global" if definition_source.startswith("global:") else "runtime",
        definition_source=definition_source,
        assignment_source=assignment_source,
        inheritance_sources=(),
        apply_target=apply_target,
        digest="sha256:" + hashlib.sha256(digest_payload).hexdigest(),
    )


def _exact_model(provider_value: Any, model_value: Any) -> str | None:
    model = _nonempty_string(model_value)
    if model is None:
        return None
    if "/" in model:
        return model
    provider = _nonempty_string(provider_value)
    return f"{provider}/{model}" if provider else model


def _nonempty_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _read_opencode_agents(path: Path) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    value = _read_json_object(path)
    agents = value.get("agent")
    if not isinstance(agents, Mapping):
        return ()
    return tuple(
        (name, config)
        for name, config in sorted(agents.items())
        if isinstance(name, str) and isinstance(config, Mapping)
    )


def _contract_from_json_agent(
    name: str,
    config: Mapping[str, Any],
    *,
    scope: str,
    definition_source: str,
    assignment_source: str | None,
    apply_target: str,
    inherited: tuple[str, ...],
) -> AgentContract:
    tools = _normalize_tools(config.get("tools")) if "tools" in config else ()
    permissions = _normalize_permissions(config.get("permission", config.get("permissions"))) if ("permission" in config or "permissions" in config) else ()
    body = _string_from_mapping(config, "prompt") or ""
    digest_payload = json.dumps(_json_digestable(config), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return AgentContract(
        name=name,
        description=_string_from_mapping(config, "description") or "",
        mode=_string_from_mapping(config, "mode"),
        model=_string_from_mapping(config, "model"),
        effort=_string_from_mapping(config, "variant") or _string_from_mapping(config, "effort") or _string_from_mapping(config, "reasoningEffort"),
        tools=tools,
        permissions=permissions,
        mutation_authority=_mutation_authority(tools, permissions),
        body=body,
        scope=scope,
        definition_source=definition_source,
        assignment_source=assignment_source,
        inheritance_sources=inherited,
        apply_target=apply_target,
        digest="sha256:" + hashlib.sha256(digest_payload).hexdigest(),
    )


def _json_digestable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_digestable(item) for key, item in value.items() if isinstance(key, str)}
    if isinstance(value, (list, tuple)):
        return [_json_digestable(item) for item in value]
    return repr(value)


def _string_from_mapping(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    return item.strip() if isinstance(item, str) and item.strip() else None


def _family_from_model_id(model_id: str) -> str | None:
    lowered = model_id.lower()
    for prefix in ("gpt", "qwen", "claude", "gemini", "llama", "mistral", "deepseek"):
        if lowered.startswith(prefix):
            return prefix
    return lowered.split("-", 1)[0].split(".", 1)[0] if lowered else None


def _shortlist_sort_key(requirements: RoleRequirements, candidate: CandidateEvidence) -> tuple[Any, ...]:
    fixture_scores = [fixture.role_score for fixture in candidate.fixtures if fixture.success and fixture.contract_success]
    score = max(fixture_scores) if fixture_scores else -1.0
    key: list[Any] = [-score]
    for priority in requirements.priority_order:
        if priority == "reliability":
            reliability = candidate.reliability_rate if candidate.reliability_rate is not None else _candidate_reliability(candidate)
            key.append(-(reliability if reliability is not None else -1.0))
        elif priority == "latency":
            elapsed = candidate.median_elapsed_ms if candidate.median_elapsed_ms is not None else _candidate_median_elapsed(candidate)
            key.append(elapsed if elapsed is not None else 10**12)
        elif priority == "cost":
            cost = candidate.metered_cost if candidate.metered_cost is not None else _candidate_cost(candidate)
            key.append(cost if cost is not None else 10**12)
        elif priority == "intervention":
            intervention = _candidate_intervention(candidate)
            key.append(intervention if intervention is not None else 10**12)
    key.extend((candidate.route.model, candidate.route.effort or ""))
    return tuple(key)


def _candidate_reliability(candidate: CandidateEvidence) -> float | None:
    runs = _all_runs(candidate)
    if not runs:
        return candidate.reliability_rate
    return sum(1 for run in runs if run.reliable) / len(runs)


def _candidate_median_elapsed(candidate: CandidateEvidence) -> int | None:
    values = sorted(run.elapsed_ms for run in _all_runs(candidate))
    if not values:
        return candidate.median_elapsed_ms
    return values[len(values) // 2]


def _candidate_cost(candidate: CandidateEvidence) -> float | None:
    values = [run.metered_cost for run in _all_runs(candidate) if run.metered_cost is not None]
    if not values:
        return candidate.metered_cost
    return sum(values) / len(values)


def _candidate_intervention(candidate: CandidateEvidence) -> float | None:
    runs = _all_runs(candidate)
    if not runs:
        return None
    return sum(run.intervention_count for run in runs) / len(runs)


def _all_runs(candidate: CandidateEvidence) -> tuple[RunObservation, ...]:
    return tuple(run for fixture in candidate.fixtures for run in fixture.runs)


def _compatible_fixture_scores(candidate: CandidateEvidence) -> dict[tuple[str, str], float]:
    return {
        (fixture.fixture_id, fixture.fixture_version): fixture.role_score
        for fixture in candidate.fixtures
        if fixture.success and fixture.contract_success
    }


def _has_higher_mandatory_tier(challenger: CandidateEvidence, incumbent: CandidateEvidence) -> bool:
    challenger_tier = _mandatory_tier(challenger)
    incumbent_tier = _mandatory_tier(incumbent)
    return challenger_tier > incumbent_tier and challenger_tier > 0


def _mandatory_tier(candidate: CandidateEvidence) -> int:
    scores = [fixture.role_score for fixture in candidate.fixtures if fixture.success and fixture.contract_success]
    if not scores:
        return 0
    best = max(scores)
    if best >= 0.90:
        return 3
    if best >= 0.80:
        return 2
    return 1


def _has_material_quality_advantage(challenger: CandidateEvidence, incumbent: CandidateEvidence) -> bool:
    challenger_scores = _compatible_fixture_scores(challenger)
    incumbent_scores = _compatible_fixture_scores(incumbent)
    common = sorted(set(challenger_scores).intersection(incumbent_scores))
    improvements = [challenger_scores[key] - incumbent_scores[key] for key in common]
    return len(improvements) >= 2 and all(delta >= 0.10 for delta in improvements)


def _needs_more_pairwise_evidence(challenger: CandidateEvidence, incumbent: CandidateEvidence) -> bool:
    if _mandatory_tier(challenger) < _mandatory_tier(incumbent):
        return False
    challenger_scores = _compatible_fixture_scores(challenger)
    incumbent_scores = _compatible_fixture_scores(incumbent)
    if not challenger_scores or not incumbent_scores:
        return True
    common = set(challenger_scores).intersection(incumbent_scores)
    if len(common) >= 2:
        return False
    challenger_best = max(challenger_scores.values())
    incumbent_best = max(incumbent_scores.values())
    return challenger_best >= incumbent_best - 0.01


def _has_material_operational_advantage(requirements: RoleRequirements, challenger: CandidateEvidence, incumbent: CandidateEvidence) -> bool:
    priority = next((item for item in requirements.priority_order if item in {"latency", "cost", "reliability", "intervention"}), None)
    if priority is None:
        return False
    challenger_runs = _runs_by_fixture(challenger)
    incumbent_runs = _runs_by_fixture(incumbent)
    common = sorted(set(challenger_runs).intersection(incumbent_runs))
    if len(common) < 2:
        return False
    wins = 0
    for key in common:
        c_runs = challenger_runs[key]
        i_runs = incumbent_runs[key]
        if not c_runs or not i_runs:
            continue
        if _reliability_rate(c_runs) < _reliability_rate(i_runs):
            return False
        if _intervention_count(c_runs) > _intervention_count(i_runs):
            return False
        if priority == "latency" and _average_elapsed(c_runs) <= _average_elapsed(i_runs) * 0.80:
            wins += 1
        elif priority == "cost" and _average_cost(c_runs) is not None and _average_cost(i_runs) is not None and _average_cost(c_runs) <= _average_cost(i_runs) * 0.80:
            wins += 1
        elif priority == "reliability" and _reliability_rate(c_runs) >= min(1.0, _reliability_rate(i_runs) * 1.20):
            wins += 1
        elif priority == "intervention" and _intervention_count(c_runs) <= _intervention_count(i_runs) * 0.80:
            wins += 1
    return wins >= 2


def _runs_by_fixture(candidate: CandidateEvidence) -> dict[tuple[str, str], tuple[RunObservation, ...]]:
    return {
        (fixture.fixture_id, fixture.fixture_version): fixture.runs
        for fixture in candidate.fixtures
        if fixture.success and fixture.contract_success and fixture.runs
    }


def _reliability_rate(runs: tuple[RunObservation, ...]) -> float:
    return sum(1 for run in runs if run.reliable) / len(runs)


def _intervention_count(runs: tuple[RunObservation, ...]) -> float:
    return sum(run.intervention_count for run in runs) / len(runs)


def _average_elapsed(runs: tuple[RunObservation, ...]) -> float:
    return sum(run.elapsed_ms for run in runs) / len(runs)


def _average_cost(runs: tuple[RunObservation, ...]) -> float | None:
    values = [run.metered_cost for run in runs if run.metered_cost is not None]
    if len(values) != len(runs) or not values:
        return None
    return sum(values) / len(values)


def _best_candidate_without_incumbent(requirements: RoleRequirements, candidates: Sequence[CandidateEvidence]) -> MappingDecision:
    if not candidates:
        return MappingDecision("ABSTAIN", None, None, ("no_eligible_candidates",))
    ordered = sorted(candidates, key=lambda candidate: _shortlist_sort_key(requirements, candidate))
    top_scores = _compatible_fixture_scores(ordered[0])
    if not top_scores:
        return MappingDecision("NEEDS_MORE_EVIDENCE", ordered[0].route, None, ("no_conclusive_local_fixture",))
    if len(ordered) > 1:
        second_scores = _compatible_fixture_scores(ordered[1])
        common = set(top_scores).intersection(second_scores)
        if len(common) < 2 and all(abs(top_scores.get(key, -1) - second_scores.get(key, -2)) < 0.10 for key in common):
            return MappingDecision("NEEDS_MORE_EVIDENCE", ordered[0].route, None, ("insufficient_separation",))
    return MappingDecision("CHANGE", ordered[0].route, None, ("best_eligible_candidate",))


def _read_bounded_definition(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError("agent_definition_unreadable") from exc
    if len(data) > _MAX_AGENT_DEFINITION_BYTES:
        raise ValueError("agent_definition_too_large")
    return data


def _decode_definition(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("agent_definition_non_utf8") from exc


def _split_frontmatter(text: str) -> tuple[str, str]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise ValueError("agent_definition_missing_frontmatter")
    lines = normalized.split("\n")
    closing_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index] == "---":
            closing_index = index
            break
    if closing_index is None:
        raise ValueError("agent_definition_missing_frontmatter")
    frontmatter = "\n".join(lines[1:closing_index])
    body = "\n".join(lines[closing_index + 1:])
    if body.endswith("\n"):
        body = body[:-1]
    if any(line == "---" for line in body.split("\n")):
        raise ValueError("agent_definition_nested_frontmatter")
    if len(frontmatter) > _MAX_AGENT_FRONTMATTER_CHARS:
        raise ValueError("agent_definition_frontmatter_too_large")
    if len(body) > _MAX_AGENT_BODY_CHARS:
        raise ValueError("agent_definition_body_too_large")
    return frontmatter, body


def _parse_frontmatter(text: str) -> dict[str, Any]:
    lines = text.split("\n") if text else []
    parsed, index = _parse_mapping(lines, 0, 0)
    if index != len(lines):
        raise ValueError("agent_definition_unsupported_nesting")
    return parsed


def _parse_mapping(lines: list[str], start: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        current_indent = _indent_of(line)
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ValueError("agent_definition_unsupported_nesting")
        stripped = line.strip()
        if stripped.startswith("-"):
            break
        if ":" not in stripped:
            raise ValueError("agent_definition_invalid_frontmatter")
        key, raw_value = stripped.split(":", 1)
        key = _strip_quotes(key.strip())
        raw_value = raw_value.strip()
        _validate_key(key)
        if key in result:
            raise ValueError(f"agent_definition_duplicate_key:{key}")
        if raw_value:
            result[key] = _parse_scalar(raw_value)
            index += 1
            continue
        index += 1
        if index >= len(lines) or not lines[index].strip() or _indent_of(lines[index]) <= indent:
            result[key] = {}
            continue
        child_indent = _indent_of(lines[index])
        if child_indent != indent + 2:
            raise ValueError("agent_definition_unsupported_nesting")
        if lines[index].strip().startswith("-"):
            result[key], index = _parse_list(lines, index, child_indent)
        else:
            result[key], index = _parse_mapping(lines, index, child_indent)
    return result, index


def _parse_list(lines: list[str], start: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        current_indent = _indent_of(line)
        if current_indent < indent:
            break
        if current_indent != indent:
            raise ValueError("agent_definition_unsupported_nesting")
        stripped = line.strip()
        if not stripped.startswith("- "):
            break
        result.append(_parse_scalar(stripped[2:].strip()))
        index += 1
    return result, index


def _indent_of(line: str) -> int:
    if "\t" in line[: len(line) - len(line.lstrip())]:
        raise ValueError("agent_definition_unsupported_nesting")
    return len(line) - len(line.lstrip(" "))


def _validate_key(key: str) -> None:
    if key in {"inherit", "extends", "<<"}:
        raise ValueError("agent_definition_ambiguous_inheritance")
    if not key or not re.fullmatch(r"[A-Za-z0-9_.*/-]+", key):
        raise ValueError(f"agent_definition_invalid_key:{key[:40]}")
    if key.startswith(("!", "&")):
        raise ValueError("agent_definition_unsupported_yaml")


def _parse_scalar(value: str) -> Any:
    if _contains_yaml_feature(value):
        raise ValueError("agent_definition_unsupported_yaml")
    if value in {"{}", "[]"}:
        return {} if value == "{}" else []
    if value.startswith(("{", "[")):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("agent_definition_invalid_json_scalar") from exc
        if not _is_bounded_json(parsed):
            raise ValueError("agent_definition_invalid_json_scalar")
        return parsed
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    return _strip_quotes(value)


def _contains_yaml_feature(value: str) -> bool:
    stripped = value.strip()
    if stripped.startswith(("!", "&")):
        return True
    if re.search(r"(?<![A-Za-z0-9_.-])&[A-Za-z]", stripped):
        return True
    if re.search(r"(?<![A-Za-z0-9_.-])\*[A-Za-z]", stripped):
        return True
    return False


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _is_bounded_json(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int, float)):
        return True
    if isinstance(value, list):
        return len(value) <= 128 and all(_is_bounded_json(item) for item in value)
    if isinstance(value, dict):
        return len(value) <= 128 and all(isinstance(key, str) and _is_bounded_json(item) for key, item in value.items())
    return False


def _required_string(parsed: Mapping[str, Any], key: str) -> str:
    value = parsed.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"agent_definition_missing_required:{key}")
    return value.strip()


def _optional_string(parsed: Mapping[str, Any], key: str) -> str | None:
    value = parsed.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"agent_definition_invalid_string:{key}")
    return value.strip()


def _normalize_tools(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    raw_tools: list[str] = []
    if isinstance(value, str):
        raw_tools.extend(part.strip() for part in value.split(","))
    elif isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            raise ValueError("agent_definition_invalid_tools")
        raw_tools.extend(item.strip() for item in value)
    elif isinstance(value, Mapping):
        for key, enabled in value.items():
            if not isinstance(key, str):
                raise ValueError("agent_definition_invalid_tools")
            if enabled is False or (isinstance(enabled, str) and enabled.lower() == "deny"):
                continue
            raw_tools.append(key.strip())
    else:
        raise ValueError("agent_definition_invalid_tools")
    normalized: list[str] = []
    for tool in raw_tools:
        if not tool:
            continue
        if not _SAFE_NAME_RE.fullmatch(tool):
            raise ValueError(f"agent_definition_unsafe_tool:{tool[:40]}")
        if tool in normalized:
            raise ValueError(f"agent_definition_duplicate_tool:{tool}")
        normalized.append(tool)
    return tuple(normalized)


def _normalize_permissions(value: Any) -> tuple[PermissionRule, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        action = value.strip().lower()
        if action not in _PERMISSION_ACTIONS:
            raise ValueError(f"agent_definition_unknown_permission_action:{action[:40]}")
        return (PermissionRule("*", "*", action),)
    if not isinstance(value, Mapping):
        raise ValueError("agent_definition_invalid_permissions")
    rules: list[PermissionRule] = []
    seen: set[tuple[str, str]] = set()
    for capability, pattern_map in value.items():
        if not isinstance(capability, str) or not _SAFE_NAME_RE.fullmatch(capability.replace("*", "wildcard")):
            raise ValueError(f"agent_definition_invalid_permission_capability:{str(capability)[:40]}")
        if isinstance(pattern_map, str):
            _append_permission_rule(rules, seen, capability, "*", pattern_map)
            continue
        if not isinstance(pattern_map, Mapping):
            raise ValueError("agent_definition_invalid_permissions")
        for pattern, action in pattern_map.items():
            if not isinstance(pattern, str) or not isinstance(action, str):
                raise ValueError("agent_definition_invalid_permissions")
            _append_permission_rule(rules, seen, capability, pattern, action)
    return tuple(rules)


def _append_permission_rule(
    rules: list[PermissionRule],
    seen: set[tuple[str, str]],
    capability: str,
    pattern: str,
    raw_action: str,
) -> None:
    action = raw_action.strip().lower()
    if action not in _PERMISSION_ACTIONS:
        raise ValueError(f"agent_definition_unknown_permission_action:{action[:40]}")
    key = (capability, pattern)
    if key in seen:
        raise ValueError(f"agent_definition_duplicate_permission:{capability}:{pattern}")
    seen.add(key)
    rules.append(PermissionRule(capability, pattern, action))


def _mutation_authority(tools: tuple[str, ...], permissions: tuple[PermissionRule, ...]) -> str:
    mutating_tools = {"bash", "edit", "write", "patch"}
    if not mutating_tools.intersection(tools):
        return "denied"
    relevant = [rule for rule in permissions if rule.capability in {"*", *mutating_tools}]
    if any(rule.action in {"deny", "ask"} for rule in relevant):
        return "confined"
    if any(rule.action == "allow" and rule.pattern == "*" for rule in relevant):
        return "unrestricted"
    if any(rule.action == "allow" for rule in relevant):
        return "confined"
    return "unknown"
