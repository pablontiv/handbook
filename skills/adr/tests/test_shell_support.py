from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

shell_support = importlib.import_module("tests.shell_support")


class ShellSupportTests(unittest.TestCase):
    def test_windows_resolution_prefers_git_bash_over_wsl_stub(self) -> None:
        resolver = getattr(shell_support, "resolve_bash", None)
        if not callable(resolver):
            self.fail("resolve_bash must select the test shell")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            git = root / "Git/cmd/git.exe"
            git_bash = root / "Git/bin/bash.exe"
            wsl_stub = root / "Windows/System32/bash.exe"
            for executable in (git, git_bash, wsl_stub):
                executable.parent.mkdir(parents=True, exist_ok=True)
                executable.touch()

            resolved = resolver(
                os_name="nt",
                which=lambda command: {"git": str(git), "bash": str(wsl_stub)}.get(
                    command
                ),
            )

            self.assertEqual(resolved, str(git_bash))

    def test_windows_resolution_rejects_wsl_stub_without_git_bash(self) -> None:
        resolver = getattr(shell_support, "resolve_bash", None)
        if not callable(resolver):
            self.fail("resolve_bash must select the test shell")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            git = root / "Git/cmd/git.exe"
            wsl_stub = root / "Windows/System32/bash.exe"
            for executable in (git, wsl_stub):
                executable.parent.mkdir(parents=True, exist_ok=True)
                executable.touch()

            with self.assertRaisesRegex(RuntimeError, "Git Bash"):
                resolver(
                    os_name="nt",
                    which=lambda command: {
                        "git": str(git),
                        "bash": str(wsl_stub),
                    }.get(command),
                )


if __name__ == "__main__":
    unittest.main()
