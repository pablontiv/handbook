import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helper.runner import CommandRunner, redact_text


class RunnerTests(unittest.TestCase):
    def test_runner_uses_argument_array_and_captures_elapsed_time(self):
        result = CommandRunner().run(
            (sys.executable, "-c", "print('PONG')"),
            timeout=5,
            cwd=Path.cwd(),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "PONG")
        self.assertFalse(result.timed_out)
        self.assertGreaterEqual(result.elapsed_ms, 0)
        self.assertEqual(result.argv[:2], (sys.executable, "-c"))

    def test_timeout_returns_bounded_hang_result(self):
        result = CommandRunner().run(
            (sys.executable, "-c", "import time; time.sleep(30)"),
            timeout=0.1,
            cwd=Path.cwd(),
        )
        self.assertTrue(result.timed_out)
        self.assertLess(len(result.stderr), 8193)

    def test_redaction_removes_tokens_and_authorization_values(self):
        text = "Authorization: Bearer secret-token api_key=sk-abc cookie=session-xyz"
        redacted = redact_text(text, ("secret-token", "sk-abc", "session-xyz"))
        self.assertNotIn("secret-token", redacted)
        self.assertNotIn("sk-abc", redacted)
        self.assertNotIn("session-xyz", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_runner_rejects_empty_or_nul_arguments(self):
        runner = CommandRunner()
        with self.assertRaisesRegex(ValueError, "runner_invalid_argv"):
            runner.run((), timeout=1, cwd=Path.cwd())
        with self.assertRaisesRegex(ValueError, "runner_invalid_argv"):
            runner.run(("echo", "bad\x00arg"), timeout=1, cwd=Path.cwd())
        with self.assertRaisesRegex(ValueError, "runner_invalid_argv"):
            runner.run("echo PONG", timeout=1, cwd=Path.cwd())

    def test_nonzero_exit_returns_captured_streams(self):
        result = CommandRunner().run(
            (
                sys.executable,
                "-c",
                "import sys; print('OUT'); print('ERR', file=sys.stderr); raise SystemExit(7)",
            ),
            timeout=5,
            cwd=Path.cwd(),
        )
        self.assertEqual(result.returncode, 7)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.stdout.strip(), "OUT")
        self.assertEqual(result.stderr.strip(), "ERR")

    def test_unicode_output_and_explicit_cwd_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            result = CommandRunner().run(
                (
                    sys.executable,
                    "-c",
                    "import os; print('snowman=☃ café'); print(os.getcwd())",
                ),
                timeout=5,
                cwd=temp_root,
            )
        lines = result.stdout.splitlines()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(lines[0], "snowman=☃ café")
        self.assertEqual(Path(lines[1]).resolve(), temp_root.resolve())

    def test_output_truncation_keeps_tail_of_both_streams(self):
        result = CommandRunner().run(
            (
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "sys.stdout.write('OUT_HEAD' + 'o' * 9000 + 'OUT_TAIL'); "
                    "sys.stderr.write('ERR_HEAD' + 'e' * 9000 + 'ERR_TAIL')"
                ),
            ),
            timeout=5,
            cwd=Path.cwd(),
        )
        self.assertLessEqual(len(result.stdout), 8192)
        self.assertLessEqual(len(result.stderr), 8192)
        self.assertNotIn("OUT_HEAD", result.stdout)
        self.assertNotIn("ERR_HEAD", result.stderr)
        self.assertTrue(result.stdout.endswith("OUT_TAIL"))
        self.assertTrue(result.stderr.endswith("ERR_TAIL"))

    def test_sensitive_inherited_and_overlay_env_are_redacted_from_both_streams(self):
        inherited_key = "RUNNER_TEST_TOKEN"
        inherited_secret = "TASK3_INHERITED_TOKEN_SENTINEL"
        overlay_secret = "TASK3_OVERLAY_PASSWORD_SENTINEL"
        public_value = "TASK3_PUBLIC_SENTINEL"
        original = os.environ.get(inherited_key)
        os.environ[inherited_key] = inherited_secret
        try:
            result = CommandRunner().run(
                (
                    sys.executable,
                    "-c",
                    (
                        "import os, sys; "
                        "values = [os.environ['RUNNER_TEST_TOKEN'], "
                        "os.environ['RUNNER_TEST_PASSWORD'], os.environ['RUNNER_TEST_PUBLIC']]; "
                        "print('STDOUT:' + '|'.join(values)); "
                        "print('STDERR:' + '|'.join(values), file=sys.stderr)"
                    ),
                ),
                timeout=5,
                cwd=Path.cwd(),
                env_overlay={
                    "RUNNER_TEST_PASSWORD": overlay_secret,
                    "RUNNER_TEST_PUBLIC": public_value,
                },
            )
        finally:
            if original is None:
                os.environ.pop(inherited_key, None)
            else:
                os.environ[inherited_key] = original

        self.assertEqual(result.returncode, 0)
        for stream in (result.stdout, result.stderr):
            self.assertNotIn(inherited_secret, stream)
            self.assertNotIn(overlay_secret, stream)
            self.assertIn(public_value, stream)
            self.assertIn("[REDACTED]", stream)
        self.assertEqual(
            set(result.__dict__),
            {"argv", "returncode", "stdout", "stderr", "elapsed_ms", "timed_out"},
        )

    @unittest.skipIf(os.name == "nt", "POSIX process-group cleanup is validated on POSIX hosts only")
    def test_timeout_kills_child_process_group_without_leaving_active_child(self):
        with tempfile.TemporaryDirectory() as td:
            heartbeat = Path(td) / "heartbeat.txt"
            script = (
                "import pathlib, subprocess, sys, time; "
                "heartbeat = pathlib.Path(sys.argv[1]); "
                "child_code = "
                "'import pathlib, sys, time\\n' "
                "+ 'path = pathlib.Path(sys.argv[1])\\n' "
                "+ 'i = 0\\n' "
                "+ 'while True:\\n' "
                "+ '    path.write_text(str(i), encoding=\"utf-8\")\\n' "
                "+ '    i += 1\\n' "
                "+ '    time.sleep(0.05)\\n'; "
                "subprocess.Popen([sys.executable, '-c', child_code, str(heartbeat)]); "
                "time.sleep(30)"
            )
            result = CommandRunner().run(
                (sys.executable, "-c", script, str(heartbeat)),
                timeout=0.4,
                cwd=Path.cwd(),
            )
            first = heartbeat.read_text(encoding="utf-8") if heartbeat.exists() else ""
            time.sleep(0.25)
            second = heartbeat.read_text(encoding="utf-8") if heartbeat.exists() else ""
        self.assertTrue(result.timed_out)
        self.assertNotEqual(first, "")
        self.assertEqual(first, second)

    def test_windows_timeout_uses_process_group_break_then_kill_with_mocks(self):
        class FakeProcess:
            pid = 12345
            returncode = None

            def __init__(self):
                self.signals = []
                self.killed = False
                self.communicate_calls = 0

            def communicate(self, timeout=None):
                self.communicate_calls += 1
                if self.communicate_calls <= 2:
                    raise subprocess.TimeoutExpired(cmd=("tool",), timeout=timeout)
                self.returncode = -9
                return ("windows stdout", "windows stderr")

            def send_signal(self, sig):
                self.signals.append(sig)

            def kill(self):
                self.killed = True

        fake_process = FakeProcess()
        with mock.patch("helper.runner._is_windows", return_value=True), \
                mock.patch("helper.runner.subprocess.Popen", return_value=fake_process) as popen:
            result = CommandRunner().run(("tool", "arg"), timeout=0.1, cwd=Path.cwd())

        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, -9)
        self.assertEqual(fake_process.signals, [mock.ANY])
        self.assertTrue(fake_process.killed)
        kwargs = popen.call_args.kwargs
        self.assertFalse(kwargs["shell"])
        self.assertNotIn("start_new_session", kwargs)
        self.assertEqual(kwargs["creationflags"], getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))


if __name__ == "__main__":
    unittest.main()
