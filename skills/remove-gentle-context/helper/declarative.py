from __future__ import annotations

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
    Ownership,
    Preimage,
    Receipt,
    RuntimeContext,
)

SCHEMA = "remove-gentle-context.adapter/v1"
CATALOG_SCHEMA = "remove-gentle-context.ownership-catalog/v1"
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
RECEIPT_DIR_ENV_KEYS = (
    "PABLONTIV_SKILLS_RECEIPTS_DIR",
    "SKILLS_RECEIPTS_DIR",
    "SKILLS_RECEIPT_DIR",
)


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
            target = _resolve_root(root, context) / Path(rule.path)
            if rule.kind == "exact_file":
                if target.is_file():
                    candidates.append(self._candidate_for_file(rule, target, context))
            elif rule.kind == "empty_directory":
                if target.is_dir() and not any(target.iterdir()):
                    candidates.append(self._candidate(rule, target, Ownership.PROVEN, "remove_empty_directory", [{"kind": "empty_directory"}], "exact empty directory"))
            elif rule.kind == "balanced_marker_block":
                if target.is_file() and _contains_marker_block(target, rule):
                    candidates.append(self._candidate(rule, target, Ownership.PROVEN, rule.data.get("proposed_action", ACTION_BY_KIND[rule.kind]), [{"kind": "balanced_marker_block"}], "recognized balanced marker block"))
            elif rule.kind == "json_key":
                if target.is_file() and _json_key_present(target, rule):
                    candidates.append(self._candidate(rule, target, Ownership.PROVEN, rule.data.get("proposed_action", ACTION_BY_KIND[rule.kind]), [{"kind": "json_key", "pointer": rule.data["pointer"], "key": rule.data["key"]}], "recognized exact JSON key"))
            elif rule.kind == "json_array_value":
                if target.is_file() and _json_array_value_present(target, rule):
                    candidates.append(self._candidate(rule, target, Ownership.PROVEN, rule.data.get("proposed_action", ACTION_BY_KIND[rule.kind]), [{"kind": "json_array_value", "pointer": rule.data["pointer"], "value": rule.data["value"]}], "recognized exact JSON array value"))
        return tuple(candidates)

    def compile(self, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]:
        if candidate.proposed_action == "report_only":
            return ()
        return (Operation(),)

    def verify(self, receipt: Receipt, context: RuntimeContext) -> tuple[Check, ...]:
        return tuple(receipt.checks)

    def _candidate_for_file(self, rule: DeclarativeRule, target: Path, context: RuntimeContext) -> Candidate:
        content = target.read_bytes()
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        text = content.decode("utf-8", errors="replace")
        frontmatter = _parse_frontmatter(text)
        metadata = frontmatter.get("metadata") if isinstance(frontmatter.get("metadata"), dict) else {}
        evidence: list[dict[str, Any]] = [{"kind": "exact_file", "rule_id": rule.id}]
        details: dict[str, Any] = {"sha256": digest}

        if metadata.get("author") == _catalog_author(self.catalog):
            details["auto_deletion_veto"] = True
            receipt = _verified_personal_receipt(target, digest, frontmatter, metadata, context, self.catalog)
            if receipt is not None:
                evidence.append({"kind": "verified_installation_receipt", "path": receipt["receipt_path"]})
                details["verified_receipt"] = {k: v for k, v in receipt.items() if k != "receipt_path"}
                return self._candidate(rule, target, Ownership.PRESERVED, "report_only", evidence, "personal ownership verified by metadata, adapted provenance, receipt, trusted release, source commit, content hash, and canonical tree hash", details)
            return self._candidate(rule, target, Ownership.AMBIGUOUS, "report_only", evidence, "personal author metadata without complete preservation evidence", details)

        corroboration = _gentle_corroboration(rule, text, digest, self.catalog)
        if corroboration:
            evidence.extend(corroboration)
            action = str(rule.data.get("proposed_action", ACTION_BY_KIND[rule.kind]))
            return self._candidate(rule, target, Ownership.PROVEN, action, evidence, "Gentle-managed content corroborated by marker, generated signature, or fingerprint", details)

        return self._candidate(rule, target, Ownership.AMBIGUOUS, "report_only", evidence, "exact path or name alone cannot prove deletion ownership", details)

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
            details={} if details is None else dict(details),
        )


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


def _load_catalog(adapter_path: Path, catalog_path: Path | None = None) -> Mapping[str, Any]:
    skill_root = Path(__file__).resolve().parents[1]
    resolved_catalog_path = catalog_path or skill_root / "references" / "ownership-catalog-v1.json"
    if resolved_catalog_path.exists():
        catalog = json.loads(resolved_catalog_path.read_text())
    else:
        catalog = {
            "schema": CATALOG_SCHEMA,
            "agent_names": [],
            "marker_prefix": "gentle-ai:",
            "generated_registry_signature": "Auto-generated by gentle-pi extensions/skill-registry.ts",
            "canonical_metadata": {"author": "pablontiv"},
            "adapted_skill_provenance": {},
            "personal_skill_releases": {},
        }
    if not isinstance(catalog, dict) or catalog.get("schema") != CATALOG_SCHEMA:
        raise ValueError("ownership_catalog_invalid_schema")
    releases = catalog.get("personal_skill_releases", {})
    if not isinstance(releases, dict):
        raise ValueError("ownership_catalog_invalid_release_map")
    return catalog


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
        if not isinstance(digest, str) or not _is_sha256_digest(digest):
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


def _is_sha256_digest(value: str) -> bool:
    if value.startswith("sha256:"):
        value = value[len("sha256:") :]
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _resolve_root(root: DeclarativeRoot, context: RuntimeContext) -> Path:
    if root.kind == "home_relative":
        return context.profile.home / Path(root.path)
    raise ValueError("adapter_forbidden_capability")


def _catalog_author(catalog: Mapping[str, Any]) -> str:
    metadata = catalog.get("canonical_metadata", {})
    if isinstance(metadata, dict) and isinstance(metadata.get("author"), str):
        return metadata["author"]
    return "pablontiv"


def _contains_marker_block(path: Path, rule: DeclarativeRule) -> bool:
    text = path.read_text(errors="replace")
    open_marker = str(rule.data["open_marker"])
    close_marker = str(rule.data["close_marker"])
    start = text.find(open_marker)
    end = text.find(close_marker, start + len(open_marker))
    return start != -1 and end != -1


def _json_key_present(path: Path, rule: DeclarativeRule) -> bool:
    try:
        data = json.loads(path.read_text())
        parent = _json_pointer_get(data, str(rule.data["pointer"]))
    except (json.JSONDecodeError, KeyError, TypeError, IndexError):
        return False
    return isinstance(parent, dict) and rule.data["key"] in parent


def _json_array_value_present(path: Path, rule: DeclarativeRule) -> bool:
    try:
        data = json.loads(path.read_text())
        array = _json_pointer_get(data, str(rule.data["pointer"]))
    except (json.JSONDecodeError, KeyError, TypeError, IndexError):
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
            current = current[int(token)]
        else:
            raise TypeError("not traversable")
    return current


def _gentle_corroboration(rule: DeclarativeRule, text: str, digest: str, catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    marker_prefix = catalog.get("marker_prefix")
    if isinstance(marker_prefix, str) and marker_prefix in text:
        evidence.append({"kind": "marker", "value": marker_prefix})
    registry_signature = catalog.get("generated_registry_signature")
    if isinstance(registry_signature, str) and registry_signature in text:
        evidence.append({"kind": "generated_registry_signature", "value": registry_signature})
    for signature in rule.data.get("content_signatures", ()):
        if signature.get("value") == digest:
            evidence.append({"kind": "content_signature", "label": signature.get("label", "sha256"), "value": digest})
    return evidence


def _parse_frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    body: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        body.append(line)
    parsed: dict[str, Any] = {}
    current_map: str | None = None
    for line in body:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            if current_map is None:
                continue
            key, value = _split_yaml_scalar(line.strip())
            if key is not None:
                nested = parsed.setdefault(current_map, {})
                if isinstance(nested, dict):
                    nested[key] = value
            continue
        key, value = _split_yaml_scalar(line.strip())
        if key is None:
            continue
        if value == "":
            parsed[key] = {}
            current_map = key
        else:
            parsed[key] = value
            current_map = None
    return parsed


def _split_yaml_scalar(line: str) -> tuple[str | None, str]:
    if ":" not in line:
        return None, ""
    key, value = line.split(":", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None, ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return key, value


def _verified_personal_receipt(
    target: Path,
    digest: str,
    frontmatter: Mapping[str, Any],
    metadata: Mapping[str, Any],
    context: RuntimeContext,
    catalog: Mapping[str, Any],
) -> dict[str, str] | None:
    skill_name = frontmatter.get("name")
    skill_version = metadata.get("version")
    if not isinstance(skill_name, str) or not isinstance(skill_version, str):
        return None
    if not _has_complete_personal_provenance(skill_name, metadata, catalog):
        return None
    release = _trusted_personal_release(catalog, skill_name)
    if release is None:
        return None
    actual_tree_sha256 = _canonical_tree_sha256(target)
    if actual_tree_sha256 != _normalize_digest(release["canonical_tree_sha256"]):
        return None
    for receipt_path in _receipt_paths(context):
        try:
            receipt = json.loads(receipt_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        normalized = _normalize_receipt(receipt)
        if normalized is None:
            continue
        if normalized["skill_name"] != skill_name or normalized["skill_version"] != skill_version:
            continue
        if Path(normalized["installed_path"]).expanduser().resolve(strict=False) != target.resolve(strict=False):
            continue
        if _normalize_digest(normalized["installed_content_sha256"]) != digest:
            continue
        if normalized["personal_source_repository"] != release["source_repository"]:
            continue
        if normalized["personal_source_commit"] != release["personal_source_commit"]:
            continue
        if _normalize_digest(normalized["canonical_tree_sha256"]) != _normalize_digest(release["canonical_tree_sha256"]):
            continue
        normalized["canonical_tree_sha256"] = actual_tree_sha256
        normalized["receipt_path"] = str(receipt_path)
        return normalized
    return None


def _receipt_paths(context: RuntimeContext) -> tuple[Path, ...]:
    paths: list[Path] = []
    for key in RECEIPT_DIR_ENV_KEYS:
        value = context.profile.env.get(key)
        if value:
            base = Path(value).expanduser()
            if base.is_dir():
                paths.extend(sorted(base.glob("*.json")))
            elif base.is_file():
                paths.append(base)
    return tuple(paths)


def _has_complete_personal_provenance(skill_name: str, metadata: Mapping[str, Any], catalog: Mapping[str, Any]) -> bool:
    canonical = catalog.get("canonical_metadata", {})
    if not isinstance(canonical, dict):
        return False
    required = canonical.get("required_string_fields", ["author", "created", "updated", "version"])
    adapted_required = canonical.get(
        "adapted_required_string_fields",
        ["upstream-author", "upstream-repository", "upstream-commit", "ownership"],
    )
    for field in tuple(required) + tuple(adapted_required):
        if not isinstance(metadata.get(field), str) or not metadata.get(field):
            return False
    if metadata.get("author") != canonical.get("author", "pablontiv"):
        return False
    if metadata.get("ownership") != canonical.get("adapted_ownership", "personal"):
        return False
    adapted_provenance = catalog.get("adapted_skill_provenance", {})
    if not isinstance(adapted_provenance, dict):
        return False
    expected = adapted_provenance.get(skill_name)
    if not isinstance(expected, dict):
        return False
    return all(metadata.get(key) == expected.get(key) for key in ("upstream-author", "upstream-repository", "upstream-commit"))


def _trusted_personal_release(catalog: Mapping[str, Any], skill_name: str) -> dict[str, str] | None:
    releases = catalog.get("personal_skill_releases", {})
    if not isinstance(releases, dict):
        return None
    release = releases.get(skill_name)
    if not isinstance(release, dict):
        return None
    fields = {
        "source_repository": release.get("source_repository"),
        "personal_source_commit": release.get("personal_source_commit"),
        "canonical_tree_sha256": release.get("canonical_tree_sha256"),
    }
    if not all(isinstance(value, str) and value for value in fields.values()):
        return None
    if not _is_full_hex_commit(fields["personal_source_commit"]):
        return None
    if not _is_sha256_digest(fields["canonical_tree_sha256"]):
        return None
    return fields


def _is_full_hex_commit(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def _canonical_tree_sha256(path: Path) -> str:
    if path.is_file():
        entries = (_canonical_tree_entry(path.name, path),)
    elif path.is_dir():
        root = path
        entries = tuple(
            _canonical_tree_entry(file.relative_to(root).as_posix(), file)
            for file in sorted(candidate for candidate in root.rglob("*") if candidate.is_file())
        )
    else:
        entries = ()
    return "sha256:" + hashlib.sha256(canonical_bytes({"entries": list(entries)})).hexdigest()


def _canonical_tree_entry(relative_path: str, path: Path) -> dict[str, str]:
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": relative_path, "sha256": digest, "type": "file"}


def _normalize_receipt(receipt: Any) -> dict[str, str] | None:
    if not isinstance(receipt, dict):
        return None
    skill = receipt.get("skill") if isinstance(receipt.get("skill"), dict) else {}
    fields = {
        "skill_name": receipt.get("skill_name", skill.get("name")),
        "skill_version": receipt.get("skill_version", skill.get("version")),
        "personal_source_repository": receipt.get("personal_source_repository", receipt.get("source_repository")),
        "personal_source_commit": receipt.get("personal_source_commit", receipt.get("source_commit")),
        "installed_path": receipt.get("installed_path"),
        "installed_content_sha256": receipt.get("installed_content_sha256"),
        "installation_timestamp": receipt.get("installation_timestamp", receipt.get("installed_at")),
        "canonical_tree_sha256": receipt.get("canonical_tree_sha256"),
    }
    if not all(isinstance(value, str) and value for value in fields.values()):
        return None
    return dict(fields)


def _normalize_digest(value: str) -> str:
    return value if value.startswith("sha256:") else "sha256:" + value
