from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath

from .models import PlatformProfile, RuntimeContext


def _is_windows_reparse_point(stat_result: os.stat_result) -> bool:
    return bool(getattr(stat_result, "st_file_attributes", 0) & 0x400)


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
    if path.is_symlink() or _is_windows_reparse_point(st):
        raise ValueError("preflight_unexpected_link")
    return st


def known_roots(context: RuntimeContext) -> dict[str, Path]:
    home = context.profile.home.expanduser()
    canonical_home = home.resolve(strict=False)
    roots: dict[str, Path] = {"home": home}
    seen_paths = {str(canonical_home)}
    project_items: list[tuple[str, Path]] = []
    for root in context.project_roots:
        resolved = Path(root).expanduser().resolve(strict=False)
        key = str(resolved)
        if key in seen_paths:
            raise ValueError("project_root_duplicate")
        seen_paths.add(key)
        root_id = _project_root_id(resolved)
        project_items.append((root_id, resolved))
    for root_id, resolved in sorted(project_items, key=lambda item: item[0]):
        existing = roots.get(root_id)
        if existing is not None and existing != resolved:
            raise ValueError("project_root_id_collision")
        roots[root_id] = resolved
    return roots


def root_map(context: RuntimeContext) -> dict[str, str]:
    return {root_id: str(path.expanduser().resolve(strict=False)) for root_id, path in known_roots(context).items()}


def _project_root_id(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()
    return f"project-{digest}"


def root_relative_path(path: Path, context: RuntimeContext, *, error_code: str = "preflight_path_escape") -> tuple[str, str]:
    resolved = path.resolve(strict=False)
    for root_id, root in known_roots(context).items():
        resolved_root = root.resolve(strict=False)
        if resolved == resolved_root or resolved.is_relative_to(resolved_root):
            relative = resolved.relative_to(resolved_root)
            return root_id, PurePosixPath(*relative.parts).as_posix()
    raise ValueError(error_code)


def path_from_root_relative(root_id: str, relative_path: str, context: RuntimeContext, *, error_code: str = "restore_path_escape") -> Path:
    roots = known_roots(context)
    if root_id not in roots:
        raise ValueError(error_code)
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(error_code)
    path = roots[root_id].joinpath(*relative.parts)
    resolved = path.resolve(strict=False)
    root = roots[root_id].resolve(strict=False)
    if resolved != root and not resolved.is_relative_to(root):
        raise ValueError(error_code)
    return path
