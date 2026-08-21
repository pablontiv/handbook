from __future__ import annotations

import json
import math
import os
import re
import secrets
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from helper.artifacts import inventory_with_digest
from helper.models import (
    CurrentAssignment,
    Exclusion,
    HealthCheck,
    HealthStatus,
    Inventory,
    ModelRecord,
    ProviderReadiness,
    ReadinessStatus,
    RuntimeInfo,
    RuntimeKind,
)
from helper.runner import MAX_STDOUT_LIMIT_CHARS, redact_text

from . import RuntimeContext

DISPLAY_TO_PROVIDER = {
    "OpenAI": "openai",
    "MiniMax Token Plan (minimax.io)": "minimax-coding-plan",
    "Z.AI Coding Plan": "zai-coding-plan",
    "nan": "nan",
}

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_OPENCODE_AUTH_FRAME_PREFIXES = frozenset({"┌", "│", "●", "└"})
_SAFE_AUTH_TYPES = frozenset({"api", "oauth"})
_EXACT_ID_RE = re.compile(r"^[^\s/{]+/[^\s/{]+$")
_SECRET_KEY_RE = re.compile(r"token|key|secret|password|cookie|authorization|credential", re.IGNORECASE)
_SESSION_OR_REF_RE = re.compile(r"\b(?:ses|err)[_-][A-Za-z0-9_-]+\b", re.IGNORECASE)
_AUTH_PATH_RE = re.compile(r"(?:~|/[^\s]+)?(?:/\.local/share/opencode/auth\.json|opencode/auth\.json)")
_STRUCTURAL_AGENT_KEYS = {"variant", "temperature", "top_p", "steps", "reasoningEffort", "textVerbosity"}
_DEFAULT_TIMEOUT_SECONDS = 15
_MAX_DETAIL_CHARS = 240
_LOG_TAIL_CHARS = 4096
_PROBE_AGENT_PREFIX = "model-optimizer-probe-"
_PROBE_TOKEN_HEX_RE = re.compile(r"^[0-9a-f]{32}$")
_DENY_ALL_PERMISSION = {"*": "deny"}
_ALLOWED_PROBE_AGENT_KEYS = frozenset({"permission", "tools", "options"})

_ERROR_NAME_TO_REASON = {
    "ProviderModelNotFoundError": "live_provider_model_not_found",
}


@dataclass(frozen=True)
class RuntimeSnapshot:
    sources: tuple[str, ...]
    current_assignments: tuple[CurrentAssignment, ...]
    warnings: tuple[str, ...] = ()


def _strip_ansi(text: str) -> str:
    return _ANSI_CSI_RE.sub("", text or "")


def _bounded(text: str, limit: int = _MAX_DETAIL_CHARS) -> str:
    safe = _redact_diagnostic(text or "")
    compact = " ".join(safe.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _redact_diagnostic(text: str) -> str:
    redacted = redact_text(text or "")
    redacted = _AUTH_PATH_RE.sub("[REDACTED]", redacted)
    redacted = _SESSION_OR_REF_RE.sub("[REDACTED]", redacted)
    return redacted


def _auth_type_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized not in _SAFE_AUTH_TYPES:
        return None
    return normalized


def _normalize_opencode_auth_line(raw_line: str) -> str:
    line = (raw_line or "").strip()
    if not line:
        return ""
    if line[0] in _OPENCODE_AUTH_FRAME_PREFIXES:
        return line[1:].strip()
    return line


def parse_opencode_auth(text: str) -> tuple[ProviderReadiness, ...]:
    readiness: list[ProviderReadiness] = []
    for raw_line in _strip_ansi(text).splitlines():
        line = _normalize_opencode_auth_line(raw_line)
        if not line:
            continue
        if line.startswith("Credentials "):
            continue
        if re.fullmatch(r"\d+\s+credentials?", line):
            continue
        if " " in line:
            display, auth_type = line.rsplit(" ", 1)
        else:
            display, auth_type = line, None
        provider = DISPLAY_TO_PROVIDER.get(display)
        if provider is None:
            readiness.append(ProviderReadiness(
                "UNKNOWN",
                ReadinessStatus.UNKNOWN,
                None,
                "auth_unknown_provider_label",
            ))
            continue
        readiness.append(ProviderReadiness(
            provider,
            ReadinessStatus.READY,
            _auth_type_or_none(auth_type),
            "auth_ready",
        ))
    return tuple(readiness)


def parse_opencode_models_verbose(text: str) -> tuple[ModelRecord, ...]:
    records, _warnings = _parse_opencode_models_verbose_with_warnings(text)
    return records


def _parse_opencode_models_verbose_with_warnings(text: str) -> tuple[tuple[ModelRecord, ...], tuple[str, ...]]:
    lines = (text or "").splitlines()
    records: list[ModelRecord] = []
    warnings: list[str] = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(lines):
        exact_id = lines[index].strip()
        if not _is_exact_id_line(exact_id):
            index += 1
            continue
        json_start = _next_nonempty_line(lines, index + 1)
        if json_start is None:
            _append_unique(warnings, f"inventory_malformed_model_block:{exact_id}")
            break
        remaining = "\n".join(lines[json_start:])
        leading = len(remaining) - len(remaining.lstrip())
        try:
            value, end = decoder.raw_decode(remaining.lstrip())
        except json.JSONDecodeError:
            _append_unique(warnings, f"inventory_malformed_model_block:{exact_id}")
            next_index = _find_next_exact_id_line(lines, json_start + 1)
            if next_index is None:
                break
            index = next_index
            continue
        consumed = remaining[: leading + end]
        consumed_lines = consumed.count("\n") + 1
        index = json_start + consumed_lines
        record = _model_record_from_metadata(exact_id, value)
        if record is None:
            _append_unique(warnings, f"inventory_model_id_mismatch:{exact_id}")
            continue
        status_warning = _model_status_warning(exact_id, value)
        if status_warning:
            _append_unique(warnings, status_warning)
            continue
        records.append(record)
    return tuple(records), tuple(warnings)


def _is_exact_id_line(line: str) -> bool:
    return bool(_EXACT_ID_RE.fullmatch(line or ""))


def _next_nonempty_line(lines: Sequence[str], start: int) -> int | None:
    for index in range(start, len(lines)):
        if lines[index].strip():
            return index
    return None


def _find_next_exact_id_line(lines: Sequence[str], start: int) -> int | None:
    for index in range(start, len(lines)):
        if _is_exact_id_line(lines[index].strip()):
            return index
    return None


def _model_status_warning(exact_id: str, value: Any) -> str | None:
    if not isinstance(value, Mapping) or "status" not in value:
        return None
    status = value.get("status")
    if not isinstance(status, str):
        return f"inventory_model_status_invalid:{exact_id}"
    if status.lower() != "active":
        return f"inventory_model_status_excluded:{exact_id}"
    return None


def _model_record_from_metadata(exact_id: str, value: Any) -> ModelRecord | None:
    if not isinstance(value, Mapping):
        return None
    provider_id = _string_or_none(value.get("providerID"))
    model_id = _string_or_none(value.get("id"))
    if not provider_id or not model_id or f"{provider_id}/{model_id}" != exact_id:
        return None
    cost = _mapping_or_empty(value.get("cost"))
    cache = _mapping_or_empty(cost.get("cache"))
    limit = _mapping_or_empty(value.get("limit"))
    capabilities = _mapping_or_empty(value.get("capabilities"))
    input_caps = _mapping_or_empty(capabilities.get("input"))
    input_modes = tuple(
        key for key, enabled in input_caps.items()
        if isinstance(key, str) and enabled is True
    )
    variants_value = value.get("variants")
    variants = tuple(sorted(
        key for key in variants_value.keys()
        if isinstance(variants_value, Mapping) and isinstance(key, str)
    )) if isinstance(variants_value, Mapping) else ()
    return ModelRecord(
        exact_id=exact_id,
        provider=provider_id,
        model=model_id,
        family=_string_or_none(value.get("family")),
        context_window=_int_or_none(limit.get("context")),
        max_output=_int_or_none(limit.get("output")),
        reasoning=capabilities.get("reasoning") if isinstance(capabilities.get("reasoning"), bool) else None,
        input_modes=input_modes,
        tool_call=capabilities.get("toolcall") if isinstance(capabilities.get("toolcall"), bool) else None,
        cache_read=_float_or_none(cache.get("read")),
        cache_write=_float_or_none(cache.get("write")),
        input_cost=_float_or_none(cost.get("input")),
        output_cost=_float_or_none(cost.get("output")),
        variants=variants,
        provenance=("opencode models --verbose",),
    )


def parse_opencode_live_events(text: str, sentinel: str) -> tuple[bool, str]:
    matched, reason, _detail = _parse_opencode_live_events_detail(text, sentinel)
    return matched, reason


def _parse_opencode_live_events_detail(text: str, sentinel: str) -> tuple[bool, str, str]:
    if not isinstance(sentinel, str) or sentinel.strip() == "":
        return False, "live_invalid_sentinel", "invalid sentinel"
    chunks: list[str] = []
    saw_text_event = False
    saw_event = False
    for raw_line in (text or "").splitlines():
        if not raw_line.strip():
            continue
        saw_event = True
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            return False, "live_malformed_jsonl", "malformed JSONL event"
        if not isinstance(event, Mapping):
            continue
        event_type = event.get("type")
        if event_type == "error":
            detail, mapped = _error_event_detail_and_reason(event)
            return False, mapped or "live_runtime_error", detail or "runtime error event"
        if event_type == "text":
            part = event.get("part")
            if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                saw_text_event = True
                chunks.append(part["text"])
    output = "".join(chunks)
    if output and sentinel in output:
        return True, "live_sentinel_matched", output
    if not saw_text_event:
        return False, "live_empty_response", "no text events" if saw_event else "empty response"
    return False, "live_sentinel_missing", output


def _error_event_detail_and_reason(event: Mapping[str, Any]) -> tuple[str, str | None]:
    error = event.get("error")
    if not isinstance(error, Mapping):
        return "", None
    safe_name = error.get("name") if isinstance(error.get("name"), str) else ""
    reason = _ERROR_NAME_TO_REASON.get(safe_name)
    messages: list[str] = []
    data = error.get("data")
    if isinstance(data, Mapping) and isinstance(data.get("message"), str):
        messages.append(data["message"])
    if isinstance(error.get("message"), str):
        messages.append(error["message"])
    detail = "\n".join(messages)
    mapped = reason or _known_live_failure_reason(detail)
    if not detail and reason:
        detail = safe_name
    return detail, mapped


def _known_live_failure_reason(text: str) -> str | None:
    if "ProviderModelNotFoundError" in (text or ""):
        return "live_provider_model_not_found"
    if "model_not_supported" in (text or ""):
        return "live_model_not_supported"
    return None


def _known_live_failure_excerpt(text: str) -> str | None:
    for marker in ("ProviderModelNotFoundError", "model_not_supported"):
        position = (text or "").find(marker)
        if position >= 0:
            line_end = (text or "").find("\n", position)
            if line_end < 0:
                line_end = len(text or "")
            return (text or "")[position:line_end]
    return None


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        converted = float(value)
    except OverflowError:
        return None
    if not math.isfinite(converted) or converted <= 0:
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        converted = float(value)
    except OverflowError:
        return None
    if not math.isfinite(converted) or converted < 0:
        return None
    return converted


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _new_probe_agent_name() -> str | None:
    token = secrets.token_hex(16)
    if not isinstance(token, str) or _PROBE_TOKEN_HEX_RE.fullmatch(token) is None:
        return None
    return f"{_PROBE_AGENT_PREFIX}{token}"


def _live_probe_env_overlay(context: RuntimeContext, probe_agent_name: str) -> dict[str, str] | None:
    inline_config: dict[str, Any] = {
        "permission": dict(_DENY_ALL_PERMISSION),
        "agent": {probe_agent_name: {"permission": "deny"}},
    }
    env: dict[str, str] = {}
    if "PATH" in context.env:
        env["PATH"] = context.env["PATH"]
    elif "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]
    for key in ("OPENCODE_TOKEN", "OPENCODE_API_KEY", "OPENCODE_AUTH", "OPENCODE_CONSOLE_TOKEN"):
        if key in context.env:
            env[key] = context.env[key]
    env["OPENCODE_PERMISSION"] = json.dumps(_DENY_ALL_PERMISSION, sort_keys=True, separators=(",", ":"))
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(inline_config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return env


def _permission_is_deny_all(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "deny"
    if not isinstance(value, Mapping):
        return False
    if set(value.keys()) != {"*"}:
        return False
    decision = value.get("*")
    return isinstance(decision, str) and decision.strip().lower() == "deny"


def _recursive_deny_only(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _recursive_deny_only(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(_recursive_deny_only(item) for item in value)
    if isinstance(value, bool):
        return value is False
    if isinstance(value, str):
        return value.strip().lower() == "deny"
    return False


def _is_empty_options(value: Any) -> bool:
    if isinstance(value, Mapping):
        return len(value) == 0
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    return False


def _probe_agent_config_is_safe(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if "prompt" in value:
        return False
    if not _permission_is_deny_all(value.get("permission")):
        return False
    for key in value.keys():
        if not isinstance(key, str) or key not in _ALLOWED_PROBE_AGENT_KEYS:
            return False
    if "tools" in value and not _recursive_deny_only(value.get("tools")):
        return False
    if "options" in value and not _is_empty_options(value.get("options")):
        return False
    return True


def _effective_probe_agent_is_safe(value: Any, probe_agent_name: str) -> bool:
    if not isinstance(value, Mapping):
        return False
    agents = value.get("agent")
    if not isinstance(agents, Mapping):
        return False
    return _probe_agent_config_is_safe(agents.get(probe_agent_name))


def _is_json_structural(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int, float)):
        return not (isinstance(value, float) and not math.isfinite(value))
    if isinstance(value, list):
        return all(_is_json_structural(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_json_structural(item) for key, item in value.items())
    return False


def _is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_RE.search(key))


def _prune_secret_named_keys(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _prune_secret_named_keys(item)
            for key, item in value.items()
            if isinstance(key, str) and not _is_secret_key(key)
        }
    if isinstance(value, list):
        return [_prune_secret_named_keys(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_prune_secret_named_keys(item) for item in value)
    return value


def _load_json(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, f"inventory_malformed_config:{path.name}"
    except OSError:
        return None, f"inventory_unreadable_source:{path.name}"


def opencode_global_config_dir(home: Path, environ: Mapping[str, str] | None = None) -> Path:
    xdg_config_home = (environ or {}).get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home).expanduser() / "opencode"
    return home / ".config" / "opencode"


def opencode_project_config_path(cwd: Path) -> Path:
    return cwd / "opencode.json"


def _config_paths(context: RuntimeContext) -> tuple[tuple[str, Path], ...]:
    return (
        ("global", opencode_global_config_dir(context.home, context.env) / "opencode.json"),
        ("project", opencode_project_config_path(context.cwd)),
    )


def _source_label(scope: str, exists: bool) -> str:
    prefix = "" if exists else "missing:"
    return f"{prefix}{scope}:opencode.json"


def _assignments_from_config(value: Any, source: str) -> tuple[CurrentAssignment, ...]:
    if not isinstance(value, Mapping):
        return ()
    agents = value.get("agent")
    if not isinstance(agents, Mapping):
        return ()
    assignments: list[CurrentAssignment] = []
    for agent, config in sorted(agents.items()):
        if not isinstance(agent, str) or not isinstance(config, Mapping):
            continue
        model = _string_or_none(config.get("model"))
        if not model:
            continue
        options = {
            key: _prune_secret_named_keys(option)
            for key, option in config.items()
            if key in _STRUCTURAL_AGENT_KEYS and not _is_secret_key(key) and _is_json_structural(option)
        }
        assignments.append(CurrentAssignment(agent, model, options, source))
    return tuple(assignments)


def _providers_in_order(records: Iterable[ModelRecord]) -> tuple[str, ...]:
    providers: list[str] = []
    for record in records:
        if record.provider not in providers:
            providers.append(record.provider)
    return tuple(providers)


class OpenCodeAdapter:
    def __init__(self, runner: Any):
        self.runner = runner
        self.warnings: list[str] = []

    def detect(self, context: RuntimeContext) -> RuntimeInfo:
        result = self.runner.run(("opencode", "--version"), timeout=_DEFAULT_TIMEOUT_SECONDS, cwd=context.cwd, env_overlay=context.env)
        version = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else "unknown"
        if result.returncode != 0 or result.timed_out:
            self._warn("runtime_opencode_version_unavailable")
        return RuntimeInfo(RuntimeKind.OPENCODE, version, str(context.cwd))

    def snapshot(self, context: RuntimeContext) -> RuntimeSnapshot:
        sources: list[str] = []
        warnings: list[str] = []
        assignments_by_agent: dict[str, CurrentAssignment] = {}
        for scope, path in _config_paths(context):
            exists = path.exists()
            sources.append(_source_label(scope, exists))
            value, warning = _load_json(path)
            if warning:
                warnings.append(warning)
                continue
            if value is None:
                continue
            if not isinstance(value, Mapping):
                warning = f"inventory_invalid_source_shape:{path.name}"
                warnings.append(warning)
                continue
            for assignment in _assignments_from_config(value, f"{scope}:opencode.json"):
                assignments_by_agent[assignment.agent] = assignment
        for warning in warnings:
            self._warn(warning)
        return RuntimeSnapshot(
            tuple(sources),
            tuple(assignments_by_agent[agent] for agent in sorted(assignments_by_agent)),
            tuple(warnings),
        )

    def list_models(self, context: RuntimeContext) -> tuple[ModelRecord, ...]:
        result = self.runner.run(
            ("opencode", "models", "--verbose"),
            timeout=_DEFAULT_TIMEOUT_SECONDS,
            cwd=context.cwd,
            env_overlay=context.env,
            stdout_limit=MAX_STDOUT_LIMIT_CHARS,
        )
        if result.timed_out:
            self._warn("inventory_list_models_timeout")
            return ()
        if result.returncode != 0:
            self._warn("inventory_list_models_failed")
            return ()
        records, warnings = _parse_opencode_models_verbose_with_warnings(result.stdout)
        if result.stdout_truncated:
            self._warn("inventory_list_models_truncated")
        for warning in warnings:
            self._warn(warning)
        if not records:
            self._warn("inventory_list_models_empty")
        return records

    def check_readiness(self, providers: Sequence[str], context: RuntimeContext) -> tuple[ProviderReadiness, ...]:
        result = self.runner.run(("opencode", "auth", "list"), timeout=_DEFAULT_TIMEOUT_SECONDS, cwd=context.cwd, env_overlay=context.env)
        if result.timed_out:
            return tuple(ProviderReadiness(provider, ReadinessStatus.UNKNOWN, None, "auth_check_timeout") for provider in providers)
        if result.returncode != 0:
            return tuple(ProviderReadiness(provider, ReadinessStatus.UNKNOWN, None, "auth_check_failed") for provider in providers)
        parsed = parse_opencode_auth(result.stdout)
        if not providers:
            return parsed
        by_provider = {item.provider: item for item in parsed if item.provider != "UNKNOWN"}
        readiness: list[ProviderReadiness] = []
        seen: set[str] = set()
        for provider in providers:
            if provider in seen:
                continue
            seen.add(provider)
            readiness.append(by_provider.get(provider) or ProviderReadiness(
                provider,
                ReadinessStatus.UNKNOWN,
                None,
                "auth_provider_not_listed",
            ))
        return tuple(readiness)

    def live_check(
        self,
        model_record: ModelRecord,
        effort: str | None,
        sentinel: str,
        timeout: float,
        context: RuntimeContext,
    ) -> HealthCheck:
        if not isinstance(sentinel, str) or sentinel.strip() == "":
            return HealthCheck(
                model=model_record.exact_id,
                effort=effort,
                status=HealthStatus.FAIL,
                elapsed_ms=0,
                reason_code="live_invalid_sentinel",
                response_matched=False,
                detail="invalid sentinel",
            )
        if effort is not None and effort not in model_record.variants:
            return HealthCheck(
                model=model_record.exact_id,
                effort=effort,
                status=HealthStatus.FAIL,
                elapsed_ms=0,
                reason_code="live_unsupported_variant",
                response_matched=False,
                detail="unsupported variant",
            )
        probe_agent_name = _new_probe_agent_name()
        if probe_agent_name is None:
            return self._health(model_record, effort, HealthStatus.FAIL, 0, "live_unsafe_permission_config", False, "unsafe permission config")

        env_replacement = _live_probe_env_overlay(context, probe_agent_name)
        if env_replacement is None:
            return self._health(model_record, effort, HealthStatus.FAIL, 0, "live_unsafe_permission_config", False, "unsafe permission config")

        probe_failure = self._verify_effective_permission_config(model_record, effort, context, env_replacement, probe_agent_name)
        if probe_failure is not None:
            return probe_failure

        argv = ["opencode", "run", "--format", "json", "--model", model_record.exact_id]
        if effort is not None:
            argv.extend(("--variant", effort))
        argv.extend(("--agent", probe_agent_name))
        argv.append(f"Reply exactly: {sentinel}")
        result = self.runner.run(tuple(argv), timeout=timeout, cwd=context.cwd, env_replacement=env_replacement)

        if result.timed_out:
            return self._health(model_record, effort, HealthStatus.HANG, result.elapsed_ms, "live_timeout", False, result.stdout or result.stderr or "timeout")
        if result.returncode != 0:
            diagnostic = "\n".join(part for part in (result.stderr, result.stdout, self._log_tail(context)) if part)
            reason = _known_live_failure_reason(diagnostic) or "live_nonzero_exit"
            detail = _known_live_failure_excerpt(diagnostic) or diagnostic or reason
            return self._health(model_record, effort, HealthStatus.FAIL, result.elapsed_ms, reason, False, detail)

        matched, reason, detail = _parse_opencode_live_events_detail(result.stdout, sentinel)
        status = HealthStatus.PASS if matched else HealthStatus.FAIL
        return self._health(model_record, effort, status, result.elapsed_ms, reason, matched, detail or reason)

    def role_eval(self, request: Any, context: RuntimeContext) -> Any:
        from dataclasses import replace

        from helper.evaluator import (
            append_command_audits,
            changed_paths_from_git_status,
            effective_config_matches,
            inconclusive_result,
            isolated_opencode_env,
            opencode_eval_config,
            parse_opencode_eval_events,
            result_from_parsed,
            run_manifest_commands,
            unsupported_custom_tools,
            validate_role_eval_request,
            with_changed_paths_result,
        )

        if request.route.runtime_kind is not RuntimeKind.OPENCODE:
            return inconclusive_result(request, "eval_runtime_kind_mismatch")
        if unsupported_custom_tools(request.agent):
            return inconclusive_result(request, "eval_essential_custom_tool_unproven")
        minimal_env = {"PATH": context.env.get("PATH") or os.environ.get("PATH", "")}
        version = self.runner.run(("opencode", "--version"), timeout=10, cwd=context.cwd, env_replacement=minimal_env, stdout_limit=MAX_STDOUT_LIMIT_CHARS)
        if version.timed_out or version.returncode != 0 or version.stdout.strip() != request.route.runtime_version:
            return inconclusive_result(request, "eval_runtime_version_mismatch", elapsed_ms=version.elapsed_ms)
        if request.fixture.requires_code_execution and request.workspace.sandbox_attestation is None:
            return inconclusive_result(request, "eval_sandbox_unavailable")
        try:
            validate_role_eval_request(request)
        except ValueError as exc:
            return inconclusive_result(request, str(exc) or "eval_request_invalid")

        token = secrets.token_hex(16)
        if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{32}", token) is None:
            return inconclusive_result(request, "eval_opencode_agent_name_unsafe")
        agent_name = f"model-optimizer-eval-{token}"
        xdg_config_home = request.workspace.root / f".opencode-eval-config-{token}"
        xdg_data_home = request.workspace.root / f".opencode-eval-data-{token}"

        def cleanup() -> str | None:
            failure = None
            for target in (xdg_config_home, xdg_data_home):
                try:
                    shutil.rmtree(target, ignore_errors=False)
                except FileNotFoundError:
                    pass
                except OSError:
                    failure = "eval_opencode_cleanup_failed"
            return failure

        def with_cleanup_failure(final_result: Any, reason: str) -> Any:
            return replace(
                final_result,
                status="INCONCLUSIVE",
                reason_codes=tuple(dict.fromkeys((*final_result.reason_codes, reason))),
            )

        def evaluate_once() -> Any:
            try:
                config_dir = xdg_config_home / "opencode"
                config_dir.mkdir(parents=True, exist_ok=True)
                xdg_data_home.mkdir(parents=True, exist_ok=True)
                expected_config = opencode_eval_config(request, agent_name)
                config_path = config_dir / "opencode.json"
                config_bytes = json.dumps(expected_config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                config_path.write_bytes(config_bytes)
                env_replacement = isolated_opencode_env(context.env, xdg_config_home, xdg_data_home, request.model_record.provider)
                if env_replacement is None:
                    return inconclusive_result(request, "eval_opencode_auth_unavailable")
            except OSError:
                return inconclusive_result(request, "eval_opencode_config_write_failed")

            debug = self.runner.run(
                ("opencode", "debug", "config", "--pure"),
                timeout=_DEFAULT_TIMEOUT_SECONDS,
                cwd=request.workspace.root,
                env_replacement=env_replacement,
                stdout_limit=MAX_STDOUT_LIMIT_CHARS,
            )
            if debug.timed_out or debug.returncode != 0 or debug.stdout_truncated:
                return inconclusive_result(request, "eval_opencode_effective_config_mismatch", elapsed_ms=debug.elapsed_ms)
            try:
                effective = json.loads(debug.stdout)
            except json.JSONDecodeError:
                return inconclusive_result(request, "eval_opencode_effective_config_mismatch", elapsed_ms=debug.elapsed_ms)
            if not effective_config_matches(effective, expected_config, agent_name):
                return inconclusive_result(request, "eval_opencode_effective_config_mismatch", elapsed_ms=debug.elapsed_ms)

            argv = [
                "opencode",
                "run",
                "--pure",
                "--format",
                "json",
                "--model",
                request.route.model,
            ]
            if request.route.effort:
                argv.extend(("--variant", request.route.effort))
            argv.extend(("--agent", agent_name, "--dir", str(request.workspace.root), request.task))
            run = self.runner.run(tuple(argv), timeout=request.timeout, cwd=request.workspace.root, env_replacement=env_replacement, stdout_limit=MAX_STDOUT_LIMIT_CHARS)
            if run.timed_out:
                return replace(inconclusive_result(request, "eval_timeout", elapsed_ms=run.elapsed_ms), status="HANG")
            if run.stdout_truncated:
                return inconclusive_result(request, "eval_truncated_audit_stream", elapsed_ms=run.elapsed_ms)
            if run.returncode != 0:
                diagnostic = "\n".join(part for part in (run.stderr, run.stdout) if part)
                if re.search(r"rate.?limit|quota", diagnostic, re.IGNORECASE):
                    return inconclusive_result(request, "eval_rate_limited", elapsed_ms=run.elapsed_ms)
                return inconclusive_result(request, "eval_runtime_nonzero", elapsed_ms=run.elapsed_ms)

            parse_fixture = replace(request.fixture, allowed_commands=())
            parsed = parse_opencode_eval_events(run.stdout, request.workspace, parse_fixture)
            role_result = result_from_parsed(request, parsed, run.elapsed_ms)
            if role_result.status == "INCONCLUSIVE":
                return role_result

            try:
                command_runs = run_manifest_commands(
                    self.runner,
                    request.workspace,
                    request.fixture,
                    request.workspace.sandbox_attestation,
                    timeout=request.timeout,
                    env={},
                )
            except ValueError as exc:
                return inconclusive_result(request, str(exc) or "eval_invalid_command_audit", elapsed_ms=run.elapsed_ms)
            required_ids = {command.command_id for command in request.fixture.allowed_commands}
            successful_ids = {audit.command_id for audit in command_runs if audit.exit_code == 0}
            timed_out_ids = {audit.command_id for audit in command_runs if audit.exit_code is None}
            if timed_out_ids:
                role_result = append_command_audits(role_result, command_runs, status="HANG", reason_codes=("eval_timeout",))
            elif required_ids and not required_ids.issubset(successful_ids):
                role_result = append_command_audits(role_result, command_runs, status="FAIL", reason_codes=("eval_required_command_failed",))
            else:
                role_result = append_command_audits(role_result, command_runs, status="PASS", reason_codes=())
            diff = self.runner.run(("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"), timeout=10, cwd=request.workspace.root, env_replacement=minimal_env, stdout_limit=None)
            return with_changed_paths_result(role_result, changed_paths_from_git_status(diff, request.workspace))

        try:
            final_result = evaluate_once()
        except Exception:
            final_result = inconclusive_result(request, "eval_opencode_runtime_exception")
        cleanup_reason = cleanup()
        if cleanup_reason:
            final_result = with_cleanup_failure(final_result, cleanup_reason)
        return final_result

    def reload_semantics(self, context: RuntimeContext) -> dict[str, Any]:
        return {
            "config_changes": "restart required",
            "applies_to": ("opencode.json",),
            "source": "opencode_default_unless_runtime_proves_otherwise",
        }

    def inventory(self, context: RuntimeContext) -> Inventory:
        self.warnings = []
        runtime = self.detect(context)
        snapshot = self.snapshot(context)
        catalog_local = self.list_models(context)
        readiness = self.check_readiness(_providers_in_order(catalog_local), context)
        readiness_by_provider = {item.provider: item for item in readiness}
        exact_catalog = {record.exact_id for record in catalog_local}
        exclusions: list[Exclusion] = []

        for assignment in snapshot.current_assignments:
            if assignment.model not in exact_catalog:
                exclusions.append(Exclusion(
                    assignment.model,
                    "inventory_current_model_not_catalog_local",
                    _bounded(f"{assignment.agent}:{assignment.source}"),
                ))

        for record in catalog_local:
            provider_readiness = readiness_by_provider.get(record.provider)
            if provider_readiness is None or provider_readiness.status is not ReadinessStatus.READY:
                exclusions.append(Exclusion(
                    record.exact_id,
                    "provider_not_ready",
                    provider_readiness.reason_code if provider_readiness else "auth_provider_not_listed",
                ))

        created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return inventory_with_digest(Inventory(
            schema="model-optimizer.inventory/v1",
            created_at=created_at,
            runtime=runtime,
            sources=snapshot.sources,
            current_assignments=snapshot.current_assignments,
            catalog_local=catalog_local,
            provider_readiness=readiness,
            exclusions=tuple(exclusions),
            warnings=tuple(dict.fromkeys((*self.warnings, *snapshot.warnings))),
            digest="",
        ))

    def _verify_effective_permission_config(
        self,
        model_record: ModelRecord,
        effort: str | None,
        context: RuntimeContext,
        env_overlay: Mapping[str, str],
        probe_agent_name: str,
    ) -> HealthCheck | None:
        result = self.runner.run(
            ("opencode", "debug", "config"),
            timeout=_DEFAULT_TIMEOUT_SECONDS,
            cwd=context.cwd,
            env_replacement=env_overlay,
            stdout_limit=MAX_STDOUT_LIMIT_CHARS,
        )
        if result.timed_out or result.returncode != 0 or result.stdout_truncated:
            return self._health(
                model_record,
                effort,
                HealthStatus.FAIL,
                result.elapsed_ms,
                "live_unsafe_permission_config",
                False,
                "unsafe permission config",
            )
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            return self._health(
                model_record,
                effort,
                HealthStatus.FAIL,
                result.elapsed_ms,
                "live_unsafe_permission_config",
                False,
                "unsafe permission config",
            )
        if not _effective_probe_agent_is_safe(parsed, probe_agent_name):
            return self._health(
                model_record,
                effort,
                HealthStatus.FAIL,
                result.elapsed_ms,
                "live_unsafe_permission_config",
                False,
                "unsafe permission config",
            )
        return None

    def _health(
        self,
        model_record: ModelRecord,
        effort: str | None,
        status: HealthStatus,
        elapsed_ms: int,
        reason: str,
        matched: bool,
        detail: str,
    ) -> HealthCheck:
        return HealthCheck(
            model=model_record.exact_id,
            effort=effort,
            status=status,
            elapsed_ms=elapsed_ms,
            reason_code=reason,
            response_matched=matched,
            detail=_bounded(detail),
        )

    def _log_tail(self, context: RuntimeContext) -> str:
        log_path = context.home / ".local" / "share" / "opencode" / "log" / "opencode.log"
        try:
            home = context.home.resolve()
            resolved_log = log_path.resolve()
            if not resolved_log.is_relative_to(home):
                return ""
            if not resolved_log.exists():
                return ""
            with resolved_log.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(0, size - _LOG_TAIL_CHARS))
                data = handle.read(_LOG_TAIL_CHARS)
        except OSError:
            return ""
        text = data.decode("utf-8", errors="replace")
        return _redact_diagnostic(text)

    def _warn(self, warning: str) -> None:
        _append_unique(self.warnings, warning)
