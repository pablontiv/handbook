from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from helper.models import HealthArtifact, Inventory

_REPLACE_RETRY_ATTEMPTS = 3
_REPLACE_RETRY_SLEEP_SECONDS = 0.01
_WRITE_LOCK_STRIPES = 64
_WRITE_LOCKS = tuple(threading.Lock() for _ in range(_WRITE_LOCK_STRIPES))


def canonical_bytes(value: Any) -> bytes:
    return _json_dumps_strict(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def inventory_with_digest(inventory: Inventory) -> Inventory:
    unsigned = inventory.to_dict()
    unsigned["digest"] = ""
    return replace(inventory, digest=digest_json(unsigned))


def write_inventory(path: Path, inventory: Inventory) -> None:
    _atomic_write_text(path, _json_dumps_strict(inventory.to_dict(), indent=2) + "\n")


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
    _atomic_write_text(path, _json_dumps_strict(health.to_dict(), indent=2) + "\n")


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, _json_dumps_strict(value, sort_keys=True, indent=2) + "\n")


def load_health(path: Path) -> HealthArtifact:
    value = _load_json_object(path)
    if value.get("schema") != "model-optimizer.health/v1":
        raise ValueError("artifact_unknown_schema")
    try:
        return HealthArtifact.from_dict(value)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError("artifact_invalid_shape") from None


def byte_inventory(paths: tuple[Path, ...]) -> tuple[dict[str, Any], ...]:
    """Return a bounded before/after byte inventory for runtime config boundaries."""
    records: list[dict[str, Any]] = []
    for path in paths:
        target = _resolved(path)
        if target.is_dir():
            digest = hashlib.sha256()
            total = 0
            count = 0
            for child in sorted(item for item in target.rglob("*") if item.is_file() and not item.is_symlink()):
                try:
                    data = child.read_bytes()
                except OSError:
                    continue
                digest.update(str(child.relative_to(target)).encode("utf-8", "surrogateescape"))
                digest.update(b"\0")
                digest.update(data)
                total += len(data)
                count += 1
            records.append({"path": str(target), "exists": True, "kind": "directory", "file_count": count, "byte_count": total, "digest": "sha256:" + digest.hexdigest()})
        elif target.exists() and not target.is_symlink():
            data = target.read_bytes()
            records.append({"path": str(target), "exists": True, "kind": "file", "file_count": 1, "byte_count": len(data), "digest": "sha256:" + hashlib.sha256(data).hexdigest()})
        else:
            records.append({"path": str(target), "exists": False, "kind": "missing", "file_count": 0, "byte_count": 0, "digest": None})
    return tuple(records)


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
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant)
    except UnicodeDecodeError:
        raise ValueError("artifact_invalid_encoding") from None
    except json.JSONDecodeError:
        raise ValueError("artifact_invalid_json") from None
    except ValueError as exc:
        if str(exc) == "artifact_invalid_number":
            raise ValueError("artifact_invalid_number") from None
        raise
    if not isinstance(value, dict):
        raise ValueError("artifact_invalid_shape")
    return value


def _json_dumps_strict(value: Any, **kwargs: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, **kwargs)
    except ValueError as exc:
        if "Out of range float values" in str(exc):
            raise ValueError("artifact_invalid_number") from None
        raise


def _reject_json_constant(_constant: str) -> None:
    raise ValueError("artifact_invalid_number")


def _atomic_write_text(path: Path, text: str) -> None:
    target = Path(path)
    encoded = text.encode("utf-8")
    write_lock = _write_lock_for_target(target)
    with write_lock:
        fd: int | None = None
        temp_name: str | None = None
        try:
            fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
            with os.fdopen(fd, "wb") as handle:
                fd = None
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            _replace_with_retry(temp_name, target)
            temp_name = None
            _fsync_directory(target.parent)
        finally:
            if fd is not None:
                os.close(fd)
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass


def _replace_with_retry(temp_name: str, target: Path) -> None:
    for attempt in range(1, _REPLACE_RETRY_ATTEMPTS + 1):
        try:
            os.replace(temp_name, target)
            return
        except PermissionError:
            if attempt == _REPLACE_RETRY_ATTEMPTS:
                raise
            time.sleep(_REPLACE_RETRY_SLEEP_SECONDS)


def _write_lock_for_target(path: Path) -> threading.Lock:
    resolved = str(_resolved(path))
    digest = hashlib.blake2b(resolved.encode("utf-8"), digest_size=8).digest()
    stripe_index = int.from_bytes(digest, "big") % _WRITE_LOCK_STRIPES
    return _WRITE_LOCKS[stripe_index]


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
