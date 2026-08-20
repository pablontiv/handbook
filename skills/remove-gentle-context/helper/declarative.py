from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from helper.canonical import canonical_bytes
from helper.models import (
    ArtifactClass,
    Candidate,
    Check,
    Operation,
    OperationKind,
    Ownership,
    Preimage,
    Receipt,
    RuntimeContext,
)
from helper.ownership import classify_exact_file_ownership, is_sha256_digest, load_ownership_catalog

SCHEMA = "remove-gentle-context.adapter/v1"
ALLOWED_TOP_LEVEL_KEYS = {"schema", "client", "roots", "rules"}
ALLOWED_ROOT_KEYS = {"kind", "path"}
ALLOWED_RULE_KINDS = {
    "exact_file",
    "empty_directory",
    "balanced_marker_block",
    "json_key",
    "json_array_value",
}
FORBIDDEN_RULE_KINDS = {"toml_edit", "sqlite_update", "runtime_state", "regex_replace"}
FORBIDDEN_KEYS = {
    "regex",
    "glob",
    "recursive",
    "shell",
    "command",
    "commands",
    "toml",
    "sqlite",
    "runtime",
    "lifecycle",
    "capability",
    "capabilities",
}
COMMON_RULE_KEYS = {
    "id",
    "kind",
    "root",
    "path",
    "artifact_class",
    "proposed_action",
    "reason",
    "catalog_name",
    "content_signatures",
}
RULE_KEYS_BY_KIND = {
    "exact_file": COMMON_RULE_KEYS,
    "empty_directory": COMMON_RULE_KEYS,
    "balanced_marker_block": COMMON_RULE_KEYS | {"open_marker", "close_marker"},
    "json_key": COMMON_RULE_KEYS | {"pointer", "key"},
    "json_array_value": COMMON_RULE_KEYS | {"pointer", "value"},
}
ACTION_BY_KIND = {
    "exact_file": "delete_file",
    "empty_directory": "remove_empty_directory",
    "balanced_marker_block": "remove_balanced_marker_block",
    "json_key": "remove_json_key",
    "json_array_value": "remove_json_array_value",
}
WRITE_RULE_KINDS = {"balanced_marker_block", "json_key", "json_array_value"}
JSON_RULE_KINDS = {"json_key", "json_array_value"}


@dataclass(frozen=True)
class DeclarativeRoot:
    id: str
    kind: str
    path: str


@dataclass(frozen=True)
class DeclarativeRule:
    id: str
    kind: str
    root: str
    path: str
    data: Mapping[str, Any]


@dataclass(frozen=True)
class DeclarativeAdapter:
    client: str
    roots: Mapping[str, DeclarativeRoot]
    rules: tuple[DeclarativeRule, ...]
    catalog: Mapping[str, Any]

    def inventory(self, context: RuntimeContext) -> tuple[Candidate, ...]:
        candidates: list[Candidate] = []
        for rule in self.rules:
            root = self.roots[rule.root]
            target = _rule_target(rule, root, context)
            if rule.kind == "exact_file":
                if target.is_file():
                    candidates.append(self._candidate_for_file(rule, target, context))
            elif rule.kind == "empty_directory":
                if target.is_dir() and not any(target.iterdir()):
                    candidates.append(self._candidate(rule, target, Ownership.PROVEN, "remove_empty_directory", [{"kind": "empty_directory", "rule_id": rule.id}], "exact empty directory"))
            elif rule.kind == "balanced_marker_block":
                if target.is_file() and _contains_marker_block(target, rule):
                    candidates.append(self._candidate(rule, target, Ownership.PROVEN, rule.data.get("proposed_action", ACTION_BY_KIND[rule.kind]), [{"kind": "balanced_marker_block", "rule_id": rule.id}], "recognized balanced marker block"))
            elif rule.kind == "json_key":
                if target.is_file() and _json_key_present(target, rule):
                    candidates.append(self._candidate(rule, target, Ownership.PROVEN, rule.data.get("proposed_action", ACTION_BY_KIND[rule.kind]), [{"kind": "json_key", "rule_id": rule.id, "pointer": rule.data["pointer"], "key": rule.data["key"]}], "recognized exact JSON key"))
            elif rule.kind == "json_array_value":
                if target.is_file() and _json_array_value_present(target, rule):
                    candidates.append(self._candidate(rule, target, Ownership.PROVEN, rule.data.get("proposed_action", ACTION_BY_KIND[rule.kind]), [{"kind": "json_array_value", "rule_id": rule.id, "pointer": rule.data["pointer"], "value": rule.data["value"]}], "recognized exact JSON array value"))
        return tuple(candidates)

    def compile(self, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]:
        if candidate.proposed_action == "report_only":
            return ()
        rule = self._rule_for_candidate(candidate)
        if rule.kind == "exact_file":
            return self._compile_exact_file(rule, candidate, context)
        if rule.kind == "empty_directory":
            return self._compile_empty_directory(rule, candidate, context)
        if rule.kind in WRITE_RULE_KINDS:
            return self._compile_grouped_write(rule, candidate, context)
        raise ValueError("declarative_unknown_rule_kind")

    def _compile_exact_file(self, rule: DeclarativeRule, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]:
        target = self._assert_candidate_target(rule, candidate, context)
        if not target.is_file():
            raise ValueError("declarative_evidence_drift")
        decision = classify_exact_file_ownership(
            target=target,
            rule_data=rule.data,
            default_action=ACTION_BY_KIND[rule.kind],
            context=context,
            catalog=self.catalog,
        )
        if decision.ownership != Ownership.PROVEN or decision.proposed_action != ACTION_BY_KIND[rule.kind]:
            raise ValueError("declarative_evidence_drift")
        return (Operation(kind=OperationKind.DELETE_FILE, path=str(target), details={"operation": ACTION_BY_KIND[rule.kind], "rule_id": rule.id}),)

    def _compile_empty_directory(self, rule: DeclarativeRule, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]:
        target = self._assert_candidate_target(rule, candidate, context)
        if not target.is_dir() or any(target.iterdir()):
            raise ValueError("declarative_evidence_drift")
        return (Operation(kind=OperationKind.REMOVE_EMPTY_DIRECTORY, path=str(target), details={"operation": ACTION_BY_KIND[rule.kind], "rule_id": rule.id}),)

    def _compile_grouped_write(self, rule: DeclarativeRule, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]:
        target = self._assert_candidate_target(rule, candidate, context)
        if not target.is_file():
            raise ValueError("declarative_evidence_drift")
        grouped_rules = self._matched_mutable_rules_for_target(target, context)
        grouped_rule_ids = tuple(sorted(item.id for item in grouped_rules))
        if rule.id not in grouped_rule_ids:
            raise ValueError("declarative_evidence_drift")
        if rule.id != grouped_rule_ids[0]:
            return ()
        postimage, content_type = _grouped_postimage(target, grouped_rules)
        return (_write_operation(candidate, target, postimage, content_type=content_type, rule_ids=grouped_rule_ids),)

    def _matched_mutable_rules_for_target(self, target: Path, context: RuntimeContext) -> tuple[DeclarativeRule, ...]:
        matched: list[DeclarativeRule] = []
        for rule in self.rules:
            if rule.kind not in WRITE_RULE_KINDS:
                continue
            if _rule_action(rule) == "report_only":
                continue
            if _rule_action(rule) != ACTION_BY_KIND[rule.kind]:
                raise ValueError("declarative_action_kind_mismatch")
            if _rule_target(rule, self.roots[rule.root], context) != target:
                continue
            if _rule_currently_matches(target, rule):
                matched.append(rule)
        return tuple(sorted(matched, key=lambda item: item.id))

    def _rule_for_candidate(self, candidate: Candidate) -> DeclarativeRule:
        rule_id = candidate.details.get("declarative_rule_id")
        if not isinstance(rule_id, str):
            for item in candidate.evidence:
                if isinstance(item, Mapping) and isinstance(item.get("rule_id"), str):
                    rule_id = item["rule_id"]
                    break
        if not isinstance(rule_id, str):
            raise ValueError("declarative_candidate_rule_missing")
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        raise ValueError("declarative_candidate_rule_unknown")

    def _assert_candidate_target(self, rule: DeclarativeRule, candidate: Candidate, context: RuntimeContext) -> Path:
        target = _rule_target(rule, self.roots[rule.root], context)
        if Path(candidate.path).expanduser().resolve(strict=False) != target.resolve(strict=False):
            raise ValueError("declarative_candidate_target_mismatch")
        if _rule_action(rule) == "report_only":
            raise ValueError("declarative_action_kind_mismatch")
        if _rule_action(rule) != ACTION_BY_KIND[rule.kind]:
            raise ValueError("declarative_action_kind_mismatch")
        return target

    def verify(self, receipt: Receipt, context: RuntimeContext) -> tuple[Check, ...]:
        return tuple(receipt.checks)

    def _candidate_for_file(self, rule: DeclarativeRule, target: Path, context: RuntimeContext) -> Candidate:
        decision = classify_exact_file_ownership(
            target=target,
            rule_data=rule.data,
            default_action=ACTION_BY_KIND[rule.kind],
            context=context,
            catalog=self.catalog,
        )
        evidence: list[dict[str, Any]] = [{"kind": "exact_file", "rule_id": rule.id}]
        evidence.extend(decision.evidence)
        return self._candidate(
            rule,
            target,
            decision.ownership,
            decision.proposed_action,
            evidence,
            decision.reason,
            decision.details,
        )

    def _candidate(
        self,
        rule: DeclarativeRule,
        target: Path,
        ownership: Ownership,
        proposed_action: str,
        evidence: list[dict[str, Any]],
        reason: str,
        details: Mapping[str, Any] | None = None,
    ) -> Candidate:
        artifact_class = ArtifactClass(str(rule.data.get("artifact_class", ArtifactClass.ACTIVE_SOURCE)))
        candidate_key = f"{self.client}\0{rule.id}\0{target}"
        candidate_details = {} if details is None else dict(details)
        candidate_details.setdefault("declarative_rule_id", rule.id)
        candidate_details.setdefault("declarative_rule_kind", rule.kind)
        return Candidate(
            candidate_id="sha256:" + hashlib.sha256(candidate_key.encode("utf-8")).hexdigest(),
            client=self.client,
            path=str(target),
            artifact_class=artifact_class,
            evidence=tuple(evidence),
            ownership=ownership,
            proposed_action=proposed_action,
            preimage=Preimage(str(target)),
            dependencies=(),
            reason=reason,
            details=candidate_details,
        )


def _rule_target(rule: DeclarativeRule, root: DeclarativeRoot, context: RuntimeContext) -> Path:
    return _resolve_root(root, context) / Path(rule.path)


def _rule_action(rule: DeclarativeRule) -> str:
    return str(rule.data.get("proposed_action", ACTION_BY_KIND[rule.kind]))


def _rule_currently_matches(target: Path, rule: DeclarativeRule) -> bool:
    if not target.is_file():
        return False
    if rule.kind == "balanced_marker_block":
        try:
            return _marker_block_span(target.read_bytes(), rule) is not None
        except OSError:
            return False
    if rule.kind == "json_key":
        return _json_key_present(target, rule)
    if rule.kind == "json_array_value":
        return _json_array_value_present(target, rule)
    return False


def _grouped_postimage(target: Path, rules: tuple[DeclarativeRule, ...]) -> tuple[bytes, str]:
    kinds = {rule.kind for rule in rules}
    if kinds == {"balanced_marker_block"}:
        return _grouped_marker_postimage(target, rules), "text/markdown"
    if kinds <= JSON_RULE_KINDS:
        return _grouped_json_postimage(target, rules), "application/json"
    raise ValueError("declarative_mixed_target_rules")


def _grouped_marker_postimage(target: Path, rules: tuple[DeclarativeRule, ...]) -> bytes:
    try:
        content = target.read_bytes()
    except OSError as exc:
        raise ValueError("declarative_evidence_drift") from exc
    spans: list[tuple[int, int, str]] = []
    for rule in rules:
        span = _marker_block_span(content, rule)
        if span is None:
            raise ValueError("declarative_evidence_drift")
        spans.append((span[0], span[1], rule.id))
    ordered = sorted(spans, key=lambda item: (item[0], item[1], item[2]))
    previous_end = -1
    for start, end, _rule_id in ordered:
        if start < previous_end:
            raise ValueError("declarative_overlapping_marker_blocks")
        previous_end = end
    postimage = content
    for start, end, _rule_id in reversed(ordered):
        postimage = postimage[:start] + postimage[end:]
    return postimage


def _marker_block_span(content: bytes, rule: DeclarativeRule) -> tuple[int, int] | None:
    open_marker = str(rule.data["open_marker"]).encode("utf-8")
    close_marker = str(rule.data["close_marker"]).encode("utf-8")
    open_positions = _find_all(content, open_marker)
    close_positions = _find_all(content, close_marker)
    if len(open_positions) != 1 or len(close_positions) != 1:
        return None
    start = open_positions[0]
    close_start = close_positions[0]
    if close_start <= start:
        return None
    end = close_start + len(close_marker)
    if content[end:end + 2] == b"\r\n":
        end += 2
    elif content[end:end + 1] == b"\n":
        end += 1
    return start, end


def _find_all(content: bytes, needle: bytes) -> list[int]:
    positions: list[int] = []
    offset = 0
    while True:
        index = content.find(needle, offset)
        if index == -1:
            return positions
        positions.append(index)
        offset = index + len(needle)


def _grouped_json_postimage(target: Path, rules: tuple[DeclarativeRule, ...]) -> bytes:
    try:
        data = json.loads(target.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("declarative_evidence_drift") from exc
    for rule in rules:
        if rule.kind == "json_key":
            _remove_json_key(data, rule)
        elif rule.kind == "json_array_value":
            _remove_json_array_value(data, rule)
        else:
            raise ValueError("declarative_mixed_target_rules")
    return canonical_bytes(data)


def _remove_json_key(data: Any, rule: DeclarativeRule) -> None:
    try:
        parent = _json_pointer_get(data, str(rule.data["pointer"]))
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise ValueError("declarative_evidence_drift") from exc
    key = rule.data["key"]
    if not isinstance(parent, dict) or key not in parent:
        raise ValueError("declarative_evidence_drift")
    del parent[key]


def _remove_json_array_value(data: Any, rule: DeclarativeRule) -> None:
    try:
        array = _json_pointer_get(data, str(rule.data["pointer"]))
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise ValueError("declarative_evidence_drift") from exc
    if not isinstance(array, list):
        raise ValueError("declarative_evidence_drift")
    value = rule.data["value"]
    filtered = [item for item in array if item != value]
    if len(filtered) == len(array):
        raise ValueError("declarative_evidence_drift")
    array[:] = filtered


def _write_operation(candidate: Candidate, target: Path, postimage: bytes, *, content_type: str, rule_ids: tuple[str, ...]) -> Operation:
    return Operation(
        kind=OperationKind.WRITE_FILE,
        path=str(target),
        candidate_id=candidate.candidate_id,
        postimage_base64=base64.b64encode(postimage).decode("ascii"),
        postimage_sha256=_sha256(postimage),
        details={"content_type": content_type, "operation": "declarative_grouped_write", "rule_ids": rule_ids},
    )


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def load_declarative_adapter(path: Path, catalog_path: Path | None = None) -> DeclarativeAdapter:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("adapter_invalid_schema")
    unknown_top_level = set(data) - ALLOWED_TOP_LEVEL_KEYS
    if unknown_top_level:
        raise ValueError("adapter_unknown_top_level_key")
    if data.get("schema") != SCHEMA:
        raise ValueError("adapter_unknown_schema")
    client = data.get("client")
    if not isinstance(client, str) or not client:
        raise ValueError("adapter_invalid_client")
    catalog = _load_catalog(path, catalog_path)
    roots = _load_roots(data.get("roots"))
    rules = _load_rules(data.get("rules"), roots, catalog)
    return DeclarativeAdapter(client=client, roots=roots, rules=rules, catalog=catalog)


def _load_catalog(_adapter_path: Path, catalog_path: Path | None = None) -> Mapping[str, Any]:
    return load_ownership_catalog(catalog_path)


def _load_roots(raw: Any) -> Mapping[str, DeclarativeRoot]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("adapter_invalid_roots")
    roots: dict[str, DeclarativeRoot] = {}
    for root_id, definition in raw.items():
        if not isinstance(root_id, str) or not root_id:
            raise ValueError("adapter_invalid_root")
        if not isinstance(definition, dict) or set(definition) != ALLOWED_ROOT_KEYS:
            raise ValueError("adapter_invalid_root")
        if definition.get("kind") != "home_relative":
            raise ValueError("adapter_forbidden_capability")
        root_path = definition.get("path")
        if not isinstance(root_path, str) or not _is_exact_relative_path(root_path, allow_dot=False):
            raise ValueError("adapter_invalid_path")
        roots[root_id] = DeclarativeRoot(root_id, "home_relative", root_path)
    return roots


def _load_rules(raw: Any, roots: Mapping[str, DeclarativeRoot], catalog: Mapping[str, Any]) -> tuple[DeclarativeRule, ...]:
    if not isinstance(raw, list):
        raise ValueError("adapter_invalid_rules")
    seen: set[str] = set()
    rules: list[DeclarativeRule] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("adapter_invalid_rule")
        _reject_forbidden_tokens(item)
        kind = item.get("kind")
        if kind in FORBIDDEN_RULE_KINDS or kind not in ALLOWED_RULE_KINDS:
            raise ValueError("adapter_forbidden_capability")
        unknown_rule_keys = set(item) - RULE_KEYS_BY_KIND[kind]
        if unknown_rule_keys:
            raise ValueError("adapter_unknown_rule_key")
        rule_id = item.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("adapter_invalid_rule_id")
        if rule_id in seen:
            raise ValueError("adapter_duplicate_rule_id")
        seen.add(rule_id)
        root = item.get("root")
        if not isinstance(root, str) or root not in roots:
            raise ValueError("adapter_unknown_root")
        rule_path = item.get("path")
        if not isinstance(rule_path, str) or not _is_exact_relative_path(rule_path, allow_dot=False):
            raise ValueError("adapter_invalid_path")
        if "catalog_name" in item:
            _validate_catalog_name(str(item["catalog_name"]), rule_path, catalog)
        if "artifact_class" in item:
            ArtifactClass(str(item["artifact_class"]))
        if "proposed_action" in item and item["proposed_action"] not in {"delete_file", "remove_empty_directory", "remove_balanced_marker_block", "remove_json_key", "remove_json_array_value", "report_only"}:
            raise ValueError("adapter_forbidden_capability")
        if kind == "balanced_marker_block":
            _validate_marker_rule(item)
        if kind in {"json_key", "json_array_value"}:
            _validate_json_rule(item, require_key=(kind == "json_key"))
        if "content_signatures" in item:
            _validate_content_signatures(item["content_signatures"])
        rules.append(DeclarativeRule(rule_id, kind, root, rule_path, dict(item)))
    return tuple(rules)


def _reject_forbidden_tokens(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str) and key.lower().replace("-", "_") in FORBIDDEN_KEYS:
                raise ValueError("adapter_forbidden_capability")
            _reject_forbidden_tokens(nested)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_tokens(item)


def _validate_marker_rule(item: Mapping[str, Any]) -> None:
    open_marker = item.get("open_marker")
    close_marker = item.get("close_marker")
    if not isinstance(open_marker, str) or not isinstance(close_marker, str) or not open_marker or not close_marker:
        raise ValueError("adapter_invalid_marker")
    if open_marker == close_marker:
        raise ValueError("adapter_invalid_marker")


def _validate_json_rule(item: Mapping[str, Any], *, require_key: bool) -> None:
    pointer = item.get("pointer")
    if not isinstance(pointer, str) or not _is_rfc6901_pointer(pointer):
        raise ValueError("adapter_invalid_json_pointer")
    if require_key and not isinstance(item.get("key"), str):
        raise ValueError("adapter_invalid_json_key")
    if not require_key and "value" not in item:
        raise ValueError("adapter_invalid_json_value")


def _validate_content_signatures(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError("adapter_invalid_content_signature")
    for item in value:
        if not isinstance(item, dict) or set(item) - {"algorithm", "value", "label"}:
            raise ValueError("adapter_invalid_content_signature")
        if item.get("algorithm") != "sha256":
            raise ValueError("adapter_invalid_content_signature")
        digest = item.get("value")
        if not isinstance(digest, str) or not is_sha256_digest(digest):
            raise ValueError("adapter_invalid_content_signature")
        if "label" in item and not isinstance(item["label"], str):
            raise ValueError("adapter_invalid_content_signature")


def _validate_catalog_name(name: str, rule_path: str, catalog: Mapping[str, Any]) -> None:
    names = catalog.get("agent_names", [])
    if names and name not in names:
        raise ValueError("ownership_catalog_unknown_agent")
    path = PurePosixPath(rule_path)
    if name not in path.name:
        raise ValueError("ownership_catalog_path_mismatch")


def _is_exact_relative_path(value: str, *, allow_dot: bool) -> bool:
    if not value or "\\" in value or value.startswith("~"):
        return False
    if any(char in value for char in "*?[]{}"):
        return False
    path = PurePosixPath(value)
    if path.is_absolute():
        return False
    if str(path) == ".":
        return allow_dot
    return all(part not in {"", ".", ".."} for part in path.parts)


def _is_rfc6901_pointer(value: str) -> bool:
    if value == "":
        return True
    if not value.startswith("/"):
        return False
    for token in value.split("/")[1:]:
        index = 0
        while index < len(token):
            if token[index] == "~":
                if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
                    return False
                index += 2
            else:
                index += 1
    return True


def _resolve_root(root: DeclarativeRoot, context: RuntimeContext) -> Path:
    if root.kind == "home_relative":
        return context.profile.home / Path(root.path)
    raise ValueError("adapter_forbidden_capability")


def _contains_marker_block(path: Path, rule: DeclarativeRule) -> bool:
    try:
        return _marker_block_span(path.read_bytes(), rule) is not None
    except OSError:
        return False


def _json_key_present(path: Path, rule: DeclarativeRule) -> bool:
    try:
        data = json.loads(path.read_text())
        parent = _json_pointer_get(data, str(rule.data["pointer"]))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, IndexError, ValueError):
        return False
    return isinstance(parent, dict) and rule.data["key"] in parent


def _json_array_value_present(path: Path, rule: DeclarativeRule) -> bool:
    try:
        data = json.loads(path.read_text())
        array = _json_pointer_get(data, str(rule.data["pointer"]))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, IndexError, ValueError):
        return False
    return isinstance(array, list) and rule.data["value"] in array


def _json_pointer_get(data: Any, pointer: str) -> Any:
    if pointer == "":
        return data
    current = data
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit():
                raise IndexError("invalid array index")
            current = current[int(token)]
        else:
            raise TypeError("not traversable")
    return current
