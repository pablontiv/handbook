from __future__ import annotations

import csv
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Iterable, Protocol, Sequence

from .models import CompletedCommand, LifecycleAction, LifecycleOutcome, ProcessSnapshot, RuntimeContext


class CommandRunner:
    def run(self, argv: tuple[str, ...], timeout: float) -> CompletedCommand:
        if not isinstance(argv, tuple) or not all(isinstance(part, str) for part in argv):
            raise TypeError("command_argv_must_be_tuple_of_strings")
        completed = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=timeout, check=False)
        return CompletedCommand(argv=argv, returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


class Clock(Protocol):
    def time(self) -> float: ...


class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


class _MonotonicClock:
    def time(self) -> float:
        return time.monotonic()


class _RealSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class ProcessProbe(Protocol):
    def inspect_processes(self, action: LifecycleAction, context: RuntimeContext) -> tuple[ProcessSnapshot, ...]: ...
    def is_running(self, snapshot: ProcessSnapshot) -> bool: ...
    def is_same_process(self, snapshot: ProcessSnapshot) -> bool: ...


class CommandProcessProbe:
    def __init__(self, runner: object, *, command_timeout: float = 5.0) -> None:
        self.runner = runner
        self.command_timeout = command_timeout

    def inspect_processes(self, action: LifecycleAction, context: RuntimeContext) -> tuple[ProcessSnapshot, ...]:
        platform = _normalize_platform(context.profile.os_name)
        if platform == "macos":
            return self._inspect_pgrep_ps(action, platform, context)
        if platform == "linux":
            return self._inspect_linux(action, context)
        if platform == "windows":
            return self._inspect_windows(action, context)
        raise ValueError("preflight_lifecycle_unsupported_platform")

    def is_running(self, snapshot: ProcessSnapshot) -> bool:
        try:
            current = self.inspect_processes(snapshot.action, RuntimeContext(snapshot.details["profile"])) if False else self._inspect_from_snapshot(snapshot)
        except ValueError:
            raise
        except Exception:
            return False
        return any(item.pid == snapshot.pid and item.identity == snapshot.identity for item in current)

    def is_same_process(self, snapshot: ProcessSnapshot) -> bool:
        try:
            current = self._inspect_from_snapshot(snapshot)
        except Exception:
            return False
        return any(item.pid == snapshot.pid and item.identity == snapshot.identity for item in current)

    def _inspect_from_snapshot(self, snapshot: ProcessSnapshot) -> tuple[ProcessSnapshot, ...]:
        platform = _normalize_platform(snapshot.platform)
        action = snapshot.action
        if platform == "macos":
            return self._inspect_pgrep_ps(action, platform, None)
        if platform == "linux":
            return self._inspect_linux(action, None)
        if platform == "windows":
            return self._inspect_windows(action, None)
        return ()

    def _inspect_pgrep_ps(self, action: LifecycleAction, platform: str, context: RuntimeContext | None) -> tuple[ProcessSnapshot, ...]:
        name = _process_name(action)
        pids = self._pgrep_exact(name)
        snapshots: list[ProcessSnapshot] = []
        metadata_missing = False
        for pid in pids:
            completed = _runner_run(self.runner, ("ps", "-p", str(pid), "-o", "pid=", "-o", "comm=", "-o", "args="), self.command_timeout)
            if completed.returncode != 0:
                metadata_missing = True
                continue
            line = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
            parts = line.split(None, 2)
            if len(parts) < 2:
                metadata_missing = True
                continue
            parsed_pid = _parse_pid(parts[0])
            if parsed_pid != pid:
                metadata_missing = True
                continue
            executable = parts[1]
            argv = tuple(parts[2].split()) if len(parts) > 2 and parts[2] else (executable,)
            bundle_id = _bundle_id(action)
            snapshots.append(
                ProcessSnapshot(
                    action=action,
                    platform=platform,
                    running=True,
                    pid=pid,
                    process_name=name,
                    executable=executable,
                    argv=argv,
                    bundle_id=bundle_id,
                    identity=f"{platform}:{pid}:{executable}:{' '.join(argv)}",
                )
            )
        if metadata_missing:
            raise ValueError("preflight_lifecycle_missing_process_metadata")
        return tuple(snapshots)

    def _inspect_linux(self, action: LifecycleAction, context: RuntimeContext | None) -> tuple[ProcessSnapshot, ...]:
        name = _process_name(action)
        pids = self._pgrep_exact(name)
        snapshots: list[ProcessSnapshot] = []
        metadata_missing = False
        for pid in pids:
            proc = Path("/proc") / str(pid)
            try:
                executable = os.readlink(proc / "exe")
                raw_cmdline = (proc / "cmdline").read_bytes()
            except OSError:
                metadata_missing = True
                continue
            argv = tuple(part.decode("utf-8", errors="surrogateescape") for part in raw_cmdline.split(b"\0") if part)
            if not executable or not argv:
                metadata_missing = True
                continue
            snapshots.append(
                ProcessSnapshot(
                    action=action,
                    platform="linux",
                    running=True,
                    pid=pid,
                    process_name=name,
                    executable=executable,
                    argv=argv,
                    identity=f"linux:{pid}:{executable}:{' '.join(argv)}",
                )
            )
        if metadata_missing:
            raise ValueError("preflight_lifecycle_missing_process_metadata")
        return tuple(snapshots)

    def _inspect_windows(self, action: LifecycleAction, context: RuntimeContext | None) -> tuple[ProcessSnapshot, ...]:
        name = _process_name(action)
        completed = _runner_run(self.runner, ("tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"), self.command_timeout)
        if completed.returncode != 0:
            raise ValueError("preflight_lifecycle_inspect_failed")
        pids: list[int] = []
        for row in csv.reader(completed.stdout.splitlines()):
            if len(row) >= 2 and row[0].lower() == name.lower():
                pid = _parse_pid(row[1])
                if pid is not None:
                    pids.append(pid)
        snapshots: list[ProcessSnapshot] = []
        for pid in pids:
            script = "param($PidValue) Get-CimInstance Win32_Process -Filter \"ProcessId=$PidValue\" | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
            metadata = _runner_run(self.runner, ("powershell", "-NoProfile", "-Command", script, str(pid)), self.command_timeout)
            if metadata.returncode != 0 or not metadata.stdout.strip():
                continue
            try:
                data = json.loads(metadata.stdout)
            except json.JSONDecodeError:
                continue
            executable = data.get("ExecutablePath")
            command_line = data.get("CommandLine")
            parsed_pid = _parse_pid(str(data.get("ProcessId", "")))
            if not isinstance(executable, str) or not executable or not isinstance(command_line, str) or parsed_pid != pid:
                continue
            restart_argv = _restart_argv(action) or _windows_restart_argv(command_line, executable)
            if not restart_argv:
                raise ValueError("preflight_lifecycle_missing_process_metadata")
            snapshots.append(
                ProcessSnapshot(
                    action=action,
                    platform="windows",
                    running=True,
                    pid=pid,
                    process_name=name,
                    executable=executable,
                    argv=restart_argv,
                    identity=f"windows:{pid}:{executable}:{command_line}",
                )
            )
        if pids and len(snapshots) != len(pids):
            raise ValueError("preflight_lifecycle_missing_process_metadata")
        return tuple(snapshots)

    def _pgrep_exact(self, name: str) -> tuple[int, ...]:
        completed = _runner_run(self.runner, ("pgrep", "-x", name), self.command_timeout)
        if completed.returncode == 1 or not completed.stdout.strip():
            return ()
        if completed.returncode != 0:
            raise ValueError("preflight_lifecycle_inspect_failed")
        pids = tuple(pid for pid in (_parse_pid(line.strip()) for line in completed.stdout.splitlines()) if pid is not None)
        return pids


class LifecycleController:
    def __init__(
        self,
        runner: object | None = None,
        *,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
        process_probe: ProcessProbe | None = None,
        stop_timeout: float = 10.0,
        command_timeout: float = 5.0,
        poll_interval: float = 0.1,
    ) -> None:
        self.runner = runner if runner is not None else CommandRunner()
        self.clock = clock if clock is not None else _MonotonicClock()
        self.sleeper = sleeper if sleeper is not None else _RealSleeper()
        if process_probe is not None:
            self.process_probe = process_probe
        elif hasattr(self.runner, "inspect_processes"):
            self.process_probe = self.runner  # type: ignore[assignment]
        else:
            self.process_probe = CommandProcessProbe(self.runner, command_timeout=command_timeout)
        self.stop_timeout = stop_timeout
        self.command_timeout = command_timeout
        self.poll_interval = poll_interval
        self._stopped_keys: set[tuple[str, str, int | None, str | None]] = set()

    def inspect(self, action: LifecycleAction, context: RuntimeContext) -> ProcessSnapshot:
        snapshots = self.process_probe.inspect_processes(action, context)
        if len(snapshots) > 1:
            raise ValueError("preflight_lifecycle_ambiguous")
        if not snapshots:
            return ProcessSnapshot(action=action, platform=_normalize_platform(context.profile.os_name), running=False, process_name=_process_name(action))
        return snapshots[0]

    def preflight(self, actions: Iterable[LifecycleAction], context: RuntimeContext) -> tuple[ProcessSnapshot, ...]:
        snapshots: list[ProcessSnapshot] = []
        for action in actions:
            snapshot = self.inspect(action, context)
            if not snapshot.running:
                continue
            if action.action != "stop" or not self._graceful_stop_available(snapshot):
                raise ValueError("preflight_lifecycle_unavailable")
            self._validate_running_snapshot(snapshot)
            snapshots.append(snapshot)
        return tuple(snapshots)

    def stop(self, snapshot: ProcessSnapshot) -> LifecycleOutcome:
        if not snapshot.running:
            return _outcome(snapshot, action="stop", status="not_running")
        self._validate_running_snapshot(snapshot)
        self._ensure_same_process(snapshot)
        argv = self._stop_argv(snapshot)
        completed = _runner_run(self.runner, argv, self.command_timeout)
        if completed.returncode != 0:
            raise ValueError("lifecycle_stop_failed")
        self._poll_exit(snapshot)
        self._stopped_keys.add(_snapshot_key(snapshot))
        return _outcome(snapshot, action="stop", status="stopped", argv=argv)

    def restart(self, snapshot: ProcessSnapshot) -> LifecycleOutcome:
        if _snapshot_key(snapshot) not in self._stopped_keys:
            return _outcome(snapshot, action="restart", status="skipped", code="lifecycle_not_stopped_by_transaction")
        argv = self._restart_argv(snapshot)
        completed = _runner_run(self.runner, argv, self.command_timeout)
        if completed.returncode != 0:
            return _outcome(snapshot, action="restart", status="failed", code="lifecycle_restart_failed", argv=argv)
        self._stopped_keys.discard(_snapshot_key(snapshot))
        return _outcome(snapshot, action="restart", status="restarted", argv=argv)

    def _graceful_stop_available(self, snapshot: ProcessSnapshot) -> bool:
        checker = getattr(self.process_probe, "graceful_stop_available", None)
        if checker is not None:
            return bool(checker(snapshot))
        return True

    def _validate_running_snapshot(self, snapshot: ProcessSnapshot) -> None:
        if snapshot.pid is None or snapshot.identity is None or not snapshot.executable:
            raise ValueError("preflight_lifecycle_missing_process_metadata")
        platform = _normalize_platform(snapshot.platform)
        if platform == "macos":
            if not snapshot.bundle_id:
                raise ValueError("preflight_lifecycle_missing_restart_metadata")
            return
        if platform in {"linux", "windows"}:
            if not snapshot.argv or not snapshot.argv[0]:
                raise ValueError("preflight_lifecycle_missing_restart_metadata")
            return
        raise ValueError("preflight_lifecycle_unsupported_platform")

    def _ensure_same_process(self, snapshot: ProcessSnapshot) -> None:
        if not self.process_probe.is_same_process(snapshot):
            raise ValueError("lifecycle_pid_identity_changed")

    def _poll_exit(self, snapshot: ProcessSnapshot) -> None:
        deadline = self.clock.time() + self.stop_timeout
        while True:
            if not self.process_probe.is_running(snapshot):
                return
            if not self.process_probe.is_same_process(snapshot):
                raise ValueError("lifecycle_pid_identity_changed")
            if self.clock.time() >= deadline:
                raise ValueError("lifecycle_exit_unconfirmed")
            self.sleeper.sleep(self.poll_interval)

    def _stop_argv(self, snapshot: ProcessSnapshot) -> tuple[str, ...]:
        platform = _normalize_platform(snapshot.platform)
        if platform == "macos":
            assert snapshot.bundle_id is not None
            return ("osascript", "-e", f'tell application id "{snapshot.bundle_id}" to quit')
        if platform == "linux":
            assert snapshot.pid is not None
            return ("kill", "-TERM", str(snapshot.pid))
        if platform == "windows":
            assert snapshot.pid is not None
            return ("taskkill", "/PID", str(snapshot.pid))
        raise ValueError("preflight_lifecycle_unsupported_platform")

    def _restart_argv(self, snapshot: ProcessSnapshot) -> tuple[str, ...]:
        platform = _normalize_platform(snapshot.platform)
        if platform == "macos":
            if not snapshot.bundle_id:
                raise ValueError("preflight_lifecycle_missing_restart_metadata")
            return ("open", "-b", snapshot.bundle_id)
        if platform in {"linux", "windows"}:
            if not snapshot.argv:
                raise ValueError("preflight_lifecycle_missing_restart_metadata")
            return snapshot.argv
        raise ValueError("preflight_lifecycle_unsupported_platform")


def _runner_run(runner: object, argv: tuple[str, ...], timeout: float) -> CompletedCommand:
    if not isinstance(argv, tuple) or not all(isinstance(part, str) for part in argv):
        raise TypeError("command_argv_must_be_tuple_of_strings")
    completed = runner.run(argv, timeout)  # type: ignore[attr-defined]
    if isinstance(completed, CompletedCommand):
        return completed
    return CompletedCommand(
        argv=tuple(getattr(completed, "argv", argv)),
        returncode=int(getattr(completed, "returncode", 0)),
        stdout=str(getattr(completed, "stdout", "")),
        stderr=str(getattr(completed, "stderr", "")),
    )


def _normalize_platform(os_name: str) -> str:
    value = os_name.lower()
    if value in {"darwin", "mac", "macos", "osx"}:
        return "macos"
    if value.startswith("win"):
        return "windows"
    if value == "linux":
        return "linux"
    return value


def _process_name(action: LifecycleAction) -> str:
    value = action.details.get("process_name")
    if isinstance(value, str) and value:
        return value
    if action.target:
        return action.target
    return action.client


def _bundle_id(action: LifecycleAction) -> str | None:
    value = action.details.get("bundle_id")
    if isinstance(value, str) and value:
        return value
    if action.target.startswith("com."):
        return action.target
    return None


def _restart_argv(action: LifecycleAction) -> tuple[str, ...]:
    value = action.details.get("restart_argv")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and all(isinstance(part, str) for part in value):
        return tuple(value)
    return ()


def _windows_restart_argv(command_line: str, executable: str) -> tuple[str, ...]:
    try:
        parsed = tuple(part.strip('"') for part in shlex.split(command_line, posix=False) if part.strip('"'))
    except ValueError:
        return ()
    if not parsed:
        return (executable,)
    return (executable, *parsed[1:])


def _parse_pid(value: str) -> int | None:
    try:
        pid = int(value.strip())
    except ValueError:
        return None
    return pid if pid > 0 else None


def _snapshot_key(snapshot: ProcessSnapshot) -> tuple[str, str, int | None, str | None]:
    return (_normalize_platform(snapshot.platform), snapshot.action.client, snapshot.pid, snapshot.identity)


def _outcome(snapshot: ProcessSnapshot, *, action: str, status: str, code: str | None = None, argv: tuple[str, ...] = ()) -> LifecycleOutcome:
    return LifecycleOutcome(action=action, client=snapshot.action.client, target=snapshot.action.target, status=status, code=code, pid=snapshot.pid, argv=argv)
