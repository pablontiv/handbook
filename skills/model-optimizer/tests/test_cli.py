from __future__ import annotations

import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor
from datetime import datetime, timezone
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from threading import Lock
from unittest.mock import patch

from helper.artifacts import inventory_with_digest, load_health, write_inventory
from helper.models import (
    HealthStatus,
    Inventory,
    ModelRecord,
    ProviderReadiness,
    ReadinessStatus,
    RuntimeInfo,
    RuntimeKind,
)
from helper.runner import CompletedCommand
from scripts.model_optimizer import main
from tests.support import FakeRunner, _command, copy_pi_fixtures_to_home, fixture_text, pi_inventory_runner_from_fixtures


SECRET = "sk-test-secret-must-never-leak"


def run_cli(root: Path, runner, found: set[str], *argv: str, environ: dict[str, str] | None = None):
    stdout, stderr = io.StringIO(), io.StringIO()
    which = lambda name: str(root / "bin" / name) if name in found else None
    cli_environ = {"HOME": str(root), "MODEL_OPTIMIZER_TEST_MODE": "1"}
    if environ:
        cli_environ.update(environ)
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(list(argv), runner=runner, environ=cli_environ, which=which)
    return code, stdout.getvalue(), stderr.getvalue()


def write_fixture_inventory(
    root: Path,
    models: tuple[str, ...],
    ready_providers: tuple[str, ...] | None = None,
    runtime: RuntimeKind = RuntimeKind.PI,
    readiness_records: tuple[ProviderReadiness, ...] | None = None,
    runtime_cwd: Path | None = None,
) -> Path:
    records = tuple(ModelRecord(
        exact_id=value,
        provider=value.split("/", 1)[0],
        model=value.split("/", 1)[1],
        variants=("minimal", "high") if runtime is RuntimeKind.OPENCODE else (),
    ) for value in models)
    ready = ready_providers if ready_providers is not None else tuple(sorted({record.provider for record in records}))
    readiness = readiness_records if readiness_records is not None else tuple(
        ProviderReadiness(provider, ReadinessStatus.READY, "test", "auth_ready") for provider in ready
    )
    base = Inventory(
        schema="model-optimizer.inventory/v1",
        created_at="1970-01-01T00:00:00Z",
        runtime=RuntimeInfo(runtime, "test", str(runtime_cwd or root)),
        sources=(), current_assignments=(), catalog_local=records,
        provider_readiness=readiness, exclusions=(), warnings=(), digest="",
    )
    path = root / "inventory.json"
    write_inventory(path, inventory_with_digest(base))
    return path


class ModelAwareRunner:
    def __init__(self, outcomes: dict[str, CompletedCommand]):
        self.outcomes = outcomes
        self.argv: list[tuple[str, ...]] = []
        self.active = 0
        self.max_active = 0
        self.lock = Lock()

    def run(self, argv, timeout, cwd, env_overlay=None):
        command = tuple(argv)
        self.argv.append(command)
        model = command[command.index("--model") + 1]
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            return self.outcomes[model]
        finally:
            with self.lock:
                self.active -= 1


class TimeoutCapturingRunner:
    def __init__(self):
        self.argv: list[tuple[str, ...]] = []
        self.timeouts: list[float] = []

    def run(self, argv, timeout, cwd, env_overlay=None):
        self.argv.append(tuple(argv))
        self.timeouts.append(timeout)
        return CompletedCommand(tuple(argv), 0, "PONG\n", "", 7, False)


class ReloadSemanticsAdapter:
    def __init__(self, inventory: Inventory):
        self.inventory_value = inventory
        self.reload_calls = []

    def inventory(self, context):
        return self.inventory_value

    def reload_semantics(self, context):
        self.reload_calls.append(context)
        return {"reload": "bounded-test-value"}


class CliTests(unittest.TestCase):
    def test_auto_detection_rejects_ambiguous_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            code, _, stderr = run_cli(root, FakeRunner(()), {"pi", "opencode"},
                "inventory", "--runtime", "auto", "--output", str(root / "i.json"))
        self.assertEqual(code, 3)
        self.assertIn("runtime_ambiguous", stderr)

    def test_inventory_writes_versioned_artifact_for_explicit_pi(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = pi_inventory_runner_from_fixtures()
            code, stdout, stderr = run_cli(root, runner, {"pi"},
                "inventory", "--runtime", "pi", "--output", str(root / "i.json"))
            payload = json.loads((root / "i.json").read_text())
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["schema"], "model-optimizer.inventory/v1")
        self.assertTrue(payload["digest"].startswith("sha256:"))
        self.assertIn("models=3", stdout)
        self.assertIn(str(root / "i.json"), stdout)

    def test_check_rejects_model_absent_from_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = write_fixture_inventory(root, ("nan/qwen3.6",))
            code, _, stderr = run_cli(root, FakeRunner(()), {"pi"},
                "check", "--inventory", str(inventory), "--model", "other/model",
                "--timeout", "1", "--output", str(root / "h.json"))
        self.assertEqual(code, 2)
        self.assertIn("live_model_not_catalog_local", stderr)

    def test_auto_detection_prefers_explicit_harness_signal_and_ignores_inherited_opencode_experimental(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = pi_inventory_runner_from_fixtures()
            code, _, stderr = run_cli(root, runner, {"pi", "opencode"},
                "inventory", "--runtime", "auto", "--output", str(root / "i.json"),
                environ={"PI_CODING_AGENT": "1", "OPENCODE_EXPERIMENTAL_FEATURE": "1"})
            payload = json.loads((root / "i.json").read_text())
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["runtime"]["kind"], "pi")
        self.assertEqual(runner.argv[0][0], "pi")

    def test_auto_detection_explicit_pi_and_opencode_signals_are_ambiguous_without_runtime_reads(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = FakeRunner(())
            code, _, stderr = run_cli(root, runner, {"pi"},
                "inventory", "--runtime", "auto", "--output", str(root / "i.json"),
                environ={"PI_SESSION_ID": "pi-1", "OPENCODE_SESSION_ID": "oc-1"})
        self.assertEqual(code, 3)
        self.assertIn("runtime_ambiguous", stderr)
        self.assertEqual(runner.argv, [])
        self.assertFalse((root / "i.json").exists())

    def test_auto_detection_explicit_pi_signal_still_requires_pi_executable_before_runtime_reads(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = FakeRunner(())
            code, _, stderr = run_cli(root, runner, set(),
                "inventory", "--runtime", "auto", "--output", str(root / "i.json"),
                environ={"PI_SESSION_ID": "pi-1"})
        self.assertEqual(code, 3)
        self.assertIn("runtime_missing:pi", stderr)
        self.assertEqual(runner.argv, [])
        self.assertFalse((root / "i.json").exists())

    def test_auto_detection_explicit_opencode_signal_still_requires_opencode_executable_before_runtime_reads(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = FakeRunner(())
            code, _, stderr = run_cli(root, runner, set(),
                "inventory", "--runtime", "auto", "--output", str(root / "i.json"),
                environ={"OPENCODE_SESSION_ID": "oc-1"})
        self.assertEqual(code, 3)
        self.assertIn("runtime_missing:opencode", stderr)
        self.assertEqual(runner.argv, [])
        self.assertFalse((root / "i.json").exists())

    def test_auto_detection_by_executable_requires_exactly_one_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            missing, _, missing_err = run_cli(root, FakeRunner(()), set(),
                "inventory", "--runtime", "auto", "--output", str(root / "missing.json"))
            ambiguous, _, ambiguous_err = run_cli(root, FakeRunner(()), {"pi", "opencode"},
                "inventory", "--runtime", "auto", "--output", str(root / "ambiguous.json"))
        self.assertEqual(missing, 3)
        self.assertIn("runtime_missing", missing_err)
        self.assertEqual(ambiguous, 3)
        self.assertIn("runtime_ambiguous", ambiguous_err)

    def test_explicit_runtime_still_requires_its_executable_and_never_reads_other_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            code, _, stderr = run_cli(root, FakeRunner(()), {"opencode"},
                "inventory", "--runtime", "pi", "--output", str(root / "i.json"))
        self.assertEqual(code, 3)
        self.assertIn("runtime_missing", stderr)

    def test_inventory_sorts_records_writes_partial_and_does_not_print_child_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = FakeRunner((
                _command("test-version\n"),
                _command("provider model context max-out thinking images\nz zeta 1K 1K no no\na alpha 1K 1K yes no\n"),
                CompletedCommand((), 7, "", f"token={SECRET}", 1, False),
                CompletedCommand((), 7, "", f"api_key={SECRET}", 1, False),
            ))
            code, stdout, stderr = run_cli(root, runner, {"pi"},
                "inventory", "--runtime", "pi", "--output", str(root / "i.json"))
            payload = json.loads((root / "i.json").read_text())
            serialized = json.dumps(payload)
        self.assertEqual(code, 4)
        self.assertEqual([record["exact_id"] for record in payload["catalog_local"]], ["a/alpha", "z/zeta"])
        self.assertEqual([item["provider"] for item in payload["provider_readiness"]], ["a", "z"])
        self.assertIn("warnings=", stdout)
        self.assertIn(str(root / "i.json"), stdout)
        self.assertNotIn(SECRET, stdout + stderr + serialized)

    def test_check_requires_ready_provider_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = write_fixture_inventory(root, ("nan/qwen3.6",), ready_providers=())
            code, _, stderr = run_cli(root, FakeRunner(()), {"pi"},
                "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                "--timeout", "1", "--output", str(root / "h.json"))
        self.assertEqual(code, 2)
        self.assertIn("live_provider_not_ready", stderr)

    def test_check_accepts_any_ready_provider_reason_code_but_rejects_not_ready_and_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ready_inventory = write_fixture_inventory(root, ("nan/qwen3.6",), readiness_records=(
                ProviderReadiness("nan", ReadinessStatus.READY, "test", "ready_contract_future_safe"),
            ))
            ready_runner = TimeoutCapturingRunner()
            ready_code, _, ready_stderr = run_cli(root, ready_runner, {"pi"},
                "check", "--inventory", str(ready_inventory), "--model", "nan/qwen3.6",
                "--timeout", "0.25", "--output", str(root / "ready-health.json"))

            for status in (ReadinessStatus.NOT_READY, ReadinessStatus.UNKNOWN):
                inventory = write_fixture_inventory(root, ("nan/qwen3.6",), readiness_records=(
                    ProviderReadiness("nan", status, "test", "bounded_reason"),
                ))
                runner = TimeoutCapturingRunner()
                code, _, stderr = run_cli(root, runner, {"pi"},
                    "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                    "--timeout", "0.25", "--output", str(root / f"{status.value}-health.json"))
                self.assertEqual(code, 2)
                self.assertIn("live_provider_not_ready", stderr)
                self.assertEqual(runner.argv, [])
                self.assertFalse((root / f"{status.value}-health.json").exists())

        self.assertEqual(ready_code, 0, ready_stderr)
        self.assertEqual(len(ready_runner.argv), 1)

    def test_check_timeout_rejects_non_positive_nan_and_infinite_values_before_runner_or_artifact(self):
        bad_values = ("0", "-1", "nan", "inf", "-inf", "Infinity")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = write_fixture_inventory(root, ("nan/qwen3.6",))
            for value in bad_values:
                output = root / f"health-{value.replace('-', 'neg').replace('+', 'pos')}.json"
                runner = TimeoutCapturingRunner()
                timeout_args = (f"--timeout={value}",) if value.startswith("-") else ("--timeout", value)
                code, _, stderr = run_cli(root, runner, {"pi"},
                    "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                    *timeout_args, "--output", str(output))
                self.assertEqual(code, 2, value)
                self.assertIn("usage_timeout_invalid", stderr)
                self.assertEqual(runner.argv, [])
                self.assertFalse(output.exists())

    def test_check_accepts_positive_finite_fractional_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = write_fixture_inventory(root, ("nan/qwen3.6",))
            runner = TimeoutCapturingRunner()
            code, _, stderr = run_cli(root, runner, {"pi"},
                "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                "--timeout", "0.25", "--output", str(root / "h.json"))
            health = load_health(root / "h.json")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(runner.timeouts, [0.25])
        self.assertEqual(health.checks[0].status, HealthStatus.PASS)

    def test_check_health_created_at_is_fresh_rfc3339_utc_not_inventory_timestamp(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = write_fixture_inventory(root, ("nan/qwen3.6",))
            before = datetime.now(timezone.utc)
            code, _, stderr = run_cli(root, TimeoutCapturingRunner(), {"pi"},
                "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                "--timeout", "0.25", "--output", str(root / "h.json"))
            after = datetime.now(timezone.utc)
            health = load_health(root / "h.json")
            created = datetime.fromisoformat(health.created_at.replace("Z", "+00:00"))
        self.assertEqual(code, 0, stderr)
        self.assertNotEqual(health.created_at, "1970-01-01T00:00:00Z")
        self.assertTrue(health.created_at.endswith("Z"))
        self.assertEqual(created.tzinfo, timezone.utc)
        self.assertLessEqual(before, created)
        self.assertLessEqual(created, after)

    def test_inventory_invokes_reload_semantics_without_mutating_schema_v1_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = Inventory.empty(RuntimeInfo(RuntimeKind.PI, "test", str(root)))
            adapter = ReloadSemanticsAdapter(base)
            with patch("scripts.model_optimizer.adapter_for", return_value=adapter):
                code, _, stderr = run_cli(root, FakeRunner(()), {"pi"},
                    "inventory", "--runtime", "pi", "--output", str(root / "i.json"))
            payload = json.loads((root / "i.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(len(adapter.reload_calls), 1)
        self.assertNotIn("reload_semantics", payload)
        self.assertEqual(payload["schema"], "model-optimizer.inventory/v1")

    def test_malformed_inventory_artifacts_return_two_with_stable_bounded_cli_errors(self):
        malformed_values = (
            7,
            [],
            {"schema": "model-optimizer.inventory/v1"},
            {
                "schema": "model-optimizer.inventory/v1",
                "created_at": "1970-01-01T00:00:00Z",
                "runtime": [],
                "sources": [],
                "current_assignments": [],
                "catalog_local": {"attacker": SECRET},
                "provider_readiness": [],
                "exclusions": [],
                "warnings": [],
                "digest": "sha256:not-a-valid-digest",
            },
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for index, value in enumerate(malformed_values):
                inventory = root / f"bad-{index}.json"
                inventory.write_text(json.dumps(value), encoding="utf-8")
                output = root / f"h-{index}.json"
                runner = TimeoutCapturingRunner()
                code, _, stderr = run_cli(root, runner, {"pi"},
                    "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                    "--timeout", "0.25", "--output", str(output))
                self.assertEqual(code, 2)
                self.assertIn("artifact_", stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertNotIn(SECRET, stderr)
                self.assertEqual(runner.argv, [])
                self.assertFalse(output.exists())

    def test_commands_reject_adversarial_output_paths_before_runner_and_preserve_config_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pi_agent = root / ".pi" / "agent"
            pi_agent.mkdir(parents=True)
            pi_config = pi_agent / "settings.json"
            pi_config.write_bytes(b"pi-config")

            opencode_global = root / ".config" / "opencode"
            opencode_global.mkdir(parents=True)
            opencode_config = opencode_global / "opencode.json"
            opencode_config.write_bytes(b"opencode-config")

            project = root / "project"
            project.mkdir()
            project_config = project / "opencode.json"
            project_config.write_bytes(b"project-opencode-config")

            cases = (
                ("pi", pi_agent / "inventory.json", {"pi"}),
                ("opencode", opencode_global / "inventory.json", {"opencode"}),
                ("pi", project_config, {"pi"}),
            )
            before = {path: path.read_bytes() for path in (pi_config, opencode_config, project_config)}
            for runtime, output, found in cases:
                runner = FakeRunner(())
                with patch("scripts.model_optimizer.Path.cwd", return_value=project):
                    code, _, stderr = run_cli(root, runner, found,
                        "inventory", "--runtime", runtime, "--output", str(output))
                self.assertEqual(code, 2)
                self.assertIn("usage_output_forbidden", stderr)
                self.assertEqual(runner.argv, [])
            after = {path: path.read_bytes() for path in before}
        self.assertEqual(after, before)
        self.assertFalse((pi_agent / "inventory.json").exists())
        self.assertFalse((opencode_global / "inventory.json").exists())

    def test_check_rejects_output_equal_to_input_inventory_before_runner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = write_fixture_inventory(root, ("nan/qwen3.6",))
            before = inventory.read_bytes()
            runner = TimeoutCapturingRunner()
            code, _, stderr = run_cli(root, runner, {"pi"},
                "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                "--timeout", "0.25", "--output", str(inventory))
            after = inventory.read_bytes()
        self.assertEqual(code, 2)
        self.assertIn("usage_output_forbidden", stderr)
        self.assertEqual(runner.argv, [])
        self.assertEqual(after, before)

    def test_check_rejects_output_in_inventory_snapshot_runtime_config_surface_before_runner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snapshot_cwd = root / "snapshot" / "project"
            snapshot_cwd.mkdir(parents=True)
            project_config = snapshot_cwd / "opencode.json"
            pi_agent_config = snapshot_cwd / ".pi" / "agent" / "settings.json"
            pi_agent_config.parent.mkdir(parents=True)
            project_config.write_bytes(b"snapshot-project-opencode-config")
            pi_agent_config.write_bytes(b"snapshot-pi-agent-config")
            symlink_output = root / "linked-opencode.json"
            try:
                symlink_output.symlink_to(project_config)
                cases = (project_config, pi_agent_config, symlink_output)
            except OSError:
                cases = (project_config, pi_agent_config)

            before = {path: path.read_bytes() for path in (project_config, pi_agent_config)}
            for output in cases:
                inventory = write_fixture_inventory(root, ("nan/qwen3.6",), runtime_cwd=snapshot_cwd)
                runner = TimeoutCapturingRunner()
                code, _, stderr = run_cli(root, runner, {"pi"},
                    "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                    "--timeout", "0.25", "--output", str(output))
                self.assertEqual(code, 2, output)
                self.assertIn("usage_output_forbidden", stderr)
                self.assertEqual(runner.argv, [], output)
            after = {path: path.read_bytes() for path in before}
        self.assertEqual(after, before)

    def test_check_rejects_invalid_utf8_inventory_with_stable_artifact_error_before_runner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = root / "bad-encoding.json"
            output = root / "h.json"
            inventory.write_bytes(b'\xff\xfe{"schema":"model-optimizer.inventory/v1","secret":"raw-secret"}')
            runner = TimeoutCapturingRunner()
            code, _, stderr = run_cli(root, runner, {"pi"},
                "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                "--timeout", "0.25", "--output", str(output))
        self.assertEqual(code, 2)
        self.assertIn("artifact_invalid_encoding", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertNotIn("utf-8", stderr)
        self.assertNotIn("codec", stderr)
        self.assertNotIn("raw-secret", stderr)
        self.assertEqual(runner.argv, [])
        self.assertFalse(output.exists())

    def test_check_uses_injected_which_for_inventory_runtime_before_launching_runner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = write_fixture_inventory(root, ("nan/qwen3.6",), runtime=RuntimeKind.OPENCODE)
            runner = TimeoutCapturingRunner()
            code, _, stderr = run_cli(root, runner, set(),
                "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                "--timeout", "0.25", "--output", str(root / "h.json"))
        self.assertEqual(code, 3)
        self.assertIn("runtime_missing:opencode", stderr)
        self.assertEqual(runner.argv, [])
        self.assertFalse((root / "h.json").exists())

    def test_check_deduplicates_preserves_request_order_binds_digest_and_returns_five_for_failures(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = write_fixture_inventory(root, ("nan/a", "nan/b", "nan/c"))
            runner = ModelAwareRunner({
                "nan/a": CompletedCommand((), 0, "PONG\n", "", 11, False),
                "nan/b": CompletedCommand((), 0, "NOPE\n", "", 22, False),
                "nan/c": CompletedCommand((), None, "", "", 33, True),
            })
            executor_workers = []
            def executor_factory(*, max_workers):
                executor_workers.append(max_workers)
                return RealThreadPoolExecutor(max_workers=max_workers)
            with patch("scripts.model_optimizer.ThreadPoolExecutor", side_effect=executor_factory):
                code, stdout, stderr = run_cli(root, runner, {"pi"},
                    "check", "--inventory", str(inventory), "--model", "nan/b", "--model", "nan/a",
                    "--model", "nan/b", "--model", "nan/c", "--timeout", "1", "--output", str(root / "h.json"))
            health = load_health(root / "h.json")
            loaded_inventory = json.loads(Path(inventory).read_text())
        self.assertEqual(code, 5, stderr)
        self.assertIn("planned_checks=3", stdout)
        self.assertEqual([check.model for check in health.checks], ["nan/b", "nan/a", "nan/c"])
        self.assertEqual([check.status for check in health.checks], [HealthStatus.FAIL, HealthStatus.PASS, HealthStatus.HANG])
        self.assertEqual(health.inventory_digest, loaded_inventory["digest"])
        self.assertEqual(executor_workers, [2])
        self.assertLessEqual(runner.max_active, 2)
        self.assertCountEqual([argv[argv.index("--model") + 1] for argv in runner.argv], ["nan/b", "nan/a", "nan/c"])

    def test_check_redacts_fake_child_stderr_from_artifact_and_stderr(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = write_fixture_inventory(root, ("nan/qwen3.6",))
            runner = FakeRunner((CompletedCommand((), 7, "", f"Authorization: Bearer {SECRET}", 1, False),))
            code, _, stderr = run_cli(root, runner, {"pi"},
                "check", "--inventory", str(inventory), "--model", "nan/qwen3.6",
                "--timeout", "1", "--output", str(root / "h.json"))
            payload = (root / "h.json").read_text()
        self.assertEqual(code, 5)
        self.assertNotIn(SECRET, stderr + payload)
        self.assertIn("[REDACTED]", payload)

    def test_commands_do_not_mutate_pi_or_opencode_configs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            copy_pi_fixtures_to_home(root)
            pi_paths = sorted((root / ".pi" / "agent").glob("*.json"))
            opencode_path = root / ".config" / "opencode" / "opencode.json"
            opencode_path.parent.mkdir(parents=True)
            opencode_path.write_text(fixture_text("opencode/opencode.json"), encoding="utf-8")
            before = {path: path.read_bytes() for path in (*pi_paths, opencode_path)}

            pi_inventory = root / "pi-inventory.json"
            pi_inventory_code, _, pi_inventory_stderr = run_cli(root, pi_inventory_runner_from_fixtures(), {"pi"},
                "inventory", "--runtime", "pi", "--output", str(pi_inventory))
            pi_check_code, _, pi_check_stderr = run_cli(root, FakeRunner((_command("PONG\n"),)), {"pi"},
                "check", "--inventory", str(pi_inventory), "--model", "nan-builders/qwen3.6",
                "--timeout", "1", "--output", str(root / "pi-health.json"))

            opencode_inventory = root / "opencode-inventory.json"
            opencode_inventory_code, _, opencode_inventory_stderr = run_cli(root, FakeRunner((
                _command("opencode 1.2.3\n"),
                _command(fixture_text("opencode/models-verbose.txt")),
                _command(fixture_text("opencode/auth-list.txt")),
            )), {"opencode"}, "inventory", "--runtime", "opencode", "--output", str(opencode_inventory))
            with patch("helper.adapters.opencode.secrets.token_hex", return_value="a" * 32):
                opencode_check_code, _, opencode_check_stderr = run_cli(root, FakeRunner((
                    _command('{"agent":{"model-optimizer-probe-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa":{"permission":"deny"}}}\n'),
                    _command('{"type":"text","part":{"text":"PONG"}}\n'),
                )), {"opencode"}, "check", "--inventory", str(opencode_inventory), "--model", "openai/gpt-5.6-terra",
                    "--timeout", "1", "--output", str(root / "opencode-health.json"))
            after = {path: path.read_bytes() for path in before}
        self.assertEqual(pi_inventory_code, 0, pi_inventory_stderr)
        self.assertEqual(pi_check_code, 0, pi_check_stderr)
        self.assertEqual(opencode_inventory_code, 0, opencode_inventory_stderr)
        self.assertEqual(opencode_check_code, 0, opencode_check_stderr)
        self.assertEqual(after, before)

    def test_main_rejects_injected_test_overrides_without_test_mode_before_runner_or_artifact_access(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = FakeRunner(())
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("scripts.model_optimizer.reject_runtime_config_output") as reject_output:
                with patch("scripts.model_optimizer.load_inventory", side_effect=RuntimeError("runtime_load_inventory_called")) as load_inventory:
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        code = main([
                            "check", "--inventory", str(root / "inventory.json"),
                            "--model", "nan/qwen3.6", "--timeout", "1", "--output", str(root / "h.json"),
                        ], runner=runner, environ={"HOME": str(root)}, which=lambda _: str(root / "bin" / "pi"))
        self.assertEqual(code, 2)
        self.assertIn("usage_error:test_overrides_require_test_mode", stderr.getvalue())
        self.assertEqual(runner.argv, [])
        reject_output.assert_not_called()
        load_inventory.assert_not_called()
        self.assertFalse((root / "h.json").exists())

    def test_main_help_paths_allow_direct_execution_without_test_overrides(self):
        top_stdout, top_stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(top_stdout), redirect_stderr(top_stderr):
            top_code = main(["--help"])

        inventory_stdout, inventory_stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(inventory_stdout), redirect_stderr(inventory_stderr):
            inventory_code = main(["inventory", "--help"])

        self.assertEqual(top_code, 0)
        self.assertEqual(inventory_code, 0)
        self.assertIn("usage:", top_stdout.getvalue())
        self.assertIn("usage:", inventory_stdout.getvalue())
        self.assertEqual(top_stderr.getvalue(), "")
        self.assertEqual(inventory_stderr.getvalue(), "")

    def test_usage_and_schema_errors_return_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad = root / "bad.json"
            bad.write_text('{"schema":"wrong"}\n', encoding="utf-8")
            usage_code, _, usage_stderr = run_cli(root, FakeRunner(()), {"pi"}, "inventory")
            schema_code, _, schema_stderr = run_cli(root, FakeRunner(()), {"pi"},
                "check", "--inventory", str(bad), "--model", "nan/qwen3.6",
                "--timeout", "1", "--output", str(root / "h.json"))
        self.assertEqual(usage_code, 2)
        self.assertEqual(schema_code, 2)
        self.assertNotIn("Traceback", usage_stderr + schema_stderr)
        self.assertIn("artifact_", schema_stderr)


if __name__ == "__main__":
    unittest.main()
