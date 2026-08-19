from __future__ import annotations

import hashlib
import json
from typing import TypeAlias

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def canonical_bytes(value: JsonValue) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest_json(value: JsonValue) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()
