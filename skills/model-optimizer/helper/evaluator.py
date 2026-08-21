from __future__ import annotations

import json
import math
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from helper.models import ModelRecord, RuntimeKind
from helper.optimizer import AgentContract, RoleRequirements, RouteKey
from helper.runner import CompletedCommand, MAX_STDOUT_LIMIT_CHARS, redact_text

_MARKER_NAME = ".model-optimizer-eval.json"
_POLICY_NAME = ".model-optimizer-policy.json"
_MAX_POLICY_BYTES = 64 * 1024
_MAX_TIMEOUT_SECONDS = 60 * 60
_FRESH_ATTESTATION_SECONDS = 24 * 60 * 60
_STABLE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_ALLOWED_BUILTIN_TOOLS = frozenset({"read", "write", "edit", "bash", "grep", "list", "glob"})
_SECRET_ENV_RE = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|COOKIE|AUTHORIZATION|CREDENTIAL", re.IGNORECASE)


@dataclass(frozen=True)
class PreparedWorkspace:
    root: Path
    token: str
    sandbox_backend: str | None


@dataclass(frozen=True)
class CapabilityAttestation:
    tool_name: str
    probe_id: str
    status: str
    observed_at: str
    probe_digest: str


@dataclass(frozen=True)
class AllowedCommand:
    command_id: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class FixturePolicy:
    fixture_id: str
    fixture_version: str
    manifest_digest: str
    grader_id: str
    allowed_read_paths: tuple[str, ...]
    allowed_write_paths: tuple[str, ...]
    allowed_commands: tuple[AllowedCommand, ...]
    requires_code_execution: bool
    capability_attestations: tuple[CapabilityAttestation, ...]


@dataclass(frozen=True)
class RoleEvalRequest:
    route: RouteKey
    model_record: ModelRecord
    agent: AgentContract
    requirements: RoleRequirements
    workspace: PreparedWorkspace
    fixture: FixturePolicy
    task: str
    timeout: float


@dataclass(frozen=True)
class CommandAudit:
    command_id: str
    exit_code: int | None
    elapsed_ms: int
    sandbox_backend: str


@dataclass(frozen=True)
class ToolAudit:
    tool_names: tuple[str, ...]
    command_runs: tuple[CommandAudit, ...]
    changed_paths: tuple[str, ...]
    outside_workspace_attempts: int
    unauthorized_tools: tuple[str, ...]


@dataclass(frozen=True)
class RoleEvalResult:
    route: RouteKey
    fixture_id: str
    fixture_version: str
    manifest_digest: str
    status: str
    elapsed_ms: int
    final_text: str
    audit: ToolAudit
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    metered_cost: float | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ParsedEvalOutput:
    status: str
    final_text: str
    audit: ToolAudit
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    metered_cost: float | None = None
    reason_codes: tuple[str, ...] = ()


def empty_audit() -> ToolAudit:
    return ToolAudit((), (), (), 0, ())


def inconclusive_result(request: RoleEvalRequest, reason: str, *, elapsed_ms: int = 0) -> RoleEvalResult:
    return RoleEvalResult(
        route=request.route,
        fixture_id=request.fixture.fixture_id,
        fixture_version=request.fixture.fixture_version,
        manifest_digest=request.fixture.manifest_digest,
        status="INCONCLUSIVE",
        elapsed_ms=elapsed_ms,
        final_text="",
        audit=empty_audit(),
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        metered_cost=None,
        reason_codes=(reason,),
    )


def result_from_parsed(request: RoleEvalRequest, parsed: ParsedEvalOutput, elapsed_ms: int) -> RoleEvalResult:
    return RoleEvalResult(
        route=request.route,
        fixture_id=request.fixture.fixture_id,
        fixture_version=request.fixture.fixture_version,
        manifest_digest=request.fixture.manifest_digest,
        status=parsed.status,
        elapsed_ms=elapsed_ms,
        final_text="",
        audit=parsed.audit,
        input_tokens=parsed.input_tokens,
        output_tokens=parsed.output_tokens,
        cache_read_tokens=parsed.cache_read_tokens,
        metered_cost=parsed.metered_cost,
        reason_codes=parsed.reason_codes,
    )


def prepare_workspace_marker(workspace: PreparedWorkspace, fixture: FixturePolicy) -> Path:
    root = _resolved(workspace.root)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / _MARKER_NAME
    payload = {
        "token": workspace.token,
        "fixture_id": fixture.fixture_id,
        "fixture_version": fixture.fixture_version,
        "manifest_digest": fixture.manifest_digest,
        "grader_id": fixture.grader_id,
    }
    marker.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return marker


def write_policy_file(request: RoleEvalRequest) -> Path:
    payload = {
        "workspace_root": str(_resolved(request.workspace.root)),
        "token": request.workspace.token,
        "fixture": {
            "fixture_id": request.fixture.fixture_id,
            "fixture_version": request.fixture.fixture_version,
            "manifest_digest": request.fixture.manifest_digest,
            "grader_id": request.fixture.grader_id,
        },
        "tools": list(request.agent.tools),
        "allowed_read_paths": list(request.fixture.allowed_read_paths),
        "allowed_write_paths": list(request.fixture.allowed_write_paths),
        "sandbox_backend": request.workspace.sandbox_backend,
        "allowed_commands": [
            {
                "command_id": command.command_id,
                "argv": list(command.argv),
                "sandbox_argv": list(sandbox_argv(request.workspace.sandbox_backend, _resolved(request.workspace.root), command.argv)) if request.workspace.sandbox_backend else [],
            }
            for command in request.fixture.allowed_commands
        ],
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(data.encode("utf-8")) > _MAX_POLICY_BYTES:
        raise ValueError("eval_policy_too_large")
    path = _resolved(request.workspace.root) / _POLICY_NAME
    path.write_text(data, encoding="utf-8")
    return path


def pi_confined_extension_path() -> Path:
    return (Path(__file__).resolve().parents[1] / "evals" / "pi-confined-tools.ts").resolve()


def validate_role_eval_request(request: RoleEvalRequest) -> None:
    if request.route.model != request.model_record.exact_id:
        raise ValueError("eval_route_model_mismatch")
    if request.route.effort is not None and request.model_record.variants and request.route.effort not in request.model_record.variants:
        raise ValueError("eval_unsupported_effort")
    if request.requirements.allowed_efforts and request.route.effort not in request.requirements.allowed_efforts:
        raise ValueError("eval_unsupported_effort")
    if not isinstance(request.task, str) or not request.task.strip():
        raise ValueError("eval_empty_task")
    if isinstance(request.timeout, bool) or not isinstance(request.timeout, (int, float)) or not math.isfinite(float(request.timeout)) or request.timeout <= 0 or request.timeout > _MAX_TIMEOUT_SECONDS:
        raise ValueError("eval_invalid_timeout")
    if any(tool.startswith("subagent_") for tool in request.agent.tools):
        raise ValueError("eval_subagent_tool_forbidden")
    missing_required = set(request.requirements.required_tools) - set(request.agent.tools)
    if missing_required:
        raise ValueError("eval_agent_tool_mismatch")
    if request.requirements.requires_mutation and request.agent.mutation_authority == "denied":
        raise ValueError("eval_agent_authority_mismatch")
    _validate_marker(request.workspace, request.fixture)
    for policy_path in (*request.fixture.allowed_read_paths, *request.fixture.allowed_write_paths):
        _resolve_policy_path(request.workspace, policy_path)
    for command in request.fixture.allowed_commands:
        if not _STABLE_ID_RE.fullmatch(command.command_id):
            raise ValueError("eval_unstable_command_id")
        if not command.argv or not all(isinstance(arg, str) and arg and "\x00" not in arg for arg in command.argv):
            raise ValueError("eval_invalid_allowed_command")
    for tool_name in request.requirements.essential_custom_tools:
        if not _has_fresh_pass_attestation(tool_name, request.fixture):
            raise ValueError("eval_essential_custom_tool_unproven")


def unsupported_custom_tools(agent: AgentContract) -> tuple[str, ...]:
    return tuple(tool for tool in agent.tools if tool not in _ALLOWED_BUILTIN_TOOLS)


def select_sandbox_backend(runner: Any, workspace: PreparedWorkspace) -> str | None:
    root = _resolved(workspace.root)
    candidates: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("sandbox-exec", ("sandbox-exec", "-p", "(version 1) (deny default) (allow process*)", "/bin/sh", "-c", "echo self-test-ok")),
        ("bwrap", ("bwrap", "--unshare-net", "--dir", "/tmp", "/bin/sh", "-c", "echo self-test-ok")),
        ("docker", ("docker", "run", "--rm", "--network", "none", "-v", f"{root}:/workspace", "-w", "/workspace", "python:3", "python3", "-c", "print('self-test-ok')")),
    )
    for backend, argv in candidates:
        if shutil.which(backend) is None:
            continue
        try:
            result = runner.run(argv, timeout=5, cwd=workspace.root, env_overlay=_scrubbed_env({}), stdout_limit=MAX_STDOUT_LIMIT_CHARS)
        except Exception:
            continue
        if result.returncode == 0 and not result.timed_out and "self-test-ok" in result.stdout:
            return backend
    return None


def run_manifest_commands(
    runner: Any,
    workspace: PreparedWorkspace,
    fixture: FixturePolicy,
    backend: str | None,
    *,
    timeout: float,
    env: Mapping[str, str] | None = None,
) -> tuple[CommandAudit, ...]:
    if backend is None:
        return ()
    root = _resolved(workspace.root)
    audits: list[CommandAudit] = []
    for command in fixture.allowed_commands:
        argv = sandbox_argv(backend, root, command.argv)
        result = runner.run(argv, timeout=timeout, cwd=workspace.root, env_overlay=_scrubbed_env(env or {}), stdout_limit=MAX_STDOUT_LIMIT_CHARS)
        audits.append(CommandAudit(command.command_id, result.returncode, result.elapsed_ms, backend))
    return tuple(audits)


def sandbox_argv(backend: str | None, root: Path, command_argv: Sequence[str]) -> tuple[str, ...]:
    command = tuple(command_argv)
    if backend is None:
        return command
    if backend == "docker":
        return ("docker", "run", "--rm", "--network", "none", "-v", f"{root}:/workspace", "-w", "/workspace", "python:3", *command)
    if backend == "bwrap":
        return ("bwrap", "--unshare-net", "--bind", str(root), str(root), "--chdir", str(root), *command)
    if backend == "sandbox-exec":
        profile = f"(version 1) (deny default) (allow process*) (allow file-read* (subpath \"{root}\")) (allow file-write* (subpath \"{root}\"))"
        return ("sandbox-exec", "-p", profile, *command)
    return command


def parse_pi_eval_events(text: str, workspace: PreparedWorkspace, fixture: FixturePolicy) -> ParsedEvalOutput:
    return _parse_eval_events(text, workspace, fixture, runtime="pi")


def parse_opencode_eval_events(text: str, workspace: PreparedWorkspace, fixture: FixturePolicy) -> ParsedEvalOutput:
    return _parse_eval_events(text, workspace, fixture, runtime="opencode")


def with_changed_paths(result: RoleEvalResult, changed_paths: tuple[str, ...]) -> RoleEvalResult:
    audit = replace(result.audit, changed_paths=changed_paths)
    return replace(result, audit=audit)


def changed_paths_from_git_diff(result: CompletedCommand, workspace: PreparedWorkspace) -> tuple[str, ...]:
    if result.returncode != 0 or result.timed_out or result.stdout_truncated:
        return ()
    paths: list[str] = []
    for line in result.stdout.splitlines():
        normalized = _normalize_workspace_path(workspace, line.strip())
        if normalized and normalized not in paths:
            paths.append(normalized)
    return tuple(paths)


def append_command_audits(result: RoleEvalResult, command_runs: tuple[CommandAudit, ...], status: str | None = None, reason_codes: tuple[str, ...] | None = None) -> RoleEvalResult:
    audit = replace(result.audit, command_runs=result.audit.command_runs + command_runs)
    return replace(result, audit=audit, status=status or result.status, reason_codes=reason_codes if reason_codes is not None else result.reason_codes)


def opencode_eval_config(request: RoleEvalRequest, agent_name: str) -> dict[str, Any]:
    workspace = str(_resolved(request.workspace.root))
    write_rules = {"*": "deny"}
    for item in request.fixture.allowed_write_paths:
        write_rules[f"{_resolve_policy_path(request.workspace, item)}/**"] = "allow"
    return {
        "permission": {"*": "deny", "external_directory": "deny"},
        "agent": {
            agent_name: {
                "description": "isolated model optimizer evaluation",
                "prompt": request.agent.body,
                "model": request.route.model,
                "variant": request.route.effort,
                "permission": {
                    "*": "deny",
                    "external_directory": "deny",
                    "read": {"*": "deny", f"{workspace}/**": "allow"},
                    "edit": write_rules,
                    "bash": "deny",
                },
            }
        },
    }


def effective_config_matches(actual: Any, expected: Mapping[str, Any], agent_name: str) -> bool:
    if not isinstance(actual, Mapping):
        return False
    return actual.get("permission") == expected.get("permission") and isinstance(actual.get("agent"), Mapping) and actual["agent"].get(agent_name) == expected["agent"][agent_name]


def isolated_opencode_env(context_env: Mapping[str, str], xdg_config_home: Path) -> dict[str, str]:
    env: dict[str, str] = {"XDG_CONFIG_HOME": str(xdg_config_home)}
    for key, value in context_env.items():
        if not key.startswith("OPENCODE_"):
            continue
        if key in {"OPENCODE_CONFIG_CONTENT", "OPENCODE_PERMISSION"}:
            continue
        env[key] = value
    if "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]
    return env


def safe_diagnostic(text: str) -> str:
    return redact_text(text or "")[:240]


def _parse_eval_events(text: str, workspace: PreparedWorkspace, fixture: FixturePolicy, *, runtime: str) -> ParsedEvalOutput:
    root = _resolved(workspace.root)
    allowed_by_argv = {command.argv: command.command_id for command in fixture.allowed_commands}
    tools: set[str] = set()
    unauthorized: set[str] = set()
    command_runs: list[CommandAudit] = []
    changed: list[str] = []
    reason_codes: list[str] = []
    outside_attempts = 0
    malformed = False
    saw_required_success: set[str] = set()

    for raw_line in (text or "").splitlines():
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            malformed = True
            break
        if not isinstance(event, Mapping):
            continue
        if event.get("truncated") is True:
            _append_unique(reason_codes, "eval_truncated_audit_stream")
        event_type = event.get("type")
        if runtime == "opencode" and event_type == "permission_ask":
            _append_unique(reason_codes, "eval_permission_ask")
            continue
        if event_type == "error":
            detail = json.dumps(event.get("error", event), sort_keys=True, default=str)
            if re.search(r"rate.?limit|quota", detail, re.IGNORECASE):
                _append_unique(reason_codes, "eval_rate_limited")
            else:
                _append_unique(reason_codes, "eval_runtime_error")
            continue
        tool = event.get("tool") or event.get("tool_name")
        if isinstance(tool, str):
            tools.add(tool)
            if tool.startswith("subagent_"):
                unauthorized.add(tool)
        path_value = event.get("path") or event.get("file")
        if isinstance(path_value, str):
            normalized = _normalize_workspace_path(workspace, path_value)
            if normalized is None:
                outside_attempts += 1
            elif tool in {"write", "edit"} and normalized not in changed:
                changed.append(normalized)
        argv_value = event.get("argv")
        if isinstance(argv_value, list) and all(isinstance(arg, str) for arg in argv_value):
            argv = tuple(argv_value)
            command_id = allowed_by_argv.get(argv)
            if command_id is None:
                unauthorized.add("bash")
                continue
            exit_code = event.get("exit_code") if isinstance(event.get("exit_code"), int) else None
            elapsed_ms = event.get("elapsed_ms") if isinstance(event.get("elapsed_ms"), int) and event.get("elapsed_ms") >= 0 else 0
            backend = event.get("sandbox_backend") if isinstance(event.get("sandbox_backend"), str) and event.get("sandbox_backend") else (workspace.sandbox_backend or "unknown")
            command_runs.append(CommandAudit(command_id, exit_code, elapsed_ms, backend))
            if exit_code == 0:
                saw_required_success.add(command_id)
        usage = event.get("usage")
        # Usage is intentionally not persisted here unless it is structural and bounded.
        if isinstance(usage, Mapping):
            pass

    if malformed:
        _append_unique(reason_codes, "eval_malformed_audit_stream")
    if outside_attempts:
        _append_unique(reason_codes, "eval_outside_workspace_attempt")
    required_ids = {command.command_id for command in fixture.allowed_commands}
    if fixture.allowed_commands and not required_ids.issubset(saw_required_success):
        _append_unique(reason_codes, "eval_missing_required_command_audit")
    if unauthorized:
        _append_unique(reason_codes, "eval_unauthorized_tool")
    status = "PASS" if not reason_codes else "INCONCLUSIVE"
    audit = ToolAudit(tuple(sorted(tools)), tuple(command_runs), tuple(changed), outside_attempts, tuple(sorted(unauthorized)))
    return ParsedEvalOutput(status=status, final_text="", audit=audit, reason_codes=tuple(reason_codes))


def _validate_marker(workspace: PreparedWorkspace, fixture: FixturePolicy) -> None:
    marker = _resolved(workspace.root) / _MARKER_NAME
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("eval_workspace_marker_missing") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("eval_workspace_marker_invalid") from exc
    expected = {
        "token": workspace.token,
        "fixture_id": fixture.fixture_id,
        "fixture_version": fixture.fixture_version,
        "manifest_digest": fixture.manifest_digest,
        "grader_id": fixture.grader_id,
    }
    if value.get("token") != expected["token"]:
        raise ValueError("eval_workspace_token_mismatch")
    for key in ("fixture_id", "fixture_version", "manifest_digest", "grader_id"):
        if value.get(key) != expected[key]:
            raise ValueError("eval_fixture_marker_mismatch")


def _has_fresh_pass_attestation(tool_name: str, fixture: FixturePolicy) -> bool:
    now = datetime.now(timezone.utc)
    for attestation in fixture.capability_attestations:
        if attestation.tool_name != tool_name or attestation.status != "PASS" or attestation.probe_digest != fixture.manifest_digest:
            continue
        observed = _parse_timestamp(attestation.observed_at)
        if observed is None:
            continue
        if now - observed <= timedelta(seconds=_FRESH_ATTESTATION_SECONDS):
            return True
    return False


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_policy_path(workspace: PreparedWorkspace, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("eval_invalid_policy_path")
    path = Path(value)
    if path.is_absolute():
        resolved = _resolved(path)
    else:
        resolved = _resolved(workspace.root / path)
    if not _is_relative_to(resolved, _resolved(workspace.root)):
        raise ValueError("eval_policy_path_escape")
    return resolved


def _normalize_workspace_path(workspace: PreparedWorkspace, value: str) -> str | None:
    if not value:
        return None
    try:
        resolved = _resolve_policy_path(workspace, value)
    except ValueError:
        return None
    try:
        return resolved.relative_to(_resolved(workspace.root)).as_posix()
    except ValueError:
        return None


def _scrubbed_env(env: Mapping[str, str]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in env.items():
        if key == "PATH" or key.startswith("PYTHON"):
            safe[key] = value
            continue
        if _SECRET_ENV_RE.search(key):
            continue
    if "PATH" not in safe and "PATH" in os.environ:
        safe["PATH"] = os.environ["PATH"]
    return safe


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)
