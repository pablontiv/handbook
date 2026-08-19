from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from helper.models import HealthArtifact, Inventory


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def inventory_with_digest(inventory: Inventory) -> Inventory:
    unsigned = inventory.to_dict()
    unsigned["digest"] = ""
    return replace(inventory, digest=digest_json(unsigned))


def write_inventory(path: Path, inventory: Inventory) -> None:
    path.write_text(json.dumps(inventory.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_inventory(path: Path) -> Inventory:
    value = _load_json_object(path)
    if value.get("schema") != "model-optimizer.inventory/v1":
        raise ValueError("artifact_unknown_schema")
    try:
        inventory = Inventory.from_dict(value)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError("artifact_invalid_shape") from None
    expected = inventory_with_digest(replace(inventory, digest="")).digest
    if inventory.digest != expected:
        raise ValueError("artifact_digest_mismatch")
    return inventory


def write_health(path: Path, health: HealthArtifact) -> None:
    path.write_text(json.dumps(health.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_health(path: Path) -> HealthArtifact:
    value = _load_json_object(path)
    if value.get("schema") != "model-optimizer.health/v1":
        raise ValueError("artifact_unknown_schema")
    try:
        return HealthArtifact.from_dict(value)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError("artifact_invalid_shape") from None


def reject_runtime_config_output(path: Path, *, home: Path, cwd: Path, inventory_input: Path | None = None) -> None:
    output = _resolved(path)
    blocked_trees = (
        _resolved(home / ".pi" / "agent"),
        _resolved(cwd / ".pi" / "agent"),
        _resolved(home / ".config" / "opencode"),
    )
    if any(_is_relative_to(output, tree) for tree in blocked_trees):
        raise ValueError("usage_output_forbidden")
    if output == _resolved(cwd / "opencode.json"):
        raise ValueError("usage_output_forbidden")
    if inventory_input is not None and output == _resolved(inventory_input):
        raise ValueError("usage_output_forbidden")


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise ValueError("artifact_invalid_encoding") from None
    except json.JSONDecodeError:
        raise ValueError("artifact_invalid_json") from None
    if not isinstance(value, dict):
        raise ValueError("artifact_invalid_shape")
    return value


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
