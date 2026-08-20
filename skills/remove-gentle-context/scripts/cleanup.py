#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform as platform_module
import stat
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from helper.adapter import AdapterRegistry  # noqa: E402
from helper.canonical import canonical_bytes, digest_json  # noqa: E402
from helper.clients.claude import ClaudeAdapter  # noqa: E402
from helper.clients.codex import CodexAdapter  # noqa: E402
from helper.clients.opencode import OpenCodeAdapter  # noqa: E402
from helper.clients.pi import PiAdapter  # noqa: E402
from helper.declarative import load_declarative_adapter  # noqa: E402
from helper.engine import build_inventory, build_plan  # noqa: E402
from helper.lifecycle import LifecycleController  # noqa: E402
from helper.models import (  # noqa: E402
    ArtifactClass,
    BackupManifest,
    Candidate,
    Check,
    Inventory,
    InventoryFinding,
    LifecycleAction,
    LifecycleOutcome,
    Operation,
    OperationKind,
    OperationOutcome,
    Ownership,
    Plan,
    PlatformProfile,
    Preimage,
    Receipt,
    ReceiptStatus,
    RuntimeContext,
    VerificationResult,
)
from helper.ownership import load_ownership_catalog  # noqa: E402
from helper.paths import ENVIRONMENT_ENV_KEYS, _is_windows_reparse_point, canonical_environment_roots, resolve_state_root, root_map  # noqa: E402
from helper.transaction import restore as restore_manifest  # noqa: E402
from helper.transaction import write_json_atomic  # noqa: E402
from helper.transaction import execute_plan  # noqa: E402
from helper.verifier import verify_receipt  # noqa: E402

INVENTORY_SCHEMA = "remove-gentle-context.inventory/v1"
PLAN_SCHEMA = "remove-gentle-context.plan/v1"
RECEIPT_SCHEMA = "remove-gentle-context.receipt/v1"
VERIFICATION_SCHEMA = "remove-gentle-context.verification/v1"
BACKUP_SCHEMA = "remove-gentle-context.backup/v1"

EXIT_USAGE = 2
EXIT_UNSAFE_PATH = 11
EXIT_ARTIFACT = 12
EXIT_IO = 13
EXIT_APPROVAL = 20
EXIT_APPLY = 21
EXIT_VERIFY_FAILED = 30
EXIT_RESTORE = 40

APPROVAL_CODES = {"plan_approval_mismatch", "restore_approval_mismatch"}
ROOT_CODES = ("root", "home_mismatch", "os_mismatch", "path_escape", "plan_inventory")


class CliError(Exception):
    def __init__(self, exit_code: int, phase: str, code: str, *, path: Path | None = None, next_action: str = "inspect diagnostic and retry") -> None:
        super().__init__(code)
        self.exit_code = exit_code
        self.phase = phase
        self.code = code
        self.path = path
        self.next_action = next_action


class UsageError(Exception):
    pass


class CleanupArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self._print_message(f"{self.prog}: error: {message}\n", sys.stderr)
        raise UsageError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if status:
            if message:
                self._print_message(message, sys.stderr)
            raise UsageError(message or "invalid arguments")
        raise SystemExit(status)


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("code=python_unsupported phase=startup next_action=run with Python 3.11+", file=sys.stderr)
        return EXIT_USAGE
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except UsageError:
        return EXIT_USAGE
    try:
        summary = dispatch(args)
    except CliError as exc:
        emit_error(exc)
        return exc.exit_code
    except ValueError as exc:
        code = stable_code(exc, "value_error")
        exit_code = EXIT_APPROVAL if code in APPROVAL_CODES else EXIT_ARTIFACT
        emit_error(CliError(exit_code, getattr(args, "command", "unknown"), code))
        return exit_code
    except OSError as exc:
        emit_error(CliError(EXIT_IO, getattr(args, "command", "unknown"), exc.__class__.__name__))
        return EXIT_IO
    sys.stdout.buffer.write(canonical_bytes(summary) + b"\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = CleanupArgumentParser(
        prog="cleanup.py",
        description="Remove gentle-ai generated registrations with explicit inventory, plan, apply, verify, and restore phases.",
    )
    sub = parser.add_subparsers(dest="command", required=True, parser_class=CleanupArgumentParser)

    inventory = sub.add_parser("inventory", help="build a read-only inventory artifact")
    inventory.add_argument("--output", type=Path)
    inventory.add_argument("--project-root", action="append", default=[], type=Path)
    inventory.add_argument("--home", type=Path, help="explicit absolute canonical home root for inventory authority")
    inventory.add_argument("--platform", dest="platform", help="explicit platform authority: linux, macos, or windows")
    inventory.add_argument("--env", action="append", default=[], metavar="KEY=VALUE", help="explicit bounded runtime environment root; repeat for XDG_STATE_HOME, XDG_CONFIG_HOME, APPDATA, or LOCALAPPDATA")

    plan = sub.add_parser("plan", help="build a read-only plan artifact and print its approval digest")
    plan.add_argument("--inventory", required=True, type=Path)
    plan.add_argument("--output", type=Path)

    apply = sub.add_parser("apply", help="execute an approved plan transaction")
    apply.add_argument("--inventory", required=True, type=Path)
    apply.add_argument("--plan", required=True, type=Path)
    apply.add_argument("--approve", required=True)
    apply.add_argument("--receipt", type=Path)

    verify = sub.add_parser("verify", help="independently verify receipt against live state")
    verify.add_argument("--inventory", required=True, type=Path)
    verify.add_argument("--plan", required=True, type=Path)
    verify.add_argument("--receipt", required=True, type=Path)
    verify.add_argument("--output", type=Path)

    restore = sub.add_parser("restore", help="restore from a verified backup manifest and receipt authority")
    restore.add_argument("--manifest", required=True, type=Path)
    restore.add_argument("--receipt", required=True, type=Path)
    restore.add_argument("--approve", required=True)
    restore.add_argument("--output", type=Path)
    return parser


def dispatch(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "inventory":
        return command_inventory(args)
    if args.command == "plan":
        return command_plan(args)
    if args.command == "apply":
        return command_apply(args)
    if args.command == "verify":
        return command_verify(args)
    if args.command == "restore":
        return command_restore(args)
    raise CliError(EXIT_USAGE, "parse", "unknown_command")


def command_inventory(args: argparse.Namespace) -> dict[str, object]:
    context = context_from_args(args)
    adapters = build_adapters()
    inventory = build_inventory(context, adapters)
    output = args.output or default_artifact_path(context, "inventory.json")
    artifact = inventory_artifact(inventory)
    write_artifact(output, artifact, phase="inventory")
    return {
        "status": "ok",
        "command": "inventory",
        "output_path": str(output),
        "digest": inventory.digest,
        "counts": inventory_counts(inventory),
        "findings": [finding.to_dict() for finding in inventory.findings],
    }


def command_plan(args: argparse.Namespace) -> dict[str, object]:
    inventory = load_inventory(args.inventory)
    context = context_from_inventory(inventory)
    assert_context_matches_inventory(inventory, context, phase="plan")
    adapters = build_adapters()
    plan = build_plan(inventory, context, adapters)
    output = args.output or default_artifact_path(context, "plan.json")
    artifact = plan_artifact(plan)
    write_artifact(output, artifact, phase="plan")
    return {
        "status": "ok",
        "command": "plan",
        "output_path": str(output),
        "digest": plan.digest,
        "approval": plan.digest,
        "counts": {"operations": len(plan.operations), "blocked": len(plan.blocked_candidate_ids), "preserved": len(plan.preservation_assertions)},
    }


def command_apply(args: argparse.Namespace) -> dict[str, object]:
    inventory = load_inventory(args.inventory)
    plan = load_plan(args.plan)
    context = context_from_inventory(inventory)
    assert_inventory_plan_binding(inventory, plan, context, phase="apply")
    if args.approve != plan.digest:
        raise CliError(EXIT_APPROVAL, "apply", "plan_approval_mismatch", next_action="rerun plan and pass exact approval digest")
    receipt_path = args.receipt or default_artifact_path(context, "receipt.json")
    lifecycle = LifecycleController()
    try:
        receipt = execute_plan(plan, args.approve, context, lifecycle, inventory=inventory)
    except ValueError as exc:
        code = stable_code(exc, "apply_failed")
        exit_code = EXIT_APPROVAL if code in APPROVAL_CODES else EXIT_APPLY
        raise CliError(exit_code, "apply", code, next_action="fix preflight condition and rebuild artifacts") from exc
    artifact = receipt_artifact(receipt)
    write_artifact(receipt_path, artifact, phase="apply")
    backup_digest = backup_manifest_digest(receipt.backup_manifest_path)
    summary = receipt_command_summary(
        command="apply",
        receipt_path=receipt_path,
        receipt=receipt,
        artifact=artifact,
        backup_manifest_digest=backup_digest,
        counts={"operations": len(receipt.operation_outcomes), "lifecycle": len(receipt.lifecycle_outcomes)},
    )
    if receipt.status != ReceiptStatus.COMPLETED:
        exit_with_summary(summary, EXIT_APPLY, "apply", f"apply_{summary['status']}")
    return summary


def command_verify(args: argparse.Namespace) -> dict[str, object]:
    inventory = load_inventory(args.inventory)
    plan = load_plan(args.plan)
    receipt = load_receipt(args.receipt)
    context = context_from_inventory(inventory)
    assert_inventory_plan_binding(inventory, plan, context, phase="verify")
    assert_receipt_binding(receipt, inventory, plan, phase="verify")
    adapters = build_adapters()
    result = verify_receipt(replace(receipt, inventory=inventory, plan=plan), context, adapters)
    output = args.output or default_artifact_path(context, "verification.json")
    artifact = verification_artifact(result)
    write_artifact(output, artifact, phase="verify")
    summary = dict(artifact)
    summary["command"] = "verify"
    summary["output_path"] = str(output)
    if result.status != "passed":
        exit_with_summary(summary, EXIT_VERIFY_FAILED, "verify", "verify_failed")
    return summary


def command_restore(args: argparse.Namespace) -> dict[str, object]:
    receipt = load_receipt(args.receipt)
    if receipt.inventory is None or receipt.plan is None:
        raise CliError(EXIT_ARTIFACT, "restore", "receipt_missing_authority")
    context = context_from_inventory(receipt.inventory)
    assert_inventory_plan_binding(receipt.inventory, receipt.plan, context, phase="restore")
    manifest = load_backup_manifest(args.manifest)
    manifest_digest = digest_json(manifest.to_unsigned_dict())
    if manifest.digest != manifest_digest:
        raise CliError(EXIT_ARTIFACT, "restore", "restore_manifest_digest_mismatch", path=args.manifest)
    if args.approve != manifest_digest:
        raise CliError(EXIT_APPROVAL, "restore", "restore_approval_mismatch", next_action="pass exact backup manifest digest")
    if receipt.backup_manifest_path is None or Path(receipt.backup_manifest_path).resolve(strict=False) != args.manifest.resolve(strict=False):
        raise CliError(EXIT_ARTIFACT, "restore", "restore_manifest_receipt_mismatch", path=args.manifest)
    if backup_manifest_digest(receipt.backup_manifest_path) != manifest_digest:
        raise CliError(EXIT_ARTIFACT, "restore", "restore_manifest_receipt_digest_mismatch", path=args.manifest)
    output = args.output or default_artifact_path(context, "restore-receipt.json")
    try:
        restore_receipt = restore_manifest(args.manifest, args.approve, context)
    except ValueError as exc:
        code = stable_code(exc, "restore_failed")
        exit_code = EXIT_APPROVAL if code in APPROVAL_CODES else (EXIT_ARTIFACT if any(token in code for token in ROOT_CODES) else EXIT_RESTORE)
        raise CliError(exit_code, "restore", code, next_action="restore with matching root map and approval") from exc
    artifact = receipt_artifact(restore_receipt)
    write_artifact(output, artifact, phase="restore")
    summary = receipt_command_summary(
        command="restore",
        receipt_path=output,
        receipt=restore_receipt,
        artifact=artifact,
    )
    if restore_receipt.status != ReceiptStatus.COMPLETED:
        exit_with_summary(summary, EXIT_RESTORE, "restore", f"restore_{summary['status']}")
    return summary


def build_adapters() -> tuple[object, ...]:
    catalog = load_ownership_catalog()
    registry = AdapterRegistry()
    registry.register(ClaudeAdapter(catalog))
    registry.register(CodexAdapter())
    registry.register(OpenCodeAdapter(catalog))
    registry.register(PiAdapter(catalog))
    for path in sorted((SKILL_ROOT / "adapters").glob("*.json"), key=lambda item: item.name):
        registry.register(load_declarative_adapter(path, SKILL_ROOT / "references" / "ownership-catalog-v1.json"))
    return tuple(registry._adapters.values())


def context_from_args(args: argparse.Namespace) -> RuntimeContext:
    explicit_env = parse_env_args(args.env)
    has_explicit_authority = args.home is not None or args.platform is not None or bool(explicit_env)
    source_env: Mapping[str, str] = {} if has_explicit_authority else os.environ
    env = validate_env_roots(selected_env(source_env, extra=explicit_env), phase="inventory")
    home = validate_authority_root(args.home if args.home is not None else Path.home(), "home", phase="inventory")
    os_name = normalize_platform(args.platform if args.platform is not None else platform_module.system())
    projects = tuple(validate_authority_root(root, "project", phase="inventory") for root in args.project_root)
    return RuntimeContext(PlatformProfile(os_name, home, env), project_roots=projects)


def context_from_inventory(inventory: Inventory) -> RuntimeContext:
    home = validate_authority_root(Path(inventory.home), "home", phase="inventory")
    os_name = normalize_platform(inventory.os_name)
    projects = tuple(validate_authority_root(Path(value), "project", phase="inventory") for root_id, value in sorted(inventory.root_map.items()) if root_id.startswith("project-"))
    env = validate_env_roots(inventory.environment, phase="inventory")
    return RuntimeContext(PlatformProfile(os_name, home, env), project_roots=projects)


def selected_env(source: Mapping[str, str], *, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = {key: str(source[key]) for key in ENVIRONMENT_ENV_KEYS if key in source and source[key]}
    if extra:
        env.update(extra)
    return env


def parse_env_args(items: Sequence[str]) -> dict[str, str]:
    allowed = set(ENVIRONMENT_ENV_KEYS)
    env: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or key not in allowed or not value or key in env:
            raise CliError(EXIT_USAGE, "inventory", "invalid_env_argument")
        env[key] = value
    return env


def validate_env_roots(env: Mapping[str, str], *, phase: str) -> dict[str, str]:
    try:
        return canonical_environment_roots(dict(env))
    except ValueError as exc:
        code = stable_code(exc, "environment_root_invalid")
        raise CliError(EXIT_USAGE, phase, code) from exc


def validate_authority_root(path: Path, root_name: str, *, phase: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise CliError(EXIT_USAGE, phase, f"{root_name}_root_not_absolute")
    resolved = candidate.resolve(strict=False)
    if candidate != resolved:
        raise CliError(EXIT_USAGE, phase, f"{root_name}_root_not_canonical")
    try:
        st = os.lstat(candidate)
    except FileNotFoundError:
        return resolved
    if stat.S_ISLNK(st.st_mode) or _is_windows_reparse_point(st):
        raise CliError(EXIT_USAGE, phase, f"{root_name}_root_link_or_reparse")
    return resolved


def normalize_platform(value: str) -> str:
    lowered = value.lower()
    if lowered in {"darwin", "mac", "macos", "osx"}:
        return "macos"
    if lowered.startswith("win"):
        return "windows"
    if lowered == "linux":
        return "linux"
    raise CliError(EXIT_USAGE, "context", "unsupported_platform")


def default_artifact_path(context: RuntimeContext, name: str) -> Path:
    return resolve_state_root(context.profile) / "artifacts" / name


def inventory_artifact(inventory: Inventory) -> dict[str, object]:
    data = inventory.to_dict()
    data["schema"] = INVENTORY_SCHEMA
    return data


def plan_artifact(plan: Plan) -> dict[str, object]:
    data = plan.to_dict()
    data["schema"] = PLAN_SCHEMA
    return data


def receipt_artifact(receipt: Receipt) -> dict[str, object]:
    unsigned = receipt.to_dict()
    data = {"schema": RECEIPT_SCHEMA, **unsigned}
    data["digest"] = digest_json(data_without_digest(data))
    return data


def receipt_command_summary(
    *,
    command: str,
    receipt_path: os.PathLike[str],
    receipt: Receipt,
    artifact: Mapping[str, object],
    backup_manifest_digest: str | None = None,
    counts: Mapping[str, object] | None = None,
) -> dict[str, object]:
    summary = {
        "status": None if receipt.status is None else str(receipt.status),
        "command": command,
        "receipt_path": str(receipt_path),
        "digest": artifact["digest"],
        "backup_manifest_path": artifact["backup_manifest_path"],
    }
    if backup_manifest_digest is not None:
        summary["backup_manifest_digest"] = backup_manifest_digest
    if counts is not None:
        summary["counts"] = dict(counts)
    return summary


def verification_artifact(result: VerificationResult) -> dict[str, object]:
    data = {"schema": VERIFICATION_SCHEMA, **result.to_dict()}
    data["digest"] = digest_json(data_without_digest(data))
    return data


def data_without_digest(data: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in data.items() if key != "digest"}


def write_artifact(path: Path, data: dict[str, object], *, phase: str) -> None:
    reject_output_path(path, phase=phase)
    try:
        write_json_atomic(path, data, mode=0o600)
    except OSError as exc:
        raise CliError(EXIT_IO, phase, exc.__class__.__name__, path=path) from exc


def reject_output_path(path: Path, *, phase: str) -> None:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(st.st_mode) or _is_windows_reparse_point(st):
        raise CliError(EXIT_UNSAFE_PATH, phase, "artifact_output_symlink", path=path, next_action="choose a regular output file path")
    if not stat.S_ISREG(st.st_mode):
        raise CliError(EXIT_UNSAFE_PATH, phase, "artifact_output_not_regular", path=path)


def load_json_artifact(path: Path, *, phase: str) -> dict[str, object]:
    reject_input_path(path, phase=phase)
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(EXIT_ARTIFACT, phase, "artifact_malformed_json", path=path) from exc
    except OSError as exc:
        raise CliError(EXIT_IO, phase, exc.__class__.__name__, path=path) from exc
    if not isinstance(data, dict):
        raise CliError(EXIT_ARTIFACT, phase, "artifact_not_object", path=path)
    return data


def reject_input_path(path: Path, *, phase: str) -> None:
    try:
        st = os.lstat(path)
    except FileNotFoundError as exc:
        raise CliError(EXIT_ARTIFACT, phase, "artifact_missing", path=path) from exc
    if stat.S_ISLNK(st.st_mode) or _is_windows_reparse_point(st):
        raise CliError(EXIT_UNSAFE_PATH, phase, "artifact_input_symlink", path=path, next_action="use the real regular artifact path")
    if not stat.S_ISREG(st.st_mode):
        raise CliError(EXIT_UNSAFE_PATH, phase, "artifact_input_not_regular", path=path)


def load_inventory(path: Path) -> Inventory:
    data = load_json_artifact(path, phase="inventory")
    require_schema(data, INVENTORY_SCHEMA, phase="inventory", path=path)
    allowed = {"schema", "os_name", "home", "root_map", "environment", "adapter_versions", "adapter_layouts", "candidates", "findings", "digest"}
    reject_unknown(data, allowed, phase="inventory", path=path)
    require_keys(data, {"schema", "os_name", "home", "root_map", "environment", "adapter_versions", "adapter_layouts", "digest"}, phase="inventory", path=path)
    inventory = Inventory(
        os_name=require_str(data, "os_name", phase="inventory", path=path),
        home=require_str(data, "home", phase="inventory", path=path),
        root_map=require_str_map(data.get("root_map"), phase="inventory", path=path),
        environment=require_environment_map(data.get("environment"), phase="inventory", path=path),
        adapter_versions=require_str_map(data.get("adapter_versions"), phase="inventory", path=path),
        adapter_layouts=require_str_map(data.get("adapter_layouts"), phase="inventory", path=path),
        candidates=tuple(candidate_from_dict(item, phase="inventory", path=path) for item in require_list(data.get("candidates", []), phase="inventory", path=path)),
        findings=tuple(finding_from_dict(item, phase="inventory", path=path) for item in require_list(data.get("findings", []), phase="inventory", path=path)),
        digest=require_str(data, "digest", phase="inventory", path=path),
    )
    if inventory.digest != digest_json(inventory.to_unsigned_dict()):
        raise CliError(EXIT_ARTIFACT, "inventory", "inventory_digest_mismatch", path=path)
    return inventory


def load_plan(path: Path) -> Plan:
    data = load_json_artifact(path, phase="plan")
    require_schema(data, PLAN_SCHEMA, phase="plan", path=path)
    allowed = {"schema", "inventory_digest", "os_name", "home", "root_map", "adapter_versions", "adapter_layouts", "operations", "blocked_candidate_ids", "dependencies", "lifecycle_actions", "preservation_assertions", "digest"}
    reject_unknown(data, allowed, phase="plan", path=path)
    require_keys(data, {"schema", "inventory_digest", "os_name", "home", "root_map", "adapter_versions", "adapter_layouts", "digest"}, phase="plan", path=path)
    plan = Plan(
        inventory_digest=require_str(data, "inventory_digest", phase="plan", path=path),
        os_name=require_str(data, "os_name", phase="plan", path=path),
        home=require_str(data, "home", phase="plan", path=path),
        root_map=require_str_map(data.get("root_map"), phase="plan", path=path),
        adapter_versions=require_str_map(data.get("adapter_versions"), phase="plan", path=path),
        adapter_layouts=require_str_map(data.get("adapter_layouts"), phase="plan", path=path),
        operations=tuple(operation_from_dict(item, phase="plan", path=path) for item in require_list(data.get("operations", []), phase="plan", path=path)),
        blocked_candidate_ids=tuple(require_str_item(item, phase="plan", path=path) for item in require_list(data.get("blocked_candidate_ids", []), phase="plan", path=path)),
        dependencies=dependencies_from_dict(data.get("dependencies", {}), phase="plan", path=path),
        lifecycle_actions=tuple(lifecycle_action_from_dict(item, phase="plan", path=path) for item in require_list(data.get("lifecycle_actions", []), phase="plan", path=path)),
        preservation_assertions=tuple(preservation_from_dict(item, phase="plan", path=path) for item in require_list(data.get("preservation_assertions", []), phase="plan", path=path)),
        digest=require_str(data, "digest", phase="plan", path=path),
    )
    if plan.digest != digest_json(plan.to_unsigned_dict()):
        raise CliError(EXIT_ARTIFACT, "plan", "plan_digest_mismatch", path=path)
    return plan


def load_receipt(path: Path) -> Receipt:
    data = load_json_artifact(path, phase="receipt")
    require_schema(data, RECEIPT_SCHEMA, phase="receipt", path=path)
    allowed = {"schema", "operation_outcomes", "backup_manifest_path", "lifecycle_outcomes", "checks", "status", "plan", "inventory", "digest"}
    reject_unknown(data, allowed, phase="receipt", path=path)
    require_keys(data, {"schema", "operation_outcomes", "backup_manifest_path", "lifecycle_outcomes", "checks", "status", "plan", "inventory", "digest"}, phase="receipt", path=path)
    expected = digest_json(data_without_digest(data))
    if data.get("digest") != expected:
        raise CliError(EXIT_ARTIFACT, "receipt", "receipt_digest_mismatch", path=path)
    plan_data = data.get("plan")
    inventory_data = data.get("inventory")
    receipt = Receipt(
        operation_outcomes=tuple(operation_outcome_from_dict(item, phase="receipt", path=path) for item in require_list(data.get("operation_outcomes"), phase="receipt", path=path)),
        backup_manifest_path=None if data.get("backup_manifest_path") is None else Path(require_str(data, "backup_manifest_path", phase="receipt", path=path)),
        lifecycle_outcomes=tuple(lifecycle_outcome_from_dict(item, phase="receipt", path=path) for item in require_list(data.get("lifecycle_outcomes"), phase="receipt", path=path)),
        checks=tuple(check_from_dict(item, phase="receipt", path=path) for item in require_list(data.get("checks"), phase="receipt", path=path)),
        status=None if data.get("status") is None else ReceiptStatus(require_str(data, "status", phase="receipt", path=path)),
        plan=None if plan_data is None else plan_from_embedded(plan_data, phase="receipt", path=path),
        inventory=None if inventory_data is None else inventory_from_embedded(inventory_data, phase="receipt", path=path),
    )
    return receipt


def load_backup_manifest(path: Path) -> BackupManifest:
    data = load_json_artifact(path, phase="restore")
    if data.get("schema") != BACKUP_SCHEMA:
        raise CliError(EXIT_ARTIFACT, "restore", "restore_manifest_invalid_schema", path=path)
    manifest = BackupManifest.from_dict(data, path)
    return manifest


def inventory_from_embedded(data: object, *, phase: str, path: Path) -> Inventory:
    if not isinstance(data, dict):
        raise CliError(EXIT_ARTIFACT, phase, "embedded_inventory_invalid", path=path)
    data = dict(data)
    data.setdefault("schema", INVENTORY_SCHEMA)
    temp = path
    allowed = {"schema", "os_name", "home", "root_map", "environment", "adapter_versions", "adapter_layouts", "candidates", "findings", "digest"}
    reject_unknown(data, allowed, phase=phase, path=temp)
    require_keys(data, {"schema", "os_name", "home", "root_map", "environment", "adapter_versions", "adapter_layouts", "digest"}, phase=phase, path=temp)
    inv = Inventory(
        os_name=require_str(data, "os_name", phase=phase, path=temp),
        home=require_str(data, "home", phase=phase, path=temp),
        root_map=require_str_map(data.get("root_map"), phase=phase, path=temp),
        environment=require_environment_map(data.get("environment"), phase=phase, path=temp),
        adapter_versions=require_str_map(data.get("adapter_versions"), phase=phase, path=temp),
        adapter_layouts=require_str_map(data.get("adapter_layouts"), phase=phase, path=temp),
        candidates=tuple(candidate_from_dict(item, phase=phase, path=temp) for item in require_list(data.get("candidates", []), phase=phase, path=temp)),
        findings=tuple(finding_from_dict(item, phase=phase, path=temp) for item in require_list(data.get("findings", []), phase=phase, path=temp)),
        digest=require_str(data, "digest", phase=phase, path=temp),
    )
    if inv.digest != digest_json(inv.to_unsigned_dict()):
        raise CliError(EXIT_ARTIFACT, phase, "inventory_digest_mismatch", path=temp)
    return inv


def plan_from_embedded(data: object, *, phase: str, path: Path) -> Plan:
    if not isinstance(data, dict):
        raise CliError(EXIT_ARTIFACT, phase, "embedded_plan_invalid", path=path)
    data = dict(data)
    data.setdefault("schema", PLAN_SCHEMA)
    allowed = {"schema", "inventory_digest", "os_name", "home", "root_map", "adapter_versions", "adapter_layouts", "operations", "blocked_candidate_ids", "dependencies", "lifecycle_actions", "preservation_assertions", "digest"}
    reject_unknown(data, allowed, phase=phase, path=path)
    plan = Plan(
        inventory_digest=require_str(data, "inventory_digest", phase=phase, path=path),
        os_name=require_str(data, "os_name", phase=phase, path=path),
        home=require_str(data, "home", phase=phase, path=path),
        root_map=require_str_map(data.get("root_map"), phase=phase, path=path),
        adapter_versions=require_str_map(data.get("adapter_versions"), phase=phase, path=path),
        adapter_layouts=require_str_map(data.get("adapter_layouts"), phase=phase, path=path),
        operations=tuple(operation_from_dict(item, phase=phase, path=path) for item in require_list(data.get("operations", []), phase=phase, path=path)),
        blocked_candidate_ids=tuple(require_str_item(item, phase=phase, path=path) for item in require_list(data.get("blocked_candidate_ids", []), phase=phase, path=path)),
        dependencies=dependencies_from_dict(data.get("dependencies", {}), phase=phase, path=path),
        lifecycle_actions=tuple(lifecycle_action_from_dict(item, phase=phase, path=path) for item in require_list(data.get("lifecycle_actions", []), phase=phase, path=path)),
        preservation_assertions=tuple(preservation_from_dict(item, phase=phase, path=path) for item in require_list(data.get("preservation_assertions", []), phase=phase, path=path)),
        digest=require_str(data, "digest", phase=phase, path=path),
    )
    if plan.digest != digest_json(plan.to_unsigned_dict()):
        raise CliError(EXIT_ARTIFACT, phase, "plan_digest_mismatch", path=path)
    return plan


def candidate_from_dict(data: object, *, phase: str, path: Path) -> Candidate:
    if not isinstance(data, dict):
        raise CliError(EXIT_ARTIFACT, phase, "candidate_invalid", path=path)
    allowed = {"candidate_id", "client", "path", "artifact_class", "evidence", "ownership", "proposed_action", "preimage", "dependencies", "reason", "details"}
    reject_unknown(data, allowed, phase=phase, path=path)
    require_keys(data, allowed, phase=phase, path=path)
    preimage_data = data.get("preimage")
    preimage = None
    if preimage_data is not None:
        if not isinstance(preimage_data, dict) or set(preimage_data) != {"path"} or not isinstance(preimage_data.get("path"), str):
            raise CliError(EXIT_ARTIFACT, phase, "preimage_invalid", path=path)
        preimage = Preimage(str(preimage_data["path"]))
    return Candidate(
        candidate_id=require_str(data, "candidate_id", phase=phase, path=path),
        client=require_str(data, "client", phase=phase, path=path),
        path=require_str(data, "path", phase=phase, path=path),
        artifact_class=ArtifactClass(require_str(data, "artifact_class", phase=phase, path=path)),
        evidence=tuple(require_list(data.get("evidence"), phase=phase, path=path)),
        ownership=Ownership(require_str(data, "ownership", phase=phase, path=path)),
        proposed_action=require_str(data, "proposed_action", phase=phase, path=path),
        preimage=preimage,
        dependencies=tuple(require_str_item(item, phase=phase, path=path) for item in require_list(data.get("dependencies"), phase=phase, path=path)),
        reason=require_str(data, "reason", phase=phase, path=path),
        details=require_mapping(data.get("details"), phase=phase, path=path),
    )


def operation_from_dict(data: object, *, phase: str, path: Path) -> Operation:
    if not isinstance(data, dict):
        raise CliError(EXIT_ARTIFACT, phase, "operation_invalid", path=path)
    allowed = {"kind", "path", "candidate_id", "preimage_base64", "preimage_sha256", "postimage_base64", "postimage_sha256", "dependencies", "details"}
    reject_unknown(data, allowed, phase=phase, path=path)
    require_keys(data, {"kind", "path"}, phase=phase, path=path)
    return Operation(
        kind=OperationKind(require_str(data, "kind", phase=phase, path=path)),
        path=require_str(data, "path", phase=phase, path=path),
        candidate_id=optional_str(data.get("candidate_id"), phase=phase, path=path),
        preimage_base64=optional_str(data.get("preimage_base64"), phase=phase, path=path),
        preimage_sha256=optional_str(data.get("preimage_sha256"), phase=phase, path=path),
        postimage_base64=optional_str(data.get("postimage_base64"), phase=phase, path=path),
        postimage_sha256=optional_str(data.get("postimage_sha256"), phase=phase, path=path),
        dependencies=tuple(require_str_item(item, phase=phase, path=path) for item in require_list(data.get("dependencies", []), phase=phase, path=path)),
        details=require_mapping(data.get("details", {}), phase=phase, path=path),
    )


def lifecycle_action_from_dict(data: object, *, phase: str, path: Path) -> LifecycleAction:
    if not isinstance(data, dict):
        raise CliError(EXIT_ARTIFACT, phase, "lifecycle_action_invalid", path=path)
    allowed = {"candidate_id", "client", "action", "target", "reason", "details"}
    reject_unknown(data, allowed, phase=phase, path=path)
    return LifecycleAction(
        candidate_id=str(data.get("candidate_id", "")),
        client=str(data.get("client", "")),
        action=str(data.get("action", "")),
        target=str(data.get("target", "")),
        reason=str(data.get("reason", "")),
        details=require_mapping(data.get("details", {}), phase=phase, path=path),
    )


def preservation_from_dict(data: object, *, phase: str, path: Path) -> Any:
    from helper.models import PreservationAssertion

    if not isinstance(data, dict):
        raise CliError(EXIT_ARTIFACT, phase, "preservation_invalid", path=path)
    allowed = {"candidate_id", "client", "path", "reason", "evidence", "details"}
    reject_unknown(data, allowed, phase=phase, path=path)
    return PreservationAssertion(
        candidate_id=str(data.get("candidate_id", "")),
        client=str(data.get("client", "")),
        path=str(data.get("path", "")),
        reason=str(data.get("reason", "")),
        evidence=tuple(require_list(data.get("evidence", []), phase=phase, path=path)),
        details=require_mapping(data.get("details", {}), phase=phase, path=path),
    )


def finding_from_dict(data: object, *, phase: str, path: Path) -> InventoryFinding:
    if not isinstance(data, dict) or set(data) != {"client", "code", "message"}:
        raise CliError(EXIT_ARTIFACT, phase, "finding_invalid", path=path)
    return InventoryFinding(client=str(data["client"]), code=str(data["code"]), message=str(data["message"]))


def operation_outcome_from_dict(data: object, *, phase: str, path: Path) -> OperationOutcome:
    if not isinstance(data, dict):
        raise CliError(EXIT_ARTIFACT, phase, "operation_outcome_invalid", path=path)
    allowed = {"operation_index", "kind", "path", "status", "error"}
    reject_unknown(data, allowed, phase=phase, path=path)
    require_keys(data, {"operation_index", "kind", "path", "status"}, phase=phase, path=path)
    return OperationOutcome(int(data["operation_index"]), str(data["kind"]), str(data["path"]), str(data["status"]), None if data.get("error") is None else str(data["error"]))


def lifecycle_outcome_from_dict(data: object, *, phase: str, path: Path) -> LifecycleOutcome:
    if not isinstance(data, dict):
        raise CliError(EXIT_ARTIFACT, phase, "lifecycle_outcome_invalid", path=path)
    allowed = {"action", "client", "target", "status", "code", "pid", "argv"}
    reject_unknown(data, allowed, phase=phase, path=path)
    require_keys(data, {"action", "client", "target", "status", "argv"}, phase=phase, path=path)
    return LifecycleOutcome(str(data["action"]), str(data["client"]), str(data["target"]), str(data["status"]), None if data.get("code") is None else str(data["code"]), None if data.get("pid") is None else int(data["pid"]), tuple(str(item) for item in require_list(data.get("argv", []), phase=phase, path=path)))


def check_from_dict(data: object, *, phase: str, path: Path) -> Check:
    if not isinstance(data, dict) or set(data) != {"code", "status", "severity", "evidence"}:
        raise CliError(EXIT_ARTIFACT, phase, "check_invalid", path=path)
    return Check(str(data["code"]), str(data["status"]), str(data["severity"]), require_mapping(data.get("evidence"), phase=phase, path=path))


def dependencies_from_dict(data: object, *, phase: str, path: Path) -> dict[str, tuple[str, ...]]:
    mapping = require_mapping(data, phase=phase, path=path)
    result: dict[str, tuple[str, ...]] = {}
    for key, value in mapping.items():
        result[str(key)] = tuple(require_str_item(item, phase=phase, path=path) for item in require_list(value, phase=phase, path=path))
    return result


def assert_context_matches_inventory(inventory: Inventory, context: RuntimeContext, *, phase: str) -> None:
    if inventory.home != str(context.profile.home.resolve(strict=False)):
        raise CliError(EXIT_ARTIFACT, phase, f"{phase}_inventory_root_home_mismatch")
    if inventory.os_name != context.profile.os_name:
        raise CliError(EXIT_ARTIFACT, phase, f"{phase}_inventory_root_os_mismatch")
    if dict(sorted(inventory.root_map.items())) != dict(sorted(root_map(context).items())):
        raise CliError(EXIT_ARTIFACT, phase, f"{phase}_inventory_root_map_mismatch")
    try:
        context_environment = canonical_environment_roots(context.profile.env)
    except ValueError as exc:
        raise CliError(EXIT_ARTIFACT, phase, stable_code(exc, "environment_root_invalid")) from exc
    if dict(sorted(inventory.environment.items())) != context_environment:
        raise CliError(EXIT_ARTIFACT, phase, f"{phase}_inventory_environment_mismatch")


def assert_inventory_plan_binding(inventory: Inventory, plan: Plan, context: RuntimeContext, *, phase: str) -> None:
    assert_context_matches_inventory(inventory, context, phase=phase)
    if plan.inventory_digest != inventory.digest:
        raise CliError(EXIT_ARTIFACT, phase, f"{phase}_plan_inventory_digest_mismatch")
    if plan.home != inventory.home or plan.os_name != inventory.os_name:
        raise CliError(EXIT_ARTIFACT, phase, f"{phase}_plan_root_context_mismatch")
    if dict(sorted(plan.root_map.items())) != dict(sorted(inventory.root_map.items())):
        raise CliError(EXIT_ARTIFACT, phase, f"{phase}_plan_root_map_mismatch")


def assert_receipt_binding(receipt: Receipt, inventory: Inventory, plan: Plan, *, phase: str) -> None:
    if receipt.inventory is None or receipt.plan is None:
        raise CliError(EXIT_ARTIFACT, phase, f"{phase}_receipt_missing_embedded_artifacts")
    if receipt.inventory.digest != inventory.digest:
        raise CliError(EXIT_ARTIFACT, phase, f"{phase}_receipt_inventory_mismatch")
    if receipt.plan.digest != plan.digest:
        raise CliError(EXIT_ARTIFACT, phase, f"{phase}_receipt_plan_mismatch")


def inventory_counts(inventory: Inventory) -> dict[str, int]:
    active = sum(1 for candidate in inventory.candidates if candidate.ownership == Ownership.PROVEN and candidate.proposed_action != "report_only")
    ambiguous = sum(1 for candidate in inventory.candidates if candidate.ownership == Ownership.AMBIGUOUS)
    preserved = sum(1 for candidate in inventory.candidates if candidate.ownership == Ownership.PRESERVED)
    return {"active": active, "ambiguous": ambiguous, "preserved": preserved, "findings": len(inventory.findings)}


def backup_manifest_digest(path: Path | None) -> str | None:
    if path is None:
        return None
    manifest = load_backup_manifest(path)
    computed = digest_json(manifest.to_unsigned_dict())
    if manifest.digest != computed:
        raise CliError(EXIT_ARTIFACT, "backup", "backup_manifest_digest_mismatch", path=path)
    return computed


def require_schema(data: Mapping[str, object], schema: str, *, phase: str, path: Path) -> None:
    if data.get("schema") != schema:
        raise CliError(EXIT_ARTIFACT, phase, "artifact_unknown_schema", path=path)


def reject_unknown(data: Mapping[str, object], allowed: set[str], *, phase: str, path: Path) -> None:
    if set(data) - allowed:
        raise CliError(EXIT_ARTIFACT, phase, "artifact_unknown_field", path=path)


def require_keys(data: Mapping[str, object], required: set[str], *, phase: str, path: Path) -> None:
    if required - set(data):
        raise CliError(EXIT_ARTIFACT, phase, "artifact_missing_field", path=path)


def require_str(data: Mapping[str, object], key: str, *, phase: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise CliError(EXIT_ARTIFACT, phase, "artifact_invalid_field", path=path)
    return value


def optional_str(value: object, *, phase: str, path: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CliError(EXIT_ARTIFACT, phase, "artifact_invalid_field", path=path)
    return value


def require_str_item(value: object, *, phase: str, path: Path) -> str:
    if not isinstance(value, str):
        raise CliError(EXIT_ARTIFACT, phase, "artifact_invalid_field", path=path)
    return value


def require_str_map(value: object, *, phase: str, path: Path) -> dict[str, str]:
    mapping = require_mapping(value, phase=phase, path=path)
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in mapping.items()):
        raise CliError(EXIT_ARTIFACT, phase, "artifact_invalid_field", path=path)
    return dict(sorted((str(key), str(item)) for key, item in mapping.items()))


def require_environment_map(value: object, *, phase: str, path: Path) -> dict[str, str]:
    mapping = require_str_map(value, phase=phase, path=path)
    try:
        return canonical_environment_roots(mapping, reject_unknown=True)
    except ValueError as exc:
        code = stable_code(exc, "environment_root_invalid")
        raise CliError(EXIT_ARTIFACT, phase, code, path=path) from exc


def require_mapping(value: object, *, phase: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CliError(EXIT_ARTIFACT, phase, "artifact_invalid_field", path=path)
    return dict(value)


def require_list(value: object, *, phase: str, path: Path) -> list[object]:
    if not isinstance(value, list):
        raise CliError(EXIT_ARTIFACT, phase, "artifact_invalid_field", path=path)
    return value


def exit_with_summary(summary: Mapping[str, object], exit_code: int, phase: str, code: str) -> None:
    sys.stdout.buffer.write(canonical_bytes(summary) + b"\n")
    emit_error(CliError(exit_code, phase, code))
    raise SystemExit(exit_code)


def stable_code(exc: BaseException, fallback: str) -> str:
    if exc.args and isinstance(exc.args[0], str):
        return exc.args[0]
    return fallback


def emit_error(error: CliError) -> None:
    parts = [f"code={error.code}", f"phase={error.phase}"]
    if error.path is not None:
        parts.append(f"path={safe_path(error.path)}")
    parts.append(f"next_action={error.next_action}")
    print(" ".join(parts), file=sys.stderr)


def safe_path(path: Path) -> str:
    return str(path)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
