from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
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
_ALLOWED_BUILTIN_TOOLS = frozenset({"read", "write", "edit", "bash", "grep", "find", "ls"})
_SECRET_ENV_RE = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|COOKIE|AUTHORIZATION|CREDENTIAL", re.IGNORECASE)
_REQUIRED_SANDBOX_TESTS = frozenset({"workspace_write", "outside_read_denied", "secret_env_denied", "network_denied"})
_SUPPORTED_SANDBOX_BACKENDS = frozenset({"sandbox-exec", "bwrap"})
_CAPABILITY_PROBE_REGISTRY = {
    "custom_safe": frozenset({"capability:custom_safe:confined-tool-v1"}),
}
_MAX_AUDIT_ITEMS = 128
_MAX_AUDIT_TEXT = 240
_MAX_ELAPSED_MS = 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class ProbeObservation:
    probe_id: str
    argv: tuple[str, ...]
    executable_identity: str
    profile_identity: str
    expected_outcome: str
    status: str
    returncode: int | None
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool
    stdout_digest: str
    stderr_digest: str
    observed_at: str


@dataclass(frozen=True)
class SandboxAttestation:
    backend: str
    workspace_root: str
    workspace_token: str
    profile_identity: str
    profile_digest: str
    observed_at: str
    probe_observations: tuple[ProbeObservation, ...]
    executable_identity: str = "unknown"


@dataclass(frozen=True)
class PreparedWorkspace:
    root: Path
    token: str
    sandbox_attestation: SandboxAttestation | None

    @property
    def sandbox_backend(self) -> str | None:
        return self.sandbox_attestation.backend if self.sandbox_attestation else None


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


@dataclass(frozen=True)
class ChangedPathsResult:
    status: str
    paths: tuple[str, ...]
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
        "sandbox_attestation": {
            "backend": request.workspace.sandbox_attestation.backend,
            "workspace_root": request.workspace.sandbox_attestation.workspace_root,
            "workspace_token": request.workspace.sandbox_attestation.workspace_token,
            "profile_identity": request.workspace.sandbox_attestation.profile_identity,
            "profile_digest": request.workspace.sandbox_attestation.profile_digest,
            "observed_at": request.workspace.sandbox_attestation.observed_at,
            "probe_observations": [
                {
                    "probe_id": observation.probe_id,
                    "argv": list(observation.argv),
                    "executable_identity": observation.executable_identity,
                    "profile_identity": observation.profile_identity,
                    "expected_outcome": observation.expected_outcome,
                    "status": observation.status,
                    "returncode": observation.returncode,
                    "timed_out": observation.timed_out,
                    "stdout_truncated": observation.stdout_truncated,
                    "stderr_truncated": observation.stderr_truncated,
                    "stdout_digest": observation.stdout_digest,
                    "stderr_digest": observation.stderr_digest,
                    "observed_at": observation.observed_at,
                }
                for observation in request.workspace.sandbox_attestation.probe_observations
            ],
        } if request.workspace.sandbox_attestation else None,
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


def validate_role_eval_request(request: RoleEvalRequest, *, now: datetime | None = None) -> None:
    recomputed_digest = canonical_fixture_digest(request.fixture)
    if request.fixture.manifest_digest != recomputed_digest:
        raise ValueError("eval_fixture_manifest_digest_mismatch")
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
    if request.fixture.requires_code_execution:
        _validate_sandbox_attestation(request.workspace, now=now)
    for policy_path in (*request.fixture.allowed_read_paths, *request.fixture.allowed_write_paths):
        _resolve_policy_path(request.workspace, policy_path)
    command_ids: set[str] = set()
    command_argvs: set[tuple[str, ...]] = set()
    for command in request.fixture.allowed_commands:
        if not _STABLE_ID_RE.fullmatch(command.command_id):
            raise ValueError("eval_unstable_command_id")
        if not command.argv or not all(isinstance(arg, str) and arg and "\x00" not in arg for arg in command.argv):
            raise ValueError("eval_invalid_allowed_command")
        if command.command_id in command_ids or command.argv in command_argvs:
            raise ValueError("eval_ambiguous_allowed_command")
        command_ids.add(command.command_id)
        command_argvs.add(command.argv)
    for tool_name in request.requirements.essential_custom_tools:
        if not _has_fresh_pass_attestation(tool_name, request, now=now):
            raise ValueError("eval_essential_custom_tool_unproven")


def unsupported_custom_tools(agent: AgentContract) -> tuple[str, ...]:
    return tuple(tool for tool in agent.tools if tool not in _ALLOWED_BUILTIN_TOOLS)


def select_sandbox_backend(runner: Any, workspace: PreparedWorkspace, *, now: datetime | None = None) -> SandboxAttestation | None:
    root = _resolved(workspace.root)
    outside: Path | None = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        fd, outside_name = tempfile.mkstemp(prefix=f".model-optimizer-outside-{workspace.token}-", dir=str(root.parent), text=True)
        outside = Path(outside_name)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("outside-sentinel")
    except OSError:
        return None
    probe_scripts: tuple[tuple[str, tuple[str, ...], str], ...] = (
        ("workspace_write", ("python3", "-c", "from pathlib import Path; p=Path('sandbox-probe.txt'); p.write_text('ok'); print(p.read_text())"), "ok"),
        ("outside_read_denied", ("python3", "-c", f"from pathlib import Path; p=Path({str(outside)!r});\ntry:\n p.read_text(); raise SystemExit(7)\nexcept Exception:\n print('denied')"), "denied"),
        ("secret_env_denied", ("python3", "-c", "import os\nif os.getenv('SECRET_SENTINEL'):\n raise SystemExit(8)\nprint('absent')"), "absent"),
        ("network_denied", ("python3", "-c", "import socket; s=socket.socket();\ntry:\n s.bind(('127.0.0.1', 0)); raise SystemExit(9)\nexcept OSError:\n print('denied')"), "denied"),
    )
    observed_now = now or datetime.now(timezone.utc)
    try:
        for backend in ("sandbox-exec", "bwrap"):
            executable = shutil.which(backend)
            if executable is None:
                continue
            executable_identity = _executable_identity(executable, backend)
            profile_identity = _sandbox_profile(backend, root)
            observations: list[ProbeObservation] = []
            failed = False
            for probe_id, command, expected in probe_scripts:
                argv = sandbox_argv(backend, root, command)
                try:
                    result = runner.run(argv, timeout=5, cwd=workspace.root, env_replacement=_minimal_env(), stdout_limit=MAX_STDOUT_LIMIT_CHARS)
                except Exception:
                    failed = True
                    break
                status = "PASS" if result.returncode == 0 and not result.timed_out and not result.stdout_truncated and expected in result.stdout else "FAIL"
                observation = probe_observation_from_result(
                    probe_id=probe_id,
                    argv=argv,
                    executable_identity=executable_identity,
                    profile_identity=profile_identity,
                    expected_outcome=expected,
                    status=status,
                    result=result,
                    observed_at=observed_now,
                )
                observations.append(observation)
                if status != "PASS":
                    failed = True
                    break
            if failed:
                continue
            if {item.probe_id for item in observations} != _REQUIRED_SANDBOX_TESTS:
                continue
            digest = sandbox_attestation_digest(backend, root, workspace.token, executable_identity, profile_identity, tuple(observations))
            return SandboxAttestation(
                backend=backend,
                workspace_root=str(root),
                workspace_token=workspace.token,
                profile_identity=profile_identity,
                profile_digest=digest,
                observed_at=_datetime_text(observed_now),
                probe_observations=tuple(observations),
                executable_identity=executable_identity,
            )
    finally:
        if outside is not None:
            try:
                outside.unlink()
            except FileNotFoundError:
                pass
    return None


def run_manifest_commands(
    runner: Any,
    workspace: PreparedWorkspace,
    fixture: FixturePolicy,
    backend: str | SandboxAttestation | None,
    *,
    timeout: float,
    env: Mapping[str, str] | None = None,
) -> tuple[CommandAudit, ...]:
    backend_name = _backend_name(backend)
    if backend_name is None:
        return ()
    if workspace.sandbox_attestation is not None and backend_name != workspace.sandbox_attestation.backend:
        raise ValueError("eval_sandbox_attestation_mismatch")
    root = _resolved(workspace.root)
    audits: list[CommandAudit] = []
    if len(fixture.allowed_commands) > _MAX_AUDIT_ITEMS:
        raise ValueError("eval_audit_too_large")
    for command in fixture.allowed_commands:
        argv = sandbox_argv(backend_name, root, command.argv)
        result = runner.run(argv, timeout=timeout, cwd=workspace.root, env_replacement=_scrubbed_env(env or {}), stdout_limit=MAX_STDOUT_LIMIT_CHARS)
        audit = validate_command_audit(CommandAudit(command.command_id, None if result.timed_out else result.returncode, result.elapsed_ms, backend_name))
        audits.append(audit)
    return tuple(audits)


def sandbox_argv(backend: str | None, root: Path, command_argv: Sequence[str]) -> tuple[str, ...]:
    command = tuple(command_argv)
    if backend is None:
        raise ValueError("eval_sandbox_unavailable")
    if backend == "bwrap":
        return ("bwrap", "--unshare-net", "--bind", str(root), str(root), "--chdir", str(root), *command)
    if backend == "sandbox-exec":
        return ("sandbox-exec", "-p", _sandbox_profile("sandbox-exec", root), *command)
    raise ValueError("eval_sandbox_unknown_backend")


def parse_pi_eval_events(text: str, workspace: PreparedWorkspace, fixture: FixturePolicy) -> ParsedEvalOutput:
    return _parse_eval_events(text, workspace, fixture, runtime="pi")


def parse_opencode_eval_events(text: str, workspace: PreparedWorkspace, fixture: FixturePolicy) -> ParsedEvalOutput:
    return _parse_eval_events(text, workspace, fixture, runtime="opencode")


def with_changed_paths(result: RoleEvalResult, changed_paths: tuple[str, ...]) -> RoleEvalResult:
    audit = replace(result.audit, changed_paths=changed_paths)
    return replace(result, audit=audit)


def with_changed_paths_result(result: RoleEvalResult, changed: ChangedPathsResult) -> RoleEvalResult:
    if changed.status != "PASS":
        return replace(result, status="INCONCLUSIVE", reason_codes=tuple(dict.fromkeys((*result.reason_codes, *changed.reason_codes))))
    return with_changed_paths(result, changed.paths)


def changed_paths_from_git_status(result: CompletedCommand, workspace: PreparedWorkspace) -> ChangedPathsResult:
    if result.returncode != 0 or result.timed_out or result.stdout_truncated:
        return ChangedPathsResult("INCONCLUSIVE", (), ("eval_changed_paths_unavailable",))
    if result.stdout_decode_replaced:
        return ChangedPathsResult("INCONCLUSIVE", (), ("eval_changed_paths_invalid",))
    if result.stdout == "":
        return ChangedPathsResult("PASS", ())
    if "\x00" not in result.stdout:
        return ChangedPathsResult("INCONCLUSIVE", (), ("eval_changed_paths_invalid",))
    fields = result.stdout.split("\x00")
    if fields and fields[-1] == "":
        fields = fields[:-1]
    paths: list[str] = []
    index = 0
    while index < len(fields):
        record = fields[index]
        if len(record) < 4 or record[2] != " ":
            return ChangedPathsResult("INCONCLUSIVE", (), ("eval_changed_paths_invalid",))
        status = record[:2]
        candidate = record[3:]
        index += 1
        candidates = [candidate]
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            if index >= len(fields):
                return ChangedPathsResult("INCONCLUSIVE", (), ("eval_changed_paths_invalid",))
            candidates.append(fields[index])
            index += 1
        for item in candidates:
            normalized = _normalize_workspace_path(workspace, item)
            if normalized is None or not _bounded_audit_text(normalized) or not _valid_utf8_text(normalized):
                return ChangedPathsResult("INCONCLUSIVE", (), ("eval_changed_paths_invalid",))
            if normalized not in paths:
                if len(paths) >= _MAX_AUDIT_ITEMS:
                    return ChangedPathsResult("INCONCLUSIVE", (), ("eval_changed_paths_too_large",))
                paths.append(normalized)
    return ChangedPathsResult("PASS", tuple(paths))


def changed_paths_from_git_diff(result: CompletedCommand, workspace: PreparedWorkspace) -> tuple[str, ...]:
    return changed_paths_from_git_status(result, workspace).paths


def append_command_audits(result: RoleEvalResult, command_runs: tuple[CommandAudit, ...], status: str | None = None, reason_codes: tuple[str, ...] | None = None) -> RoleEvalResult:
    try:
        validated_existing = tuple(validate_command_audit(item) for item in result.audit.command_runs)
        validated_new = tuple(validate_command_audit(item) for item in command_runs)
        combined = validated_existing + validated_new
        if len(combined) > _MAX_AUDIT_ITEMS:
            raise ValueError("eval_audit_too_large")
    except ValueError as exc:
        reasons = tuple(dict.fromkeys((*result.reason_codes, str(exc) or "eval_invalid_command_audit")))
        return replace(result, status="INCONCLUSIVE", reason_codes=reasons)
    expected_backend = combined[0].sandbox_backend if combined else None
    try:
        audit = validate_tool_audit(
            replace(result.audit, command_runs=combined),
            expected_backend=expected_backend,
        )
    except ValueError as exc:
        reasons = tuple(dict.fromkeys((*result.reason_codes, str(exc) or "eval_invalid_tool_audit")))
        return replace(result, status="INCONCLUSIVE", reason_codes=reasons)
    return replace(result, audit=audit, status=status or result.status, reason_codes=reason_codes if reason_codes is not None else result.reason_codes)


def validate_command_audit(audit: CommandAudit) -> CommandAudit:
    if not isinstance(audit, CommandAudit):
        raise ValueError("eval_invalid_command_audit")
    if not isinstance(audit.command_id, str) or not _STABLE_ID_RE.fullmatch(audit.command_id) or not _bounded_audit_text(audit.command_id):
        raise ValueError("eval_invalid_command_audit")
    if audit.exit_code is not None and not (isinstance(audit.exit_code, int) and not isinstance(audit.exit_code, bool) and 0 <= audit.exit_code <= 255):
        raise ValueError("eval_invalid_command_audit")
    if not (isinstance(audit.elapsed_ms, int) and not isinstance(audit.elapsed_ms, bool) and 0 <= audit.elapsed_ms <= _MAX_ELAPSED_MS):
        raise ValueError("eval_invalid_command_audit")
    if not isinstance(audit.sandbox_backend, str) or not _STABLE_ID_RE.fullmatch(audit.sandbox_backend) or not _bounded_audit_text(audit.sandbox_backend):
        raise ValueError("eval_invalid_command_audit")
    return audit


def validate_tool_audit(audit: ToolAudit, *, expected_backend: str | None) -> ToolAudit:
    if not isinstance(audit, ToolAudit):
        raise ValueError("eval_invalid_tool_audit")
    if not (isinstance(audit.outside_workspace_attempts, int) and not isinstance(audit.outside_workspace_attempts, bool) and 0 <= audit.outside_workspace_attempts <= _MAX_AUDIT_ITEMS):
        raise ValueError("eval_invalid_tool_audit")
    if len(audit.tool_names) > _MAX_AUDIT_ITEMS or len(audit.command_runs) > _MAX_AUDIT_ITEMS or len(audit.changed_paths) > _MAX_AUDIT_ITEMS or len(audit.unauthorized_tools) > _MAX_AUDIT_ITEMS:
        raise ValueError("eval_audit_too_large")

    validated_tools: list[str] = []
    for tool in audit.tool_names:
        if not isinstance(tool, str) or not _STABLE_ID_RE.fullmatch(tool) or not _bounded_audit_text(tool):
            raise ValueError("eval_invalid_tool_audit")
        validated_tools.append(tool)

    validated_changed: list[str] = []
    for path in audit.changed_paths:
        if not isinstance(path, str) or not _bounded_audit_text(path):
            raise ValueError("eval_invalid_tool_audit")
        validated_changed.append(path)

    validated_unauthorized: list[str] = []
    for tool in audit.unauthorized_tools:
        if not isinstance(tool, str) or not _bounded_audit_text(tool):
            raise ValueError("eval_invalid_tool_audit")
        validated_unauthorized.append(tool)

    validated_commands = tuple(validate_command_audit(item) for item in audit.command_runs)
    if expected_backend is not None and any(item.sandbox_backend != expected_backend for item in validated_commands):
        raise ValueError("eval_invalid_tool_audit")

    return ToolAudit(tuple(validated_tools), validated_commands, tuple(validated_changed), audit.outside_workspace_attempts, tuple(validated_unauthorized))


def build_tool_audit(
    *,
    tool_names: Sequence[str],
    command_runs: Sequence[CommandAudit],
    changed_paths: Sequence[str],
    outside_workspace_attempts: int,
    unauthorized_tools: Sequence[str],
    expected_backend: str | None,
) -> ToolAudit:
    audit = ToolAudit(tuple(tool_names), tuple(command_runs), tuple(changed_paths), outside_workspace_attempts, tuple(unauthorized_tools))
    return validate_tool_audit(audit, expected_backend=expected_backend)


def canonical_fixture_digest(fixture: FixturePolicy) -> str:
    payload = {
        "fixture_id": fixture.fixture_id,
        "fixture_version": fixture.fixture_version,
        "grader_id": fixture.grader_id,
        "allowed_read_paths": list(fixture.allowed_read_paths),
        "allowed_write_paths": list(fixture.allowed_write_paths),
        "allowed_commands": [{"command_id": command.command_id, "argv": list(command.argv)} for command in fixture.allowed_commands],
        "requires_code_execution": fixture.requires_code_execution,
    }
    return _digest_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def sandbox_attestation_digest(
    backend: str,
    root: Path,
    token: str,
    executable_identity: str,
    profile_identity: str,
    probe_observations: Sequence[ProbeObservation],
) -> str:
    payload = {
        "backend": backend,
        "workspace_root": str(_resolved(root)),
        "workspace_token": token,
        "profile_identity": profile_identity,
        "executable_identity": executable_identity,
        "probe_observations": [probe_observation_payload(item) for item in probe_observations],
    }
    return _digest_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def probe_observation_payload(observation: ProbeObservation) -> dict[str, Any]:
    return {
        "probe_id": observation.probe_id,
        "argv": list(observation.argv),
        "executable_identity": observation.executable_identity,
        "profile_identity": observation.profile_identity,
        "expected_outcome": observation.expected_outcome,
        "status": observation.status,
        "returncode": observation.returncode,
        "timed_out": observation.timed_out,
        "stdout_truncated": observation.stdout_truncated,
        "stderr_truncated": observation.stderr_truncated,
        "stdout_digest": observation.stdout_digest,
        "stderr_digest": observation.stderr_digest,
        "observed_at": observation.observed_at,
    }


def probe_observation_from_result(
    *,
    probe_id: str,
    argv: Sequence[str],
    executable_identity: str,
    profile_identity: str,
    expected_outcome: str,
    status: str,
    result: CompletedCommand,
    observed_at: datetime,
) -> ProbeObservation:
    return ProbeObservation(
        probe_id=probe_id,
        argv=tuple(argv),
        executable_identity=executable_identity,
        profile_identity=profile_identity,
        expected_outcome=expected_outcome,
        status=status,
        returncode=result.returncode,
        timed_out=result.timed_out,
        stdout_truncated=result.stdout_truncated,
        stderr_truncated=result.stderr_truncated,
        stdout_digest=_digest_text(result.stdout),
        stderr_digest=_digest_text(result.stderr),
        observed_at=_datetime_text(observed_at),
    )


def capability_probe_digest(
    request: RoleEvalRequest,
    tool_name: str,
    probe_id: str,
    *,
    status: str,
    observed_at: str,
) -> str:
    payload = {
        "probe_id": probe_id,
        "tool_name": tool_name,
        "status": status,
        "observed_at": observed_at,
        "workspace_root": str(_resolved(request.workspace.root)),
        "workspace_token": request.workspace.token,
        "fixture_digest": request.fixture.manifest_digest,
        "route": {
            "runtime_kind": request.route.runtime_kind.value,
            "runtime_version": request.route.runtime_version,
            "model": request.route.model,
            "effort": request.route.effort,
        },
        "sandbox_attestation_digest": request.workspace.sandbox_attestation.profile_digest if request.workspace.sandbox_attestation else None,
    }
    return _digest_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


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
    expected_safe_defaults = {
        "mode": {},
        "username": "unknown",
        "plugin": [],
        "plugins": [],
        "instructions": [],
        "mcp": {},
        "tool": {},
        "tools": {},
        "provider": {},
        "model": {},
        "share": "manual",
        "autoshare": False,
        "compaction": {},
    }
    allowed_top = {"$schema", "permission", "agent", "mode", "username", *expected_safe_defaults.keys()}
    for key, value in actual.items():
        if not isinstance(key, str) or key not in allowed_top:
            return False
        if key in expected_safe_defaults and value != expected_safe_defaults[key]:
            return False
    agents = actual.get("agent")
    if not isinstance(agents, Mapping) or set(agents.keys()) != {agent_name}:
        return False
    return actual.get("permission") == expected.get("permission") and agents.get(agent_name) == expected["agent"][agent_name]


_PROVIDER_AUTH_ENV = {
    "openai": ("OPENAI_API_KEY", "OPENAI_AUTH_TOKEN"),
    "nan": ("OPENCODE_TOKEN", "NAN_API_KEY"),
    "minimax-coding-plan": ("MINIMAX_API_KEY",),
    "zai-coding-plan": ("ZAI_API_KEY",),
}


def isolated_opencode_env(context_env: Mapping[str, str], xdg_config_home: Path, xdg_data_home: Path | None = None, provider: str | None = None) -> dict[str, str] | None:
    env: dict[str, str] = {"XDG_CONFIG_HOME": str(xdg_config_home)}
    if xdg_data_home is not None:
        env["XDG_DATA_HOME"] = str(xdg_data_home)
    channels = _PROVIDER_AUTH_ENV.get(provider or "")
    if channels is None:
        return None
    preserved = False
    for key in channels:
        value = context_env.get(key)
        if value:
            env[key] = value
            preserved = True
    if not preserved:
        return None
    if "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]
    return env


def safe_diagnostic(text: str) -> str:
    return redact_text(text or "")[:240]


def essential_eval_selection_status(results: Sequence[RoleEvalResult]) -> tuple[str, tuple[str, ...]]:
    """Pure selection guard: unsafe essential evaluation infrastructure forces ABSTAIN."""
    unsafe_reasons = {
        "eval_sandbox_unavailable",
        "eval_sandbox_attestation_mismatch",
        "eval_sandbox_attestation_incomplete",
        "eval_opencode_auth_unavailable",
        "eval_opencode_effective_config_mismatch",
        "eval_changed_paths_unavailable",
        "eval_changed_paths_invalid",
        "eval_truncated_audit_stream",
    }
    reasons: list[str] = []
    for result in results:
        if result.status in {"INCONCLUSIVE", "HANG"} and any(reason in unsafe_reasons for reason in result.reason_codes):
            for reason in result.reason_codes:
                if reason in unsafe_reasons:
                    _append_unique(reasons, reason)
    if reasons:
        return "ABSTAIN", tuple(reasons)
    return "CONTINUE", ()


def _parse_eval_events(text: str, workspace: PreparedWorkspace, fixture: FixturePolicy, *, runtime: str) -> ParsedEvalOutput:
    tools: set[str] = set()
    unauthorized: set[str] = set()
    command_runs: list[CommandAudit] = []
    changed: list[str] = []
    reason_codes: list[str] = []
    outside_attempts = 0
    malformed = False
    saw_required_success: set[str] = set()
    pi_started: dict[str, Mapping[str, Any]] = {}
    audit_overflow = False

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
        if event_type == "timeout" or event.get("timed_out") is True:
            _append_unique(reason_codes, "eval_timeout")
            continue
        if event_type == "error":
            detail = json.dumps(event.get("error", event), sort_keys=True, default=str)
            _append_unique(reason_codes, "eval_rate_limited" if re.search(r"rate.?limit|quota", detail, re.IGNORECASE) else "eval_runtime_error")
            continue
        if runtime == "pi":
            _parse_pi_runtime_event(event, workspace, tools, unauthorized, changed, command_runs, saw_required_success, reason_codes, pi_started)
        else:
            parsed_outside = _parse_opencode_runtime_event(event, workspace, tools, unauthorized, changed, command_runs, saw_required_success, reason_codes)
            outside_attempts += parsed_outside
        if len(tools) > _MAX_AUDIT_ITEMS or len(command_runs) > _MAX_AUDIT_ITEMS or len(changed) > _MAX_AUDIT_ITEMS or len(unauthorized) > _MAX_AUDIT_ITEMS:
            audit_overflow = True
            break

    if malformed:
        _append_unique(reason_codes, "eval_malformed_audit_stream")
    if audit_overflow:
        _append_unique(reason_codes, "eval_audit_too_large")

    outside_attempts += sum(1 for item in changed if item == "")
    changed = [item for item in changed if item]
    if outside_attempts:
        _append_unique(reason_codes, "eval_outside_workspace_attempt")
    if runtime == "pi" and pi_started:
        _append_unique(reason_codes, "eval_uncorrelated_tool_event")

    required_ids = {command.command_id for command in fixture.allowed_commands}
    audited_ids = {audit.command_id for audit in command_runs}
    if fixture.allowed_commands and not required_ids.issubset(audited_ids):
        _append_unique(reason_codes, "eval_missing_required_command_audit")
    if unauthorized:
        _append_unique(reason_codes, "eval_unauthorized_tool")

    expected_backend = workspace.sandbox_backend
    try:
        audit = build_tool_audit(
            tool_names=tuple(sorted(tools)),
            command_runs=tuple(command_runs),
            changed_paths=tuple(dict.fromkeys(changed)),
            outside_workspace_attempts=outside_attempts,
            unauthorized_tools=tuple(sorted(unauthorized)),
            expected_backend=expected_backend,
        )
    except ValueError as exc:
        _append_unique(reason_codes, str(exc) or "eval_invalid_tool_audit")
        audit = empty_audit()

    status = _status_from_audit(reason_codes, audit.command_runs, required_ids)
    return ParsedEvalOutput(status=status, final_text="", audit=audit, reason_codes=tuple(reason_codes))


def _status_from_audit(reason_codes: Sequence[str], command_runs: Sequence[CommandAudit], required_ids: set[str]) -> str:
    if any(reason == "eval_timeout" for reason in reason_codes):
        return "HANG"
    if any(reason == "eval_required_command_failed" for reason in reason_codes):
        return "FAIL"
    failed_required = {audit.command_id for audit in command_runs if audit.command_id in required_ids and audit.exit_code not in (0, None)}
    if failed_required:
        return "FAIL"
    if reason_codes:
        return "INCONCLUSIVE"
    return "PASS"


def _parse_pi_runtime_event(
    event: Mapping[str, Any],
    workspace: PreparedWorkspace,
    tools: set[str],
    unauthorized: set[str],
    changed: list[str],
    command_runs: list[CommandAudit],
    saw_required_success: set[str],
    reason_codes: list[str],
    started: dict[str, Mapping[str, Any]],
) -> None:
    event_type = event.get("type")
    if event_type == "tool_execution_start":
        call_id = event.get("toolCallId")
        tool = event.get("toolName")
        if isinstance(call_id, str) and isinstance(tool, str) and _bounded_audit_text(call_id) and _bounded_audit_text(tool):
            if len(tools) >= _MAX_AUDIT_ITEMS and tool not in tools:
                _append_unique(reason_codes, "eval_audit_too_large")
                return
            tools.add(tool)
            if tool.startswith("subagent_"):
                unauthorized.add(tool)
            started[call_id] = event
            args = event.get("args")
            if tool in {"write", "edit"} and isinstance(args, Mapping):
                path_value = args.get("path")
                if isinstance(path_value, str):
                    normalized = _normalize_workspace_path(workspace, path_value)
                    changed.append(normalized or "")
        return
    if event_type != "tool_execution_end":
        return
    call_id = event.get("toolCallId")
    tool = event.get("toolName")
    if not isinstance(call_id, str) or not isinstance(tool, str):
        _append_unique(reason_codes, "eval_uncorrelated_tool_event")
        return
    start = started.pop(call_id, None)
    if start is None or start.get("toolName") != tool:
        _append_unique(reason_codes, "eval_uncorrelated_tool_event")
        return
    tools.add(tool)
    if tool.startswith("subagent_"):
        unauthorized.add(tool)
    if tool == "bash":
        details = _event_details(event)
        audit = _command_audit_from_details(details, workspace.sandbox_backend)
        if audit is None:
            _append_unique(reason_codes, "eval_missing_required_command_audit")
            return
        if len(command_runs) >= _MAX_AUDIT_ITEMS:
            _append_unique(reason_codes, "eval_audit_too_large")
            return
        command_runs.append(audit)
        if audit.exit_code is None:
            _append_unique(reason_codes, "eval_timeout")
        elif audit.exit_code == 0:
            saw_required_success.add(audit.command_id)


def _parse_opencode_runtime_event(
    event: Mapping[str, Any],
    workspace: PreparedWorkspace,
    tools: set[str],
    unauthorized: set[str],
    changed: list[str],
    command_runs: list[CommandAudit],
    saw_required_success: set[str],
    reason_codes: list[str],
) -> int:
    event_type = event.get("type")
    if event_type in {"permission.asked", "permission.v2.asked", "permission_ask"}:
        _append_unique(reason_codes, "eval_permission_ask")
        return 0
    if event_type != "tool_use":
        return 0
    part = event.get("part")
    if not isinstance(part, Mapping) or part.get("type") != "tool":
        return 0
    tool = part.get("tool")
    if not isinstance(tool, str):
        return 0
    tools.add(tool)
    if tool.startswith("subagent_") or tool == "task":
        unauthorized.add(tool)
    state = part.get("state")
    if not isinstance(state, Mapping):
        return 0
    input_value = state.get("input")
    outside = 0
    if tool in {"write", "edit"} and isinstance(input_value, Mapping):
        path_value = input_value.get("path")
        if isinstance(path_value, str):
            normalized = _normalize_workspace_path(workspace, path_value)
            if normalized is None:
                outside += 1
            elif normalized not in changed:
                changed.append(normalized)
    if tool == "bash" and state.get("status") == "completed":
        audit = _command_audit_from_details(state.get("metadata"), workspace.sandbox_backend)
        if audit:
            if len(command_runs) >= _MAX_AUDIT_ITEMS:
                _append_unique(reason_codes, "eval_audit_too_large")
                return outside
            command_runs.append(audit)
            if audit.exit_code is None:
                _append_unique(reason_codes, "eval_timeout")
            elif audit.exit_code == 0:
                saw_required_success.add(audit.command_id)
        else:
            _append_unique(reason_codes, "eval_missing_required_command_audit")
    return outside


def _event_details(event: Mapping[str, Any]) -> Any:
    result = event.get("result")
    if isinstance(result, Mapping):
        details = result.get("details")
        if isinstance(details, Mapping):
            return details
        return result
    return None


def _command_audit_from_details(value: Any, default_backend: str | None) -> CommandAudit | None:
    if not isinstance(value, Mapping):
        return None
    command_id = value.get("command_id")
    if not isinstance(command_id, str) or not _STABLE_ID_RE.fullmatch(command_id) or not _bounded_audit_text(command_id):
        return None
    exit_code_value = value.get("exit_code")
    timed_out = value.get("timed_out") is True
    if exit_code_value is None and timed_out:
        exit_code = None
    elif isinstance(exit_code_value, int) and not isinstance(exit_code_value, bool) and 0 <= exit_code_value <= 255:
        exit_code = exit_code_value
    else:
        return None
    elapsed_value = value.get("elapsed_ms")
    if not (isinstance(elapsed_value, int) and not isinstance(elapsed_value, bool) and 0 <= elapsed_value <= _MAX_ELAPSED_MS):
        return None
    backend_value = value.get("sandbox_backend")
    if not isinstance(backend_value, str):
        return None
    if default_backend is not None and backend_value != default_backend:
        return None
    try:
        return validate_command_audit(CommandAudit(command_id, exit_code, elapsed_value, backend_value))
    except ValueError:
        return None


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


def _validate_sandbox_attestation(workspace: PreparedWorkspace, *, now: datetime | None = None) -> None:
    attestation = workspace.sandbox_attestation
    if attestation is None:
        raise ValueError("eval_sandbox_unavailable")
    root = _resolved(workspace.root)
    root_text = str(root)
    if attestation.backend not in _SUPPORTED_SANDBOX_BACKENDS:
        raise ValueError("eval_sandbox_unknown_backend")
    if attestation.workspace_root != root_text or attestation.workspace_token != workspace.token:
        raise ValueError("eval_sandbox_attestation_mismatch")
    if not _STABLE_ID_RE.fullmatch(attestation.backend):
        raise ValueError("eval_sandbox_unknown_backend")

    executable = shutil.which(attestation.backend)
    if executable is None:
        raise ValueError("eval_sandbox_unavailable")
    current_identity = _executable_identity(executable, attestation.backend)
    if attestation.executable_identity != current_identity:
        raise ValueError("eval_sandbox_attestation_mismatch")
    expected_profile = _sandbox_profile(attestation.backend, root)
    if attestation.profile_identity != expected_profile:
        raise ValueError("eval_sandbox_attestation_mismatch")

    expected_digest = sandbox_attestation_digest(
        attestation.backend,
        root,
        workspace.token,
        attestation.executable_identity,
        attestation.profile_identity,
        attestation.probe_observations,
    )
    if attestation.profile_digest != expected_digest:
        raise ValueError("eval_sandbox_attestation_mismatch")

    current_time = now or datetime.now(timezone.utc)
    observed = _parse_timestamp(attestation.observed_at)
    if observed is None or observed > current_time or current_time - observed > timedelta(seconds=_FRESH_ATTESTATION_SECONDS):
        raise ValueError("eval_sandbox_attestation_stale")

    if len(attestation.probe_observations) != len(_REQUIRED_SANDBOX_TESTS):
        raise ValueError("eval_sandbox_attestation_incomplete")
    probe_names: set[str] = set()
    for observation in attestation.probe_observations:
        if observation.probe_id not in _REQUIRED_SANDBOX_TESTS:
            raise ValueError("eval_sandbox_attestation_incomplete")
        if observation.status != "PASS":
            raise ValueError("eval_sandbox_attestation_incomplete")
        if observation.executable_identity != attestation.executable_identity:
            raise ValueError("eval_sandbox_attestation_mismatch")
        if observation.profile_identity != attestation.profile_identity:
            raise ValueError("eval_sandbox_attestation_mismatch")
        if not observation.argv or Path(observation.argv[0]).name != attestation.backend:
            raise ValueError("eval_sandbox_attestation_mismatch")
        observed_probe = _parse_timestamp(observation.observed_at)
        if observed_probe is None or observed_probe > current_time or current_time - observed_probe > timedelta(seconds=_FRESH_ATTESTATION_SECONDS):
            raise ValueError("eval_sandbox_attestation_stale")
        probe_names.add(observation.probe_id)
    if probe_names != _REQUIRED_SANDBOX_TESTS:
        raise ValueError("eval_sandbox_attestation_incomplete")


def _has_fresh_pass_attestation(tool_name: str, request: RoleEvalRequest, *, now: datetime | None = None) -> bool:
    current_time = now or datetime.now(timezone.utc)
    for attestation in request.fixture.capability_attestations:
        if attestation.tool_name != tool_name or attestation.status != "PASS":
            continue
        if attestation.probe_id not in _CAPABILITY_PROBE_REGISTRY.get(tool_name, frozenset()):
            continue
        if attestation.probe_digest != capability_probe_digest(
            request,
            tool_name,
            attestation.probe_id,
            status=attestation.status,
            observed_at=attestation.observed_at,
        ):
            continue
        observed = _parse_timestamp(attestation.observed_at)
        if observed is None or observed > current_time:
            continue
        if current_time - observed <= timedelta(seconds=_FRESH_ATTESTATION_SECONDS):
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


def _minimal_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]
    return env


def _backend_name(value: str | SandboxAttestation | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, SandboxAttestation):
        return value.backend
    return value


def _sandbox_profile(backend: str, root: Path) -> str:
    if backend == "sandbox-exec":
        return f"(version 1) (deny default) (allow process*) (allow file-read* (subpath \"{root}\")) (allow file-write* (subpath \"{root}\"))"
    return f"{backend}:{root}:network=none:env=minimal"


def _digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _datetime_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_now_text() -> str:
    return _datetime_text(datetime.now(timezone.utc))


def _bounded_audit_text(value: str, limit: int = _MAX_AUDIT_TEXT) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit and "\x00" not in value and _valid_utf8_text(value)


def _valid_utf8_text(value: str) -> bool:
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        return False
    return True


def _executable_identity(executable: str, backend: str) -> str:
    path = Path(executable)
    try:
        stat = path.stat()
        return f"{backend}:{path.resolve()}:{stat.st_ino}:{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        return f"{backend}:{executable}:unknown"


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
