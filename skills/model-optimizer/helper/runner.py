from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

MAX_STREAM_CHARS = 8192
SENSITIVE_KEY_RE = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|COOKIE|AUTHORIZATION|CREDENTIAL", re.IGNORECASE)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
CTRL_BREAK_EVENT = getattr(signal, "CTRL_BREAK_EVENT", signal.SIGTERM)
_TERMINATION_GRACE_SECONDS = 0.5


@dataclass(frozen=True)
class CompletedCommand:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    elapsed_ms: int
    timed_out: bool


def _is_windows() -> bool:
    return os.name == "nt"


def _validate_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if isinstance(argv, (str, bytes)):
        raise ValueError("runner_invalid_argv")
    normalized = tuple(argv)
    if not normalized:
        raise ValueError("runner_invalid_argv")
    for arg in normalized:
        if not isinstance(arg, str) or "\x00" in arg:
            raise ValueError("runner_invalid_argv")
    return normalized


def _sensitive_env_values(env: Mapping[str, str]) -> tuple[str, ...]:
    values: list[str] = []
    for key, value in env.items():
        if value and SENSITIVE_KEY_RE.search(key):
            values.append(value)
    return tuple(values)


def _truncate_tail(text: str) -> str:
    if len(text) <= MAX_STREAM_CHARS:
        return text
    return text[-MAX_STREAM_CHARS:]


def redact_text(text: str, sensitive_values: Sequence[str] = ()) -> str:
    redacted = text
    for value in sorted({str(candidate) for candidate in sensitive_values if candidate}, key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    redacted = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)([^\s,;]+)",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(\b(?:api[_-]?key|token|secret|password|cookie|credential)\b\s*[=:]\s*)([^\s,;]+)",
        r"\1[REDACTED]",
        redacted,
    )
    return redacted


class CommandRunner:
    def run(
        self,
        argv: Sequence[str],
        timeout: float,
        cwd: Path,
        env_overlay: Mapping[str, str] | None = None,
    ) -> CompletedCommand:
        command = _validate_argv(argv)
        env = dict(os.environ)
        if env_overlay:
            env.update(env_overlay)
        sensitive_values = _sensitive_env_values(env)
        start = time.monotonic()
        timed_out = False
        stdout = ""
        stderr = ""

        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "cwd": str(cwd),
            "env": env,
            "shell": False,
        }
        if _is_windows():
            popen_kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(command, **popen_kwargs)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stdout, stderr = self._terminate_after_timeout(process)

        elapsed_ms = max(0, int((time.monotonic() - start) * 1000))
        return CompletedCommand(
            argv=command,
            returncode=process.returncode,
            stdout=_truncate_tail(redact_text(stdout or "", sensitive_values)),
            stderr=_truncate_tail(redact_text(stderr or "", sensitive_values)),
            elapsed_ms=elapsed_ms,
            timed_out=timed_out,
        )

    def _terminate_after_timeout(self, process: subprocess.Popen[str]) -> tuple[str, str]:
        if _is_windows():
            process.send_signal(CTRL_BREAK_EVENT)
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        try:
            return process.communicate(timeout=_TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            if _is_windows():
                process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                return process.communicate(timeout=_TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                return "", "runner_timeout_kill_failed"
