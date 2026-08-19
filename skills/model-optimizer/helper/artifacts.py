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
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "model-optimizer.inventory/v1":
        raise ValueError("artifact_unknown_schema")
    inventory = Inventory.from_dict(value)
    expected = inventory_with_digest(replace(inventory, digest="")).digest
    if inventory.digest != expected:
        raise ValueError("artifact_digest_mismatch")
    return inventory


def write_health(path: Path, health: HealthArtifact) -> None:
    path.write_text(json.dumps(health.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_health(path: Path) -> HealthArtifact:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "model-optimizer.health/v1":
        raise ValueError("artifact_unknown_schema")
    return HealthArtifact.from_dict(value)
