from __future__ import annotations

import unittest
from pathlib import Path

from helper.lifecycle import CommandProcessProbe, LifecycleController
from helper.models import CompletedCommand, LifecycleAction, PlatformProfile, ProcessSnapshot, RuntimeContext


def mac_context() -> RuntimeContext:
    return RuntimeContext(PlatformProfile("macos", Path("/tmp/home"), {}))


def linux_context() -> RuntimeContext:
    return RuntimeContext(PlatformProfile("linux", Path("/tmp/home"), {}))


def windows_context() -> RuntimeContext:
    return RuntimeContext(PlatformProfile("windows", Path("C:/Users/example"), {}))


def codex_action(**details: object) -> LifecycleAction:
    merged = {"process_name": "Codex", "bundle_id": "com.openai.codex", **details}
    return LifecycleAction(candidate_id="codex-config", client="codex", action="stop", target="Codex", reason="quiesce before edit", details=merged)


class CommandProbeRunner:
    def __init__(self, *, platform: str, missing_metadata: bool = False) -> None:
        self.platform = platform
        self.missing_metadata = missing_metadata
        self.running = True
        self.commands: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], timeout: float) -> CompletedCommand:
        self.commands.append(argv)
        if self.platform in {"macos", "linux"} and argv == ("pgrep", "-x", "Codex"):
            return CompletedCommand(argv=argv, returncode=0, stdout="123\n")
        if self.platform == "macos" and argv[:3] == ("ps", "-p", "123"):
            stdout = "123\n" if self.missing_metadata else "123 /Applications/Codex.app/Contents/MacOS/Codex /Applications/Codex.app/Contents/MacOS/Codex\n"
            return CompletedCommand(argv=argv, returncode=0, stdout=stdout)
        if self.platform == "windows" and argv[:2] == ("tasklist", "/FI"):
            stdout = "" if not self.running else '"codex.exe","123","Console","1","10,000 K"\n'
            return CompletedCommand(argv=argv, returncode=0, stdout=stdout)
        if self.platform == "windows" and argv[:3] == ("powershell", "-NoProfile", "-Command"):
            stdout = "{}" if self.missing_metadata else '{"ProcessId":123,"ExecutablePath":"C:/Program Files/Codex/codex.exe","CommandLine":"\\\"C:/Program Files/Codex/codex.exe\\\" --foreground"}'
            return CompletedCommand(argv=argv, returncode=0, stdout=stdout)
        if argv == ("taskkill", "/PID", "123"):
            self.running = False
            return CompletedCommand(argv=argv, returncode=0)
        if argv == ("C:/Program Files/Codex/codex.exe", "--foreground"):
            return CompletedCommand(argv=argv, returncode=0)
        return CompletedCommand(argv=argv, returncode=0)


class FakeRunner:
    def __init__(
        self,
        *,
        running: bool = True,
        stoppable: bool = True,
        platform: str = "macos",
        ambiguous: bool = False,
        changed_identity: bool = False,
        exits: bool = True,
        restart_returncode: int = 0,
    ) -> None:
        self.running = running
        self.stoppable = stoppable
        self.platform = platform
        self.ambiguous = ambiguous
        self.changed_identity = changed_identity
        self.exits = exits
        self.restart_returncode = restart_returncode
        self.commands: list[tuple[str, ...]] = []

    def inspect_processes(self, action: LifecycleAction, context: RuntimeContext) -> tuple[ProcessSnapshot, ...]:
        if not self.running:
            return ()
        first = self._snapshot(action, context, pid=123)
        if self.ambiguous:
            return (first, self._snapshot(action, context, pid=456))
        return (first,)

    def graceful_stop_available(self, snapshot: ProcessSnapshot) -> bool:
        return self.stoppable

    def is_same_process(self, snapshot: ProcessSnapshot) -> bool:
        return not self.changed_identity

    def is_running(self, snapshot: ProcessSnapshot) -> bool:
        return self.running

    def run(self, argv: tuple[str, ...], timeout: float):
        self.commands.append(argv)
        if argv[:2] in {("open", "-b"), ("/usr/bin/open", "-b")} or argv == ("/usr/bin/codex", "--foreground") or argv == ("C:/Program Files/Codex/codex.exe", "--foreground"):
            return type("Completed", (), {"argv": argv, "returncode": self.restart_returncode, "stdout": "", "stderr": ""})()
        if argv and argv[0] in {"osascript", "kill", "taskkill"} and self.exits:
            self.running = False
        return type("Completed", (), {"argv": argv, "returncode": 0, "stdout": "", "stderr": ""})()

    def _snapshot(self, action: LifecycleAction, context: RuntimeContext, *, pid: int) -> ProcessSnapshot:
        if self.platform == "linux":
            return ProcessSnapshot(
                action=action,
                platform="linux",
                running=True,
                pid=pid,
                process_name="codex",
                executable="/usr/bin/codex",
                argv=("/usr/bin/codex", "--foreground"),
                identity=f"linux:{pid}:/usr/bin/codex",
            )
        if self.platform == "windows":
            return ProcessSnapshot(
                action=action,
                platform="windows",
                running=True,
                pid=pid,
                process_name="codex.exe",
                executable="C:/Program Files/Codex/codex.exe",
                argv=("C:/Program Files/Codex/codex.exe", "--foreground"),
                identity=f"windows:{pid}:C:/Program Files/Codex/codex.exe",
            )
        return ProcessSnapshot(
            action=action,
            platform="macos",
            running=True,
            pid=pid,
            process_name="Codex",
            executable="/Applications/Codex.app/Contents/MacOS/Codex",
            argv=("/Applications/Codex.app/Contents/MacOS/Codex",),
            bundle_id=action.details.get("bundle_id") if isinstance(action.details.get("bundle_id"), str) else None,
            identity=f"macos:{pid}:/Applications/Codex.app/Contents/MacOS/Codex",
        )


class LifecycleTests(unittest.TestCase):
    def test_preflight_rejects_running_client_without_graceful_stop(self):
        controller = LifecycleController(FakeRunner(running=True, stoppable=False))
        with self.assertRaisesRegex(ValueError, "preflight_lifecycle_unavailable"):
            controller.preflight((codex_action(),), windows_context())

    def test_restart_only_applies_to_clients_stopped_by_transaction(self):
        controller = LifecycleController(FakeRunner(running=True, stoppable=True))
        snapshot = controller.preflight((codex_action(),), mac_context())[0]
        controller.stop(snapshot)
        controller.restart(snapshot)
        self.assertEqual(controller.runner.commands[-1], ("open", "-b", "com.openai.codex"))

    def test_mac_uses_graceful_applescript_quit_and_bundle_restart(self):
        runner = FakeRunner(platform="macos")
        controller = LifecycleController(runner)
        snapshot = controller.preflight((codex_action(),), mac_context())[0]

        controller.stop(snapshot)
        controller.restart(snapshot)

        self.assertIn(("osascript", "-e", 'tell application id "com.openai.codex" to quit'), runner.commands)
        self.assertEqual(runner.commands[-1], ("open", "-b", "com.openai.codex"))

    def test_linux_uses_sigterm_only_and_recorded_executable_argv_restart(self):
        runner = FakeRunner(platform="linux")
        controller = LifecycleController(runner)
        snapshot = controller.preflight((codex_action(process_name="codex"),), linux_context())[0]

        controller.stop(snapshot)
        controller.restart(snapshot)

        self.assertIn(("kill", "-TERM", "123"), runner.commands)
        self.assertNotIn(("kill", "-KILL", "123"), runner.commands)
        self.assertEqual(runner.commands[-1], ("/usr/bin/codex", "--foreground"))

    def test_windows_uses_taskkill_without_force_and_recorded_executable_argv_restart(self):
        runner = FakeRunner(platform="windows")
        controller = LifecycleController(runner)
        snapshot = controller.preflight((codex_action(process_name="codex.exe"),), windows_context())[0]

        controller.stop(snapshot)
        controller.restart(snapshot)

        self.assertIn(("taskkill", "/PID", "123"), runner.commands)
        self.assertNotIn(("taskkill", "/F", "/PID", "123"), runner.commands)
        self.assertEqual(runner.commands[-1], ("C:/Program Files/Codex/codex.exe", "--foreground"))

    def test_preflight_rejects_ambiguous_running_matches(self):
        controller = LifecycleController(FakeRunner(ambiguous=True))
        with self.assertRaisesRegex(ValueError, "preflight_lifecycle_ambiguous"):
            controller.preflight((codex_action(),), mac_context())

    def test_preflight_rejects_running_client_missing_restart_metadata(self):
        controller = LifecycleController(FakeRunner(platform="macos"))
        action = LifecycleAction(candidate_id="codex-config", client="codex", action="stop", target="Codex", details={"process_name": "Codex"})
        with self.assertRaisesRegex(ValueError, "preflight_lifecycle_missing_restart_metadata"):
            controller.preflight((action,), mac_context())

    def test_stop_rejects_changed_pid_identity(self):
        controller = LifecycleController(FakeRunner(changed_identity=True))
        snapshot = controller.preflight((codex_action(),), mac_context())[0]
        with self.assertRaisesRegex(ValueError, "lifecycle_pid_identity_changed"):
            controller.stop(snapshot)

    def test_stop_rejects_unconfirmed_exit_without_force_fallback(self):
        runner = FakeRunner(exits=False)
        controller = LifecycleController(runner, stop_timeout=0)
        snapshot = controller.preflight((codex_action(),), mac_context())[0]
        with self.assertRaisesRegex(ValueError, "lifecycle_exit_unconfirmed"):
            controller.stop(snapshot)
        self.assertNotIn(("kill", "-KILL", "123"), runner.commands)

    def test_command_probe_rejects_pid_match_with_missing_metadata(self):
        runner = CommandProbeRunner(platform="macos", missing_metadata=True)
        controller = LifecycleController(runner, process_probe=CommandProcessProbe(runner))

        with self.assertRaisesRegex(ValueError, "preflight_lifecycle_missing_process_metadata"):
            controller.preflight((codex_action(),), mac_context())

    def test_windows_command_probe_restarts_recorded_executable_argv(self):
        runner = CommandProbeRunner(platform="windows")
        action = codex_action(process_name="codex.exe")
        controller = LifecycleController(runner, process_probe=CommandProcessProbe(runner))
        snapshot = controller.preflight((action,), windows_context())[0]

        controller.stop(snapshot)
        controller.restart(snapshot)

        self.assertIn(("taskkill", "/PID", "123"), runner.commands)
        self.assertNotIn(("taskkill", "/F", "/PID", "123"), runner.commands)
        self.assertEqual(runner.commands[-1], ("C:/Program Files/Codex/codex.exe", "--foreground"))


if __name__ == "__main__":
    unittest.main()
