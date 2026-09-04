"""Shell runtime selection helpers for ADR integration tests."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

Which = Callable[[str], str | None]


def resolve_bash(*, os_name: str = os.name, which: Which = shutil.which) -> str:
    """Resolve Git Bash on Windows and ordinary Bash elsewhere."""
    if os_name == "nt":
        git = which("git")
        if git is not None:
            for ancestor in Path(git).parents:
                for relative in (Path("bin/bash.exe"), Path("usr/bin/bash.exe")):
                    candidate = ancestor / relative
                    if candidate.is_file():
                        return str(candidate)
        raise RuntimeError(
            "ADR workspace tests on Windows require Git Bash from the active Git installation"
        )

    bash = which("bash")
    if bash is None:
        raise RuntimeError("ADR workspace tests require Bash")
    return bash
