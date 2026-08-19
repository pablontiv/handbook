from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from helper.models import ArtifactClass, Candidate, Check, Operation, OperationKind, Ownership, Preimage, Receipt, RuntimeContext
from helper.paths import known_roots
from helper.ownership import classify_exact_file_ownership, load_ownership_catalog, normalize_digest

CLIENT = "claude"
VERSION = "1"
LAYOUT_VERSION = "claude-bounded-v1"
_MARKER_RE = re.compile(br"<!--[ \t]*(/?)gentle-ai:([A-Za-z0-9._/-]+)[ \t]*-->")
_DEFAULT_MARKER_PATHS = (".claude/CLAUDE.md",)
_DEFAULT_THEME_PATH = ".claude/themes/gentleman.json"
_DEFAULT_THEME_DIGEST = "sha256:6872874db5ea5a500d0ae724611e473bab33d5addd162d59fe68d8d03d0656ad"
_DEFAULT_THEME_REQUIRED = {
    "schema": "claude-theme/v1",
    "name": "gentleman",
    "metadata.managedBy": "gentle-ai",
    "metadata.themeId": "gentleman",
}
_IDENTIFIER_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/")


@dataclass(frozen=True)
class _Block:
    identifier: str
    start: int
    end: int


@dataclass(frozen=True)
class _MalformedMarker:
    identifier: str
    state: str


class ClaudeAdapter:
    client = CLIENT
    version = VERSION
    layout_version = LAYOUT_VERSION

    def __init__(self, catalog: Mapping[str, Any] | None = None, *, project_roots: Sequence[Path | str] = ()) -> None:
        self.catalog = load_ownership_catalog() if catalog is None else catalog
        # Compatibility only: project scope authority comes from RuntimeContext.project_roots.
        self.project_roots = tuple(Path(root).expanduser().resolve(strict=False) for root in project_roots)

    def inventory(self, context: RuntimeContext) -> tuple[Candidate, ...]:
        candidates: list[Candidate] = []
        seen: set[tuple[str, str]] = set()
        for target in self._marker_targets(context):
            if not target.is_file():
                continue
            for candidate in self._marker_candidates(target):
                key = (candidate.path, str(candidate.details.get("marker", "")))
                if key not in seen:
                    seen.add(key)
                    candidates.append(candidate)

        for rule in self._exact_file_rules():
            target = context.profile.home / Path(str(rule["path"]))
            if not self._is_allowed_home_relative_target(target, context) or not target.is_file():
                continue
            candidates.append(self._exact_file_candidate(rule, target, context))

        theme = self._theme_rule()
        theme_path = context.profile.home / Path(str(theme["path"]))
        if self._is_allowed_home_relative_target(theme_path, context) and theme_path.is_file():
            candidates.append(self._theme_candidate(theme, theme_path))

        return tuple(sorted(candidates, key=lambda candidate: (candidate.path, candidate.candidate_id)))

    def compile(self, candidate: Candidate, context: RuntimeContext) -> tuple[Operation, ...]:
        if candidate.ownership != Ownership.PROVEN or candidate.proposed_action == "report_only":
            return ()
        kind = candidate.details.get("kind")
        if kind == "marker_block" and candidate.proposed_action == "remove_balanced_marker_block":
            return self._compile_marker_block(candidate)
        if kind in {"exact_file", "theme"} and candidate.proposed_action == "delete_file":
            if "/.atl/" in Path(candidate.path).as_posix():
                return ()
            return (Operation(kind=OperationKind.DELETE_FILE, path=candidate.path),)
        return ()

    def verify(self, receipt: Receipt, context: RuntimeContext) -> tuple[Check, ...]:
        for outcome in receipt.operation_outcomes:
            if outcome.status != "completed" or not self._is_allowed_verification_target(Path(outcome.path), context):
                continue
            target = Path(outcome.path)
            kind = OperationKind(str(outcome.kind))
            if kind == OperationKind.DELETE_FILE and (target.exists() or target.is_symlink()):
                raise ValueError("verify_delete_file_still_present")
            if kind == OperationKind.WRITE_FILE:
                try:
                    target.read_bytes()
                except OSError as exc:
                    raise ValueError("verify_write_file_unreadable") from exc
        return tuple(receipt.checks)

    def _marker_targets(self, context: RuntimeContext) -> tuple[Path, ...]:
        targets: list[Path] = []
        for relative in self._marker_paths():
            target = context.profile.home / Path(relative)
            if self._is_allowed_home_relative_target(target, context):
                targets.append(target)
        for root in context.project_roots:
            targets.append(root / "CLAUDE.md")
        return tuple(dict.fromkeys(targets))

    def _marker_paths(self) -> tuple[str, ...]:
        raw = self._claude_catalog().get("marker_paths", _DEFAULT_MARKER_PATHS)
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return _DEFAULT_MARKER_PATHS
        paths = tuple(path for path in raw if isinstance(path, str) and _is_safe_relative_path(path))
        return paths or _DEFAULT_MARKER_PATHS

    def _exact_file_rules(self) -> tuple[Mapping[str, Any], ...]:
        raw = self._claude_catalog().get("exact_files", ())
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return ()
        rules: list[Mapping[str, Any]] = []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            path = item.get("path")
            if not isinstance(path, str) or not _is_safe_relative_path(path):
                continue
            if ".atl" in PurePosixPath(path).parts:
                continue
            rules.append(item)
        return tuple(rules)

    def _theme_rule(self) -> Mapping[str, Any]:
        raw = self._claude_catalog().get("theme", {})
        if isinstance(raw, Mapping):
            path = raw.get("path")
            if isinstance(path, str) and _is_safe_relative_path(path) and PurePosixPath(path).as_posix() == _DEFAULT_THEME_PATH:
                return raw
        return {
            "id": "theme-gentleman",
            "path": _DEFAULT_THEME_PATH,
            "content_signatures": [{"algorithm": "sha256", "value": _DEFAULT_THEME_DIGEST, "label": "fixture"}],
            "required_fields": dict(_DEFAULT_THEME_REQUIRED),
        }

    def _claude_catalog(self) -> Mapping[str, Any]:
        raw = self.catalog.get("claude", {})
        return raw if isinstance(raw, Mapping) else {}

    def _marker_candidates(self, target: Path) -> tuple[Candidate, ...]:
        content = target.read_bytes()
        blocks, malformed = _analyze_marker_blocks(content)
        if malformed:
            return tuple(
                self._candidate(
                    rule_id=f"marker:{item.identifier}:{item.state}",
                    target=target,
                    artifact_class=ArtifactClass.AMBIGUOUS,
                    ownership=Ownership.AMBIGUOUS,
                    proposed_action="report_only",
                    evidence=({"kind": "marker", "identifier": item.identifier, "state": item.state},),
                    reason="managed marker is missing, duplicate, nested, or unbalanced",
                    details={"kind": "marker_block", "marker": f"gentle-ai:{item.identifier}", "marker_state": item.state},
                )
                for item in malformed
            )
        return tuple(
            self._candidate(
                rule_id=f"marker:{block.identifier}",
                target=target,
                artifact_class=ArtifactClass.ACTIVE_SOURCE,
                ownership=Ownership.PROVEN,
                proposed_action="remove_balanced_marker_block",
                evidence=({"kind": "balanced_marker_block", "identifier": block.identifier},),
                reason="recognized complete Gentle-managed Claude marker block",
                details={
                    "kind": "marker_block",
                    "marker": f"gentle-ai:{block.identifier}",
                    "open_marker": f"<!-- gentle-ai:{block.identifier} -->",
                    "close_marker": f"<!-- /gentle-ai:{block.identifier} -->",
                },
            )
            for block in blocks
        )

    def _exact_file_candidate(self, rule: Mapping[str, Any], target: Path, context: RuntimeContext) -> Candidate:
        decision = classify_exact_file_ownership(
            target=target,
            rule_data=rule,
            default_action="delete_file",
            context=context,
            catalog=self.catalog,
        )
        ownership = decision.ownership
        proposed_action = decision.proposed_action
        reason = decision.reason
        evidence = [{"kind": "exact_file", "path": str(rule.get("path", "")), "rule_id": str(rule.get("id", "exact-file"))}]
        evidence.extend(decision.evidence)

        expected_markers = tuple(str(value) for value in rule.get("expected_markers", ()) if isinstance(value, str))
        if ownership == Ownership.PROVEN and expected_markers and not _has_expected_marker(decision.evidence, expected_markers):
            ownership = Ownership.AMBIGUOUS
            proposed_action = "report_only"
            reason = "exact path was present, but marker/fingerprint corroboration did not match the Claude catalog rule"

        details = dict(decision.details)
        details.update({"kind": "exact_file", "catalog_rule_id": str(rule.get("id", "exact-file"))})
        return self._candidate(
            rule_id=f"exact:{rule.get('id', target.name)}",
            target=target,
            artifact_class=ArtifactClass(str(rule.get("artifact_class", ArtifactClass.ACTIVE_SOURCE))),
            ownership=ownership,
            proposed_action=proposed_action,
            evidence=tuple(evidence),
            reason=reason,
            details=details,
        )

    def _theme_candidate(self, rule: Mapping[str, Any], target: Path) -> Candidate:
        content = target.read_bytes()
        digest = _sha256(content)
        evidence: list[dict[str, Any]] = [{"kind": "exact_file", "path": str(rule.get("path", _DEFAULT_THEME_PATH)), "rule_id": str(rule.get("id", "theme-gentleman"))}]
        details: dict[str, Any] = {"kind": "theme", "sha256": digest}
        if _theme_is_recognized(rule, content, digest, evidence):
            ownership = Ownership.PROVEN
            proposed_action = "delete_file"
            reason = "Claude Gentleman theme matched exact catalog path, structured fields, and content signature"
        else:
            ownership = Ownership.AMBIGUOUS
            proposed_action = "report_only"
            reason = "Claude theme path exists but recognized structured content and exact signature did not both match"
            details["theme_state"] = "unrecognized_or_changed"
        return self._candidate(
            rule_id=f"theme:{rule.get('id', 'gentleman')}",
            target=target,
            artifact_class=ArtifactClass.ACTIVE_SOURCE,
            ownership=ownership,
            proposed_action=proposed_action,
            evidence=tuple(evidence),
            reason=reason,
            details=details,
        )

    def _compile_marker_block(self, candidate: Candidate) -> tuple[Operation, ...]:
        target = Path(candidate.path)
        if not target.is_file():
            return ()
        content = target.read_bytes()
        marker = candidate.details.get("marker")
        if not isinstance(marker, str) or not marker.startswith("gentle-ai:"):
            return ()
        identifier = marker.removeprefix("gentle-ai:")
        blocks, malformed = _analyze_marker_blocks(content)
        matching = [block for block in blocks if block.identifier == identifier]
        if malformed or len(matching) != 1:
            return ()
        block = matching[0]
        postimage = content[: block.start] + content[block.end :]
        return (
            Operation(
                kind=OperationKind.WRITE_FILE,
                path=candidate.path,
                postimage_base64=base64.b64encode(postimage).decode("ascii"),
                postimage_sha256=_sha256(postimage),
                details={"content_type": "text/markdown", "operation": "remove_balanced_marker_block", "marker": marker},
            ),
        )

    def _candidate(
        self,
        *,
        rule_id: str,
        target: Path,
        artifact_class: ArtifactClass,
        ownership: Ownership,
        proposed_action: str,
        evidence: Sequence[object],
        reason: str,
        details: Mapping[str, Any],
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

    def _is_allowed_home_relative_target(self, target: Path, context: RuntimeContext) -> bool:
        home = context.profile.home.resolve(strict=False)
        resolved = target.resolve(strict=False)
        return (resolved == home or resolved.is_relative_to(home)) and ".atl" not in resolved.parts

    def _is_allowed_verification_target(self, target: Path, context: RuntimeContext) -> bool:
        resolved = target.resolve(strict=False)
        home = context.profile.home.resolve(strict=False)
        if (resolved == home or resolved.is_relative_to(home)) and ".atl" not in resolved.parts:
            return True
        for root_id, project_root in known_roots(context).items():
            if root_id == "home":
                continue
            if resolved == project_root or resolved.is_relative_to(project_root):
                return True
        return False


def _analyze_marker_blocks(content: bytes) -> tuple[tuple[_Block, ...], tuple[_MalformedMarker, ...]]:
    markers = list(_MARKER_RE.finditer(content))
    if not markers:
        return (), ()
    stack: list[tuple[str, int]] = []
    blocks: list[_Block] = []
    malformed: dict[str, str] = {}
    for marker in markers:
        is_close = marker.group(1) == b"/"
        identifier = marker.group(2).decode("ascii")
        if not _valid_identifier(identifier):
            malformed[identifier] = "invalid_identifier"
            continue
        if not is_close:
            if stack:
                malformed.setdefault(stack[-1][0], "nested")
                malformed.setdefault(identifier, "nested")
            stack.append((identifier, marker.start()))
            continue
        if not stack:
            malformed.setdefault(identifier, "unbalanced_close")
            continue
        open_identifier, start = stack.pop()
        if open_identifier != identifier:
            malformed.setdefault(open_identifier, "mismatched_close")
            malformed.setdefault(identifier, "mismatched_close")
            continue
        blocks.append(_Block(identifier=identifier, start=start, end=_end_after_line(marker.end(), content)))
    for identifier, _start in stack:
        malformed.setdefault(identifier, "missing_close")
    counts = Counter(block.identifier for block in blocks)
    for identifier, count in counts.items():
        if count > 1:
            malformed.setdefault(identifier, "duplicate")
    if malformed:
        return (), tuple(_MalformedMarker(identifier, state) for identifier, state in sorted(malformed.items()))
    return tuple(blocks), ()


def _end_after_line(index: int, content: bytes) -> int:
    if index < len(content) and content[index:index + 2] == b"\r\n":
        return index + 2
    if index < len(content) and content[index:index + 1] == b"\n":
        return index + 1
    return index


def _valid_identifier(identifier: str) -> bool:
    return bool(identifier) and all(char in _IDENTIFIER_CHARS for char in identifier)


def _has_expected_marker(evidence: Sequence[object], expected_markers: tuple[str, ...]) -> bool:
    normalized = {marker.removeprefix("gentle-ai:") for marker in expected_markers}
    for item in evidence:
        if isinstance(item, Mapping):
            identifier = item.get("identifier")
            if isinstance(identifier, str) and identifier in normalized:
                return True
            value = item.get("value")
            if isinstance(value, str) and any(f"gentle-ai:{identifier}" in value for identifier in normalized):
                return True
            if item.get("kind") in {"content_signature", "generated_registry_signature"}:
                return True
    return False


def _theme_is_recognized(rule: Mapping[str, Any], content: bytes, digest: str, evidence: list[dict[str, Any]]) -> bool:
    if not _has_theme_signature(rule, digest, evidence):
        return False
    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    required = rule.get("required_fields", _DEFAULT_THEME_REQUIRED)
    if not isinstance(required, Mapping):
        required = _DEFAULT_THEME_REQUIRED
    for dotted_key, expected in required.items():
        if not isinstance(dotted_key, str) or _json_dotted_get(data, dotted_key) != expected:
            return False
    evidence.append({"kind": "structured_theme", "required_fields": dict(required)})
    return True


def _has_theme_signature(rule: Mapping[str, Any], digest: str, evidence: list[dict[str, Any]]) -> bool:
    for signature in rule.get("content_signatures", ()):
        if not isinstance(signature, Mapping):
            continue
        value = signature.get("value")
        if isinstance(value, str) and normalize_digest(value) == digest:
            evidence.append({"kind": "content_signature", "label": signature.get("label", "sha256"), "value": digest})
            return True
    return False


def _json_dotted_get(data: Any, dotted_key: str) -> Any:
    current = data
    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _is_safe_relative_path(value: str) -> bool:
    if not value or "\\" in value or value.startswith("~"):
        return False
    path = PurePosixPath(value)
    if path.is_absolute():
        return False
    return all(part not in {"", ".", ".."} for part in path.parts)


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()
