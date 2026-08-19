from pathlib import Path


def assert_test_path(path: Path, temp_root: Path) -> None:
    if not path.resolve().is_relative_to(temp_root.resolve()):
        raise AssertionError(f"test target escaped temporary root: {path}")
