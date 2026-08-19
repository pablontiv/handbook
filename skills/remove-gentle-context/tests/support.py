from __future__ import annotations

from pathlib import Path


def assert_test_home(home: Path, temp_root: Path) -> None:
    resolved = home.resolve()
    if not resolved.is_relative_to(temp_root.resolve()):
        raise AssertionError(f"test target escaped temporary root: {resolved}")
