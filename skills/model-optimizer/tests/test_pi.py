import json
import math
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from helper.adapters import RuntimeContext
from helper.adapters.pi import PiAdapter, parse_pi_auth, parse_pi_model_listing, _find_model_metadata
from helper.evaluator import (
    AllowedCommand,
    FixturePolicy,
    PreparedWorkspace,
    RoleEvalRequest,
    SandboxAttestation,
    canonical_fixture_digest,
    prepare_workspace_marker,
    sandbox_attestation_digest,
)
from helper.models import HealthStatus, ModelRecord, ProviderReadiness, ReadinessStatus, RuntimeKind
from helper.optimizer import AgentContract, PermissionRule, RoleRequirements, RouteKey
from helper.runner import CompletedCommand, MAX_STDOUT_LIMIT_CHARS
from tests.support import (
    FakeRunner,
    _command,
    copy_pi_fixtures_to_home,
    fixture_text,
    pi_inventory_runner_from_fixtures,
)


class PiAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = RuntimeContext(home=self.root, cwd=self.root / "project", env={})
        self.context.cwd.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_runtime_context_defensively_copies_env(self):
        env = {"PI_MODEL": "nan-builders/qwen3.6"}
        context = RuntimeContext(home=self.root, cwd=self.root / "project", env=env)
        env["PI_MODEL"] = "mutated"
        self.assertEqual(context.env["PI_MODEL"], "nan-builders/qwen3.6")
        with self.assertRaises(TypeError):
            context.env["NEW"] = "blocked"

    def test_listing_preserves_exact_ids_and_display_limits(self):
        models = parse_pi_model_listing(fixture_text("pi/list-models.txt"))
        self.assertEqual([m.exact_id for m in models], [
            "github-copilot/gemini-3.1-pro-preview",
            "nan-builders/qwen3.6",
            "openai-codex/gpt-5.6-terra",
        ])
        self.assertEqual(models[1].context_window, 262100)
        self.assertEqual(models[1].input_modes, ("text", "image"))

    def test_listing_non_finite_display_limits_do_not_raise(self):
        models = parse_pi_model_listing("""\
provider        model       context  max-out  thinking  images
bad-provider    inf-model   inf      -inf     yes       no
bad-provider    nan-model   nan      nan      no        yes
ok-provider     ok-model    1K       2K       yes       no
""")
        by_id = {model.exact_id: model for model in models}
        self.assertEqual(set(by_id), {
            "bad-provider/inf-model",
            "bad-provider/nan-model",
            "ok-provider/ok-model",
        })
        self.assertIsNone(by_id["bad-provider/inf-model"].context_window)
        self.assertIsNone(by_id["bad-provider/inf-model"].max_output)
        self.assertIsNone(by_id["bad-provider/nan-model"].context_window)
        self.assertIsNone(by_id["bad-provider/nan-model"].max_output)
        self.assertEqual(by_id["ok-provider/ok-model"].context_window, 1000)
        self.assertEqual(by_id["ok-provider/ok-model"].max_output, 2000)

    def test_auth_check_never_requires_credentials_output(self):
        readiness = parse_pi_auth(fixture_text("pi/auth-ready.json"), "nan-builders")
        self.assertEqual(readiness.status, ReadinessStatus.READY)
        self.assertEqual(readiness.auth_type, "api_key")

    def test_auth_type_must_be_bounded_structural_string(self):
        invalid_values = (123, ["api_key"], {"kind": "api_key"}, "x" * 65, "api key")
        for auth_type in invalid_values:
            with self.subTest(auth_type=auth_type):
                readiness = parse_pi_auth(json.dumps({
                    "status": "ready",
                    "provider": "nan-builders",
                    "authType": auth_type,
                }), "nan-builders")
                self.assertEqual(readiness.status, ReadinessStatus.READY)
                self.assertIsNone(readiness.auth_type)
                self.assertEqual(readiness.reason_code, "auth_ready")

    def test_check_readiness_uses_exact_no_refresh_json_command(self):
        runner = FakeRunner.stdout(fixture_text("pi/auth-ready.json"))
        readiness = PiAdapter(runner).check_readiness(["nan-builders"], self.context)
        self.assertEqual(readiness[0].status, ReadinessStatus.READY)
        self.assertEqual(runner.argv[-1], (
            "pi", "auth", "check", "--provider", "nan-builders", "--json", "--no-refresh",
        ))
        self.assertNotIn("--credentials", runner.argv[-1])

    def test_live_check_uses_exact_pi_command(self):
        runner = FakeRunner.stdout("PONG\n")
        model = ModelRecord(
            exact_id="nan-builders/qwen3.6",
            provider="nan-builders",
            model="qwen3.6",
        )
        check = PiAdapter(runner).live_check(
            model, "minimal", "PONG", 60, self.context
        )
        self.assertEqual(check.status, HealthStatus.PASS)
        self.assertEqual(runner.argv[-1], (
            "pi", "--no-session", "-p", "--no-tools", "--model",
            "nan-builders/qwen3.6", "--thinking", "minimal", "Reply exactly: PONG",
        ))

    def test_live_check_status_reason_rules_are_independent(self):
        model = ModelRecord("nan-builders/qwen3.6", "nan-builders", "qwen3.6")
        cases = (
            (_command("PONG\n"), HealthStatus.PASS, "live_sentinel_matched"),
            (_command(""), HealthStatus.FAIL, "live_empty_response"),
            (_command("NOPE\n"), HealthStatus.FAIL, "live_sentinel_missing"),
            (_command("ERR\n", returncode=7), HealthStatus.FAIL, "live_nonzero_exit"),
            (type(_command("partial"))((), None, "partial", "", 1, True), HealthStatus.HANG, "live_timeout"),
        )
        for command, status, reason in cases:
            with self.subTest(reason=reason):
                check = PiAdapter(FakeRunner((command,))).live_check(model, "minimal", "PONG", 1, self.context)
                self.assertEqual(check.status, status)
                self.assertEqual(check.reason_code, reason)
                self.assertLessEqual(len(check.detail), 240)

    def test_list_models_uses_structured_stdout_limit_and_warns_on_truncation(self):
        ids = tuple(f"nan-builders/qwen-{index:03d}" for index in range(72))
        listing = "provider model context max-out thinking images notes\n" + "".join(
            f"nan-builders qwen-{index:03d} 262K 16K yes yes {'x' * 120}\n"
            for index in range(len(ids))
        )
        self.assertGreater(len(listing), 8192)
        runner = FakeRunner((_command(listing),))
        adapter = PiAdapter(runner)

        models = adapter.list_models(self.context)

        self.assertEqual(runner.stdout_limits, [MAX_STDOUT_LIMIT_CHARS])
        parsed_ids = [model.exact_id for model in models]
        self.assertEqual(parsed_ids[0], ids[0])
        self.assertEqual(parsed_ids[-1], ids[-1])

        truncated_runner = FakeRunner((CompletedCommand((), 0, listing, "", 1, False, True, False),))
        truncated_adapter = PiAdapter(truncated_runner)
        truncated_models = truncated_adapter.list_models(self.context)
        self.assertEqual([model.exact_id for model in truncated_models][:1], [ids[0]])
        self.assertIn("inventory_list_models_truncated", truncated_adapter.warnings)

    def test_profile_options_omit_non_finite_structural_numbers_without_crashing(self):
        project_agent = self.context.cwd / ".pi" / "agent"
        project_agent.mkdir(parents=True)
        (project_agent / "subagents.json").write_text(json.dumps({
            "model_profiles": {
                "worker": {
                    "model": "nan-builders/qwen3.6",
                    "temperature": math.nan,
                    "tools": {"enabled": True},
                }
            }
        }), encoding="utf-8")

        snapshot = PiAdapter(FakeRunner.stdout("0.84.2\n")).snapshot(self.context)

        worker = next(item for item in snapshot.current_assignments if item.agent == "worker")
        self.assertEqual(worker.options, {"tools": {"enabled": True}})

    def test_find_model_metadata_does_not_recurse_through_processed_models_list(self):
        metadata = {
            "providers": {
                "nan-builders": {
                    "models": [{
                        "id": "qwen3.6",
                        "cost": {"input": 0},
                        "models": [{"id": "qwen3.6", "provider": "nan-builders", "cost": {"input": 9.9}}],
                    }]
                }
            }
        }

        found = list(_find_model_metadata(metadata))

        self.assertEqual([exact_id for exact_id, _ in found], ["nan-builders/qwen3.6"])
        self.assertEqual(found[0][1]["cost"], {"input": 0})

    def test_metadata_costs_reject_bool_negative_non_finite_and_pathological_but_keep_zero(self):
        agent_dir = self.root / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        huge_json_integer = "1" + ("0" * 400)
        (agent_dir / "models-store.json").write_text(f"""{{
          "providers": {{
            "nan-builders": {{
              "models": [{{
                "id": "qwen3.6",
                "cost": {{
                  "input": 0,
                  "output": -1,
                  "cacheRead": true,
                  "cacheWrite": NaN
                }},
                "cache": {{"read": Infinity, "write": {huge_json_integer}}}
              }}]
            }}
          }}
        }}""", encoding="utf-8")

        models = PiAdapter(FakeRunner.stdout(fixture_text("pi/list-models.txt"))).list_models(self.context)

        qwen = {model.exact_id: model for model in models}["nan-builders/qwen3.6"]
        self.assertEqual(qwen.input_cost, 0)
        self.assertIsNone(qwen.output_cost)
        self.assertIsNone(qwen.cache_read)
        self.assertIsNone(qwen.cache_write)
        json.dumps(qwen.to_dict(), allow_nan=False)

    def test_inventory_excludes_catalog_model_when_readiness_record_is_missing(self):
        class MissingReadinessPiAdapter(PiAdapter):
            def check_readiness(self, providers, context):
                return (ProviderReadiness("github-copilot", ReadinessStatus.READY, "test", "auth_ready"),)

        inventory = MissingReadinessPiAdapter(FakeRunner((
            _command("0.84.2\n"),
            _command(fixture_text("pi/list-models.txt")),
        ))).inventory(self.context)

        missing = [item for item in inventory.exclusions if item.subject == "nan-builders/qwen3.6"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].reason_code, "provider_not_ready")
        self.assertEqual(missing[0].detail, "auth_provider_not_listed")

    def test_secret_decoy_is_not_extracted_from_models_store(self):
        copy_pi_fixtures_to_home(self.root)
        adapter = PiAdapter(FakeRunner.stdout(fixture_text("pi/list-models.txt")))
        models = adapter.list_models(self.context)
        by_id = {model.exact_id: model for model in models}
        serialized = json.dumps([m.to_dict() for m in models])
        self.assertNotIn("sk-must-never-leak", serialized)
        self.assertEqual(models[0].cache_read, 0.10)
        self.assertEqual(models[0].cache_write, 0.50)
        self.assertEqual(by_id["nan-builders/qwen3.6"].variants, ("minimal", "medium", "high"))

    def test_models_json_custom_provider_shape_enriches_exact_ids(self):
        agent_dir = self.root / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "models.json").write_text(json.dumps({
            "providers": {
                "nan-builders": {
                    "models": [{
                        "id": "qwen3.6",
                        "reasoning": True,
                        "input": ["text", "image"],
                        "contextWindow": 333000,
                        "maxTokens": 7777,
                        "cost": {
                            "input": 0.31,
                            "output": 0.91,
                            "cacheRead": 0.031,
                            "cacheWrite": 0.091,
                        },
                    }]
                },
                "other-provider": {
                    "models": [{
                        "id": "qwen3.6",
                        "reasoning": False,
                        "input": ["text"],
                        "contextWindow": 1,
                        "maxTokens": 1,
                        "cost": {"input": 9.9, "output": 9.9, "cacheRead": 9.9, "cacheWrite": 9.9},
                    }]
                },
            }
        }), encoding="utf-8")
        models = PiAdapter(FakeRunner.stdout(fixture_text("pi/list-models.txt"))).list_models(self.context)
        by_id = {model.exact_id: model for model in models}
        enriched = by_id["nan-builders/qwen3.6"]
        self.assertIs(enriched.reasoning, True)
        self.assertEqual(enriched.input_modes, ("text", "image"))
        self.assertEqual(enriched.context_window, 333000)
        self.assertEqual(enriched.max_output, 7777)
        self.assertEqual(enriched.input_cost, 0.31)
        self.assertEqual(enriched.output_cost, 0.91)
        self.assertEqual(enriched.cache_read, 0.031)
        self.assertEqual(enriched.cache_write, 0.091)
        self.assertNotEqual(by_id["nan-builders/qwen3.6"].context_window, 1)

    def test_later_metadata_without_optional_costs_preserves_existing_enrichment(self):
        agent_dir = self.root / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "models-store.json").write_text(json.dumps({
            "providers": {
                "nan-builders": {
                    "models": [{
                        "id": "qwen3.6",
                        "costs": {"input": 0.20, "output": 0.80},
                        "cache": {"read": 0.02, "write": 0.08},
                    }]
                }
            }
        }), encoding="utf-8")
        (agent_dir / "models.json").write_text(json.dumps({
            "providers": {
                "nan-builders": {
                    "models": [{
                        "id": "qwen3.6",
                        "contextWindow": 999000,
                    }]
                }
            }
        }), encoding="utf-8")
        models = PiAdapter(FakeRunner.stdout(fixture_text("pi/list-models.txt"))).list_models(self.context)
        enriched = {model.exact_id: model for model in models}["nan-builders/qwen3.6"]
        self.assertEqual(enriched.context_window, 999000)
        self.assertEqual(enriched.input_cost, 0.20)
        self.assertEqual(enriched.output_cost, 0.80)
        self.assertEqual(enriched.cache_read, 0.02)
        self.assertEqual(enriched.cache_write, 0.08)
        self.assertEqual(enriched.provenance, ("pi --list-models", "models-store.json", "models.json"))

    def test_snapshot_sources_and_project_precedence_without_inheritance(self):
        copy_pi_fixtures_to_home(self.root)
        project_agent = self.context.cwd / ".pi" / "agent"
        project_agent.mkdir(parents=True)
        (project_agent / "subagents.json").write_text(json.dumps({
            "model_profiles": {
                "worker": {"model": "nan-builders/qwen3.6"},
                "qa": {"model": "github-copilot/gemini-3.1-pro-preview", "effort": "medium"},
            }
        }), encoding="utf-8")
        context = RuntimeContext(
            home=self.root,
            cwd=self.context.cwd,
            env={"PI_PROVIDER": "github-copilot", "PI_MODEL": "gemini-3.1-pro-preview", "PI_REASONING_LEVEL": "minimal"},
        )
        snapshot = PiAdapter(FakeRunner.stdout("0.84.2\n")).snapshot(context)
        by_agent = {assignment.agent: assignment for assignment in snapshot.current_assignments}
        self.assertEqual(by_agent["current"].model, "github-copilot/gemini-3.1-pro-preview")
        self.assertEqual(by_agent["current"].options, {"thinking": "minimal"})
        self.assertEqual(by_agent["worker"].model, "nan-builders/qwen3.6")
        self.assertEqual(by_agent["worker"].options, {})
        self.assertEqual(by_agent["qa"].options, {"effort": "medium"})
        self.assertIn("global:settings.json", snapshot.sources)
        self.assertIn("project:subagents.json", snapshot.sources)

    def test_snapshot_uses_configured_global_root_and_project_pi_subagents_json(self):
        global_root = self.root / "custom-pi-agent"
        global_root.mkdir()
        (global_root / "settings.json").write_text(json.dumps({
            "defaultProvider": "openai-codex",
            "defaultModel": "gpt-5.6-terra",
        }), encoding="utf-8")
        project_pi = self.context.cwd / ".pi"
        project_pi.mkdir()
        (project_pi / "subagents.json").write_text(json.dumps({
            "model_profiles": {"worker": {"model": "nan-builders/qwen3.6", "effort": "medium"}}
        }), encoding="utf-8")
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"PI_CODING_AGENT_DIR": str(global_root)})

        snapshot = PiAdapter(FakeRunner.stdout("0.84.2\n")).snapshot(context)

        by_agent = {assignment.agent: assignment for assignment in snapshot.current_assignments}
        self.assertEqual(by_agent["default"].model, "openai-codex/gpt-5.6-terra")
        self.assertEqual(by_agent["worker"].model, "nan-builders/qwen3.6")
        self.assertEqual(by_agent["worker"].source, "project:subagents.json")
        self.assertIn("global:settings.json", snapshot.sources)
        self.assertIn("project:subagents.json", snapshot.sources)

    def test_list_models_malformed_metadata_warns_and_preserves_listing(self):
        copy_pi_fixtures_to_home(self.root)
        store = self.root / ".pi" / "agent" / "models-store.json"
        store.write_text("{malformed", encoding="utf-8")
        adapter = PiAdapter(FakeRunner.stdout(fixture_text("pi/list-models.txt")))
        models = adapter.list_models(self.context)
        self.assertEqual([m.exact_id for m in models], [
            "github-copilot/gemini-3.1-pro-preview",
            "nan-builders/qwen3.6",
            "openai-codex/gpt-5.6-terra",
        ])
        self.assertIn("inventory_malformed_metadata:models-store.json", adapter.warnings)

    def test_list_models_invalid_utf8_metadata_warns_and_preserves_inventory(self):
        copy_pi_fixtures_to_home(self.root)
        store = self.root / ".pi" / "agent" / "models-store.json"
        store.write_bytes(b"{\xff")

        adapter = PiAdapter(FakeRunner.stdout(fixture_text("pi/list-models.txt")))
        models = adapter.list_models(self.context)
        self.assertEqual([m.exact_id for m in models], [
            "github-copilot/gemini-3.1-pro-preview",
            "nan-builders/qwen3.6",
            "openai-codex/gpt-5.6-terra",
        ])
        self.assertIn("inventory_malformed_metadata:models-store.json", adapter.warnings)

        inventory = PiAdapter(pi_inventory_runner_from_fixtures()).inventory(self.context)
        self.assertEqual([m.exact_id for m in inventory.catalog_local], [
            "github-copilot/gemini-3.1-pro-preview",
            "nan-builders/qwen3.6",
            "openai-codex/gpt-5.6-terra",
        ])
        self.assertIn("inventory_malformed_metadata:models-store.json", inventory.warnings)

    def test_non_object_settings_and_subagents_sources_warn(self):
        global_agent = self.root / ".pi" / "agent"
        project_agent = self.context.cwd / ".pi" / "agent"
        global_agent.mkdir(parents=True)
        project_agent.mkdir(parents=True)
        (global_agent / "settings.json").write_text("[]", encoding="utf-8")
        (project_agent / "subagents.json").write_text("[]", encoding="utf-8")

        adapter = PiAdapter(FakeRunner.stdout("0.84.2\n"))
        snapshot = adapter.snapshot(self.context)
        self.assertIn("inventory_invalid_source_shape:settings.json", snapshot.warnings)
        self.assertIn("inventory_invalid_source_shape:subagents.json", snapshot.warnings)
        self.assertIn("inventory_invalid_source_shape:settings.json", adapter.warnings)
        self.assertIn("inventory_invalid_source_shape:subagents.json", adapter.warnings)

    def test_repeated_inventory_does_not_leak_prior_warnings(self):
        first_agent = self.root / ".pi" / "agent"
        first_agent.mkdir(parents=True)
        (first_agent / "models-store.json").write_text("{malformed", encoding="utf-8")

        with tempfile.TemporaryDirectory() as second_temp:
            second_root = Path(second_temp)
            second_context = RuntimeContext(home=second_root, cwd=second_root / "project", env={})
            second_context.cwd.mkdir()
            runner = FakeRunner((
                _command("0.84.2\n"),
                _command(fixture_text("pi/list-models.txt")),
                _command(json.dumps({"status": "ready", "authType": "test"})),
                _command(json.dumps({"status": "ready", "authType": "test"})),
                _command(json.dumps({"status": "ready", "authType": "test"})),
                _command("0.84.2\n"),
                _command(fixture_text("pi/list-models.txt")),
                _command(json.dumps({"status": "ready", "authType": "test"})),
                _command(json.dumps({"status": "ready", "authType": "test"})),
                _command(json.dumps({"status": "ready", "authType": "test"})),
            ))
            adapter = PiAdapter(runner)
            first = adapter.inventory(self.context)
            second = adapter.inventory(second_context)

        self.assertIn("inventory_malformed_metadata:models-store.json", first.warnings)
        self.assertNotIn("inventory_malformed_metadata:models-store.json", second.warnings)

    def test_missing_settings_sources_are_allowed_and_represented(self):
        snapshot = PiAdapter(FakeRunner.stdout("0.84.2\n")).snapshot(self.context)
        self.assertIn("missing:global:settings.json", snapshot.sources)
        self.assertIn("missing:global:subagents.json", snapshot.sources)
        self.assertIn("missing:project:subagents.json", snapshot.sources)

    def test_inventory_excludes_not_ready_provider_and_flags_broken_current(self):
        copy_pi_fixtures_to_home(self.root)
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={
            "PI_PROVIDER": "ghost-provider",
            "PI_MODEL": "missing-model",
        })
        runner = FakeRunner((
            _command("0.84.2\n"),
            _command(fixture_text("pi/list-models.txt")),
            _command(json.dumps({"status": "ready", "provider": "github-copilot", "authType": "test"})),
            _command(json.dumps({"status": "not_ready", "provider": "nan-builders", "reason": "missing_api_key"})),
            _command(json.dumps({"status": "ready", "provider": "openai-codex", "authType": "test"})),
        ))
        inventory = PiAdapter(runner).inventory(context)
        self.assertIn("inventory_current_model_not_catalog_local", [e.reason_code for e in inventory.exclusions])
        provider_exclusions = [e for e in inventory.exclusions if e.reason_code == "provider_not_ready"]
        self.assertEqual([e.subject for e in provider_exclusions], ["nan-builders/qwen3.6"])
        self.assertIn("nan-builders/qwen3.6", [m.exact_id for m in inventory.catalog_local])

    def test_detect_and_inventory_runner_use_expected_command_sequence(self):
        runner = pi_inventory_runner_from_fixtures()
        inventory = PiAdapter(runner).inventory(self.context)
        self.assertEqual(inventory.runtime.version, "0.84.2")
        self.assertEqual(runner.argv[:5], [
            ("pi", "--version"),
            ("pi", "--list-models"),
            ("pi", "auth", "check", "--provider", "github-copilot", "--json", "--no-refresh"),
            ("pi", "auth", "check", "--provider", "nan-builders", "--json", "--no-refresh"),
            ("pi", "auth", "check", "--provider", "openai-codex", "--json", "--no-refresh"),
        ])

    def _role_eval_request(self):
        workspace_root = self.root / "eval-workspace"
        workspace_root.mkdir()
        (workspace_root / "src").mkdir()
        probe_results = (
            "workspace_write:PASS:sha256:" + "1" * 64,
            "outside_read_denied:PASS:sha256:" + "2" * 64,
            "secret_env_denied:PASS:sha256:" + "3" * 64,
            "network_denied:PASS:sha256:" + "4" * 64,
        )
        executable_identity = "docker:/fake/docker:1:2:3"
        workspace = PreparedWorkspace(workspace_root, "token-pi", SandboxAttestation(
            backend="docker",
            workspace_root=str(workspace_root.resolve()),
            workspace_token="token-pi",
            profile_digest=sandbox_attestation_digest("docker", workspace_root, "token-pi", executable_identity, probe_results),
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            self_tests=("workspace_write:PASS", "outside_read_denied:PASS", "secret_env_denied:PASS", "network_denied:PASS"),
            probe_results=probe_results,
            executable_identity=executable_identity,
        ))
        fixture_base = FixturePolicy(
            fixture_id="mechanical",
            fixture_version="v1",
            manifest_digest="",
            grader_id="grader@v1",
            allowed_read_paths=("src",),
            allowed_write_paths=("src",),
            allowed_commands=(AllowedCommand("cmd-test", ("python3", "-m", "unittest")),),
            requires_code_execution=True,
            capability_attestations=(),
        )
        fixture = replace(fixture_base, manifest_digest=canonical_fixture_digest(fixture_base))
        prepare_workspace_marker(workspace, fixture)
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("high",), tool_call=True)
        route = RouteKey(RuntimeKind.PI, "0.84.2", "nan/qwen3.6", "high")
        agent = AgentContract(
            name="worker",
            description="",
            mode=None,
            model="nan/qwen3.6",
            effort="high",
            tools=("read", "edit", "bash"),
            permissions=(PermissionRule("edit", "src/**", "allow"),),
            mutation_authority="confined",
            body="Worker prompt",
            scope="project",
            definition_source="test",
            assignment_source="test",
            inheritance_sources=(),
            apply_target=None,
            digest="sha256:agent",
        )
        requirements = RoleRequirements(
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
        return RoleEvalRequest(route, model, agent, requirements, workspace, fixture, "Fix the fixture", 30)

    def test_role_eval_constructs_confined_pi_command_and_parses_audit(self):
        request = self._role_eval_request()
        events = "\n".join((
            json.dumps({"type": "tool_execution_start", "toolCallId": "call-1", "toolName": "bash", "args": {"command": "python3 -m unittest"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "call-1", "toolName": "bash", "isError": False, "result": {"details": {"command_id": "cmd-test", "exit_code": 0, "elapsed_ms": 10, "sandbox_backend": "docker"}}}),
            json.dumps({"type": "tool_execution_start", "toolCallId": "call-2", "toolName": "write", "args": {"path": "src/out.txt"}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "call-2", "toolName": "write", "isError": False, "result": {"details": {}}}),
        ))
        runner = FakeRunner((_command("0.84.2\n"), _command(events), _command("?? src/out.txt\x00")))
        result = PiAdapter(runner).role_eval(request, self.context)
        argv = runner.argv[0]
        self.assertEqual(runner.argv[0], ("pi", "--version"))
        argv = runner.argv[1]
        for flag in ("--no-extensions", "--no-builtin-tools", "--extension", "--mode", "json", "--no-session", "--no-context-files", "--no-skills", "--no-prompt-templates", "--tools", "--system-prompt"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--model") + 1], request.route.model)
        self.assertEqual(argv[argv.index("--thinking") + 1], request.route.effort)
        self.assertEqual(argv[argv.index("--tools") + 1], ",".join(request.agent.tools))
        extension_path = Path(argv[argv.index("--extension") + 1])
        self.assertTrue(extension_path.is_absolute())
        self.assertEqual(extension_path.name, "pi-confined-tools.ts")
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.audit.changed_paths, ("src/out.txt",))
        self.assertEqual(runner.stdout_limits[0], MAX_STDOUT_LIMIT_CHARS)
        self.assertEqual(runner.argv[-1], ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"))

    def test_role_eval_unsupported_custom_tool_fails_closed_without_ambient_extension(self):
        request = self._role_eval_request()
        custom_agent = replace(request.agent, tools=("read", "custom_prod_tool"))
        custom_requirements = replace(request.requirements, required_tools=("read",), essential_custom_tools=("custom_prod_tool",), requires_mutation=False)
        result = PiAdapter(FakeRunner(())).role_eval(replace(request, agent=custom_agent, requirements=custom_requirements), self.context)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertIn("eval_essential_custom_tool_unproven", result.reason_codes)

    def test_reload_semantics_reports_reload_or_restart(self):
        semantics = PiAdapter(FakeRunner.stdout("0.84.2\n")).reload_semantics(self.context)
        self.assertEqual(semantics["profile_changes"], "/reload or restart")
        self.assertIn("subagents.json", semantics["applies_to"])


if __name__ == "__main__":
    unittest.main()
