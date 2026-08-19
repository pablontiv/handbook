from __future__ import annotations

import os
from pathlib import Path

from .models import PlatformProfile


def resolve_state_root(profile: PlatformProfile) -> Path:
    os_name = profile.os_name.lower()
    if os_name == "linux":
        base = Path(profile.env.get("XDG_STATE_HOME", profile.home / ".local" / "state"))
        return base / "remove-gentle-context"
    if os_name == "macos":
        return profile.home / "Library" / "Application Support" / "remove-gentle-context" / "state"
    if os_name == "windows":
        return Path(profile.env.get("LOCALAPPDATA", profile.home / "AppData" / "Local")) / "remove-gentle-context" / "state"
    raise ValueError(f"unsupported platform: {profile.os_name}")


def assert_safe_target(path: Path, allowed_roots: tuple[Path, ...]) -> os.stat_result:
    resolved = path.resolve(strict=False)
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed_roots):
        raise ValueError("preflight_path_escape")
    parent = path.parent
    if not parent.exists() and not any(parent.resolve(strict=False).is_relative_to(root.resolve()) for root in allowed_roots):
        raise ValueError("preflight_path_escape")
    st = os.lstat(path)
    if path.is_symlink():
        raise ValueError("preflight_unexpected_link")
    if hasattr(st, "st_file_attributes") and st.st_file_attributes & getattr(os, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise ValueError("preflight_unexpected_link")
    return st
