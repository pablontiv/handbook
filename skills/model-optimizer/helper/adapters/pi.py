from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
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
from helper.runner import MAX_STDOUT_LIMIT_CHARS

from . import RuntimeContext

_SECRET_KEY_RE = re.compile(r"token|key|secret|password|cookie|authorization|credential", re.IGNORECASE)
_SECRET_KEY_ALLOWLIST = {"maxtokens"}
_STRUCTURAL_PROFILE_KEYS = {"effort", "thinking", "reasoning", "defaultThinkingLevel", "tools", "temperature"}
_AUTH_TYPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,63}$")
_METADATA_FILENAMES = ("models-store.json", "models.json")
_DEFAULT_TIMEOUT_SECONDS = 15
_MAX_DETAIL_CHARS = 240


@dataclass(frozen=True)
class RuntimeSnapshot:
    sources: tuple[str, ...]
    current_assignments: tuple[CurrentAssignment, ...]
    warnings: tuple[str, ...] = ()


def _bounded(text: str, limit: int = _MAX_DETAIL_CHARS) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _display_int(value: str) -> int | None:
    text = value.strip().upper()
    if not text:
        return None
    multiplier = 1
    if text.endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    try:
        parsed = float(text) * multiplier
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed)


def parse_pi_model_listing(text: str) -> tuple[ModelRecord, ...]:
    records: list[ModelRecord] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("provider"):
            continue
        columns = stripped.split()
        if len(columns) < 6:
            continue
        provider, model, context, max_output, thinking, images = columns[:6]
        input_modes = ("text", "image") if images.lower() == "yes" else ("text",)
        records.append(ModelRecord(
            exact_id=f"{provider}/{model}",
            provider=provider,
            model=model,
            context_window=_display_int(context),
            max_output=_display_int(max_output),
            reasoning=thinking.lower() == "yes",
            input_modes=input_modes,
            provenance=("pi --list-models",),
        ))
    return tuple(records)


def parse_pi_auth(text: str, provider: str) -> ProviderReadiness:
    try:
        value = json.loads(text or "{}")
    except json.JSONDecodeError:
        return ProviderReadiness(provider, ReadinessStatus.UNKNOWN, None, "auth_malformed_json")
    if not isinstance(value, Mapping):
        return ProviderReadiness(provider, ReadinessStatus.UNKNOWN, None, "auth_malformed_json")

    status_text = str(value.get("status", "unknown")).lower()
    auth_type = value.get("authType", value.get("auth_type"))
    auth_type_text = _auth_type_or_none(auth_type)
    if status_text == ReadinessStatus.READY.value:
        return ProviderReadiness(provider, ReadinessStatus.READY, auth_type_text, "auth_ready")
    if status_text in {ReadinessStatus.NOT_READY.value, "missing", "expired", "unauthorized"}:
        return ProviderReadiness(provider, ReadinessStatus.NOT_READY, auth_type_text, "auth_not_ready")
    return ProviderReadiness(provider, ReadinessStatus.UNKNOWN, auth_type_text, "auth_unknown")


def _auth_type_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if not _AUTH_TYPE_RE.fullmatch(value):
        return None
    return value


def pi_global_agent_dir(home: Path, environ: Mapping[str, str] | None = None) -> Path:
    configured = (environ or {}).get("PI_CODING_AGENT_DIR")
    if configured:
        return Path(configured).expanduser()
    return home / ".pi" / "agent"


def pi_project_config_dir(cwd: Path) -> Path:
    return cwd / ".pi"


def pi_project_subagents_path(cwd: Path) -> Path:
    primary = pi_project_config_dir(cwd) / "subagents.json"
    if primary.exists():
        return primary
    return cwd / ".pi" / "agent" / "subagents.json"


def _agent_dir(home: Path, environ: Mapping[str, str] | None = None) -> Path:
    return pi_global_agent_dir(home, environ)


def _load_json(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, f"inventory_malformed_metadata:{path.name}"
    except OSError:
        return None, f"inventory_unreadable_source:{path.name}"


def _is_secret_key(key: str) -> bool:
    return key.lower() not in _SECRET_KEY_ALLOWLIST and bool(_SECRET_KEY_RE.search(key))


def _prune_secret_keys(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _prune_secret_keys(item)
            for key, item in value.items()
            if isinstance(key, str) and not _is_secret_key(key)
        }
    if isinstance(value, list):
        return [_prune_secret_keys(item) for item in value]
    return value


def _is_json_structural(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_structural(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_json_structural(item) for key, item in value.items())
    return False


def _source_label(scope: str, filename: str, exists: bool) -> str:
    prefix = "" if exists else "missing:"
    return f"{prefix}{scope}:{filename}"


def _invalid_source_shape_warning(path: Path) -> str:
    return f"inventory_invalid_source_shape:{path.name}"


def _exact_model(provider: str | None, model: str | None) -> str | None:
    if not model:
        return None
    if "/" in model:
        return model
    if provider:
        return f"{provider}/{model}"
    return model


def _settings_assignment(settings: Mapping[str, Any]) -> CurrentAssignment | None:
    exact = _exact_model(
        _string_or_none(settings.get("defaultProvider")),
        _string_or_none(settings.get("defaultModel")),
    )
    if not exact:
        return None
    options: dict[str, Any] = {}
    thinking = _string_or_none(settings.get("defaultThinkingLevel"))
    if thinking:
        options["thinking"] = thinking
    return CurrentAssignment("default", exact, options, "global:settings.json")


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _profile_options(profile: Mapping[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for key, value in profile.items():
        if key == "model" or _is_secret_key(str(key)):
            continue
        if key in _STRUCTURAL_PROFILE_KEYS and _is_json_structural(value):
            normalized = "thinking" if key == "defaultThinkingLevel" else key
            options[normalized] = value
    return options


def _profiles_from_source(value: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    profiles = value.get("model_profiles", value.get("profiles", {}))
    if not isinstance(profiles, Mapping):
        return {}
    return {
        str(agent): profile
        for agent, profile in profiles.items()
        if isinstance(agent, str) and isinstance(profile, Mapping)
    }


def _assignments_from_profiles(
    profiles: Mapping[str, Mapping[str, Any]],
    source_by_agent: Mapping[str, str],
) -> tuple[CurrentAssignment, ...]:
    assignments: list[CurrentAssignment] = []
    for agent in sorted(profiles):
        profile = profiles[agent]
        model = _string_or_none(profile.get("model"))
        if not model:
            continue
        assignments.append(CurrentAssignment(
            agent=agent,
            model=model,
            options=_profile_options(profile),
            source=source_by_agent[agent],
        ))
    return tuple(assignments)


def _providers_in_order(records: Iterable[ModelRecord]) -> tuple[str, ...]:
    providers: list[str] = []
    for record in records:
        if record.provider not in providers:
            providers.append(record.provider)
    return tuple(providers)


def _find_model_metadata(value: Any, provider_hint: str | None = None) -> Iterable[tuple[str, Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        provider = _string_or_none(value.get("provider")) or provider_hint
        models = value.get("models")
        if isinstance(models, list):
            for model in models:
                if not isinstance(model, Mapping):
                    continue
                model_id = _string_or_none(model.get("id")) or _string_or_none(model.get("name"))
                model_provider = _string_or_none(model.get("provider")) or provider
                if not model_id or not model_provider:
                    continue
                exact = model_id if "/" in model_id else f"{model_provider}/{model_id}"
                yield exact, model
        for key, item in value.items():
            if key == "models":
                continue
            next_provider = provider_hint
            if isinstance(item, Mapping):
                next_provider = str(key)
            yield from _find_model_metadata(item, next_provider)
    elif isinstance(value, list):
        for item in value:
            yield from _find_model_metadata(item, provider_hint)


def _number_from_metadata(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return int(value)
    if isinstance(value, str):
        return _display_int(value)
    return None


def _float_from_metadata(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        converted = float(value)
    except OverflowError:
        return None
    if not math.isfinite(converted) or converted < 0:
        return None
    return converted


def _reasoning_from_metadata(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return bool(value)
    return None


def _tuple_of_strings(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    return None


def _first_known(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _metadata_map(metadata: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _variants_from_metadata(value: Any) -> tuple[str, ...] | None:
    explicit = _tuple_of_strings(value)
    if explicit is not None:
        return explicit
    if isinstance(value, Mapping):
        return tuple(
            key
            for key, enabled in value.items()
            if isinstance(key, str) and bool(enabled)
        )
    return None


def _enrich_record(record: ModelRecord, metadata: Mapping[str, Any], provenance: str) -> ModelRecord:
    cache = _metadata_map(metadata, "cache")
    costs = _metadata_map(metadata, "costs", "cost")
    input_modes = (
        _tuple_of_strings(metadata.get("inputModes"))
        or _tuple_of_strings(metadata.get("input_modes"))
        or _tuple_of_strings(metadata.get("input"))
    )
    variants = _variants_from_metadata(metadata.get("variants")) or _variants_from_metadata(metadata.get("thinking"))
    reasoning = _first_known(
        _reasoning_from_metadata(metadata.get("reasoning")),
        _reasoning_from_metadata(metadata.get("thinking")),
        record.reasoning,
    )
    return replace(
        record,
        family=_string_or_none(metadata.get("family")) or record.family,
        context_window=_first_known(
            _number_from_metadata(metadata.get("context")),
            _number_from_metadata(metadata.get("contextWindow")),
            record.context_window,
        ),
        max_output=_first_known(
            _number_from_metadata(metadata.get("maxTokens")),
            _number_from_metadata(metadata.get("max_output")),
            record.max_output,
        ),
        reasoning=reasoning,
        input_modes=input_modes or record.input_modes,
        tool_call=metadata.get("toolCall") if isinstance(metadata.get("toolCall"), bool) else record.tool_call,
        cache_read=_first_known(
            _float_from_metadata(cache.get("read")),
            _float_from_metadata(costs.get("cacheRead")),
            _float_from_metadata(costs.get("cache_read")),
            record.cache_read,
        ),
        cache_write=_first_known(
            _float_from_metadata(cache.get("write")),
            _float_from_metadata(costs.get("cacheWrite")),
            _float_from_metadata(costs.get("cache_write")),
            record.cache_write,
        ),
        input_cost=_first_known(_float_from_metadata(costs.get("input")), record.input_cost),
        output_cost=_first_known(_float_from_metadata(costs.get("output")), record.output_cost),
        variants=variants or record.variants,
        provenance=tuple(dict.fromkeys((*record.provenance, provenance))),
    )


class PiAdapter:
    def __init__(self, runner: Any):
        self.runner = runner
        self.warnings: list[str] = []

    def detect(self, context: RuntimeContext) -> RuntimeInfo:
        result = self.runner.run(("pi", "--version"), timeout=_DEFAULT_TIMEOUT_SECONDS, cwd=context.cwd, env_overlay=context.env)
        version = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else "unknown"
        if result.returncode != 0 or result.timed_out:
            self._warn("runtime_pi_version_unavailable")
        return RuntimeInfo(RuntimeKind.PI, version, str(context.cwd))

    def snapshot(self, context: RuntimeContext) -> RuntimeSnapshot:
        sources: list[str] = []
        assignments: list[CurrentAssignment] = []
        warnings: list[str] = []

        env_provider = _string_or_none(context.env.get("PI_PROVIDER"))
        env_model = _string_or_none(context.env.get("PI_MODEL"))
        env_exact = _exact_model(env_provider, env_model)
        env_thinking = _string_or_none(context.env.get("PI_REASONING_LEVEL"))
        if env_provider or env_model or env_thinking:
            sources.append("env:PI_PROVIDER,PI_MODEL,PI_REASONING_LEVEL")
        if env_exact:
            options = {"thinking": env_thinking} if env_thinking else {}
            assignments.append(CurrentAssignment("current", env_exact, options, "env"))

        global_dir = _agent_dir(context.home, context.env)
        project_subagents_path = pi_project_subagents_path(context.cwd)

        settings_path = global_dir / "settings.json"
        settings, warning = _load_json(settings_path)
        sources.append(_source_label("global", "settings.json", settings_path.exists()))
        if warning:
            warnings.append(warning)
        elif settings is None:
            pass
        elif isinstance(settings, Mapping):
            assignment = _settings_assignment(_prune_secret_keys(settings))
            if assignment is not None:
                assignments.append(assignment)
        else:
            warnings.append(_invalid_source_shape_warning(settings_path))

        merged_profiles: dict[str, Mapping[str, Any]] = {}
        source_by_agent: dict[str, str] = {}
        for scope, subagents_path in (("global", global_dir / "subagents.json"), ("project", project_subagents_path)):
            data, warning = _load_json(subagents_path)
            sources.append(_source_label(scope, "subagents.json", subagents_path.exists()))
            if warning:
                warnings.append(warning)
                continue
            if data is None:
                continue
            if not isinstance(data, Mapping):
                warnings.append(_invalid_source_shape_warning(subagents_path))
                continue
            profiles = _profiles_from_source(_prune_secret_keys(data))
            for agent, profile in profiles.items():
                merged_profiles[agent] = profile
                source_by_agent[agent] = f"{scope}:subagents.json"
        assignments.extend(_assignments_from_profiles(merged_profiles, source_by_agent))

        for warning in warnings:
            self._warn(warning)
        return RuntimeSnapshot(tuple(sources), tuple(assignments), tuple(warnings))

    def list_models(self, context: RuntimeContext) -> tuple[ModelRecord, ...]:
        result = self.runner.run(
            ("pi", "--list-models"),
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
        records = {record.exact_id: record for record in parse_pi_model_listing(result.stdout)}
        if result.stdout_truncated:
            self._warn("inventory_list_models_truncated")
        if not records:
            self._warn("inventory_list_models_empty")
        for filename in _METADATA_FILENAMES:
            self._merge_metadata_file(records, _agent_dir(context.home, context.env) / filename, filename)
        return tuple(records[exact_id] for exact_id in records)

    def check_readiness(self, providers: Sequence[str], context: RuntimeContext) -> tuple[ProviderReadiness, ...]:
        readiness: list[ProviderReadiness] = []
        seen: set[str] = set()
        for provider in providers:
            if provider in seen:
                continue
            seen.add(provider)
            result = self.runner.run(
                ("pi", "auth", "check", "--provider", provider, "--json", "--no-refresh"),
                timeout=_DEFAULT_TIMEOUT_SECONDS,
                cwd=context.cwd,
                env_overlay=context.env,
            )
            if result.timed_out:
                readiness.append(ProviderReadiness(provider, ReadinessStatus.UNKNOWN, None, "auth_check_timeout"))
            elif result.returncode != 0:
                readiness.append(ProviderReadiness(provider, ReadinessStatus.UNKNOWN, None, "auth_check_failed"))
            else:
                readiness.append(parse_pi_auth(result.stdout, provider))
        return tuple(readiness)

    def live_check(
        self,
        model_record: ModelRecord,
        effort: str | None,
        sentinel: str,
        timeout: float,
        context: RuntimeContext,
    ) -> HealthCheck:
        argv = ["pi", "--no-session", "-p", "--no-tools", "--model", model_record.exact_id]
        if effort:
            argv.extend(("--thinking", effort))
        argv.append(f"Reply exactly: {sentinel}")
        result = self.runner.run(tuple(argv), timeout=timeout, cwd=context.cwd, env_overlay=context.env)

        output = result.stdout or ""
        if result.timed_out:
            status = HealthStatus.HANG
            reason = "live_timeout"
            matched = False
        elif result.returncode != 0:
            status = HealthStatus.FAIL
            reason = "live_nonzero_exit"
            matched = False
        elif output.strip() == "":
            status = HealthStatus.FAIL
            reason = "live_empty_response"
            matched = False
        elif sentinel in output:
            status = HealthStatus.PASS
            reason = "live_sentinel_matched"
            matched = True
        else:
            status = HealthStatus.FAIL
            reason = "live_sentinel_missing"
            matched = False
        detail = _bounded(output or result.stderr or reason)
        return HealthCheck(
            model=model_record.exact_id,
            effort=effort,
            status=status,
            elapsed_ms=result.elapsed_ms,
            reason_code=reason,
            response_matched=matched,
            detail=detail,
        )

    def role_eval(self, request: Any, context: RuntimeContext) -> Any:
        from helper.evaluator import (
            changed_paths_from_git_status,
            inconclusive_result,
            parse_pi_eval_events,
            pi_confined_extension_path,
            result_from_parsed,
            unsupported_custom_tools,
            validate_role_eval_request,
            with_changed_paths_result,
            write_policy_file,
        )

        if request.route.runtime_kind is not RuntimeKind.PI:
            return inconclusive_result(request, "eval_runtime_kind_mismatch")
        if unsupported_custom_tools(request.agent):
            return inconclusive_result(request, "eval_essential_custom_tool_unproven")

        path_value = context.env.get("PATH") or os.environ.get("PATH", "")
        minimal_env = {"PATH": path_value}
        version = self.runner.run(("pi", "--version"), timeout=10, cwd=context.cwd, env_replacement=minimal_env, stdout_limit=MAX_STDOUT_LIMIT_CHARS)
        if version.timed_out or version.returncode != 0 or version.stdout.strip() != request.route.runtime_version:
            return inconclusive_result(request, "eval_runtime_version_mismatch", elapsed_ms=version.elapsed_ms)
        if request.fixture.requires_code_execution and request.workspace.sandbox_attestation is None:
            return inconclusive_result(request, "eval_sandbox_unavailable")

        try:
            validate_role_eval_request(request)
            policy_path = write_policy_file(request)
        except ValueError as exc:
            return inconclusive_result(request, str(exc) or "eval_request_invalid")

        extension_path = pi_confined_extension_path()
        pi_data_root = request.workspace.root / ".pi-eval-runtime"
        pi_home = pi_data_root / "home"
        env = {
            "PATH": path_value,
            "HOME": str(pi_home),
            "XDG_CONFIG_HOME": str(pi_data_root / "xdg-config"),
            "XDG_DATA_HOME": str(pi_data_root / "xdg-data"),
            "XDG_CACHE_HOME": str(pi_data_root / "xdg-cache"),
            "NPM_CONFIG_USERCONFIG": str(pi_data_root / "npmrc"),
            "PI_EVAL_POLICY": str(policy_path),
            "PI_CODING_AGENT_DIR": str(pi_data_root / "agent"),
            "PI_SESSION_DIR": str(pi_data_root / "sessions"),
        }

        preflight_argv = (
            "pi",
            "--offline",
            "--no-extensions",
            "--no-builtin-tools",
            "--extension",
            str(extension_path),
            "--mode",
            "rpc",
            "--no-session",
            "--session-dir",
            str(pi_data_root / "rpc-sessions"),
            "--no-context-files",
            "--no-skills",
            "--no-prompt-templates",
            "--tools",
            ",".join(request.agent.tools),
        )
        preflight_stdin = json.dumps({"id": "commands-1", "type": "get_commands"}) + "\n"
        preflight = self.runner.run(
            preflight_argv,
            timeout=10,
            cwd=request.workspace.root,
            env_replacement=env,
            stdout_limit=MAX_STDOUT_LIMIT_CHARS,
            stdin_text=preflight_stdin,
        )
        if preflight.timed_out or preflight.returncode != 0 or preflight.stdout_truncated or preflight.stdout_decode_replaced:
            return inconclusive_result(request, "eval_pi_isolation_unverified", elapsed_ms=preflight.elapsed_ms)
        try:
            responses = [json.loads(line) for line in preflight.stdout.splitlines() if line.strip()]
        except json.JSONDecodeError:
            return inconclusive_result(request, "eval_pi_isolation_unverified", elapsed_ms=preflight.elapsed_ms)
        command_response = next((item for item in responses if isinstance(item, Mapping) and item.get("type") == "response" and item.get("command") == "get_commands"), None)
        if not isinstance(command_response, Mapping) or command_response.get("success") is not True:
            return inconclusive_result(request, "eval_pi_isolation_unverified", elapsed_ms=preflight.elapsed_ms)
        payload = command_response.get("data")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("commands"), Sequence):
            return inconclusive_result(request, "eval_pi_isolation_unverified", elapsed_ms=preflight.elapsed_ms)
        command_names = []
        for item in payload.get("commands", ()):  # type: ignore[arg-type]
            if not isinstance(item, Mapping):
                return inconclusive_result(request, "eval_pi_isolation_unverified", elapsed_ms=preflight.elapsed_ms)
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                return inconclusive_result(request, "eval_pi_isolation_unverified", elapsed_ms=preflight.elapsed_ms)
            command_names.append(name)
        if command_names != ["model_optimizer_eval_smoke"]:
            return inconclusive_result(request, "eval_pi_isolation_unavailable", elapsed_ms=preflight.elapsed_ms)

        argv = [
            "pi",
            "--no-extensions",
            "--no-builtin-tools",
            "--extension",
            str(extension_path),
            "--mode",
            "json",
            "--no-session",
            "--no-context-files",
            "--no-skills",
            "--no-prompt-templates",
            "--model",
            request.route.model,
        ]
        if request.route.effort:
            argv.extend(("--thinking", request.route.effort))
        argv.extend((
            "--tools",
            ",".join(request.agent.tools),
            "--system-prompt",
            request.agent.body,
            "-p",
            request.task,
        ))

        result = self.runner.run(
            tuple(argv),
            timeout=request.timeout,
            cwd=request.workspace.root,
            env_replacement=env,
            stdout_limit=MAX_STDOUT_LIMIT_CHARS,
        )
        if result.timed_out:
            from dataclasses import replace

            return replace(inconclusive_result(request, "eval_timeout", elapsed_ms=result.elapsed_ms), status="HANG")
        if result.stdout_truncated:
            return inconclusive_result(request, "eval_truncated_audit_stream", elapsed_ms=result.elapsed_ms)
        if result.returncode != 0:
            return inconclusive_result(request, "eval_runtime_nonzero", elapsed_ms=result.elapsed_ms)

        parsed = parse_pi_eval_events(result.stdout, request.workspace, request.fixture)
        role_result = result_from_parsed(request, parsed, result.elapsed_ms)
        diff = self.runner.run(
            ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
            timeout=10,
            cwd=request.workspace.root,
            env_replacement=minimal_env,
            stdout_limit=MAX_STDOUT_LIMIT_CHARS,
        )
        return with_changed_paths_result(role_result, changed_paths_from_git_status(diff, request.workspace))

    def reload_semantics(self, context: RuntimeContext) -> dict[str, Any]:
        return {
            "profile_changes": "/reload or restart",
            "applies_to": ("subagents.json", "subagent markdown"),
            "source": "pi_default_unless_runtime_proves_otherwise",
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

    def _merge_metadata_file(self, records: dict[str, ModelRecord], path: Path, provenance: str) -> None:
        if not path.exists():
            return
        value, warning = _load_json(path)
        if warning:
            self._warn(warning)
            return
        pruned = _prune_secret_keys(value)
        for exact_id, metadata in _find_model_metadata(pruned):
            if exact_id in records:
                records[exact_id] = _enrich_record(records[exact_id], metadata, provenance)

    def _warn(self, warning: str) -> None:
        if warning not in self.warnings:
            self.warnings.append(warning)
