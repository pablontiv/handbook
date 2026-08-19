import json
import tempfile
import unittest
from pathlib import Path

from helper.adapters import RuntimeContext
from helper.adapters.pi import PiAdapter, parse_pi_auth, parse_pi_model_listing
from helper.models import HealthStatus, ModelRecord, ReadinessStatus
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

    def test_auth_check_never_requires_credentials_output(self):
        readiness = parse_pi_auth(fixture_text("pi/auth-ready.json"), "nan-builders")
        self.assertEqual(readiness.status, ReadinessStatus.READY)
        self.assertEqual(readiness.auth_type, "api_key")

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

    def test_reload_semantics_reports_reload_or_restart(self):
        semantics = PiAdapter(FakeRunner.stdout("0.84.2\n")).reload_semantics(self.context)
        self.assertEqual(semantics["profile_changes"], "/reload or restart")
        self.assertIn("subagents.json", semantics["applies_to"])


if __name__ == "__main__":
    unittest.main()
