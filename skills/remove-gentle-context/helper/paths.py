from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath

from .models import PlatformProfile, RuntimeContext


ENVIRONMENT_ENV_KEYS = ("XDG_STATE_HOME", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA")
_PLATFORM_CONFIG_ENV_KEYS = ("XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA")


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
    canonical_authority_roots = [canonical_home]
    project_items: list[tuple[str, Path]] = []
    for root in context.project_roots:
        resolved = Path(root).expanduser().resolve(strict=False)
        key = str(resolved)
        if key in seen_paths:
            raise ValueError("project_root_duplicate")
        seen_paths.add(key)
        canonical_authority_roots.append(resolved)
        root_id = _project_root_id(resolved)
        project_items.append((root_id, resolved))
    for root_id, resolved in sorted(project_items, key=lambda item: item[0]):
        existing = roots.get(root_id)
        if existing is not None and existing != resolved:
            raise ValueError("project_root_id_collision")
        roots[root_id] = resolved

    platform_items: list[tuple[str, Path]] = []
    for env_key in _PLATFORM_CONFIG_ENV_KEYS:
        resolved = explicit_platform_config_root(context.profile, env_key)
        if resolved is None or _is_inside_any(resolved, tuple(canonical_authority_roots)):
            continue
        key = str(resolved)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        canonical_authority_roots.append(resolved)
        platform_items.append((_platform_config_root_id(resolved), resolved))
    for root_id, resolved in sorted(platform_items, key=lambda item: item[0]):
        existing = roots.get(root_id)
        if existing is not None and existing != resolved:
            raise ValueError("platform_config_root_id_collision")
        roots[root_id] = resolved
    return roots


def root_map(context: RuntimeContext) -> dict[str, str]:
    return {root_id: str(path.expanduser().resolve(strict=False)) for root_id, path in known_roots(context).items()}


def canonical_environment_roots(env: object, *, reject_unknown: bool = False) -> dict[str, str]:
    if not isinstance(env, dict):
        env = dict(env)  # type: ignore[arg-type]
    result: dict[str, str] = {}
    for key, value in sorted(env.items()):
        if key not in ENVIRONMENT_ENV_KEYS:
            if reject_unknown:
                raise ValueError("environment_key_unsupported")
            continue
        if not isinstance(value, str) or not value:
            raise ValueError("environment_root_invalid")
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("environment_root_invalid")
        resolved = path.resolve(strict=False)
        if path != resolved:
            raise ValueError("environment_root_invalid")
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            result[key] = str(resolved)
            continue
        if path.is_symlink() or _is_windows_reparse_point(st):
            raise ValueError("environment_root_invalid")
        result[key] = str(resolved)
    return result


def explicit_platform_config_root(profile: PlatformProfile, env_key: str) -> Path | None:
    raw = profile.env.get(env_key)
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        raise ValueError("platform_config_root_invalid")
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError("platform_config_root_invalid")
    return path.resolve(strict=False)


def _project_root_id(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()
    return f"project-{digest}"


def _platform_config_root_id(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()
    return f"platform-config-{digest}"


def _is_inside_any(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


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
