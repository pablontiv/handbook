#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

# Portable direct-script bootstrap: when invoked as
# `python3 skills/model-optimizer/scripts/model_optimizer.py` from the repo root,
# Python places only this scripts directory on sys.path. Add the skill root so the
# sibling `helper` package is importable without personal paths or installation.
_SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from helper.adapters import RuntimeContext, adapter_for
from helper.artifacts import inventory_with_digest, load_inventory, reject_runtime_config_output, write_health, write_inventory
from helper.models import (
    HealthArtifact,
    HealthCheck,
    HealthStatus,
    Inventory,
    ReadinessStatus,
    RuntimeKind,
)
from helper.runner import CommandRunner, redact_text

EXIT_OK = 0
EXIT_USAGE_OR_SCHEMA = 2
EXIT_DETECTION = 3
EXIT_PARTIAL = 4
EXIT_FAILED_OR_HUNG = 5
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


def _sanitize_check(check: HealthCheck) -> HealthCheck:
    return replace(check, detail=_safe_message(check.detail))


def _safe_message(text: str) -> str:
    return redact_text(text or "")


def _schema_or_usage_message(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    if text.startswith("runtime_"):
        return text
    if text.startswith(("artifact_", "live_", "usage_")):
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
