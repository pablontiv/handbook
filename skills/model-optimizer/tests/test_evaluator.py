import json
import os
import tempfile
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from helper.adapters import RuntimeContext
from helper.evaluator import (
    AllowedCommand,
    CapabilityAttestation,
    CommandAudit,
    FixturePolicy,
    PreparedWorkspace,
    RoleEvalRequest,
    RoleEvalResult,
    ToolAudit,
    parse_opencode_eval_events,
    parse_pi_eval_events,
    prepare_workspace_marker,
    run_manifest_commands,
    select_sandbox_backend,
    validate_role_eval_request,
)
from helper.models import ModelRecord, RuntimeKind
from helper.optimizer import AgentContract, PermissionRule, RoleRequirements, RouteKey
from helper.runner import CompletedCommand, CommandRunner
from tests.support import FakeRunner, _command


class RecordingRunner(FakeRunner):
    def __init__(self, responses):
        super().__init__(responses)
        self.env_overlays = []
        self.cwd_values = []
        self.timeout_values = []

    def run(self, argv, timeout, cwd, env_overlay=None, *, stdout_limit=None):
        self.env_overlays.append(dict(env_overlay or {}))
        self.cwd_values.append(Path(cwd))
        self.timeout_values.append(timeout)
        return super().run(argv, timeout, cwd, env_overlay=env_overlay, stdout_limit=stdout_limit)


class EvaluatorContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace_root = self.root / "workspace"
        self.workspace_root.mkdir()
        (self.workspace_root / "allowed").mkdir()
        (self.workspace_root / "src").mkdir()
        self.workspace = PreparedWorkspace(self.workspace_root, "token-123", "docker")
        self.fixture = FixturePolicy(
            fixture_id="mechanical",
            fixture_version="v1",
            manifest_digest="sha256:" + "a" * 64,
            grader_id="grader/mechanical@v1",
            allowed_read_paths=("allowed",),
            allowed_write_paths=("src",),
            allowed_commands=(AllowedCommand("cmd-test", ("python3", "-m", "unittest")),),
            requires_code_execution=True,
            capability_attestations=(),
        )
        prepare_workspace_marker(self.workspace, self.fixture)
        self.route = RouteKey(RuntimeKind.PI, "0.84.2", "nan/qwen3.6", "high")
        self.model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low", "high"), tool_call=True)
        self.agent = AgentContract(
            name="worker",
            description="",
            mode=None,
            model="nan/qwen3.6",
            effort="high",
            tools=("read", "edit", "bash"),
            permissions=(PermissionRule("edit", "src/**", "allow"),),
            mutation_authority="confined",
            body="Implement the requested change.",
            scope="project",
            definition_source="test",
            assignment_source="test",
            inheritance_sources=(),
            apply_target=None,
            digest="sha256:agent",
        )
        self.requirements = RoleRequirements(
            archetype="mechanical",
            required_tools=("read", "edit", "bash"),
            essential_custom_tools=(),
            requires_vision=False,
            requires_mutation=True,
            min_context=None,
            min_output=None,
            allowed_efforts=("high",),
            structured_output=False,
            adversarial_against_family=None,
            priority_order=("quality",),
        )
        self.request = RoleEvalRequest(
            route=self.route,
            model_record=self.model,
            agent=self.agent,
            requirements=self.requirements,
            workspace=self.workspace,
            fixture=self.fixture,
            task="Make tests pass",
            timeout=30,
        )

    def tearDown(self):
        self.temp.cleanup()

    def assert_invalid(self, request, reason):
        with self.assertRaisesRegex(ValueError, reason):
            validate_role_eval_request(request)

    def test_valid_request_passes_and_marker_matches(self):
        validate_role_eval_request(self.request)

    def test_request_validation_rejects_mismatched_route_model_effort_and_authority(self):
        self.assert_invalid(replace(self.request, route=replace(self.route, model="nan/other")), "eval_route_model_mismatch")
        self.assert_invalid(replace(self.request, route=replace(self.route, effort="max")), "eval_unsupported_effort")
        denied = replace(self.agent, mutation_authority="denied")
        self.assert_invalid(replace(self.request, agent=denied), "eval_agent_authority_mismatch")
        missing_tool = replace(self.agent, tools=("read",))
        self.assert_invalid(replace(self.request, agent=missing_tool), "eval_agent_tool_mismatch")

    def test_request_validation_rejects_marker_token_fixture_path_task_timeout_and_subagents(self):
        self.assert_invalid(replace(self.request, workspace=replace(self.workspace, token="wrong")), "eval_workspace_token_mismatch")
        bad_fixture = replace(self.fixture, manifest_digest="sha256:" + "b" * 64)
        self.assert_invalid(replace(self.request, fixture=bad_fixture), "eval_fixture_marker_mismatch")
        escaped = replace(self.fixture, allowed_read_paths=("../outside",))
        self.assert_invalid(replace(self.request, fixture=escaped), "eval_policy_path_escape")
        self.assert_invalid(replace(self.request, task="   "), "eval_empty_task")
        self.assert_invalid(replace(self.request, timeout=0), "eval_invalid_timeout")
        subagent = replace(self.agent, tools=("read", "subagent_worker"))
        self.assert_invalid(replace(self.request, agent=subagent), "eval_subagent_tool_forbidden")

    def test_request_validation_rejects_unstable_commands_and_unproven_custom_tools(self):
        bad_command = replace(self.fixture, allowed_commands=(AllowedCommand("cmd test", ("python3",)),))
        self.assert_invalid(replace(self.request, fixture=bad_command), "eval_unstable_command_id")
        custom_reqs = replace(self.requirements, essential_custom_tools=("custom_safe",))
        self.assert_invalid(replace(self.request, requirements=custom_reqs), "eval_essential_custom_tool_unproven")
        stale = CapabilityAttestation("custom_safe", "probe-1", "PASS", "2000-01-01T00:00:00Z", self.fixture.manifest_digest)
        stale_fixture = replace(self.fixture, capability_attestations=(stale,))
        self.assert_invalid(replace(self.request, requirements=custom_reqs, fixture=stale_fixture), "eval_essential_custom_tool_unproven")
        fresh = CapabilityAttestation(
            "custom_safe", "probe-1", "PASS",
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            self.fixture.manifest_digest,
        )
        validate_role_eval_request(replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(fresh,))))

    def test_parse_pi_eval_events_derives_audit_from_allowed_command_ids_not_boolean(self):
        text = "\n".join((
            json.dumps({"type": "tool", "tool": "read", "path": "allowed/input.txt"}),
            json.dumps({"type": "tool", "tool": "bash", "argv": ["python3", "-m", "unittest"], "exit_code": 0, "elapsed_ms": 22, "sandbox_backend": "docker"}),
            json.dumps({"type": "tool", "tool": "write", "path": "src/out.txt"}),
            json.dumps({"type": "message", "text": "done", "tests_passed": False}),
        ))
        parsed = parse_pi_eval_events(text, self.workspace, self.fixture)
        self.assertEqual(parsed.status, "PASS")
        self.assertEqual(parsed.audit.tool_names, ("bash", "read", "write"))
        self.assertEqual(parsed.audit.command_runs, (CommandAudit("cmd-test", 0, 22, "docker"),))
        self.assertEqual(parsed.audit.changed_paths, ("src/out.txt",))
        self.assertEqual(parsed.final_text, "")

    def test_parse_eval_events_malformed_truncated_missing_or_escape_are_inconclusive(self):
        malformed = parse_pi_eval_events("{not-json", self.workspace, self.fixture)
        self.assertEqual(malformed.status, "INCONCLUSIVE")
        self.assertIn("eval_malformed_audit_stream", malformed.reason_codes)
        missing = parse_pi_eval_events(json.dumps({"type": "message", "text": "all good"}), self.workspace, self.fixture)
        self.assertEqual(missing.status, "INCONCLUSIVE")
        escaped = parse_pi_eval_events(json.dumps({"type": "tool", "tool": "read", "path": "../secret"}), self.workspace, self.fixture)
        self.assertEqual(escaped.audit.outside_workspace_attempts, 1)
        self.assertEqual(escaped.status, "INCONCLUSIVE")
        truncated = parse_pi_eval_events(json.dumps({"type": "tool", "tool": "bash", "argv": ["python3", "-m", "unittest"], "exit_code": 0, "elapsed_ms": 1, "sandbox_backend": "docker", "truncated": True}), self.workspace, self.fixture)
        self.assertEqual(truncated.status, "INCONCLUSIVE")
        self.assertIn("eval_truncated_audit_stream", truncated.reason_codes)

    def test_opencode_parser_preserves_quota_and_permission_reasons(self):
        permission = parse_opencode_eval_events(json.dumps({"type": "permission_ask", "permission": "read"}), self.workspace, self.fixture)
        self.assertEqual(permission.status, "INCONCLUSIVE")
        self.assertIn("eval_permission_ask", permission.reason_codes)
        quota = parse_opencode_eval_events(json.dumps({"type": "error", "error": {"message": "rate limit exceeded"}}), self.workspace, self.fixture)
        self.assertEqual(quota.status, "INCONCLUSIVE")
        self.assertIn("eval_rate_limited", quota.reason_codes)

    def test_sandbox_selection_self_tests_supported_fake_backend_and_scrubbed_manifest_runs(self):
        runner = RecordingRunner((_command("self-test-ok"), _command("tests ok")))
        with patch("helper.evaluator.shutil.which", side_effect=lambda name: f"/fake/{name}" if name == "docker" else None):
            backend = select_sandbox_backend(runner, self.workspace)
        self.assertEqual(backend, "docker")
        audits = run_manifest_commands(runner, self.workspace, self.fixture, backend, timeout=5, env={"SECRET_SENTINEL": "must-not-leak", "PATH": os.environ.get("PATH", "")})
        self.assertEqual(audits, (CommandAudit("cmd-test", 0, 1, "docker"),))
        self.assertEqual(runner.cwd_values[-1], self.workspace_root)
        self.assertNotIn("SECRET_SENTINEL", runner.env_overlays[-1])
        self.assertIn("--network", runner.argv[-1])
        self.assertIn("none", runner.argv[-1])

    def test_sandbox_unavailable_is_fail_closed_for_code_execution_fixture(self):
        runner = RecordingRunner(())
        with patch("helper.evaluator.shutil.which", return_value=None):
            backend = select_sandbox_backend(runner, self.workspace)
        self.assertIsNone(backend)
        result = run_manifest_commands(runner, self.workspace, self.fixture, backend, timeout=5)
        self.assertEqual(result, ())

    def test_real_command_runner_timeout_terminates_process_group_children(self):
        script = self.root / "spawn_child.py"
        marker = self.root / "child-marker"
        script.write_text(
            "import pathlib, subprocess, sys, time\n"
            f"marker = pathlib.Path({str(marker)!r})\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "marker.write_text(str(child.pid), encoding='utf-8')\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        result = CommandRunner().run(("python3", str(script)), timeout=0.2, cwd=self.root, env_overlay={})
        self.assertTrue(result.timed_out)
        deadline = time.monotonic() + 2
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if marker.exists():
            child_pid = int(marker.read_text(encoding="utf-8"))
            time.sleep(0.2)
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                child_alive = False
            else:
                child_alive = True
            self.assertFalse(child_alive, "timeout should terminate child process group")


if __name__ == "__main__":
    unittest.main()
