#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import urlsplit

# Portable direct-script bootstrap: when invoked as
# `python3 skills/model-optimizer/scripts/model_optimizer.py` from the repo root,
# Python places only this scripts directory on sys.path. Add the skill root so the
# sibling `helper` package is importable without personal paths or installation.
_SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from helper.adapters import RuntimeContext, adapter_for
from helper.artifacts import digest_json, inventory_with_digest, load_inventory, reject_runtime_config_output, write_health, write_inventory, write_json_atomic
from helper.evaluator import (
    EvaluationArtifact,
    FixturePolicy,
    RoleEvalRequest,
    canonical_fixture_digest,
    grade_fixture,
    load_fixture,
    load_representative_fixture,
    prepare_fixture,
    prepare_workspace_marker,
    select_sandbox_backend,
)
from helper.models import (
    HealthArtifact,
    HealthCheck,
    HealthStatus,
    Inventory,
    ModelRecord,
    ReadinessStatus,
    RuntimeKind,
)
from helper.optimizer import AgentContract, IdentityMatch, RoleRequirements, RouteKey, discover_agent_contracts
from helper.runner import CommandRunner, redact_text
from helper.state import BenchmarkSummary, EvaluationKey, EvaluationSummary, OptimizerState, state_path, update_state

EXIT_OK = 0
EXIT_USAGE_OR_SCHEMA = 2
EXIT_DETECTION = 3
EXIT_PARTIAL = 4
EXIT_FAILED_OR_HUNG = 5
EXIT_EVALUATION_INCONCLUSIVE = 6
_SENTINEL = "PONG"

_PI_SIGNAL_KEYS = frozenset({
    "PI_CODING_AGENT",
    "PI_SESSION_ID",
    "PI_PROVIDER",
    "PI_MODEL",
    "PI_REASONING_LEVEL",
    "SUPERPOWERS_SESSION_ID",
    "SDD_TASK_ID",
    "GENTLEMAN_SESSION_ID",
})
_OPENCODE_SIGNAL_KEYS = frozenset({"OPENCODE", "OPENCODE_SESSION_ID"})
_RUNTIME_EXECUTABLE = {
    RuntimeKind.PI: "pi",
    RuntimeKind.OPENCODE: "opencode",
}


class _CliUsageError(Exception):
    pass


class _ReturningParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - exercised through argparse flows
        raise _CliUsageError(f"usage_error:{message}")

    def exit(self, status: int = 0, message: str | None = None) -> None:  # pragma: no cover
        if status == 0:
            raise SystemExit(0)
        raise _CliUsageError((message or "usage_error").strip())


class _SingleValueAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            raise _CliUsageError(f"usage_duplicate_argument:{option_string or self.dest}")
        setattr(namespace, self.dest, values)


def _add_single(parser: argparse.ArgumentParser, name: str, **kwargs: Any) -> None:
    parser.add_argument(name, action=_SingleValueAction, default=None, **kwargs)


def _parser() -> argparse.ArgumentParser:
    parser = _ReturningParser(prog="model_optimizer.py", description="Read-only model optimizer evidence helper")
    sub = parser.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser("inventory", help="write read-only runtime inventory")
    inventory.add_argument("--runtime", choices=("auto", "pi", "opencode"), default="auto")
    inventory.add_argument("--output", required=True)

    check = sub.add_parser("check", help="live-check exact catalog-local model IDs")
    check.add_argument("--inventory", required=True)
    check.add_argument("--model", action="append", required=True)
    check.add_argument("--effort")
    check.add_argument("--timeout", required=True, type=float)
    check.add_argument("--output", required=True)

    evaluate = sub.add_parser("evaluate", help="run one read-only runtime-exact role evaluation")
    for option in ("--inventory", "--agent", "--model", "--effort", "--timeout", "--output"):
        _add_single(evaluate, option, required=option != "--output")
    fixture_group = evaluate.add_mutually_exclusive_group(required=True)
    fixture_group.add_argument("--fixture", action=_SingleValueAction, default=None)
    fixture_group.add_argument("--fixture-path", action=_SingleValueAction, default=None)
    _add_single(evaluate, "--fixture-token", required=False)

    benchmark = sub.add_parser("cache-benchmark", help="cache one normalized benchmark observation")
    for option in (
        "--inventory", "--model", "--effort", "--identity", "--source-name", "--benchmark", "--benchmark-version",
        "--source-url", "--evaluated-model-identity", "--harness-or-agent", "--reasoning-mode", "--observed-at",
        "--metric-name", "--metric-value",
    ):
        _add_single(benchmark, option, required=option not in {"--harness-or-agent", "--reasoning-mode"})
    return parser


def main(argv: Sequence[str] | None = None, runner=None, environ=None, which: Callable[[str], str | None] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("usage_error:python_3_11_required", file=sys.stderr)
        return EXIT_USAGE_OR_SCHEMA

    if _uses_test_overrides(runner, environ, which):
        effective_environ = os.environ if environ is None else environ
        if effective_environ.get("MODEL_OPTIMIZER_TEST_MODE") != "1":
            print("usage_error:test_overrides_require_test_mode", file=sys.stderr)
            return EXIT_USAGE_OR_SCHEMA

    actual_runner = runner if runner is not None else CommandRunner()
    actual_environ = dict(os.environ if environ is None else environ)
    actual_which = which if which is not None else shutil.which

    try:
        args = _parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    except _CliUsageError as exc:
        print(_safe_message(str(exc)), file=sys.stderr)
        return EXIT_USAGE_OR_SCHEMA
    except SystemExit as exc:
        return int(exc.code or 0)

    try:
        if args.command == "inventory":
            return _inventory(args, actual_runner, actual_environ, actual_which)
        if args.command == "check":
            return _check(args, actual_runner, actual_environ, actual_which)
        if args.command == "evaluate":
            return _evaluate(args, actual_runner, actual_environ, actual_which)
        if args.command == "cache-benchmark":
            return _cache_benchmark(args, actual_runner, actual_environ, actual_which)
    except RuntimeError as exc:
        message = _safe_message(str(exc))
        print(message, file=sys.stderr)
        return EXIT_DETECTION if message.startswith("runtime_") else EXIT_USAGE_OR_SCHEMA
    except (ValueError, OSError, TypeError) as exc:
        print(_safe_message(_schema_or_usage_message(exc)), file=sys.stderr)
        return EXIT_USAGE_OR_SCHEMA
    print("usage_error:unknown_command", file=sys.stderr)
    return EXIT_USAGE_OR_SCHEMA


def _inventory(args, runner, environ: dict[str, str], which: Callable[[str], str | None]) -> int:
    context = RuntimeContext(home=_home_from_env(environ), cwd=Path.cwd(), env=environ)
    reject_runtime_config_output(Path(args.output), home=context.home, cwd=context.cwd)
    runtime = _resolve_runtime(args.runtime, environ, which)
    adapter = adapter_for(runtime, runner)
    adapter.reload_semantics(context)
    inventory = _normalize_inventory(adapter.inventory(context))
    write_inventory(Path(args.output), inventory)
    print(f"models={len(inventory.catalog_local)} assignments={len(inventory.current_assignments)} warnings={len(inventory.warnings)} output={Path(args.output)}")
    return EXIT_PARTIAL if inventory.warnings else EXIT_OK


def _check(args, runner, environ: dict[str, str], which: Callable[[str], str | None]) -> int:
    timeout = _validate_timeout(args.timeout)
    context_home = _home_from_env(environ)
    context_cwd = Path.cwd()
    reject_runtime_config_output(Path(args.output), home=context_home, cwd=context_cwd, inventory_input=Path(args.inventory))
    inventory = load_inventory(Path(args.inventory))
    reject_runtime_config_output(Path(args.output), home=context_home, cwd=Path(inventory.runtime.cwd), inventory_input=Path(args.inventory))
    _ensure_runtime_executable(inventory.runtime.kind, which)
    requested = _dedupe(args.model)
    catalog = {record.exact_id: record for record in inventory.catalog_local}
    readiness = {item.provider: item for item in inventory.provider_readiness}

    for model_id in requested:
        record = catalog.get(model_id)
        if record is None:
            raise ValueError(f"live_model_not_catalog_local:{model_id}")
        provider = readiness.get(record.provider)
        if provider is None or provider.status is not ReadinessStatus.READY:
            raise ValueError(f"live_provider_not_ready:{record.provider}")

    print(f"planned_checks={len(requested)} output={Path(args.output)}")
    context = RuntimeContext(home=_home_from_env(environ), cwd=Path(inventory.runtime.cwd), env=environ)
    adapter = adapter_for(inventory.runtime.kind, runner)
    ordered_records = [catalog[model_id] for model_id in requested]
    with ThreadPoolExecutor(max_workers=2) as executor:
        checks = list(executor.map(lambda record: adapter.live_check(record, args.effort, _SENTINEL, timeout, context), ordered_records))
    safe_checks = tuple(_sanitize_check(check) for check in checks)
    health = HealthArtifact(
        schema="model-optimizer.health/v1",
        created_at=_utc_now_rfc3339(),
        inventory_digest=inventory.digest,
        checks=safe_checks,
    )
    write_health(Path(args.output), health)
    if any(check.status in {HealthStatus.FAIL, HealthStatus.HANG} for check in safe_checks):
        return EXIT_FAILED_OR_HUNG
    return EXIT_OK


def _evaluate(args, runner, environ: dict[str, str], which: Callable[[str], str | None]) -> int:
    timeout = _validate_timeout(float(args.timeout))
    home = _home_from_env(environ)
    context_cwd = Path.cwd()
    inventory = load_inventory(Path(args.inventory))
    _ensure_runtime_executable(inventory.runtime.kind, which)
    inventory_cwd = Path(inventory.runtime.cwd)
    if args.output is not None:
        _reject_output_all_configs(Path(args.output), environ=environ, home=home, cwd=context_cwd, inventory_cwd=inventory_cwd, inventory_input=Path(args.inventory))
    record = _model_record_or_error(inventory, args.model, prefix="eval")
    _ensure_provider_ready(inventory, record, prefix="eval")
    effort = _normalize_effort(args.effort, allow_none=False)
    _validate_route_effort(record, effort, prefix="eval")
    route = RouteKey(inventory.runtime.kind, inventory.runtime.version, record.exact_id, effort)

    agents = discover_agent_contracts(inventory.runtime.kind, home, inventory_cwd, environ)
    agent = _select_agent(args.agent, agents)
    fixture = _load_requested_fixture(args)
    workspace = prepare_fixture(fixture)
    try:
        attestation = select_sandbox_backend(runner, workspace)
        if fixture.requires_code_execution and attestation is None:
            print("evaluation=INCONCLUSIVE reason=eval_sandbox_unavailable", file=sys.stdout)
            return EXIT_EVALUATION_INCONCLUSIVE
        workspace = replace(workspace, sandbox_attestation=attestation)
        policy = _policy_from_fixture(fixture)
        prepare_workspace_marker(workspace, policy)
        request = RoleEvalRequest(route, record, agent, _requirements_for_fixture(fixture, agent), workspace, policy, fixture.task, timeout)
        result = adapter_for(inventory.runtime.kind, runner).role_eval(request, RuntimeContext(home=home, cwd=inventory_cwd, env=environ))
        grade = grade_fixture(fixture, workspace.root, replace(result, manifest_digest=fixture.manifest_digest))
        conclusive = result.status in {"PASS", "FAIL"} and grade.status in {"PASS", "FAIL"}
        if not conclusive:
            print(f"evaluation=INCONCLUSIVE reason={_first_reason(result.reason_codes, grade.reason_codes)}")
            return EXIT_EVALUATION_INCONCLUSIVE
        summary = _evaluation_summary(inventory, record, route, agent, fixture, result, grade)
        cache_path = state_path(environ, home, _runtime_config_trees(environ, home, inventory_cwd))
        updated = update_state(cache_path, lambda state: _upsert_evaluation(state, summary))
        if args.output is not None:
            artifact = EvaluationArtifact(
                schema="model-optimizer.evaluation/v1",
                created_at=summary.created_at,
                inventory_digest=inventory.digest,
                route=route,
                agent_digest=agent.digest,
                fixture_id=fixture.fixture_id,
                fixture_version=fixture.version,
                result=summary,
            )
            write_json_atomic(Path(args.output), artifact.to_dict())
        status = "PASS" if summary.success else "FAIL"
        warnings = f" warnings={len(updated.warnings)}" if updated.warnings else ""
        print(f"evaluation={status} fixture={fixture.fixture_id} state={cache_path}{warnings}")
        return EXIT_OK if summary.success else EXIT_FAILED_OR_HUNG
    finally:
        shutil.rmtree(workspace.root, ignore_errors=True)


def _cache_benchmark(args, runner, environ: dict[str, str], which: Callable[[str], str | None]) -> int:
    del runner, which
    home = _home_from_env(environ)
    inventory = load_inventory(Path(args.inventory))
    inventory_cwd = Path(inventory.runtime.cwd)
    record = _model_record_or_error(inventory, args.model, prefix="benchmark")
    _ensure_provider_ready(inventory, record, prefix="benchmark")
    effort = _normalize_effort(args.effort, allow_none=True)
    _validate_route_effort(record, effort, prefix="benchmark")
    identity = _identity(args.identity)
    source_url = _https_url(args.source_url)
    observed_at = _rfc3339_utc_text(args.observed_at)
    metric_value = _metric_value(args.metric_value)
    for value, reason in (
        (args.source_name, "benchmark_source_name_invalid"),
        (args.benchmark, "benchmark_name_invalid"),
        (args.benchmark_version, "benchmark_version_invalid"),
        (args.evaluated_model_identity, "benchmark_evaluated_identity_invalid"),
        (args.metric_name, "benchmark_metric_name_invalid"),
        (args.harness_or_agent, "benchmark_harness_invalid"),
        (args.reasoning_mode, "benchmark_reasoning_mode_invalid"),
    ):
        _validate_optional_text(value, reason)
    cache_path = state_path(environ, home, _runtime_config_trees(environ, home, inventory_cwd))
    summary = BenchmarkSummary(
        route=RouteKey(inventory.runtime.kind, inventory.runtime.version, record.exact_id, effort),
        identity=identity.value,
        source_name=args.source_name,
        source_url=source_url,
        benchmark=args.benchmark,
        benchmark_version=args.benchmark_version,
        harness_or_agent=args.harness_or_agent,
        evaluated_model_identity=args.evaluated_model_identity,
        reasoning_mode=args.reasoning_mode,
        observed_at=observed_at,
        cached_at=_utc_now_rfc3339(),
        metric_name=args.metric_name,
        metric_value=metric_value,
    )
    updated = update_state(cache_path, lambda state: _upsert_benchmark(state, summary))
    warnings = f" warnings={len(updated.warnings)}" if updated.warnings else ""
    print(f"benchmark_cached=1 state={cache_path}{warnings}")
    return EXIT_OK


def _resolve_runtime(requested: str, environ: dict[str, str], which: Callable[[str], str | None]) -> RuntimeKind:
    if requested != "auto":
        kind = RuntimeKind(requested)
        _ensure_runtime_executable(kind, which)
        return kind

    pi_signal = _has_any_signal(environ, _PI_SIGNAL_KEYS)
    opencode_signal = _has_any_signal(environ, _OPENCODE_SIGNAL_KEYS)
    if pi_signal and opencode_signal:
        raise RuntimeError("runtime_ambiguous:harness_signals")
    if pi_signal:
        _ensure_runtime_executable(RuntimeKind.PI, which)
        return RuntimeKind.PI
    if opencode_signal:
        _ensure_runtime_executable(RuntimeKind.OPENCODE, which)
        return RuntimeKind.OPENCODE

    found = tuple(kind for kind, executable in _RUNTIME_EXECUTABLE.items() if which(executable) is not None)
    if len(found) == 1:
        return found[0]
    if not found:
        raise RuntimeError("runtime_missing:no_runtime_executable")
    raise RuntimeError("runtime_ambiguous:multiple_runtime_executables")


def _ensure_runtime_executable(kind: RuntimeKind, which: Callable[[str], str | None]) -> None:
    if which(_RUNTIME_EXECUTABLE[kind]) is None:
        raise RuntimeError(f"runtime_missing:{kind.value}")


def _validate_timeout(timeout: float) -> float:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("usage_timeout_invalid")
    return timeout


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _has_any_signal(environ: dict[str, str], keys: Iterable[str]) -> bool:
    for key in keys:
        if key in environ and str(environ[key]) != "":
            return True
    return False


def _normalize_inventory(inventory: Inventory) -> Inventory:
    warnings = list(dict.fromkeys(inventory.warnings))
    for readiness in inventory.provider_readiness:
        if readiness.status is not ReadinessStatus.READY:
            warning = f"auth_not_ready:{readiness.provider}:{readiness.reason_code}"
            if warning not in warnings:
                warnings.append(warning)
    normalized = replace(
        inventory,
        current_assignments=tuple(sorted(inventory.current_assignments, key=lambda item: (item.agent, item.source, item.model))),
        catalog_local=tuple(sorted(inventory.catalog_local, key=lambda item: item.exact_id)),
        provider_readiness=tuple(sorted(inventory.provider_readiness, key=lambda item: item.provider)),
        exclusions=tuple(sorted(inventory.exclusions, key=lambda item: (item.subject, item.reason_code, item.detail))),
        sources=tuple(sorted(inventory.sources)),
        warnings=tuple(warnings),
        digest="",
    )
    return inventory_with_digest(normalized)


def _model_record_or_error(inventory: Inventory, model_id: str, *, prefix: str) -> ModelRecord:
    for record in inventory.catalog_local:
        if record.exact_id == model_id:
            return record
    raise ValueError(f"{prefix}_model_not_catalog_local:{model_id}")


def _ensure_provider_ready(inventory: Inventory, record: ModelRecord, *, prefix: str) -> None:
    readiness = {item.provider: item for item in inventory.provider_readiness}
    provider = readiness.get(record.provider)
    if provider is None or provider.status is not ReadinessStatus.READY:
        raise ValueError(f"{prefix}_provider_not_ready:{record.provider}")


def _normalize_effort(value: str, *, allow_none: bool) -> str | None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError("usage_effort_invalid")
    normalized = value.strip()
    if allow_none and normalized.lower() == "none":
        return None
    if not _stable_text(normalized, max_len=80):
        raise ValueError("usage_effort_invalid")
    return normalized


def _validate_route_effort(record: ModelRecord, effort: str | None, *, prefix: str) -> None:
    if record.variants and (effort is None or effort not in record.variants):
        raise ValueError(f"{prefix}_unsupported_effort:{effort or 'none'}")


def _select_agent(name: str, agents: Sequence[AgentContract]) -> AgentContract:
    if not _stable_text(name, max_len=80):
        raise ValueError("eval_agent_name_invalid")
    matches = tuple(agent for agent in agents if agent.name == name)
    if not matches:
        raise ValueError(f"eval_agent_unknown:{name}")
    if len(matches) > 1:
        raise ValueError(f"eval_agent_ambiguous:{name}")
    return matches[0]


def _load_requested_fixture(args):
    if args.fixture is not None:
        return load_fixture(_SKILL_ROOT, args.fixture)
    if args.fixture_path is None or args.fixture_token is None:
        raise ValueError("eval_representative_token_missing")
    return load_representative_fixture(Path(tempfile.gettempdir()), Path(args.fixture_path), args.fixture_token)


def _policy_from_fixture(fixture) -> FixturePolicy:
    base = FixturePolicy(
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.version,
        manifest_digest="",
        grader_id=fixture.grader_id,
        allowed_read_paths=(".",),
        allowed_write_paths=fixture.allowed_changed_files,
        allowed_commands=fixture.allowed_commands,
        requires_code_execution=fixture.requires_code_execution,
        capability_attestations=(),
    )
    return replace(base, manifest_digest=canonical_fixture_digest(base))


def _requirements_for_fixture(fixture, agent: AgentContract) -> RoleRequirements:
    required_tools = ("read", "edit") if fixture.archetype == "mechanical" else ("read",)
    return RoleRequirements(
        archetype=fixture.archetype,
        required_tools=required_tools,
        essential_custom_tools=(),
        requires_vision=False,
        requires_mutation=fixture.archetype == "mechanical",
        min_context=None,
        min_output=None,
        allowed_efforts=(),
        structured_output=fixture.archetype == "debugger",
        adversarial_against_family=None,
        priority_order=("quality", "latency", "cost"),
    )


def _evaluation_summary(inventory: Inventory, record: ModelRecord, route: RouteKey, agent: AgentContract, fixture, result, grade) -> EvaluationSummary:
    success = result.status == "PASS" and grade.status == "PASS" and grade.contract_success
    reason_codes = tuple(dict.fromkeys((*result.reason_codes, *grade.reason_codes, "eval_pass" if success else "eval_contract_fail")))
    key = EvaluationKey(
        route=route,
        agent_digest=agent.digest,
        tool_digest=digest_json({"tools": sorted(agent.tools)}),
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.version,
        model_fingerprint=digest_json(record.to_dict()),
    )
    return EvaluationSummary(
        key=key,
        created_at=_utc_now_rfc3339(),
        success=success,
        role_score=grade.role_score,
        contract_success=grade.contract_success,
        elapsed_ms=int(result.elapsed_ms),
        metered_cost=result.metered_cost,
        reason_codes=reason_codes,
    )


def _upsert_evaluation(state: OptimizerState, summary: EvaluationSummary) -> OptimizerState:
    retained = tuple(item for item in state.evaluations if item.key != summary.key)
    return replace(state, evaluations=retained + (summary,))


def _upsert_benchmark(state: OptimizerState, summary: BenchmarkSummary) -> OptimizerState:
    retained: list[BenchmarkSummary] = []
    preserve_new = True
    for item in state.benchmarks:
        if not _same_benchmark_slot(item, summary):
            retained.append(item)
            continue
        if item.identity == "SOURCE_UNAVAILABLE" and summary.identity == "ABSENT":
            retained.append(item)
            preserve_new = False
            continue
        if item.identity != summary.identity:
            retained.append(item)
            continue
    if preserve_new:
        retained.append(summary)
    return replace(state, benchmarks=tuple(retained))


def _same_benchmark_slot(left: BenchmarkSummary, right: BenchmarkSummary) -> bool:
    return (
        left.route == right.route
        and left.source_name == right.source_name
        and left.benchmark == right.benchmark
        and left.benchmark_version == right.benchmark_version
        and left.evaluated_model_identity == right.evaluated_model_identity
        and left.reasoning_mode == right.reasoning_mode
    )


def _identity(value: str) -> IdentityMatch:
    try:
        return IdentityMatch(value)
    except ValueError:
        raise ValueError(f"identity_invalid:{value}") from None


def _https_url(value: str) -> str:
    parts = urlsplit(value or "")
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
        raise ValueError("benchmark_source_url_invalid")
    return value


def _rfc3339_utc_text(value: str) -> str:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("benchmark_observed_at_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("benchmark_observed_at_invalid") from None
    if parsed.tzinfo is None:
        raise ValueError("benchmark_observed_at_invalid")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _metric_value(value: str) -> float | None:
    if value == "omit":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError("benchmark_metric_invalid") from None
    if not math.isfinite(parsed):
        raise ValueError("benchmark_metric_invalid")
    return parsed


def _validate_optional_text(value: str | None, reason: str) -> None:
    if value is None:
        return
    if not _stable_text(value, max_len=160):
        raise ValueError(reason)


def _stable_text(value: str, *, max_len: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= max_len and "\x00" not in value and all(ch not in "\r\n" for ch in value)


def _first_reason(*groups: Sequence[str]) -> str:
    for group in groups:
        for item in group:
            if item:
                return item
    return "eval_inconclusive"


def _runtime_config_trees(environ: dict[str, str], home: Path, cwd: Path) -> tuple[Path, ...]:
    from helper.adapters.opencode import opencode_global_config_dir, opencode_project_config_path
    from helper.adapters.pi import pi_global_agent_dir

    return (
        pi_global_agent_dir(home, environ),
        cwd / ".pi" / "agent",
        opencode_global_config_dir(home, environ),
        cwd / ".opencode",
        opencode_project_config_path(cwd),
    )


def _reject_output_all_configs(path: Path, *, environ: dict[str, str], home: Path, cwd: Path, inventory_cwd: Path, inventory_input: Path | None = None) -> None:
    reject_runtime_config_output(path, home=home, cwd=cwd, inventory_input=inventory_input)
    reject_runtime_config_output(path, home=home, cwd=inventory_cwd, inventory_input=inventory_input)
    output = _resolved(path)
    for tree in _runtime_config_trees(environ, home, cwd) + _runtime_config_trees(environ, home, inventory_cwd):
        resolved_tree = _resolved(tree)
        if output == resolved_tree or _is_relative_to(output, resolved_tree):
            raise ValueError("usage_output_forbidden")


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _sanitize_check(check: HealthCheck) -> HealthCheck:
    return replace(check, detail=_safe_message(check.detail))


def _safe_message(text: str) -> str:
    return redact_text(text or "")


def _schema_or_usage_message(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    if text.startswith("runtime_"):
        return text
    if text.startswith(("artifact_", "live_", "usage_", "eval_", "state_", "identity_", "benchmark_")):
        return text
    return f"usage_error:{text}"


def _home_from_env(environ: dict[str, str]) -> Path:
    home = environ.get("HOME") or environ.get("USERPROFILE") or str(Path.home())
    return Path(home)


def _uses_test_overrides(runner, environ, which: Callable[[str], str | None] | None) -> bool:
    return runner is not None or environ is not None or which is not None


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
