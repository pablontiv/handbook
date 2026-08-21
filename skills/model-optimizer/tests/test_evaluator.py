import json
import os
import tempfile
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from helper.evaluator import (
    AllowedCommand,
    CapabilityAttestation,
    ChangedPathsResult,
    CommandAudit,
    FixturePolicy,
    PreparedWorkspace,
    RoleEvalRequest,
    SandboxAttestation,
    RoleEvalResult,
    ToolAudit,
    canonical_fixture_digest,
    capability_probe_digest,
    changed_paths_from_git_status,
    essential_eval_selection_status,
    parse_opencode_eval_events,
    parse_pi_eval_events,
    prepare_workspace_marker,
    run_manifest_commands,
    sandbox_attestation_digest,
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
        self.env_replacements = []
        self.cwd_values = []
        self.timeout_values = []

    def run(self, argv, timeout, cwd, env_overlay=None, *, stdout_limit=None, env_replacement=None):
        self.env_overlays.append(dict(env_overlay or {}))
        self.env_replacements.append(dict(env_replacement) if env_replacement is not None else None)
        self.cwd_values.append(Path(cwd))
        self.timeout_values.append(timeout)
        return super().run(argv, timeout, cwd, env_overlay=env_overlay, stdout_limit=stdout_limit, env_replacement=env_replacement)


class EvaluatorContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace_root = self.root / "workspace"
        self.workspace_root.mkdir()
        (self.workspace_root / "allowed").mkdir()
        (self.workspace_root / "src").mkdir()
        probe_results = (
            "workspace_write:PASS:sha256:" + "1" * 64,
            "outside_read_denied:PASS:sha256:" + "2" * 64,
            "secret_env_denied:PASS:sha256:" + "3" * 64,
            "network_denied:PASS:sha256:" + "4" * 64,
        )
        executable_identity = "docker:/fake/docker:1:2:3"
        self.workspace = PreparedWorkspace(self.workspace_root, "token-123", SandboxAttestation(
            backend="docker",
            workspace_root=str(self.workspace_root.resolve()),
            workspace_token="token-123",
            profile_digest=sandbox_attestation_digest("docker", self.workspace_root, "token-123", executable_identity, probe_results),
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            self_tests=("workspace_write:PASS", "outside_read_denied:PASS", "secret_env_denied:PASS", "network_denied:PASS"),
            probe_results=probe_results,
            executable_identity=executable_identity,
        ))
        fixture_base = FixturePolicy(
            fixture_id="mechanical",
            fixture_version="v1",
            manifest_digest="",
            grader_id="grader/mechanical@v1",
            allowed_read_paths=("allowed",),
            allowed_write_paths=("src",),
            allowed_commands=(AllowedCommand("cmd-test", ("python3", "-m", "unittest")),),
            requires_code_execution=True,
            capability_attestations=(),
        )
        self.fixture = replace(fixture_base, manifest_digest=canonical_fixture_digest(fixture_base))
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
        fixture_changed = replace(self.fixture, fixture_version="v2", manifest_digest="")
        bad_fixture = replace(fixture_changed, manifest_digest=canonical_fixture_digest(fixture_changed))
        self.assert_invalid(replace(self.request, fixture=bad_fixture), "eval_fixture_marker_mismatch")
        digest_tampered = replace(self.fixture, manifest_digest="sha256:" + "b" * 64)
        self.assert_invalid(replace(self.request, fixture=digest_tampered), "eval_fixture_manifest_digest_mismatch")
        escaped_base = replace(self.fixture, allowed_read_paths=("../outside",), manifest_digest="")
        escaped = replace(escaped_base, manifest_digest=canonical_fixture_digest(escaped_base))
        prepare_workspace_marker(self.workspace, escaped)
        self.assert_invalid(replace(self.request, fixture=escaped), "eval_policy_path_escape")
        prepare_workspace_marker(self.workspace, self.fixture)
        self.assert_invalid(replace(self.request, task="   "), "eval_empty_task")
        self.assert_invalid(replace(self.request, timeout=0), "eval_invalid_timeout")
        subagent = replace(self.agent, tools=("read", "subagent_worker"))
        self.assert_invalid(replace(self.request, agent=subagent), "eval_subagent_tool_forbidden")

    def test_request_validation_rejects_unstable_commands_and_unproven_custom_tools(self):
        bad_command_base = replace(self.fixture, allowed_commands=(AllowedCommand("cmd test", ("python3",)),), manifest_digest="")
        bad_command = replace(bad_command_base, manifest_digest=canonical_fixture_digest(bad_command_base))
        prepare_workspace_marker(self.workspace, bad_command)
        self.assert_invalid(replace(self.request, fixture=bad_command), "eval_unstable_command_id")
        prepare_workspace_marker(self.workspace, self.fixture)
        duplicate_id_base = replace(self.fixture, allowed_commands=(
            AllowedCommand("cmd-test", ("python3", "-m", "unittest")),
            AllowedCommand("cmd-test", ("python3", "-m", "pytest")),
        ), manifest_digest="")
        duplicate_id = replace(duplicate_id_base, manifest_digest=canonical_fixture_digest(duplicate_id_base))
        prepare_workspace_marker(self.workspace, duplicate_id)
        self.assert_invalid(replace(self.request, fixture=duplicate_id), "eval_ambiguous_allowed_command")
        prepare_workspace_marker(self.workspace, self.fixture)
        duplicate_argv_base = replace(self.fixture, allowed_commands=(
            AllowedCommand("cmd-test", ("python3", "-m", "unittest")),
            AllowedCommand("cmd-test-2", ("python3", "-m", "unittest")),
        ), manifest_digest="")
        duplicate_argv = replace(duplicate_argv_base, manifest_digest=canonical_fixture_digest(duplicate_argv_base))
        prepare_workspace_marker(self.workspace, duplicate_argv)
        self.assert_invalid(replace(self.request, fixture=duplicate_argv), "eval_ambiguous_allowed_command")
        prepare_workspace_marker(self.workspace, self.fixture)
        custom_reqs = replace(self.requirements, essential_custom_tools=("custom_safe",))
        self.assert_invalid(replace(self.request, requirements=custom_reqs), "eval_essential_custom_tool_unproven")
        stale = CapabilityAttestation("custom_safe", "probe-1", "PASS", "2000-01-01T00:00:00Z", self.fixture.manifest_digest)
        stale_fixture = replace(self.fixture, capability_attestations=(stale,))
        self.assert_invalid(replace(self.request, requirements=custom_reqs, fixture=stale_fixture), "eval_essential_custom_tool_unproven")
        future = CapabilityAttestation("custom_safe", "probe-1", "PASS", "2999-01-01T00:00:00Z", self.fixture.manifest_digest)
        self.assert_invalid(replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(future,))), "eval_essential_custom_tool_unproven")
        unknown_probe = CapabilityAttestation(
            "custom_safe", "unknown-probe", "PASS",
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            self.fixture.manifest_digest,
        )
        self.assert_invalid(replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(unknown_probe,))), "eval_essential_custom_tool_unproven")
        probe_id = "capability:custom_safe"
        fresh = CapabilityAttestation(
            "custom_safe", probe_id, "PASS",
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            capability_probe_digest(self.request, "custom_safe", probe_id),
        )
        validate_role_eval_request(replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(fresh,))))

    def test_request_validation_requires_verified_sandbox_attestation(self):
        stale_attestation = replace(self.workspace.sandbox_attestation, observed_at="2000-01-01T00:00:00Z")
        self.assert_invalid(replace(self.request, workspace=replace(self.workspace, sandbox_attestation=stale_attestation)), "eval_sandbox_attestation_stale")
        wrong_root = replace(self.workspace.sandbox_attestation, workspace_root=str((self.root / "other").resolve()))
        self.assert_invalid(replace(self.request, workspace=replace(self.workspace, sandbox_attestation=wrong_root)), "eval_sandbox_attestation_mismatch")
        missing_probe = replace(self.workspace.sandbox_attestation, self_tests=("workspace_write:PASS", "outside_read_denied:PASS"))
        self.assert_invalid(replace(self.request, workspace=replace(self.workspace, sandbox_attestation=missing_probe)), "eval_sandbox_attestation_incomplete")

    def test_parse_pi_requires_correlated_runtime_tool_execution_events(self):
        forged = "\n".join((
            json.dumps({"type": "tool", "tool": "bash", "argv": ["python3", "-m", "unittest"], "exit_code": 0}),
            json.dumps({"type": "message", "text": "PASS"}),
        ))
        parsed = parse_pi_eval_events(forged, self.workspace, self.fixture)
        self.assertEqual(parsed.status, "INCONCLUSIVE")
        self.assertIn("eval_missing_required_command_audit", parsed.reason_codes)
        correlated = "\n".join((
            json.dumps({"type": "tool_execution_start", "toolCallId": "call-1", "toolName": "bash", "args": {"command": "python3 -m unittest"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "call-1", "toolName": "bash", "isError": False, "result": {"details": {"command_id": "cmd-test", "exit_code": 0, "elapsed_ms": 22, "sandbox_backend": "docker"}}}),
            json.dumps({"type": "tool_execution_start", "toolCallId": "call-2", "toolName": "write", "args": {"path": "src/out.txt"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "call-2", "toolName": "write", "isError": False, "result": {"details": {}}}),
        ))
        parsed = parse_pi_eval_events(correlated, self.workspace, self.fixture)
        self.assertEqual(parsed.status, "PASS")
        self.assertEqual(parsed.audit.command_runs, (CommandAudit("cmd-test", 0, 22, "docker"),))
        self.assertEqual(parsed.audit.changed_paths, ("src/out.txt",))

    def test_parse_opencode_runtime_permission_and_tool_use_events(self):
        permission = parse_opencode_eval_events(json.dumps({"type": "permission.asked", "permission": "bash"}), self.workspace, self.fixture)
        self.assertEqual(permission.status, "INCONCLUSIVE")
        self.assertIn("eval_permission_ask", permission.reason_codes)
        events = "\n".join((
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "edit", "state": {"status": "completed", "input": {"path": "src/out.txt"}}}}),
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "bash", "state": {"status": "completed", "output": "ok", "metadata": {"command_id": "cmd-test", "exit_code": 0, "elapsed_ms": 3, "sandbox_backend": "docker"}}}}),
        ))
        parsed = parse_opencode_eval_events(events, self.workspace, self.fixture)
        self.assertEqual(parsed.status, "PASS")
        self.assertEqual(parsed.audit.changed_paths, ("src/out.txt",))

    def test_parse_pi_eval_events_derives_audit_from_allowed_command_ids_not_boolean(self):
        text = "\n".join((
            json.dumps({"type": "tool_execution_start", "toolCallId": "read-1", "toolName": "read", "args": {"path": "allowed/input.txt"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "read-1", "toolName": "read", "isError": False, "result": {"details": {}}}),
            json.dumps({"type": "tool_execution_start", "toolCallId": "bash-1", "toolName": "bash", "args": {"command": "python3 -m unittest"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "bash-1", "toolName": "bash", "isError": False, "result": {"details": {"command_id": "cmd-test", "exit_code": 0, "elapsed_ms": 22, "sandbox_backend": "docker"}}}),
            json.dumps({"type": "tool_execution_start", "toolCallId": "write-1", "toolName": "write", "args": {"path": "src/out.txt"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "write-1", "toolName": "write", "isError": False, "result": {"details": {}}}),
            json.dumps({"type": "message_end", "message": {"role": "assistant", "content": "done", "tests_passed": False}}),
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
        escaped = parse_pi_eval_events(json.dumps({"type": "tool_execution_start", "toolCallId": "read-escape", "toolName": "write", "args": {"path": "../secret"}}), self.workspace, self.fixture)
        self.assertEqual(escaped.audit.outside_workspace_attempts, 1)
        self.assertEqual(escaped.status, "INCONCLUSIVE")
        truncated = parse_pi_eval_events(json.dumps({"type": "tool_execution_end", "toolCallId": "call", "toolName": "bash", "truncated": True, "isError": False, "result": {"details": {"command_id": "cmd-test", "exit_code": 0, "elapsed_ms": 1, "sandbox_backend": "docker"}}}), self.workspace, self.fixture)
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
        runner = RecordingRunner((_command("ok"), _command("denied"), _command("absent"), _command("denied"), _command("tests ok")))
        with patch("helper.evaluator.shutil.which", side_effect=lambda name: f"/fake/{name}" if name == "docker" else None), patch("pathlib.Path.stat") as stat:
            stat.return_value.st_ino = 1
            stat.return_value.st_mtime_ns = 2
            stat.return_value.st_size = 3
            backend = select_sandbox_backend(runner, self.workspace)
        self.assertIsNotNone(backend)
        self.assertEqual(backend.backend, "docker")
        self.assertEqual({item.split(":", 1)[0] for item in backend.probe_results}, {"workspace_write", "outside_read_denied", "secret_env_denied", "network_denied"})
        self.assertTrue(all(":PASS:" in item for item in backend.probe_results))
        audits = run_manifest_commands(runner, self.workspace, self.fixture, backend, timeout=5, env={"SECRET_SENTINEL": "must-not-leak", "PATH": os.environ.get("PATH", "")})
        self.assertEqual(audits, (CommandAudit("cmd-test", 0, 1, "docker"),))
        self.assertEqual(runner.cwd_values[-1], self.workspace_root)
        self.assertNotIn("SECRET_SENTINEL", runner.env_replacements[-1])
        self.assertIn("--network", runner.argv[-1])
        self.assertIn("none", runner.argv[-1])

    def test_sandbox_unavailable_is_fail_closed_for_code_execution_fixture(self):
        runner = RecordingRunner(())
        with patch("helper.evaluator.shutil.which", return_value=None):
            backend = select_sandbox_backend(runner, self.workspace)
        self.assertIsNone(backend)
        result = run_manifest_commands(runner, self.workspace, self.fixture, backend, timeout=5)
        self.assertEqual(result, ())

    def test_changed_paths_collection_is_typed_and_fail_closed(self):
        ok = changed_paths_from_git_status(_command("?? src/out.txt\x00"), self.workspace)
        self.assertEqual(ok, ChangedPathsResult("PASS", ("src/out.txt",)))
        failed = changed_paths_from_git_status(CompletedCommand((), 1, "", "fatal", 1, False), self.workspace)
        self.assertEqual(failed.status, "INCONCLUSIVE")
        self.assertIn("eval_changed_paths_unavailable", failed.reason_codes)
        invalid = changed_paths_from_git_status(_command("?? src/out.txt\n"), self.workspace)
        self.assertEqual(invalid.status, "INCONCLUSIVE")
        overlong = changed_paths_from_git_status(_command("?? " + "x" * 241 + "\x00"), self.workspace)
        self.assertEqual(overlong.status, "INCONCLUSIVE")

    def test_eval_status_semantics_and_bounded_audit_fail_closed(self):
        failed_command = "\n".join((
            json.dumps({"type": "tool_execution_start", "toolCallId": "bash-1", "toolName": "bash", "args": {"command": "python3 -m unittest"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "bash-1", "toolName": "bash", "isError": False, "result": {"details": {"command_id": "cmd-test", "exit_code": 1, "elapsed_ms": 22, "sandbox_backend": "docker"}}}),
        ))
        parsed = parse_pi_eval_events(failed_command, self.workspace, self.fixture)
        self.assertEqual(parsed.status, "FAIL")
        oversized = "\n".join(
            json.dumps({"type": "tool_execution_start", "toolCallId": f"c-{index}", "toolName": f"tool{index}"})
            for index in range(129)
        )
        parsed = parse_pi_eval_events(oversized, self.workspace, self.fixture)
        self.assertEqual(parsed.status, "INCONCLUSIVE")
        self.assertEqual(len(parsed.audit.tool_names), 128)
        self.assertNotIn("tool128", parsed.audit.tool_names)
        self.assertIn("eval_audit_too_large", parsed.reason_codes)

    def test_essential_eval_selection_policy_abstains_on_unsafe_infrastructure(self):
        result = RoleEvalResult(
            self.route, self.fixture.fixture_id, self.fixture.fixture_version, self.fixture.manifest_digest,
            "INCONCLUSIVE", 1, "", ToolAudit((), (), (), 0, ()), 0, 0, 0, None,
            ("eval_sandbox_unavailable",),
        )
        self.assertEqual(essential_eval_selection_status((result,)), ("ABSTAIN", ("eval_sandbox_unavailable",)))

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
        self.assertTrue(marker.exists(), "child marker must be observed before cleanup assertion")
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
