from __future__ import annotations

import base64
import copy
import fnmatch
import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence, TypeAlias

from helper.canonical import digest_json
from helper.models import ArtifactClass, Candidate, Check, LifecycleAction, Operation, OperationKind, Ownership, Preimage, Receipt, RuntimeContext
from helper.paths import root_relative_path

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]

CLIENT = "codex"
VERSION = "1"
LAYOUT_VERSION = "codex-chatgpt-bounded-v1"
PROFILE_ID = "gentle-dev"
PROFILE_FAMILY = "permissions.gentle-dev"
_RECOGNIZED_PROFILE_DESCRIPTION = "Gentle development permissions managed by gentle-ai"
_RECOGNIZED_PROFILE_MANAGED_BY = "gentle-ai"
_CODEX_DIR = ".codex"
_CONFIG_NAMES = ("config.toml", "config.toml.bak")
_RUNTIME_NAMES = ("global-state.json", "global-state.json.bak")
_CONFIG_RECOVERY_PATTERNS = (".config.toml.*.tmp",)
_RUNTIME_RECOVERY_PATTERNS = (".global-state.json.*.tmp",)
_RECOVERY_PATTERNS = _CONFIG_RECOVERY_PATTERNS + _RUNTIME_RECOVERY_PATTERNS
_HISTORICAL_DIRS = ("archived_sessions", "sessions")
_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ROOT_SELECTOR_RE = re.compile(r'^default_permissions\s*=\s*"([^"]*)"\s*(?:#.*)?$')
_EXACT_GENTLE_SELECTOR_RE = re.compile(r'^default_permissions\s*=\s*"gentle-dev"\s*(?:#.*)?$')


class CodexAdapter:
    client = CLIENT
    version = VERSION
    layout_version = LAYOUT_VERSION

    def __init__(self, *, runner: object | None = None, command_timeout: float = 5.0) -> None:
        self.runner = runner
        self.command_timeout = command_timeout

    def inventory(self, context: RuntimeContext) -> tuple[Candidate, ...]:
        codex_dir = context.profile.home / _CODEX_DIR
        if not _allowed_home_child(codex_dir, context):
            return ()
        if not codex_dir.exists():
            return ()
        if not codex_dir.is_dir():
            raise ValueError("codex_layout_not_directory")

        member_preconditions = _directory_member_preconditions(codex_dir, context)
        mutable: list[Candidate] = []
        historical: list[Candidate] = []

        for path in _config_paths(codex_dir):
            if path.is_file():
                candidate = self._config_candidate(path, context, member_preconditions)
                if candidate is not None:
                    mutable.append(candidate)

        for path in _runtime_paths(codex_dir):
            if path.is_file():
                candidate = self._runtime_candidate(path, context, member_preconditions)
                if candidate is not None:
                    mutable.append(candidate)

        lifecycle_attached = False
        with_lifecycle: list[Candidate] = []
        for candidate in sorted(mutable, key=lambda item: (_kind_priority(str(item.details.get("kind", ""))), item.path)):
            if not lifecycle_attached and candidate.details.get("kind") == "runtime_json":
                details = dict(candidate.details)
                details["lifecycle_actions"] = (_lifecycle_action(candidate),)
                candidate = _replace_candidate_details(candidate, details)
                lifecycle_attached = True
            with_lifecycle.append(candidate)

        for directory in _HISTORICAL_DIRS:
            root = codex_dir / directory
            if root.is_dir():
                for path in sorted(root.rglob("*.jsonl")):
                    if path.is_file() and _allowed_home_child(path, context):
                        historical.append(self._historical_candidate(path, directory))

        return tuple(sorted([*with_lifecycle, *historical], key=lambda candidate: (candidate.path, candidate.candidate_id)))

    def compile(self, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]:
        if candidate.ownership != Ownership.PROVEN or candidate.proposed_action == "report_only":
            return ()
        kind = candidate.details.get("kind")
        path = Path(candidate.path)
        if kind == "config_toml":
            text = path.read_text()
            post_text = remove_toml_table_family(text, PROFILE_FAMILY)
            if post_text == text:
                return ()
            return (_write_operation(candidate, post_text.encode("utf-8"), content_type="text/toml"),)
        if kind == "runtime_json":
            before = _load_json_file(path)
            after, count = sanitize_runtime_profile(before, PROFILE_ID)
            if count == 0:
                return ()
            postimage = (json.dumps(after, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            return (_write_operation(candidate, postimage, content_type="application/json"),)
        return ()

    def verify(self, receipt: Receipt, context: RuntimeContext) -> tuple[Check, ...]:
        codex_dir = context.profile.home / _CODEX_DIR
        if codex_dir.is_dir() and _allowed_home_child(codex_dir, context):
            for path in _config_paths(codex_dir):
                if path.is_file():
                    parsed = _load_toml_file(path)
                    if parsed.get("default_permissions") == PROFILE_ID:
                        raise ValueError("verify_codex_default_permissions_present")
                    if PROFILE_ID in parsed.get("permissions", {}):
                        raise ValueError("verify_codex_permission_profile_present")
            for path in _runtime_paths(codex_dir):
                if path.is_file():
                    value = _load_json_file(path)
                    if _has_active_profile(value, PROFILE_ID):
                        raise ValueError("verify_codex_runtime_profile_present")
        self._smoke_codex_version()
        return tuple(receipt.checks)

    def _config_candidate(self, path: Path, context: RuntimeContext, member_preconditions: tuple[Mapping[str, object], ...]) -> Candidate | None:
        text = path.read_text()
        post_text = remove_toml_table_family(text, PROFILE_FAMILY)
        if post_text == text:
            return None
        return _candidate(
            rule_id=f"config:{path.name}",
            target=path,
            artifact_class=ArtifactClass.ACTIVE_SOURCE if path.name == "config.toml" else ArtifactClass.RUNTIME_STATE,
            ownership=Ownership.PROVEN,
            proposed_action="write_file",
            evidence=({"kind": "codex_toml_profile_family", "family": PROFILE_FAMILY},),
            reason="recognized Gentle Codex permission profile selector or table family",
            details={"kind": "config_toml", "profile_id": PROFILE_ID, "directory_member_preconditions": member_preconditions},
        )

    def _runtime_candidate(self, path: Path, context: RuntimeContext, member_preconditions: tuple[Mapping[str, object], ...]) -> Candidate | None:
        before = _load_json_file(path)
        _after, count = sanitize_runtime_profile(before, PROFILE_ID)
        if count == 0:
            return None
        return _candidate(
            rule_id=f"runtime:{path.name}",
            target=path,
            artifact_class=ArtifactClass.RUNTIME_STATE,
            ownership=Ownership.PROVEN,
            proposed_action="write_file",
            evidence=({"kind": "codex_runtime_active_permission_profile", "profile_id": PROFILE_ID, "count": count},),
            reason="runtime activePermissionProfile references the recognized Gentle Codex profile",
            details={"kind": "runtime_json", "profile_id": PROFILE_ID, "directory_member_preconditions": member_preconditions},
        )

    def _historical_candidate(self, path: Path, directory: str) -> Candidate:
        digest = _sha256(path.read_bytes())
        return _candidate(
            rule_id=f"historical:{directory}:{path.name}:{digest}",
            target=path,
            artifact_class=ArtifactClass.HISTORICAL,
            ownership=Ownership.PRESERVED,
            proposed_action="report_only",
            evidence=({"kind": "historical_jsonl", "sha256": digest, "directory": directory},),
            reason="Codex session JSONL is historical and must remain hash-preserved",
            details={"kind": "historical_jsonl", "sha256": digest, "directory": directory},
        )

    def _smoke_codex_version(self) -> None:
        if self.runner is None:
            return
        argv = ("codex", "--version")
        try:
            completed = self.runner.run(argv, self.command_timeout)  # type: ignore[attr-defined]
        except FileNotFoundError as exc:
            raise ValueError("codex_smoke_missing_executable") from exc
        if not isinstance(completed, object):
            raise ValueError("codex_smoke_failed")
        returncode = int(getattr(completed, "returncode", 1))
        if returncode != 0:
            raise ValueError("codex_smoke_failed")


def remove_toml_table_family(text: str, family: str) -> str:
    before = _loads_toml(text, "codex_toml_malformed")
    family_parts = tuple(family.split("."))
    if not family_parts or not all(_BARE_KEY_RE.fullmatch(part) for part in family_parts):
        raise ValueError("codex_toml_unsafe_family")

    for line in text.splitlines(keepends=True):
        _parse_table_header(line)
    _validate_profile_ownership(before, family_parts)
    selector_value = before.get("default_permissions")
    selector_line_count = 0
    root_selector_line_index: int | None = None
    lines = text.splitlines(keepends=True)
    current_path: tuple[str, ...] = ()
    table_remove_flags: list[bool] = []

    for index, line in enumerate(lines):
        header = _parse_table_header(line)
        if header is not None:
            current_path = header
        elif current_path == ():
            match = _ROOT_SELECTOR_RE.match(_strip_line_ending(line).strip())
            if match:
                selector_line_count += 1
                if match.group(1) == PROFILE_ID and _EXACT_GENTLE_SELECTOR_RE.match(_strip_line_ending(line).strip()):
                    root_selector_line_index = index
        table_remove_flags.append(_is_family_path(current_path, family_parts))

    if selector_line_count > 1:
        raise ValueError("codex_toml_duplicate_selector")
    if selector_value == PROFILE_ID and root_selector_line_index is None:
        raise ValueError("codex_toml_unsafe_selector")

    output: list[str] = []
    current_path = ()
    removing_table = False
    for index, line in enumerate(lines):
        header = _parse_table_header(line)
        if header is not None:
            current_path = header
            removing_table = _is_family_path(current_path, family_parts)
        if index == root_selector_line_index:
            continue
        if removing_table:
            continue
        output.append(line)

    cleaned = "".join(output)
    after = _loads_toml(cleaned, "codex_toml_postimage_malformed")
    if _get_nested(after, family_parts) is not None:
        raise ValueError("codex_toml_family_still_present")
    if after.get("default_permissions") == PROFILE_ID:
        raise ValueError("codex_toml_selector_still_present")
    return cleaned


def sanitize_runtime_profile(value: JsonValue, profile_id: str) -> tuple[JsonValue, int]:
    sanitized, count = _sanitize_runtime_profile(copy.deepcopy(value), profile_id)
    return sanitized, count


def _sanitize_runtime_profile(value: JsonValue, profile_id: str) -> tuple[JsonValue, int]:
    if isinstance(value, dict):
        count = 0
        result: dict[str, JsonValue] = {}
        for key, child in value.items():
            if key == "activePermissionProfile" and _is_expected_runtime_profile(child, profile_id):
                result[key] = None
                count += 1
                continue
            sanitized_child, child_count = _sanitize_runtime_profile(child, profile_id)
            result[key] = sanitized_child
            count += child_count
        return result, count
    if isinstance(value, list):
        items: list[JsonValue] = []
        count = 0
        for child in value:
            sanitized_child, child_count = _sanitize_runtime_profile(child, profile_id)
            items.append(sanitized_child)
            count += child_count
        return items, count
    return value, 0


def _is_expected_runtime_profile(value: JsonValue, profile_id: str) -> bool:
    return isinstance(value, dict) and set(value.keys()) == {"id", "extends"} and value.get("id") == profile_id and value.get("extends") is None


def _has_active_profile(value: JsonValue, profile_id: str) -> bool:
    if isinstance(value, dict):
        profile = value.get("activePermissionProfile")
        if _is_expected_runtime_profile(profile, profile_id):
            return True
        return any(_has_active_profile(child, profile_id) for child in value.values())
    if isinstance(value, list):
        return any(_has_active_profile(child, profile_id) for child in value)
    return False


def _parse_table_header(line: str) -> tuple[str, ...] | None:
    stripped = _strip_line_ending(line).strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("[["):
        if "permissions" in stripped or PROFILE_ID in stripped:
            raise ValueError("codex_toml_unsupported_array_table")
        return None
    if not stripped.startswith("["):
        return None
    close = stripped.find("]")
    if close == -1:
        raise ValueError("codex_toml_malformed_header")
    body = stripped[1:close].strip()
    suffix = stripped[close + 1 :].strip()
    if suffix and not suffix.startswith("#"):
        raise ValueError("codex_toml_malformed_header")
    if '"' in body or "'" in body:
        raise ValueError("codex_toml_unsafe_quoted_header")
    parts = tuple(part.strip() for part in body.split("."))
    if not parts or not all(_BARE_KEY_RE.fullmatch(part) for part in parts):
        raise ValueError("codex_toml_unsafe_header")
    return parts


def _validate_profile_ownership(parsed: Mapping[str, Any], family_parts: tuple[str, ...]) -> None:
    profile = _get_nested(parsed, family_parts)
    if profile is None:
        return
    if not isinstance(profile, Mapping):
        raise ValueError("codex_profile_ownership_unproven")
    if profile.get("description") != _RECOGNIZED_PROFILE_DESCRIPTION or profile.get("managed_by") != _RECOGNIZED_PROFILE_MANAGED_BY:
        raise ValueError("codex_profile_ownership_unproven")


def _loads_toml(text: str, code: str) -> Mapping[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(code) from exc


def _load_toml_file(path: Path) -> Mapping[str, Any]:
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ValueError("codex_toml_malformed") from exc


def _load_json_file(path: Path) -> JsonValue:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError("codex_json_malformed") from exc


def _get_nested(value: Mapping[str, Any], parts: tuple[str, ...]) -> Any:
    current: Any = value
    for part in parts:
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _is_family_path(path: tuple[str, ...], family_parts: tuple[str, ...]) -> bool:
    return len(path) >= len(family_parts) and path[: len(family_parts)] == family_parts


def _strip_line_ending(line: str) -> str:
    return line[:-2] if line.endswith("\r\n") else line[:-1] if line.endswith("\n") else line


def _config_paths(codex_dir: Path) -> tuple[Path, ...]:
    paths = [codex_dir / name for name in _CONFIG_NAMES]
    paths.extend(_recovery_paths(codex_dir, _CONFIG_RECOVERY_PATTERNS))
    return tuple(dict.fromkeys(paths))


def _runtime_paths(codex_dir: Path) -> tuple[Path, ...]:
    paths = [codex_dir / name for name in _RUNTIME_NAMES]
    paths.extend(_recovery_paths(codex_dir, _RUNTIME_RECOVERY_PATTERNS))
    return tuple(dict.fromkeys(paths))


def _recovery_paths(codex_dir: Path, patterns: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    if codex_dir.is_dir():
        for child in sorted(codex_dir.iterdir(), key=lambda item: item.name):
            if child.is_file() and any(fnmatch.fnmatchcase(child.name, pattern) for pattern in patterns):
                paths.append(child)
    return paths


def _directory_member_preconditions(codex_dir: Path, context: RuntimeContext) -> tuple[Mapping[str, object], ...]:
    root_id, relative_dir = root_relative_path(codex_dir, context)
    members = _governed_member_set(codex_dir)
    return (
        {
            "kind": "directory_member_set",
            "root_id": root_id,
            "relative_dir": relative_dir,
            "file_names": list(_CONFIG_NAMES + _RUNTIME_NAMES),
            "patterns": list(_RECOVERY_PATTERNS),
            "members": members,
            "digest": digest_json({"members": members}),
        },
    )


def _governed_member_set(codex_dir: Path) -> list[dict[str, object]]:
    members: list[dict[str, object]] = []
    if not codex_dir.is_dir():
        return members
    governed_names = set(_CONFIG_NAMES + _RUNTIME_NAMES)
    for child in sorted(codex_dir.iterdir(), key=lambda item: item.name):
        if not child.is_file():
            continue
        if child.name not in governed_names and not any(fnmatch.fnmatchcase(child.name, pattern) for pattern in _RECOVERY_PATTERNS):
            continue
        members.append({"name": child.name, "sha256": _sha256(child.read_bytes()), "type": "file"})
    return members


def _write_operation(candidate: Candidate, postimage: bytes, *, content_type: str) -> Operation:
    return Operation(
        kind=OperationKind.WRITE_FILE,
        path=candidate.path,
        postimage_base64=base64.b64encode(postimage).decode("ascii"),
        postimage_sha256=_sha256(postimage),
        details={
            "content_type": content_type,
            "operation": "sanitize_codex_gentle_profile",
            "directory_member_preconditions": tuple(candidate.details.get("directory_member_preconditions", ())),
        },
    )


def _lifecycle_action(candidate: Candidate) -> dict[str, object]:
    return LifecycleAction(
        candidate_id=candidate.candidate_id,
        client=CLIENT,
        action="stop",
        target="Codex",
        reason="quiesce Codex/ChatGPT before runtime permission-state edit",
        details={"process_name": "Codex", "bundle_id": "com.openai.codex", "restart_argv": ["codex"]},
    ).to_dict()


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


def _replace_candidate_details(candidate: Candidate, details: Mapping[str, object]) -> Candidate:
    return Candidate(
        candidate_id=candidate.candidate_id,
        client=candidate.client,
        path=candidate.path,
        artifact_class=candidate.artifact_class,
        evidence=candidate.evidence,
        ownership=candidate.ownership,
        proposed_action=candidate.proposed_action,
        preimage=candidate.preimage,
        dependencies=candidate.dependencies,
        reason=candidate.reason,
        details=dict(details),
    )


def _kind_priority(kind: str) -> int:
    if kind == "runtime_json":
        return 0
    if kind == "config_toml":
        return 1
    return 2


def _allowed_home_child(path: Path, context: RuntimeContext) -> bool:
    home = context.profile.home.resolve(strict=False)
    resolved = path.resolve(strict=False)
    return resolved == home or resolved.is_relative_to(home)


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()
