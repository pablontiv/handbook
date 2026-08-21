from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from helper.runner import CompletedCommand

FIXTURES = Path(__file__).parent / "fixtures"


def assert_test_path(path: Path, temp_root: Path) -> None:
    if not path.resolve().is_relative_to(temp_root.resolve()):
        raise AssertionError(f"test target escaped temporary root: {path}")


def fixture_text(relative: str) -> str:
    return (FIXTURES / relative).read_text(encoding="utf-8")


class FakeRunner:
    def __init__(self, responses: tuple[CompletedCommand, ...]):
        self.responses = deque(responses)
        self.argv: list[tuple[str, ...]] = []
        self.stdout_limits: list[int | None] = []
        self.env_overlays: list[dict[str, str]] = []
        self.env_replacements: list[dict[str, str] | None] = []
        self.cwd_values: list[Path] = []
        self.stdin_payloads: list[str | None] = []

    @classmethod
    def stdout(cls, text: str, returncode: int = 0) -> "FakeRunner":
        return cls((CompletedCommand(
            argv=(), returncode=returncode, stdout=text, stderr="",
            elapsed_ms=1, timed_out=False,
        ),))

    def run(self, argv, timeout, cwd, env_overlay=None, *, stdout_limit=None, env_replacement=None, stdin_text=None):
        self.argv.append(tuple(argv))
        self.stdout_limits.append(stdout_limit)
        self.env_overlays.append(dict(env_overlay or {}))
        self.env_replacements.append(dict(env_replacement) if env_replacement is not None else None)
        self.cwd_values.append(Path(cwd))
        self.stdin_payloads.append(stdin_text)
        if not self.responses:
            raise AssertionError(f"unexpected command: {tuple(argv)!r}")
        result = self.responses.popleft()
        return CompletedCommand(
            argv=tuple(argv), returncode=result.returncode,
            stdout=result.stdout, stderr=result.stderr,
            elapsed_ms=result.elapsed_ms, timed_out=result.timed_out,
            stdout_truncated=result.stdout_truncated,
            stderr_truncated=result.stderr_truncated,
            stdout_decode_replaced=result.stdout_decode_replaced,
            stderr_decode_replaced=result.stderr_decode_replaced,
        )


def _command(stdout: str, returncode: int = 0) -> CompletedCommand:
    return CompletedCommand(
        argv=(), returncode=returncode, stdout=stdout, stderr="",
        elapsed_ms=1, timed_out=False,
    )


def pi_inventory_runner_from_fixtures() -> FakeRunner:
    readiness = tuple(_command(json.dumps({
        "status": "ready", "provider": provider, "authType": "test",
    })) for provider in ("github-copilot", "nan-builders", "openai-codex"))
    return FakeRunner((
        _command("0.84.2\n"),
        _command(fixture_text("pi/list-models.txt")),
        *readiness,
    ))


def copy_pi_fixtures_to_home(root: Path) -> None:
    agent_dir = root / ".pi" / "agent"
    assert_test_path(agent_dir, root)
    agent_dir.mkdir(parents=True)
    for name in ("settings.json", "models-store.json", "subagents.json"):
        target = agent_dir / name
        assert_test_path(target, root)
        target.write_text(fixture_text(f"pi/{name}"), encoding="utf-8")
