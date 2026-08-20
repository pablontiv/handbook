from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from helper.canonical import digest_json
from helper.models import ArtifactClass, Candidate, Check, Operation, OperationKind, Ownership, Preimage, Receipt, RuntimeContext
from helper.ownership import classify_exact_file_ownership, load_ownership_catalog, recognized_managed_marker_evidence

CLIENT = "opencode"
VERSION = "1"
LAYOUT_VERSION = "opencode-bounded-v1"
_CONFIG_FILE = "opencode.json"
_TUI_FILE = "tui.json"
_PACKAGE_FILE = "package.json"
_SDD_PLUGIN_PACKAGE = "opencode-sdd-engram-manage"
_BROKEN_LOGO_FILE = "gentle-logo.tsx"
_DEFAULT_GENTLE_AGENT = "gentle-orchestrator"
_DEFAULT_FALLBACK_AGENT = "general"
_CONFIG_FAMILIES = ("agent", "agents", "command", "commands", "prompt", "prompts", "skill", "skills")
_AGENT_CONFIG_FAMILIES = ("agent", "agents")
_EXACT_FILE_ROOTS = ("agent", "agents", "command", "commands", "prompt", "prompts", "skill", "skills")
_EXACT_FILE_SUFFIXES = (".md", ".json")


class OpenCodeAdapter:
    client = CLIENT
    version = VERSION
    layout_version = LAYOUT_VERSION

    def __init__(self, catalog: Mapping[str, Any] | None = None, *, general_builtin_fallback: bool = True) -> None:
        self.catalog = load_ownership_catalog() if catalog is None else catalog
        self.general_builtin_fallback = general_builtin_fallback

    def inventory(self, context: RuntimeContext) -> tuple[Candidate, ...]:
        config_dir = _config_dir(context)
        if not _allowed_home_child(config_dir, context):
            raise ValueError("opencode_config_dir_outside_home")
        if not config_dir.exists():
            return ()
        if not config_dir.is_dir():
            raise ValueError("opencode_layout_not_directory")

        candidates: list[Candidate] = []
        config_path = config_dir / _CONFIG_FILE
        tui_path = config_dir / _TUI_FILE
        package_path = config_dir / _PACKAGE_FILE

        config_data: dict[str, Any] | None = None
        if config_path.is_file():
            config_data = _load_json_object(config_path)
            candidates.extend(self._config_candidates(config_path, config_data))
            if "mcp" in config_data:
                candidates.append(_preserved_candidate(
                    rule_id="mcp",
                    target=config_path,
                    artifact_class=ArtifactClass.PRESERVED_INFRASTRUCTURE,
                    reason="OpenCode MCP configuration is preserved byte-for-byte unless another owned field in the same JSON file changes",
                    details={"kind": "mcp", "digest": digest_json(config_data["mcp"])},
                    evidence=({"kind": "mcp", "digest": digest_json(config_data["mcp"])},),
                ))

        local_plugin_decisions: dict[str, Candidate] = {}
        if tui_path.is_file():
            tui_data = _load_json_object(tui_path)
            plugin_values = _plugin_values(tui_data, tui_path)
            local_plugin_decisions = self._local_plugin_file_candidates(plugin_values, context)
            candidates.extend(local_plugin_decisions.values())
            candidates.extend(self._tui_candidates(tui_path, tui_data, local_plugin_decisions))

        if package_path.is_file():
            package_data = _load_json_object(package_path)
            candidates.extend(self._package_preservation_candidates(package_path, package_data, config_dir))

        candidates.extend(self._exact_root_file_candidates(config_dir, context))
        return tuple(sorted(_dedupe_candidates(candidates), key=lambda candidate: (candidate.path, candidate.candidate_id)))

    def compile(self, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]:
        if candidate.ownership != Ownership.PROVEN or candidate.proposed_action == "report_only":
            return ()
        kind = candidate.details.get("kind")
        if kind == "config_json_cleanup":
            path = Path(candidate.path)
            data = _load_json_object(path)
            after, _actions, _ambiguous_default, _ambiguous_entries = _sanitize_config(data, self._gentle_config_names(), self.general_builtin_fallback, self.catalog)
            if after == data:
                return ()
            return (_write_json_operation(candidate, after, operation="sanitize_opencode_config"),)
        if kind == "tui_json_cleanup":
            path = Path(candidate.path)
            data = _load_json_object(path)
            remove_values = tuple(str(value) for value in candidate.details.get("remove_values", ()) if isinstance(value, str))
            after = _remove_plugin_values(data, remove_values)
            if after == data:
                return ()
            return (_write_json_operation(candidate, after, operation="sanitize_opencode_tui_plugins"),)
        if kind in {"local_plugin_file", "exact_root_file"} and candidate.proposed_action == "delete_file":
            return (Operation(kind=OperationKind.DELETE_FILE, path=candidate.path),)
        return ()

    def verify(self, receipt: Receipt, context: RuntimeContext) -> tuple[Check, ...]:
        config_dir = _config_dir(context)
        if not _allowed_home_child(config_dir, context):
            raise ValueError("opencode_config_dir_outside_home")
        config_path = config_dir / _CONFIG_FILE
        tui_path = config_dir / _TUI_FILE

        if config_path.is_file():
            data = _load_json_object(config_path)
            after, _actions, _ambiguous_default, _ambiguous_entries = _sanitize_config(data, self._gentle_config_names(), self.general_builtin_fallback, self.catalog)
            if after != data:
                raise ValueError("verify_opencode_gentle_config_entry_present")

        if tui_path.is_file():
            data = _load_json_object(tui_path)
            for value in _plugin_values(data, tui_path):
                if _is_exact_sdd_plugin_registration(value) or _is_missing_gentle_logo_registration(value, config_dir):
                    raise ValueError("verify_opencode_plugin_registration_present")

        for outcome in receipt.operation_outcomes:
            if outcome.status != "completed" or not _allowed_home_child(Path(outcome.path), context):
                continue
            target = Path(outcome.path)
            kind = OperationKind(str(outcome.kind))
            if kind == OperationKind.DELETE_FILE and (target.exists() or target.is_symlink()):
                raise ValueError("verify_delete_file_still_present")
            if kind == OperationKind.WRITE_FILE and target in {config_path, tui_path}:
                _load_json_object(target)
        return tuple(receipt.checks)

    def _config_candidates(self, path: Path, data: Mapping[str, Any]) -> list[Candidate]:
        after, actions, ambiguous_default, ambiguous_entries = _sanitize_config(data, self._gentle_config_names(), self.general_builtin_fallback, self.catalog)
        candidates: list[Candidate] = []
        if ambiguous_default:
            candidates.append(_candidate(
                rule_id="default-agent:ambiguous",
                target=path,
                artifact_class=ArtifactClass.AMBIGUOUS,
                ownership=Ownership.AMBIGUOUS,
                proposed_action="report_only",
                evidence=({"kind": "default_agent", "value": data.get("default_agent")},),
                reason="OpenCode default_agent references a catalog Gentle registration, but the active default does not have proven removable registration evidence and a safe fallback",
                details={"kind": "default_agent", "default_agent": data.get("default_agent"), "fallback": _DEFAULT_FALLBACK_AGENT},
            ))
        for entry in ambiguous_entries:
            family = str(entry.get("family", ""))
            name = str(entry.get("name", ""))
            candidates.append(_candidate(
                rule_id=f"config-entry:ambiguous:{family}:{name}",
                target=path,
                artifact_class=ArtifactClass.AMBIGUOUS,
                ownership=Ownership.AMBIGUOUS,
                proposed_action="report_only",
                evidence=({"kind": "config_entry", "family": family, "name": name, "catalog_identity": True},),
                reason="OpenCode config entry matches a catalog name, but catalog key/name alone does not prove removal ownership",
                details={"kind": "config_entry", "family": family, "name": name},
            ))
        if after != data:
            candidates.append(_candidate(
                rule_id="config-json-cleanup",
                target=path,
                artifact_class=ArtifactClass.ACTIVE_SOURCE,
                ownership=Ownership.PROVEN,
                proposed_action="write_file",
                evidence=tuple(actions),
                reason="OpenCode config contains recognized Gentle registrations or default-agent state removable as one JSON postimage",
                details={"kind": "config_json_cleanup", "actions": tuple(actions)},
            ))
        return candidates

    def _tui_candidates(self, path: Path, data: Mapping[str, Any], local_plugin_decisions: Mapping[str, Candidate]) -> list[Candidate]:
        plugin_values = _plugin_values(data, path)
        removable_values: list[str] = []
        evidence_candidates: list[Candidate] = []
        seen_evidence: set[tuple[str, ArtifactClass]] = set()

        for value in plugin_values:
            plugin_name = _plugin_display_name(value)
            artifact_class: ArtifactClass | None = None
            evidence: tuple[object, ...] = ()
            reason = ""
            if _is_exact_sdd_plugin_registration(value):
                artifact_class = ArtifactClass.ACTIVE_SOURCE
                evidence = ({"kind": "plugin_registration", "value": value, "package_dependency_preserved": True},)
                reason = "OpenCode TUI registers the exact Gentle SDD Engram plugin; unregister it without removing the package"
            elif _is_missing_gentle_logo_registration(value, path.parent):
                artifact_class = ArtifactClass.BROKEN_REGISTRATION
                evidence = ({"kind": "missing_plugin_file", "value": value, "plugin": plugin_name},)
                reason = "OpenCode TUI still registers the known Gentle logo plugin, but the exact plugin file is absent"
            elif value in local_plugin_decisions and local_plugin_decisions[value].ownership == Ownership.PROVEN:
                artifact_class = ArtifactClass.ACTIVE_SOURCE
                evidence = ({"kind": "local_plugin_registration", "value": value, "plugin": plugin_name},)
                reason = "OpenCode TUI registers a local plugin whose file has Gentle-managed marker or fingerprint evidence"

            if artifact_class is None:
                continue
            removable_values.append(value)
            key = (value, artifact_class)
            if key in seen_evidence:
                continue
            seen_evidence.add(key)
            evidence_candidates.append(_candidate(
                rule_id=f"plugin-registration:{artifact_class}:{value}",
                target=path,
                artifact_class=artifact_class,
                ownership=Ownership.PROVEN,
                proposed_action="report_only",
                evidence=evidence,
                reason=reason,
                details={"kind": "plugin_registration", "plugin": plugin_name, "registration_value": value},
            ))

        candidates = evidence_candidates
        if removable_values:
            unique_remove_values = tuple(dict.fromkeys(removable_values))
            candidates.append(_candidate(
                rule_id="tui-plugin-cleanup",
                target=path,
                artifact_class=ArtifactClass.ACTIVE_SOURCE,
                ownership=Ownership.PROVEN,
                proposed_action="write_file",
                evidence=({"kind": "tui_plugin_cleanup", "remove_values": unique_remove_values},),
                reason="OpenCode TUI plugin registrations can be removed as one deterministic JSON postimage",
                details={"kind": "tui_json_cleanup", "remove_values": unique_remove_values},
            ))
            preserved_order = [value for value in plugin_values if value not in set(unique_remove_values)]
            candidates.append(_preserved_candidate(
                rule_id="tui-unrelated-plugin-order",
                target=path,
                artifact_class=ArtifactClass.PRESERVED_INFRASTRUCTURE,
                reason="OpenCode unrelated TUI plugin registrations and relative plugin values remain in their original order",
                evidence=({"kind": "plugin_order", "preserved_values": tuple(preserved_order)},),
                details={"kind": "plugin_order", "preserved_values": tuple(preserved_order)},
            ))
        return candidates

    def _package_preservation_candidates(self, package_path: Path, package_data: Mapping[str, Any], config_dir: Path) -> list[Candidate]:
        candidates: list[Candidate] = []
        dependency_sections: list[str] = []
        for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            raw = package_data.get(section)
            if isinstance(raw, Mapping) and _SDD_PLUGIN_PACKAGE in raw:
                dependency_sections.append(section)
        if dependency_sections:
            candidates.append(_preserved_candidate(
                rule_id="package-dependency:opencode-sdd-engram-manage",
                target=package_path,
                artifact_class=ArtifactClass.PRESERVED_INFRASTRUCTURE,
                reason="OpenCode SDD Engram npm dependency is package infrastructure and remains installed",
                evidence=({"kind": "package_dependency", "package": _SDD_PLUGIN_PACKAGE, "sections": tuple(dependency_sections)},),
                details={"kind": "package_dependency", "package": _SDD_PLUGIN_PACKAGE, "sections": tuple(dependency_sections)},
            ))
        node_module = config_dir / "node_modules" / _SDD_PLUGIN_PACKAGE
        if node_module.is_dir():
            candidates.append(_preserved_candidate(
                rule_id="node-module:opencode-sdd-engram-manage",
                target=node_module,
                artifact_class=ArtifactClass.PRESERVED_INFRASTRUCTURE,
                reason="OpenCode SDD Engram node_modules directory is installed package infrastructure and is not removed",
                evidence=({"kind": "node_module", "package": _SDD_PLUGIN_PACKAGE},),
                details={"kind": "node_module", "package": _SDD_PLUGIN_PACKAGE},
                preimage=False,
            ))
        return candidates

    def _local_plugin_file_candidates(self, plugin_values: Sequence[str], context: RuntimeContext) -> dict[str, Candidate]:
        decisions: dict[str, Candidate] = {}
        for value in dict.fromkeys(plugin_values):
            if not _is_absolute_path(value):
                continue
            target = Path(value)
            if not _allowed_home_child(target, context):
                continue
            if not target.exists():
                continue
            if not target.is_file():
                continue
            decision = self._exact_file_candidate(
                rule_id=f"local-plugin:{target.name}:{target.resolve(strict=False)}",
                target=target,
                context=context,
                kind="local_plugin_file",
                artifact_class=ArtifactClass.ACTIVE_SOURCE,
            )
            decisions[value] = decision
        return decisions

    def _exact_root_file_candidates(self, config_dir: Path, context: RuntimeContext) -> list[Candidate]:
        candidates: list[Candidate] = []
        names = tuple(dict.fromkeys((*self._gentle_config_names(), *self._personal_skill_names())))
        for root in _EXACT_FILE_ROOTS:
            for name in names:
                for target in _exact_targets(config_dir, root, name):
                    if target.is_file() and _allowed_home_child(target, context):
                        candidates.append(self._exact_file_candidate(
                            rule_id=f"exact-root:{root}:{name}:{target.name}",
                            target=target,
                            context=context,
                            kind="exact_root_file",
                            artifact_class=ArtifactClass.ACTIVE_SOURCE,
                        ))
        return candidates

    def _exact_file_candidate(self, *, rule_id: str, target: Path, context: RuntimeContext, kind: str, artifact_class: ArtifactClass) -> Candidate:
        rule = {"id": rule_id, "path": _home_relative(target, context), "artifact_class": str(artifact_class)}
        decision = classify_exact_file_ownership(target=target, rule_data=rule, default_action="delete_file", context=context, catalog=self.catalog)
        evidence = [{"kind": kind, "path": str(target)}]
        evidence.extend(decision.evidence)
        ownership = decision.ownership
        proposed_action = decision.proposed_action
        reason = decision.reason
        details = dict(decision.details)
        details.update({"kind": kind})

        return _candidate(
            rule_id=rule_id,
            target=target,
            artifact_class=artifact_class,
            ownership=ownership,
            proposed_action=proposed_action,
            evidence=tuple(evidence),
            reason=reason,
            details=details,
        )

    def _gentle_config_names(self) -> tuple[str, ...]:
        raw = self.catalog.get("agent_names", ())
        names = [name for name in raw if isinstance(name, str)] if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) else []
        names.append(_DEFAULT_GENTLE_AGENT)
        return tuple(dict.fromkeys(names))

    def _personal_skill_names(self) -> tuple[str, ...]:
        raw = self.catalog.get("adapted_skill_provenance", {})
        if not isinstance(raw, Mapping):
            return ()
        return tuple(name for name in raw if isinstance(name, str))


def _sanitize_config(data: Mapping[str, Any], gentle_names: Sequence[str], general_builtin_fallback: bool, catalog: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, object]], bool, list[dict[str, object]]]:
    after = copy.deepcopy(dict(data))
    actions: list[dict[str, object]] = []
    ambiguous_entries: list[dict[str, object]] = []
    ambiguous_default = False
    gentle_set = set(gentle_names)
    marker_prefix = _marker_prefix(catalog)
    proven_by_family: dict[str, dict[str, tuple[dict[str, object], ...]]] = {}

    for family in _CONFIG_FAMILIES:
        raw = data.get(family)
        if not isinstance(raw, Mapping):
            continue
        for name, value in raw.items():
            if not isinstance(name, str) or name not in gentle_set:
                continue
            proof = _config_entry_managed_proof(family, name, value, marker_prefix)
            if proof:
                proven_by_family.setdefault(family, {})[name] = proof
            else:
                ambiguous_entries.append({"family": family, "name": name})

    default_agent = data.get("default_agent")
    default_change_allowed = False
    protected_default_families: set[str] = set()
    if isinstance(default_agent, str) and default_agent in gentle_set:
        default_families = tuple(
            family
            for family in _AGENT_CONFIG_FAMILIES
            if isinstance(data.get(family), Mapping) and default_agent in data[family]
        )
        if len(default_families) == 1:
            default_family = default_families[0]
            agent_map = data.get(default_family)
            general_configured = isinstance(agent_map, Mapping) and _DEFAULT_FALLBACK_AGENT in agent_map
            default_proven = default_agent in proven_by_family.get(default_family, {})
            default_change_allowed = default_proven and (general_configured or general_builtin_fallback)
            if default_change_allowed:
                after["default_agent"] = _DEFAULT_FALLBACK_AGENT
                actions.append({
                    "kind": "default_agent",
                    "family": default_family,
                    "from": default_agent,
                    "to": _DEFAULT_FALLBACK_AGENT,
                    "fallback": "configured" if general_configured else "documented_builtin",
                })
            else:
                ambiguous_default = True
                protected_default_families.add(default_family)
        else:
            ambiguous_default = True
            protected_default_families.update(default_families)

    for family in _CONFIG_FAMILIES:
        raw = after.get(family)
        if not isinstance(raw, dict):
            continue
        removed: list[str] = []
        proof_evidence: list[dict[str, object]] = []
        for name, proof in proven_by_family.get(family, {}).items():
            if family in protected_default_families and name == default_agent:
                continue
            if name in raw:
                raw.pop(name, None)
                removed.append(name)
                proof_evidence.extend(proof)
        if removed:
            actions.append({"kind": "config_entries", "family": family, "removed": tuple(removed), "evidence": tuple(proof_evidence)})
    return after, actions, ambiguous_default, ambiguous_entries


def _marker_prefix(catalog: Mapping[str, Any]) -> str:
    value = catalog.get("marker_prefix")
    return value if isinstance(value, str) and value else "gentle-ai:"


def _config_entry_managed_proof(family: str, name: str, value: object, marker_prefix: str) -> tuple[dict[str, object], ...]:
    for text in _string_values(value):
        for marker in recognized_managed_marker_evidence(text, marker_prefix):
            if marker.get("identifier") == name:
                return (
                    {"kind": "config_entry", "family": family, "name": name, "catalog_identity": True},
                    {"kind": "marker", "value": marker["value"], "identifier": name},
                )
    return ()


def _string_values(value: object) -> tuple[str, ...]:
    values: list[str] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            values.append(current)
        elif isinstance(current, Mapping):
            stack.extend(current.values())
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            stack.extend(current)
    return tuple(values)


def _remove_plugin_values(data: Mapping[str, Any], remove_values: Sequence[str]) -> dict[str, Any]:
    after = copy.deepcopy(dict(data))
    raw = after.get("plugin")
    if not isinstance(raw, list):
        return after
    remove = set(remove_values)
    after["plugin"] = [value for value in raw if not (isinstance(value, str) and value in remove)]
    return after


def _plugin_values(data: Mapping[str, Any], source: Path) -> tuple[str, ...]:
    raw = data.get("plugin", ())
    if raw in (None, ()):
        return ()
    if not isinstance(raw, list) or not all(isinstance(value, str) for value in raw):
        raise ValueError(f"opencode_json_invalid:{source.name}:plugin")
    return tuple(raw)


def _is_exact_sdd_plugin_registration(value: str) -> bool:
    return value == _SDD_PLUGIN_PACKAGE


def _is_missing_gentle_logo_registration(value: str, config_dir: Path) -> bool:
    if value == _BROKEN_LOGO_FILE:
        return not (config_dir / value).exists()
    if _is_absolute_path(value):
        path = Path(value)
        return path.name == _BROKEN_LOGO_FILE and not path.exists()
    return False


def _plugin_display_name(value: str) -> str:
    if _is_absolute_path(value):
        return Path(value).name
    return value


def _exact_targets(config_dir: Path, root: str, name: str) -> tuple[Path, ...]:
    base = config_dir / root
    targets: list[Path] = []
    for suffix in _EXACT_FILE_SUFFIXES:
        targets.append(base / f"{name}{suffix}")
    targets.append(base / name / "SKILL.md")
    return tuple(targets)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"opencode_json_malformed:{path.name}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"opencode_json_invalid:{path.name}:object")
    return data


def _write_json_operation(candidate: Candidate, data: Mapping[str, Any], *, operation: str) -> Operation:
    postimage = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    json.loads(postimage.decode("utf-8"))
    return Operation(
        kind=OperationKind.WRITE_FILE,
        path=candidate.path,
        postimage_base64=base64.b64encode(postimage).decode("ascii"),
        postimage_sha256=_sha256(postimage),
        details={"content_type": "application/json", "operation": operation},
    )


def _candidate(
    *,
    rule_id: str,
    target: Path,
    artifact_class: ArtifactClass,
    ownership: Ownership,
    proposed_action: str,
    evidence: Sequence[object],
    reason: str,
    details: Mapping[str, object],
) -> Candidate:
    candidate_key = f"{CLIENT}\0{rule_id}\0{target.resolve(strict=False)}"
    return Candidate(
        candidate_id="sha256:" + hashlib.sha256(candidate_key.encode("utf-8")).hexdigest(),
        client=CLIENT,
        path=str(target),
        artifact_class=artifact_class,
        evidence=tuple(evidence),
        ownership=ownership,
        proposed_action=proposed_action,
        preimage=Preimage(str(target)),
        dependencies=(),
        reason=reason,
        details=dict(details),
    )


def _preserved_candidate(
    *,
    rule_id: str,
    target: Path,
    artifact_class: ArtifactClass,
    reason: str,
    evidence: Sequence[object],
    details: Mapping[str, object],
    preimage: bool = True,
) -> Candidate:
    candidate_key = f"{CLIENT}\0preserved:{rule_id}\0{target.resolve(strict=False)}"
    return Candidate(
        candidate_id="sha256:" + hashlib.sha256(candidate_key.encode("utf-8")).hexdigest(),
        client=CLIENT,
        path=str(target),
        artifact_class=artifact_class,
        evidence=tuple(evidence),
        ownership=Ownership.PRESERVED,
        proposed_action="report_only",
        preimage=Preimage(str(target)) if preimage else None,
        dependencies=(),
        reason=reason,
        details=dict(details),
    )


def _dedupe_candidates(candidates: Sequence[Candidate]) -> tuple[Candidate, ...]:
    seen: set[str] = set()
    unique: list[Candidate] = []
    for candidate in candidates:
        if candidate.candidate_id in seen:
            continue
        seen.add(candidate.candidate_id)
        unique.append(candidate)
    return tuple(unique)


def _config_dir(context: RuntimeContext) -> Path:
    profile = context.profile
    os_name = profile.os_name.lower()
    if os_name == "linux":
        base = Path(profile.env.get("XDG_CONFIG_HOME", profile.home / ".config"))
        return base / "opencode"
    if os_name == "macos":
        if "XDG_CONFIG_HOME" in profile.env:
            return Path(profile.env["XDG_CONFIG_HOME"]) / "opencode"
        return profile.home / "Library" / "Application Support" / "opencode"
    if os_name == "windows":
        return Path(profile.env.get("APPDATA", profile.home / "AppData" / "Roaming")) / "opencode"
    raise ValueError(f"unsupported platform: {profile.os_name}")


def _allowed_home_child(path: Path, context: RuntimeContext) -> bool:
    home = context.profile.home.resolve(strict=False)
    resolved = path.resolve(strict=False)
    return resolved == home or resolved.is_relative_to(home)


def _home_relative(target: Path, context: RuntimeContext) -> str:
    home = context.profile.home.resolve(strict=False)
    resolved = target.resolve(strict=False)
    if resolved == home:
        return "."
    if resolved.is_relative_to(home):
        return PurePosixPath(*resolved.relative_to(home).parts).as_posix()
    return str(target)


def _is_absolute_path(value: str) -> bool:
    try:
        return Path(value).expanduser().is_absolute()
    except (OSError, ValueError):
        return False


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()
