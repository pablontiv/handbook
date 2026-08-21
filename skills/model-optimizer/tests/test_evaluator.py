import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from helper import evaluator as evaluator_module
from helper.evaluator import (
    AllowedCommand,
    CapabilityAttestation,
    ChangedPathsResult,
    CommandAudit,
    FixturePolicy,
    GradeResult,
    PreparedWorkspace,
    ProbeObservation,
    RoleEvalRequest,
    SandboxAttestation,
    RoleEvalResult,
    ToolAudit,
    canonical_fixture_digest,
    capability_probe_digest,
    changed_paths_from_git_status,
    cited_lines,
    essential_eval_selection_status,
    grade_fixture,
    load_fixture,
    load_representative_fixture,
    prepare_fixture,
    parse_opencode_eval_events,
    parse_pi_eval_events,
    prepare_workspace_marker,
    run_manifest_commands,
    sandbox_attestation_digest,
    select_sandbox_backend,
    probe_observation_from_result,
    validate_role_eval_request,
)
from helper.models import ModelRecord, RuntimeKind
from helper.optimizer import AgentContract, PermissionRule, RoleRequirements, RouteKey
from helper.runner import CompletedCommand, CommandRunner
from tests.support import FakeRunner, _command, fixture_text

SKILL_ROOT = Path(__file__).resolve().parents[1]


class RecordingRunner(FakeRunner):
    def __init__(self, responses):
        super().__init__(responses)
        self.env_overlays = []
        self.env_replacements = []
        self.cwd_values = []
        self.timeout_values = []

    def run(self, argv, timeout, cwd, env_overlay=None, *, stdout_limit=None, env_replacement=None, stdin_text=None):
        self.env_overlays.append(dict(env_overlay or {}))
        self.env_replacements.append(dict(env_replacement) if env_replacement is not None else None)
        self.cwd_values.append(Path(cwd))
        self.timeout_values.append(timeout)
        return super().run(argv, timeout, cwd, env_overlay=env_overlay, stdout_limit=stdout_limit, env_replacement=env_replacement, stdin_text=stdin_text)


class TrustedFixtureTests(unittest.TestCase):
    def _route(self):
        return RouteKey(RuntimeKind.PI, "0.84.2", "nan/qwen3.6", "high")

    def _result(self, fixture, *, status="PASS", text="", changed=(), command_exit=0):
        return RoleEvalResult(
            self._route(),
            fixture.fixture_id,
            fixture.version,
            fixture.manifest_digest,
            status,
            100,
            text,
            ToolAudit(("bash",), (CommandAudit("python-unittest", command_exit, 25, "bwrap"),), tuple(changed), 0, ()),
            0,
            0,
            0,
            None,
            (),
        )

    def test_load_fixture_enforces_id_grader_bounds_and_symlink_escape(self):
        fixture = load_fixture(SKILL_ROOT, "mechanical-slugify")
        self.assertEqual(fixture.fixture_id, "mechanical-slugify")
        self.assertEqual(fixture.grader_id, "mechanical-slugify-v1")
        for bad_id in ("../mechanical-slugify", "Mechanical", "", "a" * 65):
            with self.subTest(bad_id=bad_id), self.assertRaisesRegex(ValueError, "eval_fixture_id_invalid"):
                load_fixture(SKILL_ROOT, bad_id)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "evals").mkdir()
            (root / "evals" / "escape").symlink_to(SKILL_ROOT / "evals" / "mechanical-slugify")
            with self.assertRaisesRegex(ValueError, "eval_fixture_path_escape"):
                load_fixture(root, "escape")
            unknown = root / "evals" / "unknown"
            unknown.mkdir()
            (unknown / "eval.json").write_text(json.dumps({
                "schema": "model-optimizer.eval-fixture/v1",
                "id": "unknown",
                "version": "1",
                "archetype": "mechanical",
                "task": "Do it",
                "grader": "unknown-grader",
                "allowed_changed_files": [],
                "allowed_commands": [],
                "requires_code_execution": False,
            }), encoding="utf-8")
            (unknown / "project").mkdir()
            with self.assertRaisesRegex(ValueError, "eval_fixture_unknown_grader"):
                load_fixture(root, "unknown")

    def test_representative_fixture_must_be_beneath_temp_root_and_marker_token(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td) / "owned"
            fixture_path = temp_root / "representative"
            (fixture_path / "project").mkdir(parents=True)
            (fixture_path / ".model-optimizer-representative-token").write_text("token-abc", encoding="utf-8")
            (fixture_path / "eval.json").write_text(json.dumps({
                "schema": "model-optimizer.eval-fixture/v1",
                "id": "representative",
                "version": "1",
                "archetype": "mechanical",
                "task": "Do it",
                "grader": "mechanical-slugify-v1",
                "allowed_changed_files": ["slugify.py"],
                "allowed_commands": [{"id": "python-unittest", "argv": ["python3", "-m", "unittest", "discover", "-v"]}],
                "requires_code_execution": True,
            }), encoding="utf-8")
            fixture = load_representative_fixture(temp_root, fixture_path, "token-abc")
            self.assertEqual(fixture.fixture_id, "representative")
            with self.assertRaisesRegex(ValueError, "eval_representative_token_mismatch"):
                load_representative_fixture(temp_root, fixture_path, "wrong")
            with self.assertRaisesRegex(ValueError, "eval_representative_path_escape"):
                load_representative_fixture(temp_root, Path(td) / "outside", "token-abc")

    def test_prepare_fixture_copies_project_to_disposable_workspace_and_baselines_are_red(self):
        expected_failures = {
            "mechanical-slugify": "FAILED",
            "mechanical-duration": "FAILED",
            "regression-timeout": "FAILED",
            "regression-retry-delay": "FAILED",
        }
        for fixture_id, expected in expected_failures.items():
            with self.subTest(fixture_id=fixture_id):
                fixture = load_fixture(SKILL_ROOT, fixture_id)
                prepared = prepare_fixture(fixture)
                self.addCleanup(lambda root=prepared.root: shutil.rmtree(root, ignore_errors=True))
                self.assertTrue((prepared.root / ".model-optimizer-eval.json").exists())
                command = subprocess.run(["python3", "-m", "unittest", "discover", "-v"], cwd=prepared.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
                self.assertNotEqual(command.returncode, 0)
                self.assertIn(expected, command.stdout)

    def test_mechanical_graders_require_successful_unittest_command_and_allowed_changes(self):
        fixture = load_fixture(SKILL_ROOT, "mechanical-slugify")
        prepared = prepare_fixture(fixture)
        self.addCleanup(lambda root=prepared.root: shutil.rmtree(root, ignore_errors=True))
        good = grade_fixture(fixture, prepared.root, self._result(fixture, changed=("slugify.py",)))
        self.assertEqual(good, GradeResult("PASS", 1.0, True, ()))
        no_test = grade_fixture(fixture, prepared.root, self._result(fixture, changed=("slugify.py",), command_exit=None))
        self.assertEqual(no_test.status, "FAIL")
        self.assertIn("fixture_required_command_missing", no_test.reason_codes)
        bad_change = grade_fixture(fixture, prepared.root, self._result(fixture, changed=("test_slugify.py",)))
        self.assertIn("fixture_unauthorized_change", bad_change.reason_codes)

    def test_regression_semantic_graders_accept_line_variants_and_reject_wrong_cause_or_mutation(self):
        fixture = load_fixture(SKILL_ROOT, "regression-timeout")
        prepared = prepare_fixture(fixture)
        self.addCleanup(lambda root=prepared.root: shutil.rmtree(root, ignore_errors=True))
        accepted = """status: diagnosed
root_cause: client.py returns timeout_ms without converting milliseconds to seconds
evidence: client.py:4-9 and test_service.py:7
proposed_fix: divide config[\"timeout_ms\"] by 1000
confidence: high
"""
        self.assertEqual(cited_lines("see client.py:5,8 and client.py:10-11", "client.py"), {5, 8, 10, 11})
        good = grade_fixture(fixture, prepared.root, self._result(fixture, status="FAIL", text=accepted, command_exit=1))
        self.assertEqual(good.status, "PASS")
        wrong = grade_fixture(fixture, prepared.root, self._result(fixture, status="FAIL", text=accepted.replace("client.py returns timeout_ms", "the caller passes"), command_exit=1))
        self.assertIn("fixture_wrong_root_cause", wrong.reason_codes)
        mutated = grade_fixture(fixture, prepared.root, self._result(fixture, status="FAIL", text=accepted, changed=("client.py",), command_exit=1))
        self.assertIn("fixture_unauthorized_change", mutated.reason_codes)


class EvaluatorContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace_root = self.root / "workspace"
        self.workspace_root.mkdir()
        (self.workspace_root / "allowed").mkdir()
        (self.workspace_root / "src").mkdir()
        observed_at = datetime.now(timezone.utc).replace(microsecond=0)
        executable_identity = "bwrap:/fake/bwrap:1:2:3"
        profile_identity = f"bwrap:{self.workspace_root.resolve()}:network=none:env=minimal"
        outside_probe = self.workspace_root.resolve().parent / ".model-optimizer-outside-token-123.txt"
        probe_specs = (
            (
                "workspace_write",
                (
                    "python3",
                    "-c",
                    "from pathlib import Path; import sys; p=Path('sandbox-probe.txt'); p.write_text('ok', encoding='utf-8'); sys.stdout.write(p.read_text(encoding='utf-8'))",
                ),
                "ok",
            ),
            (
                "outside_read_denied",
                (
                    "python3",
                    "-c",
                    f"from pathlib import Path; import sys; p=Path({str(outside_probe)!r});\ntry:\n p.read_text(encoding='utf-8'); raise SystemExit(7)\nexcept Exception:\n sys.stdout.write('denied')",
                ),
                "denied",
            ),
            (
                "secret_env_denied",
                (
                    "python3",
                    "-c",
                    "import os, sys\nif os.getenv('SECRET_SENTINEL'):\n raise SystemExit(8)\nsys.stdout.write('absent')",
                ),
                "absent",
            ),
            (
                "network_denied",
                (
                    "python3",
                    "-c",
                    "import socket, sys; s=socket.socket();\ntry:\n s.bind(('127.0.0.1', 0)); raise SystemExit(9)\nexcept OSError:\n sys.stdout.write('denied')",
                ),
                "denied",
            ),
        )
        observations: tuple[ProbeObservation, ...] = tuple(
            probe_observation_from_result(
                probe_id=probe_id,
                argv=(
                    "bwrap",
                    "--unshare-net",
                    "--bind",
                    str(self.workspace_root.resolve()),
                    str(self.workspace_root.resolve()),
                    "--chdir",
                    str(self.workspace_root.resolve()),
                    *command,
                ),
                executable_identity=executable_identity,
                profile_identity=profile_identity,
                expected_outcome=expected,
                result=CompletedCommand((), 0, expected, "", 1, False),
                observed_at=observed_at,
            )
            for probe_id, command, expected in probe_specs
        )
        self.workspace = PreparedWorkspace(self.workspace_root, "token-123", SandboxAttestation(
            backend="bwrap",
            workspace_root=str(self.workspace_root.resolve()),
            workspace_token="token-123",
            profile_identity=profile_identity,
            profile_digest=sandbox_attestation_digest("bwrap", self.workspace_root, "token-123", executable_identity, profile_identity, observations),
            observed_at=observed_at.isoformat().replace("+00:00", "Z"),
            probe_observations=observations,
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
        self._which_patch = patch("helper.evaluator.shutil.which", return_value="/fake/bwrap")
        self._identity_patch = patch("helper.evaluator._executable_identity", return_value=executable_identity)
        self._which_patch.start()
        self._identity_patch.start()

    def tearDown(self):
        self._identity_patch.stop()
        self._which_patch.stop()
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
        registered_probe = "capability:custom_safe:confined-tool-v1"
        stale_time = (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        stale = CapabilityAttestation("custom_safe", registered_probe, "PASS", stale_time, self.fixture.manifest_digest)
        stale_fixture = replace(self.fixture, capability_attestations=(stale,))
        self.assert_invalid(replace(self.request, requirements=custom_reqs, fixture=stale_fixture), "eval_essential_custom_tool_unproven")
        future_time = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        future = CapabilityAttestation("custom_safe", registered_probe, "PASS", future_time, self.fixture.manifest_digest)
        self.assert_invalid(replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(future,))), "eval_essential_custom_tool_unproven")
        unknown_probe = CapabilityAttestation(
            "custom_safe", "unknown-probe", "PASS",
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            self.fixture.manifest_digest,
        )
        self.assert_invalid(replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(unknown_probe,))), "eval_essential_custom_tool_unproven")
        arbitrary_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        arbitrary_prefix = CapabilityAttestation(
            "custom_safe", "capability:custom_safe:attacker", "PASS",
            arbitrary_time,
            capability_probe_digest(
                self.request,
                "custom_safe",
                "capability:custom_safe:attacker",
                status="PASS",
                observed_at=arbitrary_time,
            ),
        )
        self.assert_invalid(replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(arbitrary_prefix,))), "eval_essential_custom_tool_unproven")
        probe_id = registered_probe
        fresh_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        fresh = CapabilityAttestation(
            "custom_safe", probe_id, "PASS",
            fresh_time,
            capability_probe_digest(
                self.request,
                "custom_safe",
                probe_id,
                status="PASS",
                observed_at=fresh_time,
            ),
        )
        validate_role_eval_request(replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(fresh,))))

    def test_capability_attestation_boundaries_use_injected_clock(self):
        custom_reqs = replace(self.requirements, essential_custom_tools=("custom_safe",))
        probe_id = "capability:custom_safe:confined-tool-v1"
        base_now = datetime.now(timezone.utc).replace(microsecond=0)
        fresh_at = (base_now - timedelta(seconds=(24 * 60 * 60))).isoformat().replace("+00:00", "Z")
        fresh = CapabilityAttestation(
            "custom_safe",
            probe_id,
            "PASS",
            fresh_at,
            capability_probe_digest(self.request, "custom_safe", probe_id, status="PASS", observed_at=fresh_at),
        )
        validate_role_eval_request(
            replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(fresh,))),
            now=base_now,
        )

        stale_at = (base_now - timedelta(seconds=(24 * 60 * 60) + 1)).isoformat().replace("+00:00", "Z")
        stale = CapabilityAttestation(
            "custom_safe",
            probe_id,
            "PASS",
            stale_at,
            capability_probe_digest(self.request, "custom_safe", probe_id, status="PASS", observed_at=stale_at),
        )
        with self.assertRaisesRegex(ValueError, "eval_essential_custom_tool_unproven"):
            validate_role_eval_request(
                replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(stale,))),
                now=base_now,
            )

        future_at = (base_now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        future = CapabilityAttestation(
            "custom_safe",
            probe_id,
            "PASS",
            future_at,
            capability_probe_digest(self.request, "custom_safe", probe_id, status="PASS", observed_at=future_at),
        )
        with self.assertRaisesRegex(ValueError, "eval_essential_custom_tool_unproven"):
            validate_role_eval_request(
                replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(future,))),
                now=base_now,
            )

    def test_request_validation_requires_verified_sandbox_attestation(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        stale_at = (now - timedelta(seconds=(24 * 60 * 60) + 1)).isoformat().replace("+00:00", "Z")
        stale_observations = tuple(replace(item, observed_at=stale_at) for item in self.workspace.sandbox_attestation.probe_observations)
        stale_digest = sandbox_attestation_digest(
            self.workspace.sandbox_attestation.backend,
            self.workspace_root,
            self.workspace.token,
            self.workspace.sandbox_attestation.executable_identity,
            self.workspace.sandbox_attestation.profile_identity,
            stale_observations,
        )
        stale_attestation = replace(self.workspace.sandbox_attestation, observed_at=stale_at, probe_observations=stale_observations, profile_digest=stale_digest)
        self.assert_invalid(replace(self.request, workspace=replace(self.workspace, sandbox_attestation=stale_attestation)), "eval_sandbox_attestation_stale")

        future_at = (now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        future_observations = tuple(replace(item, observed_at=future_at) for item in self.workspace.sandbox_attestation.probe_observations)
        future_digest = sandbox_attestation_digest(
            self.workspace.sandbox_attestation.backend,
            self.workspace_root,
            self.workspace.token,
            self.workspace.sandbox_attestation.executable_identity,
            self.workspace.sandbox_attestation.profile_identity,
            future_observations,
        )
        future_attestation = replace(self.workspace.sandbox_attestation, observed_at=future_at, probe_observations=future_observations, profile_digest=future_digest)
        self.assert_invalid(replace(self.request, workspace=replace(self.workspace, sandbox_attestation=future_attestation)), "eval_sandbox_attestation_stale")

        wrong_root = replace(self.workspace.sandbox_attestation, workspace_root=str((self.root / "other").resolve()))
        self.assert_invalid(replace(self.request, workspace=replace(self.workspace, sandbox_attestation=wrong_root)), "eval_sandbox_attestation_mismatch")
        incomplete_observations = self.workspace.sandbox_attestation.probe_observations[:2]
        incomplete_digest = sandbox_attestation_digest(
            self.workspace.sandbox_attestation.backend,
            self.workspace_root,
            self.workspace.token,
            self.workspace.sandbox_attestation.executable_identity,
            self.workspace.sandbox_attestation.profile_identity,
            incomplete_observations,
        )
        missing_probe = replace(self.workspace.sandbox_attestation, probe_observations=incomplete_observations, profile_digest=incomplete_digest)
        self.assert_invalid(replace(self.request, workspace=replace(self.workspace, sandbox_attestation=missing_probe)), "eval_sandbox_attestation_incomplete")

    def test_probe_observations_derive_status_from_result_semantics(self):
        observed_at = datetime.now(timezone.utc).replace(microsecond=0)
        pass_probe = probe_observation_from_result(
            probe_id="workspace_write",
            argv=("bwrap", "--unshare-net", "python3", "-c", "print('ok')"),
            executable_identity="bwrap:/fake/bwrap:1:2:3",
            profile_identity="bwrap:/tmp/work:network=none:env=minimal",
            expected_outcome="ok",
            result=CompletedCommand((), 0, "ok", "", 1, False),
            observed_at=observed_at,
        )
        self.assertEqual(pass_probe.status, "PASS")
        fail_probe = probe_observation_from_result(
            probe_id="workspace_write",
            argv=pass_probe.argv,
            executable_identity=pass_probe.executable_identity,
            profile_identity=pass_probe.profile_identity,
            expected_outcome="ok",
            result=CompletedCommand((), 0, "partial", "", 1, False),
            observed_at=observed_at,
        )
        self.assertEqual(fail_probe.status, "FAIL")

    def test_sandbox_attestation_rejects_tampered_probe_observation_fields(self):
        base_attestation = self.workspace.sandbox_attestation
        base_observation = base_attestation.probe_observations[0]

        def mutated_attestation(updated: ProbeObservation) -> SandboxAttestation:
            observations = (updated, *base_attestation.probe_observations[1:])
            digest = sandbox_attestation_digest(
                base_attestation.backend,
                self.workspace_root,
                self.workspace.token,
                base_attestation.executable_identity,
                base_attestation.profile_identity,
                observations,
            )
            return replace(base_attestation, probe_observations=observations, profile_digest=digest)

        cases = (
            (replace(base_observation, probe_id="unknown"), "eval_sandbox_attestation_incomplete"),
            (replace(base_observation, argv=base_observation.argv[:-1]), "eval_sandbox_attestation_mismatch"),
            (replace(base_observation, executable_identity="bwrap:relative:1:2:3"), "eval_sandbox_attestation_mismatch"),
            (replace(base_observation, profile_identity="bwrap:/other:network=none:env=minimal"), "eval_sandbox_attestation_mismatch"),
            (replace(base_observation, expected_outcome="tampered"), "eval_sandbox_attestation_mismatch"),
            (replace(base_observation, status="FAIL"), "eval_sandbox_attestation_incomplete"),
            (replace(base_observation, returncode=1), "eval_sandbox_attestation_incomplete"),
            (replace(base_observation, timed_out=True), "eval_sandbox_attestation_incomplete"),
            (replace(base_observation, stdout_truncated=True), "eval_sandbox_attestation_incomplete"),
            (replace(base_observation, stderr_truncated=True), "eval_sandbox_attestation_incomplete"),
            (replace(base_observation, stdout_digest="sha256:" + "f" * 64), "eval_sandbox_attestation_incomplete"),
            (replace(base_observation, stderr_digest="sha256:" + "f" * 64), "eval_sandbox_attestation_incomplete"),
            (replace(base_observation, observed_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")), "eval_sandbox_attestation_stale"),
        )
        for updated, reason in cases:
            with self.subTest(field=reason):
                tampered = mutated_attestation(updated)
                self.assert_invalid(
                    replace(self.request, workspace=replace(self.workspace, sandbox_attestation=tampered)),
                    reason,
                )

    def test_capability_attestation_mismatch_matrix(self):
        probe_id = "capability:custom_safe:confined-tool-v1"
        custom_reqs = replace(self.requirements, essential_custom_tools=("custom_safe",))
        base_now = datetime.now(timezone.utc).replace(microsecond=0)
        observed_at = (base_now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")

        def attestation_for(request: RoleEvalRequest, *, status: str = "PASS", when: str = observed_at, tool_name: str = "custom_safe") -> CapabilityAttestation:
            return CapabilityAttestation(
                tool_name,
                probe_id,
                status,
                when,
                capability_probe_digest(request, tool_name, probe_id, status=status, observed_at=when),
            )

        valid = attestation_for(self.request)
        validate_role_eval_request(
            replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(valid,))),
            now=base_now,
        )

        alternate_root = self.root / "alternate-workspace"
        alternate_root.mkdir()
        alternate_workspace = replace(self.workspace, root=alternate_root)
        mismatches = (
            attestation_for(self.request, status="FAIL"),
            replace(valid, observed_at=base_now.isoformat().replace("+00:00", "Z")),
            attestation_for(replace(self.request, workspace=alternate_workspace)),
            attestation_for(replace(self.request, workspace=replace(self.workspace, token="token-other"))),
            attestation_for(replace(self.request, fixture=replace(self.fixture, manifest_digest="sha256:" + "e" * 64))),
            attestation_for(replace(self.request, route=replace(self.route, runtime_kind=RuntimeKind.OPENCODE))),
            attestation_for(replace(self.request, route=replace(self.route, runtime_version="0.84.3"))),
            attestation_for(replace(self.request, route=replace(self.route, model="nan/other"))),
            attestation_for(replace(self.request, route=replace(self.route, effort="medium"))),
            attestation_for(replace(self.request, workspace=replace(self.workspace, sandbox_attestation=replace(self.workspace.sandbox_attestation, profile_digest="sha256:" + "d" * 64)))),
            replace(valid, probe_digest=capability_probe_digest(self.request, "other_tool", probe_id, status="PASS", observed_at=observed_at)),
        )
        for mismatched in mismatches:
            with self.subTest(attestation=mismatched):
                with self.assertRaisesRegex(ValueError, "eval_essential_custom_tool_unproven"):
                    validate_role_eval_request(
                        replace(self.request, requirements=custom_reqs, fixture=replace(self.fixture, capability_attestations=(mismatched,))),
                        now=base_now,
                    )

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
            json.dumps({"type": "tool_execution_end", "toolCallId": "call-1", "toolName": "bash", "isError": False, "result": {"details": {"command_id": "cmd-test", "exit_code": 0, "elapsed_ms": 22, "sandbox_backend": "bwrap"}}}),
            json.dumps({"type": "tool_execution_start", "toolCallId": "call-2", "toolName": "write", "args": {"path": "src/out.txt"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "call-2", "toolName": "write", "isError": False, "result": {"details": {}}}),
        ))
        parsed = parse_pi_eval_events(correlated, self.workspace, self.fixture)
        self.assertEqual(parsed.status, "PASS")
        self.assertEqual(parsed.audit.command_runs, (CommandAudit("cmd-test", 0, 22, "bwrap"),))
        self.assertEqual(parsed.audit.changed_paths, ("src/out.txt",))

    def test_parse_opencode_runtime_permission_and_tool_use_events(self):
        for fixture_name in ("permission-asked.jsonl", "permission-v2-asked.jsonl"):
            with self.subTest(fixture=fixture_name):
                permission = parse_opencode_eval_events(fixture_text(f"opencode/{fixture_name}"), self.workspace, self.fixture)
                self.assertEqual(permission.status, "INCONCLUSIVE")
                self.assertIn("eval_permission_ask", permission.reason_codes)
        parsed = parse_opencode_eval_events(fixture_text("opencode/tool-success.jsonl"), self.workspace, self.fixture)
        self.assertEqual(parsed.status, "PASS")
        self.assertEqual(parsed.audit.changed_paths, ("src/out.txt",))
        failed = parse_opencode_eval_events(fixture_text("opencode/tool-failure.jsonl"), self.workspace, self.fixture)
        self.assertEqual(failed.status, "FAIL")
        rejected = parse_opencode_eval_events(fixture_text("opencode/cli-rejection.jsonl"), self.workspace, self.fixture)
        self.assertEqual(rejected.status, "INCONCLUSIVE")
        self.assertIn("eval_runtime_error", rejected.reason_codes)

    def test_parse_pi_eval_events_derives_audit_from_allowed_command_ids_not_boolean(self):
        text = "\n".join((
            json.dumps({"type": "tool_execution_start", "toolCallId": "read-1", "toolName": "read", "args": {"path": "allowed/input.txt"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "read-1", "toolName": "read", "isError": False, "result": {"details": {}}}),
            json.dumps({"type": "tool_execution_start", "toolCallId": "bash-1", "toolName": "bash", "args": {"command": "python3 -m unittest"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "bash-1", "toolName": "bash", "isError": False, "result": {"details": {"command_id": "cmd-test", "exit_code": 0, "elapsed_ms": 22, "sandbox_backend": "bwrap"}}}),
            json.dumps({"type": "tool_execution_start", "toolCallId": "write-1", "toolName": "write", "args": {"path": "src/out.txt"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "write-1", "toolName": "write", "isError": False, "result": {"details": {}}}),
            json.dumps({"type": "message_end", "message": {"role": "assistant", "content": "done", "tests_passed": False}}),
        ))
        parsed = parse_pi_eval_events(text, self.workspace, self.fixture)
        self.assertEqual(parsed.status, "PASS")
        self.assertEqual(parsed.audit.tool_names, ("bash", "read", "write"))
        self.assertEqual(parsed.audit.command_runs, (CommandAudit("cmd-test", 0, 22, "bwrap"),))
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
        truncated = parse_pi_eval_events(json.dumps({"type": "tool_execution_end", "toolCallId": "call", "toolName": "bash", "truncated": True, "isError": False, "result": {"details": {"command_id": "cmd-test", "exit_code": 0, "elapsed_ms": 1, "sandbox_backend": "bwrap"}}}), self.workspace, self.fixture)
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
        with patch("helper.evaluator.shutil.which", side_effect=lambda name: f"/fake/{name}" if name == "bwrap" else None):
            backend = select_sandbox_backend(runner, self.workspace)
        self.assertIsNotNone(backend)
        self.assertEqual(backend.backend, "bwrap")
        self.assertEqual({item.probe_id for item in backend.probe_observations}, {"workspace_write", "outside_read_denied", "secret_env_denied", "network_denied"})
        self.assertTrue(all(item.status == "PASS" for item in backend.probe_observations))
        audits = run_manifest_commands(runner, self.workspace, self.fixture, backend, timeout=5, env={"SECRET_SENTINEL": "must-not-leak", "PATH": os.environ.get("PATH", "")})
        self.assertEqual(audits, (CommandAudit("cmd-test", 0, 1, "bwrap"),))
        self.assertEqual(runner.cwd_values[-1], self.workspace_root)
        self.assertNotIn("SECRET_SENTINEL", runner.env_replacements[-1])
        self.assertIn("--unshare-net", runner.argv[-1])
        self.assertIn("--chdir", runner.argv[-1])

    def test_sandbox_unavailable_is_fail_closed_for_code_execution_fixture(self):
        runner = RecordingRunner(())
        with patch("helper.evaluator.shutil.which", return_value=None):
            backend = select_sandbox_backend(runner, self.workspace)
        self.assertIsNone(backend)
        result = run_manifest_commands(runner, self.workspace, self.fixture, backend, timeout=5)
        self.assertEqual(result, ())

    def test_select_sandbox_backend_never_overwrites_or_unlinks_preexisting_outside_sentinel(self):
        predictable = self.workspace_root.resolve().parent / f".model-optimizer-outside-{self.workspace.token}.txt"
        predictable.write_text("owned-by-someone-else", encoding="utf-8")
        runner = RecordingRunner(())
        with patch("helper.evaluator.shutil.which", return_value=None):
            backend = select_sandbox_backend(runner, self.workspace)
        self.assertIsNone(backend)
        self.assertEqual(predictable.read_text(encoding="utf-8"), "owned-by-someone-else")

    def test_executable_identity_binds_canonical_path_stat_and_hash(self):
        self._identity_patch.stop()
        try:
            executable = self.root / "bin" / "backend"
            executable.parent.mkdir()
            executable.write_text("#!/bin/sh\necho one\n", encoding="utf-8")
            identity_one = evaluator_module._executable_identity(str(executable), "bwrap")
            executable.write_text("#!/bin/sh\necho two\n", encoding="utf-8")
            identity_two = evaluator_module._executable_identity(str(executable), "bwrap")
        finally:
            self._identity_patch.start()
        self.assertRegex(identity_one, r"^bwrap:/.*:sha256:[0-9a-f]{64}$")
        self.assertRegex(identity_two, r"^bwrap:/.*:sha256:[0-9a-f]{64}$")
        self.assertNotEqual(identity_one, identity_two)

    def test_changed_paths_collection_is_typed_and_fail_closed(self):
        ok = changed_paths_from_git_status(_command("?? src/out.txt\x00"), self.workspace)
        self.assertEqual(ok, ChangedPathsResult("PASS", ("src/out.txt",)))
        failed = changed_paths_from_git_status(CompletedCommand((), 1, "", "fatal", 1, False), self.workspace)
        self.assertEqual(failed.status, "INCONCLUSIVE")
        self.assertIn("eval_changed_paths_unavailable", failed.reason_codes)
        rename = changed_paths_from_git_status(_command("R  src/new.txt\x00src/old.txt\x00"), self.workspace)
        self.assertEqual(rename, ChangedPathsResult("PASS", ("src/new.txt", "src/old.txt")))
        copy = changed_paths_from_git_status(_command("C  src/copy.txt\x00src/original.txt\x00"), self.workspace)
        self.assertEqual(copy, ChangedPathsResult("PASS", ("src/copy.txt", "src/original.txt")))
        invalid = changed_paths_from_git_status(_command("?? src/out.txt\n"), self.workspace)
        self.assertEqual(invalid.status, "INCONCLUSIVE")
        invalid_utf8 = changed_paths_from_git_status(_command("?? src/\udcff.txt\x00"), self.workspace)
        self.assertEqual(invalid_utf8.status, "INCONCLUSIVE")
        decode_replaced = changed_paths_from_git_status(CompletedCommand((), 0, "?? src/out.txt\x00", "", 1, False, False, False, True, False), self.workspace)
        self.assertEqual(decode_replaced.status, "INCONCLUSIVE")
        overlong = changed_paths_from_git_status(_command("?? " + "x" * 241 + "\x00"), self.workspace)
        self.assertEqual(overlong.status, "INCONCLUSIVE")
        too_many_stream = "".join(f"?? src/file-{index}.txt\x00" for index in range(130))
        too_many = changed_paths_from_git_status(_command(too_many_stream), self.workspace)
        self.assertEqual(too_many.status, "INCONCLUSIVE")
        self.assertIn("eval_changed_paths_too_large", too_many.reason_codes)

    def test_changed_paths_real_git_porcelain_boundaries(self):
        if shutil.which("git") is None:
            self.skipTest("git is unavailable")

        def init_repo(path: Path) -> Path:
            path.mkdir(parents=True, exist_ok=True)
            subprocess.run(("git", "init", "-q"), cwd=path, check=True)
            subprocess.run(("git", "config", "user.email", "test@example.com"), cwd=path, check=True)
            subprocess.run(("git", "config", "user.name", "Test"), cwd=path, check=True)
            return path

        runner = CommandRunner()

        untracked_repo = init_repo(self.root / "git-untracked")
        (untracked_repo / "tracked.txt").write_text("base", encoding="utf-8")
        subprocess.run(("git", "add", "tracked.txt"), cwd=untracked_repo, check=True)
        subprocess.run(("git", "commit", "-qm", "init"), cwd=untracked_repo, check=True)
        (untracked_repo / "new.txt").write_text("new", encoding="utf-8")
        untracked_result = runner.run(("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"), timeout=5, cwd=untracked_repo, env_overlay={})
        parsed_untracked = changed_paths_from_git_status(untracked_result, PreparedWorkspace(untracked_repo, "token-git", None))
        self.assertEqual(parsed_untracked.status, "PASS")
        self.assertIn("new.txt", parsed_untracked.paths)

        rename_repo = init_repo(self.root / "git-rename")
        (rename_repo / "old.txt").write_text("rename", encoding="utf-8")
        subprocess.run(("git", "add", "old.txt"), cwd=rename_repo, check=True)
        subprocess.run(("git", "commit", "-qm", "init"), cwd=rename_repo, check=True)
        subprocess.run(("git", "mv", "old.txt", "new.txt"), cwd=rename_repo, check=True)
        rename_result = runner.run(("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"), timeout=5, cwd=rename_repo, env_overlay={})
        parsed_rename = changed_paths_from_git_status(rename_result, PreparedWorkspace(rename_repo, "token-git", None))
        self.assertEqual(parsed_rename.status, "PASS")
        self.assertEqual(parsed_rename.paths, ("new.txt", "old.txt"))

        copy_repo = init_repo(self.root / "git-copy")
        (copy_repo / "src.txt").write_text("copy me\n", encoding="utf-8")
        subprocess.run(("git", "add", "src.txt"), cwd=copy_repo, check=True)
        subprocess.run(("git", "commit", "-qm", "init"), cwd=copy_repo, check=True)
        (copy_repo / "copy.txt").write_text("copy me\n", encoding="utf-8")
        (copy_repo / "src.txt").write_text("copy me\nplus\n", encoding="utf-8")
        subprocess.run(("git", "add", "src.txt", "copy.txt"), cwd=copy_repo, check=True)
        subprocess.run(("git", "config", "status.renames", "copies"), cwd=copy_repo, check=True)
        copy_result = runner.run(("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"), timeout=5, cwd=copy_repo, env_overlay={})
        parsed_copy = changed_paths_from_git_status(copy_result, PreparedWorkspace(copy_repo, "token-git", None))
        self.assertEqual(parsed_copy.status, "PASS")
        self.assertIn("copy.txt", parsed_copy.paths)
        self.assertIn("src.txt", parsed_copy.paths)

        timeout_result = runner.run(("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"), timeout=0.0001, cwd=copy_repo, env_overlay={})
        parsed_timeout = changed_paths_from_git_status(timeout_result, PreparedWorkspace(copy_repo, "token-git", None))
        self.assertEqual(parsed_timeout.status, "INCONCLUSIVE")
        self.assertIn("eval_changed_paths_unavailable", parsed_timeout.reason_codes)

        truncation_result = runner.run(("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"), timeout=5, cwd=copy_repo, env_overlay={}, stdout_limit=8)
        parsed_truncation = changed_paths_from_git_status(truncation_result, PreparedWorkspace(copy_repo, "token-git", None))
        self.assertEqual(parsed_truncation.status, "INCONCLUSIVE")
        self.assertIn("eval_changed_paths_unavailable", parsed_truncation.reason_codes)

        cardinality_repo = init_repo(self.root / "git-cardinality")
        (cardinality_repo / "base.txt").write_text("base", encoding="utf-8")
        subprocess.run(("git", "add", "base.txt"), cwd=cardinality_repo, check=True)
        subprocess.run(("git", "commit", "-qm", "init"), cwd=cardinality_repo, check=True)
        for index in range(130):
            (cardinality_repo / f"file-{index}.txt").write_text("x", encoding="utf-8")
        cardinality_result = runner.run(("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"), timeout=5, cwd=cardinality_repo, env_overlay={})
        parsed_cardinality = changed_paths_from_git_status(cardinality_result, PreparedWorkspace(cardinality_repo, "token-git", None))
        self.assertEqual(parsed_cardinality.status, "INCONCLUSIVE")
        self.assertIn("eval_changed_paths_too_large", parsed_cardinality.reason_codes)

        fake_git_dir = self.root / "fake-git"
        fake_git_dir.mkdir()
        fake_git = fake_git_dir / "git"
        fake_git.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdout.buffer.write(b'?? src/\\xff.txt\\x00')\n", encoding="utf-8")
        fake_git.chmod(0o755)
        decode_result = runner.run(
            ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
            timeout=5,
            cwd=copy_repo,
            env_replacement={"PATH": str(fake_git_dir) + os.pathsep + os.environ.get("PATH", "")},
        )
        parsed_decode = changed_paths_from_git_status(decode_result, PreparedWorkspace(copy_repo, "token-git", None))
        self.assertTrue(decode_result.stdout_decode_replaced)
        self.assertEqual(parsed_decode.status, "INCONCLUSIVE")
        self.assertIn("eval_changed_paths_invalid", parsed_decode.reason_codes)

    def test_parser_status_matrix_pass_fail_hang_inconclusive(self):
        success = parse_pi_eval_events("\n".join((
            json.dumps({"type": "tool_execution_start", "toolCallId": "ok", "toolName": "bash", "args": {"command": "python3 -m unittest"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "ok", "toolName": "bash", "result": {"details": {"command_id": "cmd-test", "exit_code": 0, "elapsed_ms": 1, "sandbox_backend": "bwrap"}}}),
        )), self.workspace, self.fixture)
        self.assertEqual(success.status, "PASS")
        failure = parse_pi_eval_events("\n".join((
            json.dumps({"type": "tool_execution_start", "toolCallId": "fail", "toolName": "bash", "args": {"command": "python3 -m unittest"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "fail", "toolName": "bash", "result": {"details": {"command_id": "cmd-test", "exit_code": 1, "elapsed_ms": 1, "sandbox_backend": "bwrap"}}}),
        )), self.workspace, self.fixture)
        self.assertEqual(failure.status, "FAIL")
        hang = parse_pi_eval_events("\n".join((
            json.dumps({"type": "tool_execution_start", "toolCallId": "hang", "toolName": "bash", "args": {"command": "python3 -m unittest"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "hang", "toolName": "bash", "result": {"details": {"command_id": "cmd-test", "exit_code": None, "timed_out": True, "elapsed_ms": 1, "sandbox_backend": "bwrap"}}}),
        )), self.workspace, self.fixture)
        self.assertEqual(hang.status, "HANG")
        inconclusive = parse_pi_eval_events("{not-json", self.workspace, self.fixture)
        self.assertEqual(inconclusive.status, "INCONCLUSIVE")
        opencode_hang = parse_opencode_eval_events(json.dumps({"type": "timeout"}), self.workspace, self.fixture)
        self.assertEqual(opencode_hang.status, "HANG")

    def test_parser_rejects_candidate_command_backend_mismatch(self):
        mismatch = "\n".join((
            json.dumps({"type": "tool_execution_start", "toolCallId": "bash-1", "toolName": "bash", "args": {"command": "python3 -m unittest"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "bash-1", "toolName": "bash", "result": {"details": {"command_id": "cmd-test", "exit_code": 0, "elapsed_ms": 1, "sandbox_backend": "sandbox-exec"}}}),
        ))
        parsed = parse_pi_eval_events(mismatch, self.workspace, self.fixture)
        self.assertEqual(parsed.status, "INCONCLUSIVE")
        self.assertIn("eval_missing_required_command_audit", parsed.reason_codes)

    def test_eval_status_semantics_and_bounded_audit_fail_closed(self):
        failed_command = "\n".join((
            json.dumps({"type": "tool_execution_start", "toolCallId": "bash-1", "toolName": "bash", "args": {"command": "python3 -m unittest"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "bash-1", "toolName": "bash", "isError": False, "result": {"details": {"command_id": "cmd-test", "exit_code": 1, "elapsed_ms": 22, "sandbox_backend": "bwrap"}}}),
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

    def test_append_command_audits_revalidates_total_without_clamping(self):
        base = RoleEvalResult(
            self.route, self.fixture.fixture_id, self.fixture.fixture_version, self.fixture.manifest_digest,
            "PASS", 1, "", ToolAudit((), tuple(CommandAudit(f"cmd-{index}", 0, 1, "bwrap") for index in range(128)), (), 0, ()), 0, 0, 0, None, (),
        )
        from helper.evaluator import append_command_audits
        too_many = append_command_audits(base, (CommandAudit("cmd-extra", 0, 1, "bwrap"),))
        self.assertEqual(too_many.status, "INCONCLUSIVE")
        self.assertIn("eval_audit_too_large", too_many.reason_codes)
        invalid = append_command_audits(replace(base, audit=ToolAudit((), (), (), 0, ())), (CommandAudit("cmd-invalid", 999, 1, "bwrap"),))
        self.assertEqual(invalid.status, "INCONCLUSIVE")
        self.assertIn("eval_invalid_command_audit", invalid.reason_codes)

    def test_essential_eval_selection_policy_abstains_on_unsafe_infrastructure(self):
        result = RoleEvalResult(
            self.route, self.fixture.fixture_id, self.fixture.fixture_version, self.fixture.manifest_digest,
            "INCONCLUSIVE", 1, "", ToolAudit((), (), (), 0, ()), 0, 0, 0, None,
            ("eval_sandbox_unavailable",),
        )
        self.assertEqual(essential_eval_selection_status((result,)), ("ABSTAIN", ("eval_sandbox_unavailable",)))
        pi_isolation = replace(result, reason_codes=("eval_pi_isolation_unverified", "eval_pi_isolation_unavailable"))
        self.assertEqual(
            essential_eval_selection_status((pi_isolation,)),
            ("ABSTAIN", ("eval_pi_isolation_unverified", "eval_pi_isolation_unavailable")),
        )

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
