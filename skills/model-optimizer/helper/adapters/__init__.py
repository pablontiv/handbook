from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class RuntimeContext:
    home: Path
    cwd: Path
    env: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "home", Path(self.home))
        object.__setattr__(self, "cwd", Path(self.cwd))
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))
