from __future__ import annotations

import hashlib
import json
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from helper.runner import CompletedCommand

FIXTURES = Path(__file__).parent / "fixtures"


def assert_test_path(path: Path, temp_root: Path) -> None:
    if not path.resolve().is_relative_to(temp_root.resolve()):
        raise AssertionError(f"test target escaped temporary root: {path}")


def fixture_text(relative: str) -> str:
    return (FIXTURES / relative).read_text(encoding="utf-8")


class FakeRunner:
    def __init__(self, responses: tuple[CompletedCommand, ...]):
        self.responses = deque(responses)
        self.argv: list[tuple[str, ...]] = []
        self.stdout_limits: list[int | None] = []
        self.env_overlays: list[dict[str, str]] = []
        self.env_replacements: list[dict[str, str] | None] = []
        self.cwd_values: list[Path] = []
        self.stdin_payloads: list[str | None] = []

    @classmethod
    def stdout(cls, text: str, returncode: int = 0) -> "FakeRunner":
        return cls((CompletedCommand(
            argv=(), returncode=returncode, stdout=text, stderr="",
            elapsed_ms=1, timed_out=False,
        ),))

    def run(self, argv, timeout, cwd, env_overlay=None, *, stdout_limit=None, env_replacement=None, stdin_text=None):
        self.argv.append(tuple(argv))
        self.stdout_limits.append(stdout_limit)
        self.env_overlays.append(dict(env_overlay or {}))
        self.env_replacements.append(dict(env_replacement) if env_replacement is not None else None)
        self.cwd_values.append(Path(cwd))
        self.stdin_payloads.append(stdin_text)
        if not self.responses:
            raise AssertionError(f"unexpected command: {tuple(argv)!r}")
        result = self.responses.popleft()
        return CompletedCommand(
            argv=tuple(argv), returncode=result.returncode,
            stdout=result.stdout, stderr=result.stderr,
            elapsed_ms=result.elapsed_ms, timed_out=result.timed_out,
            stdout_truncated=result.stdout_truncated,
            stderr_truncated=result.stderr_truncated,
            stdout_decode_replaced=result.stdout_decode_replaced,
            stderr_decode_replaced=result.stderr_decode_replaced,
        )


def _command(stdout: str, returncode: int = 0) -> CompletedCommand:
    return CompletedCommand(
        argv=(), returncode=returncode, stdout=stdout, stderr="",
        elapsed_ms=1, timed_out=False,
    )


def pi_inventory_runner_from_fixtures() -> FakeRunner:
    readiness = tuple(_command(json.dumps({
        "status": "ready", "provider": provider, "authType": "test",
    })) for provider in ("github-copilot", "nan-builders", "openai-codex"))
    return FakeRunner((
        _command("0.84.2\n"),
        _command(fixture_text("pi/list-models.txt")),
        *readiness,
    ))


def copy_pi_fixtures_to_home(root: Path) -> None:
    agent_dir = root / ".pi" / "agent"
    assert_test_path(agent_dir, root)
    agent_dir.mkdir(parents=True)
    for name in ("settings.json", "models-store.json", "subagents.json"):
        target = agent_dir / name
        assert_test_path(target, root)
        target.write_text(fixture_text(f"pi/{name}"), encoding="utf-8")


@dataclass(frozen=True)
class Route:
    model: str
    effort: str | None = None


@dataclass(frozen=True)
class ApplyTarget:
    runtime: str
    scope: str
    path: Path
    format: str


@dataclass(frozen=True)
class ApprovedChange:
    agent: str
    previous_route: Route
    selected_route: Route
    apply_target: ApplyTarget
    source_digest: str

    @classmethod
    def after_approval(
        cls,
        *,
        approved: bool,
        agent: str,
        previous_route: Route,
        selected_route: Route,
        apply_target: ApplyTarget,
        source_digest: str,
    ) -> "ApprovedChange":
        if not approved:
            raise ValueError("approval_required")
        return cls(agent, previous_route, selected_route, apply_target, source_digest)


@dataclass(frozen=True)
class ApplySimulationResult:
    applied: bool
    rollback_applied: bool
    backup_path: Path
    changed_fields: tuple[str, ...]
    events: tuple[str, ...]


def simulate_approved_apply(
    change: ApprovedChange,
    *,
    temp_root: Path,
    timestamp: str,
    fail_at: str | None = None,
) -> ApplySimulationResult:
    """Test-only executable contract for the documented approved apply sequence.

    This intentionally is not imported by production code. It mutates only the
    caller-provided temporary target, records the required backup/edit/validate/
    reload-or-restart/agent-path checks, and uses os.replace for rollback.
    """
    target = change.apply_target.path
    assert_test_path(target, temp_root)
    original = target.read_bytes()
    if _sha256_digest(original) != change.source_digest:
        raise AssertionError("source_digest_mismatch")

    backup_dir = target.parent / ".model-optimizer-backups"
    assert_test_path(backup_dir, temp_root)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{target.name}.{timestamp}.bak"
    assert_test_path(backup_path, temp_root)
    backup_path.write_bytes(original)
    events: list[str] = ["backup"]

    changed_fields = _apply_minimal_scoped_edit(change)
    events.append("edit")
    _validate_source(target, change.apply_target.format)
    events.append("validate:forward")

    transition = "reload" if change.apply_target.runtime == "pi" else "restart"
    first_transition = f"{transition}:first"
    events.append(first_transition)
    failed = fail_at in {first_transition, "reload:first"}
    if not failed:
        events.append("verify:selected")
        _verify_route(target, change.apply_target.format, change.agent, change.selected_route)
        failed = fail_at == "verify:selected"

    if not failed:
        return ApplySimulationResult(
            applied=True,
            rollback_applied=False,
            backup_path=backup_path,
            changed_fields=changed_fields,
            events=tuple(events),
        )

    restore_temp = target.with_name(f".{target.name}.{timestamp}.restore")
    assert_test_path(restore_temp, temp_root)
    restore_temp.write_bytes(backup_path.read_bytes())
    os.replace(restore_temp, target)
    events.append("restore:os.replace")
    _validate_source(target, change.apply_target.format)
    events.append("validate:restored")
    events.append(f"{transition}:second")
    events.append("verify:restored")
    _verify_route(target, change.apply_target.format, change.agent, change.previous_route)
    if target.read_bytes() != original:
        raise AssertionError("rollback_byte_mismatch")
    return ApplySimulationResult(
        applied=False,
        rollback_applied=True,
        backup_path=backup_path,
        changed_fields=changed_fields,
        events=tuple(events),
    )


def _sha256_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _apply_minimal_scoped_edit(change: ApprovedChange) -> tuple[str, ...]:
    target = change.apply_target.path
    text = target.read_text(encoding="utf-8")
    fields: list[str] = []
    if change.apply_target.format == "pi-json":
        text = _replace_json_string_member(text, ("model_profiles", change.agent, "model"), change.selected_route.model)
        fields.append(f"model_profiles.{change.agent}.model")
        if change.selected_route.effort is not None and _json_member_exists(text, ("model_profiles", change.agent, "effort")):
            text = _replace_json_string_member(text, ("model_profiles", change.agent, "effort"), change.selected_route.effort)
            fields.append(f"model_profiles.{change.agent}.effort")
    elif change.apply_target.format == "opencode-json":
        text = _replace_json_string_member(text, ("agent", change.agent, "model"), change.selected_route.model)
        fields.append(f"agent.{change.agent}.model")
        if change.selected_route.effort is not None and _json_member_exists(text, ("agent", change.agent, "variant")):
            text = _replace_json_string_member(text, ("agent", change.agent, "variant"), change.selected_route.effort)
            fields.append(f"agent.{change.agent}.variant")
    elif change.apply_target.format == "opencode-markdown":
        text, changed = _replace_frontmatter_field(text, "model", change.selected_route.model)
        if changed:
            fields.append("frontmatter.model")
        if change.selected_route.effort is not None:
            text, changed = _replace_frontmatter_field(text, "variant", change.selected_route.effort)
            if changed:
                fields.append("frontmatter.variant")
    else:
        raise AssertionError(f"unsupported_apply_format:{change.apply_target.format}")
    target.write_text(text, encoding="utf-8")
    return tuple(fields)


def _validate_source(path: Path, source_format: str) -> None:
    text = path.read_text(encoding="utf-8")
    if source_format in {"pi-json", "opencode-json"}:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise AssertionError("json_config_not_object")
    elif source_format == "opencode-markdown":
        _frontmatter_bounds(text)
    else:
        raise AssertionError(f"unsupported_apply_format:{source_format}")


def _verify_route(path: Path, source_format: str, agent: str, route: Route) -> None:
    text = path.read_text(encoding="utf-8")
    if source_format == "pi-json":
        profile = json.loads(text)["model_profiles"][agent]
        model = profile.get("model")
        effort = profile.get("effort")
    elif source_format == "opencode-json":
        profile = json.loads(text)["agent"][agent]
        model = profile.get("model")
        effort = profile.get("variant")
    elif source_format == "opencode-markdown":
        metadata = _frontmatter_mapping(text)
        model = metadata.get("model")
        effort = metadata.get("variant")
    else:
        raise AssertionError(f"unsupported_apply_format:{source_format}")
    if model != route.model:
        raise AssertionError(f"agent_route_model_mismatch:{agent}")
    if route.effort is not None and effort is not None and effort != route.effort:
        raise AssertionError(f"agent_route_effort_mismatch:{agent}")


def _json_member_exists(text: str, path: tuple[str, ...]) -> bool:
    try:
        _json_member_span(text, path)
    except AssertionError:
        return False
    return True


def _replace_json_string_member(text: str, path: tuple[str, ...], replacement: str) -> str:
    start, end = _json_member_span(text, path)
    current = json.loads(text[start:end])
    if not isinstance(current, str):
        raise AssertionError("json_target_not_string")
    return text[:start] + json.dumps(replacement) + text[end:]


def _json_member_span(text: str, path: tuple[str, ...]) -> tuple[int, int]:
    span = (0, len(text))
    for key in path:
        span = _find_object_member_value_span(text, span, key)
    return span


def _find_object_member_value_span(text: str, object_span: tuple[int, int], key: str) -> tuple[int, int]:
    start, end = object_span
    start = _skip_ws(text, start)
    if start >= end or text[start] != "{":
        raise AssertionError("json_parent_not_object")
    index = start + 1
    decoder = json.JSONDecoder()
    while index < end:
        index = _skip_ws(text, index)
        if index >= end or text[index] == "}":
            break
        if text[index] == ",":
            index += 1
            continue
        if text[index] != '"':
            raise AssertionError("json_object_key_expected")
        decoded_key, key_end = decoder.raw_decode(text, index)
        colon = _skip_ws(text, key_end)
        if colon >= end or text[colon] != ":":
            raise AssertionError("json_object_colon_expected")
        value_start = _skip_ws(text, colon + 1)
        value_end = _skip_json_value(text, value_start)
        if decoded_key == key:
            return value_start, value_end
        index = value_end
    raise AssertionError(f"json_member_missing:{'.'.join((key,))}")


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


def _skip_json_value(text: str, index: int) -> int:
    decoder = json.JSONDecoder()
    if text[index] == '"':
        _, end = decoder.raw_decode(text, index)
        return end
    if text[index] in "{[":
        return _skip_json_container(text, index)
    while index < len(text) and text[index] not in ",}]\r\n\t ":
        index += 1
    return index


def _skip_json_container(text: str, index: int) -> int:
    opening = text[index]
    closing = "}" if opening == "{" else "]"
    stack = [closing]
    index += 1
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char in "{[":
                stack.append("}" if char == "{" else "]")
            elif char in "}]":
                expected = stack.pop()
                if char != expected:
                    raise AssertionError("json_container_mismatch")
                if not stack:
                    return index + 1
        index += 1
    raise AssertionError("json_container_unclosed")


def _frontmatter_bounds(text: str) -> tuple[int, int, int]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise AssertionError("markdown_frontmatter_missing")
    offset = len(lines[0])
    for line in lines[1:]:
        if line.strip() == "---":
            return len(lines[0]), offset, offset + len(line)
        offset += len(line)
    raise AssertionError("markdown_frontmatter_unclosed")


def _frontmatter_mapping(text: str) -> dict[str, str]:
    start, end, _body_start = _frontmatter_bounds(text)
    result: dict[str, str] = {}
    for line in text[start:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def _replace_frontmatter_field(text: str, field: str, replacement: str) -> tuple[str, bool]:
    start, end, _body_start = _frontmatter_bounds(text)
    index = start
    while index < end:
        line_end = text.find("\n", index, end)
        if line_end == -1:
            line_end = end
            newline_end = end
        else:
            newline_end = line_end + 1
        line = text[index:newline_end]
        if line.startswith(f"{field}:"):
            value_start = index + len(field) + 1
            while value_start < line_end and text[value_start] in " \t":
                value_start += 1
            value_end = line_end
            if value_end > value_start and text[value_end - 1] == "\r":
                value_end -= 1
            current = text[value_start:value_end]
            if current == replacement:
                return text, False
            return text[:value_start] + replacement + text[value_end:], True
        index = newline_end
    raise AssertionError(f"frontmatter_field_missing:{field}")
