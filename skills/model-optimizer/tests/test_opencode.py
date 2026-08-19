import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helper.adapters import RuntimeContext
from helper.adapters.opencode import (
    OpenCodeAdapter,
    parse_opencode_auth,
    parse_opencode_live_events,
    parse_opencode_models_verbose,
)
from helper.models import HealthStatus, ModelRecord, ReadinessStatus
from tests.support import FakeRunner, _command, assert_test_path, fixture_text


class OpenCodeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = RuntimeContext(home=self.root, cwd=self.root / "project", env={})
        self.context.cwd.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def _write_project_config(self, text: str | None = None) -> Path:
        target = self.context.cwd / "opencode.json"
        assert_test_path(target, self.root)
        target.write_text(text or fixture_text("opencode/opencode.json"), encoding="utf-8")
        return target

    def test_auth_parser_strips_ansi_and_returns_provider_ids(self):
        ready = parse_opencode_auth(fixture_text("opencode/auth-list.txt"))
        self.assertEqual({r.provider for r in ready}, {"openai", "minimax-coding-plan", "nan"})
        self.assertTrue(all(r.status is ReadinessStatus.READY for r in ready))

    def test_every_shipped_auth_display_label_has_explicit_mapping(self):
        cases = {
            "OpenAI oauth": "openai",
            "MiniMax Token Plan (minimax.io) api": "minimax-coding-plan",
            "Z.AI Coding Plan api": "zai-coding-plan",
            "nan api": "nan",
        }
        for line, provider in cases.items():
            with self.subTest(line=line):
                ready = parse_opencode_auth(line)
                self.assertEqual(ready[0].provider, provider)
                self.assertEqual(ready[0].status, ReadinessStatus.READY)
                self.assertEqual(ready[0].reason_code, "auth_ready")

    def test_unknown_auth_label_does_not_invent_provider_or_leak_content(self):
        ready = parse_opencode_auth('{"apiKey":"sk-do-not-leak","provider":"mystery"} api\n')
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].provider, "UNKNOWN")
        self.assertEqual(ready[0].status, ReadinessStatus.UNKNOWN)
        self.assertEqual(ready[0].reason_code, "auth_unknown_provider_label")
        self.assertNotIn("sk-do-not-leak", json.dumps([item.to_dict() for item in ready]))

    def test_verbose_models_preserve_family_cache_vision_and_variants(self):
        models = parse_opencode_models_verbose(fixture_text("opencode/models-verbose.txt"))
        terra = next(m for m in models if m.exact_id == "openai/gpt-5.6-terra")
        self.assertEqual(terra.family, "gpt")
        self.assertEqual(terra.context_window, 1050000)
        self.assertEqual(terra.cache_read, 0.2)
        self.assertEqual(terra.input_modes, ("text", "image"))
        self.assertEqual(terra.variants, ("high", "max"))

    def test_verbose_models_drop_pathological_and_non_finite_costs(self):
        huge_json_integer = "1" + ("0" * 400)
        text = f"""\
openai/gpt-5.6-terra
{{"id":"gpt-5.6-terra","providerID":"openai","cost":{{"input":{huge_json_integer},"output":Infinity,"cache":{{"read":NaN,"write":0.4}}}}}}
"""
        models = parse_opencode_models_verbose(text)
        self.assertEqual(len(models), 1)
        self.assertIsNone(models[0].input_cost)
        self.assertIsNone(models[0].output_cost)
        self.assertIsNone(models[0].cache_read)
        self.assertEqual(models[0].cache_write, 0.4)
        serialized = json.dumps(models[0].to_dict(), allow_nan=False)
        self.assertNotIn("Infinity", serialized)
        self.assertNotIn("NaN", serialized)

    def test_verbose_models_accept_pretty_nested_json_and_validate_exact_id(self):
        text = """\
nan/qwen3.6
{
  "id": "qwen3.6",
  "providerID": "nan",
  "family": "qwen",
  "limit": {"context": 262144, "output": 16384},
  "capabilities": {"input": {"image": true, "text": true}, "toolcall": true},
  "variants": {"z": {}, "a": {}}
}
openai/wrong
{"id":"not-wrong","providerID":"openai"}
"""
        adapter = OpenCodeAdapter(FakeRunner.stdout(text))
        models = adapter.list_models(self.context)
        self.assertEqual([m.exact_id for m in models], ["nan/qwen3.6"])
        self.assertEqual(models[0].variants, ("a", "z"))
        self.assertEqual(models[0].input_modes, ("image", "text"))
        self.assertIn("inventory_model_id_mismatch:openai/wrong", adapter.warnings)

    def test_malformed_verbose_model_block_isolated_from_neighbors(self):
        text = """\
nan/qwen3.6
{"id":"qwen3.6","providerID":"nan"}
bad/provider
{"id":"provider","providerID":"bad",
openai/gpt-5.6-terra
{"id":"gpt-5.6-terra","providerID":"openai"}
"""
        adapter = OpenCodeAdapter(FakeRunner.stdout(text))
        models = adapter.list_models(self.context)
        self.assertEqual([m.exact_id for m in models], ["nan/qwen3.6", "openai/gpt-5.6-terra"])
        self.assertIn("inventory_malformed_model_block:bad/provider", adapter.warnings)

    def test_snapshot_reads_project_agents_and_preserves_only_present_options(self):
        self._write_project_config()
        snapshot = OpenCodeAdapter(FakeRunner.stdout("1.18.18\n")).snapshot(self.context)
        by_agent = {assignment.agent: assignment for assignment in snapshot.current_assignments}
        self.assertEqual(by_agent["worker"].model, "openai/gpt-5.6-terra")
        self.assertEqual(by_agent["worker"].options, {"variant": "high", "steps": 80})
        self.assertEqual(by_agent["reviewer"].options, {"temperature": 0.1})
        self.assertIn("project:opencode.json", snapshot.sources)

    def test_project_config_does_not_inherit_absent_global_options(self):
        global_config = self.root / ".config" / "opencode" / "opencode.json"
        assert_test_path(global_config, self.root)
        global_config.parent.mkdir(parents=True)
        global_config.write_text(json.dumps({
            "agent": {"worker": {"model": "openai/gpt-5.6-terra", "temperature": 0.9, "steps": 99}}
        }), encoding="utf-8")
        self._write_project_config(json.dumps({
            "agent": {"worker": {"model": "nan/qwen3.6"}}
        }))
        snapshot = OpenCodeAdapter(FakeRunner.stdout("1.18.18\n")).snapshot(self.context)
        worker = next(item for item in snapshot.current_assignments if item.agent == "worker")
        self.assertEqual(worker.model, "nan/qwen3.6")
        self.assertEqual(worker.options, {})
        self.assertEqual(worker.source, "project:opencode.json")

    def test_live_check_uses_json_events_and_supported_variant(self):
        runner = FakeRunner.stdout('{"type":"text","part":{"text":"PONG"}}\n')
        model = ModelRecord(
            exact_id="openai/gpt-5.6-terra",
            provider="openai",
            model="gpt-5.6-terra",
            variants=("high", "max"),
        )
        check = OpenCodeAdapter(runner).live_check(
            model, "high", "PONG", 60, self.context
        )
        self.assertEqual(check.status, HealthStatus.PASS)
        self.assertEqual(runner.argv[-1], (
            "opencode", "run", "--format", "json", "--model",
            "openai/gpt-5.6-terra", "--variant", "high", "Reply exactly: PONG",
        ))

    def test_error_event_is_fail_even_when_process_exit_is_zero(self):
        runner = FakeRunner.stdout(fixture_text("opencode/live-error.jsonl"))
        model = ModelRecord(
            exact_id="nan/qwen3.6", provider="nan", model="qwen3.6", variants=("low",),
        )
        check = OpenCodeAdapter(runner).live_check(
            model, "low", "PONG", 60, self.context
        )
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_runtime_error")
        self.assertIn("Unexpected server error", check.detail)
        self.assertNotIn("ses_fixture", check.detail)
        self.assertNotIn("err_fixture", check.detail)

    def test_error_event_structural_name_maps_known_reason_with_generic_message(self):
        event = {
            "type": "error",
            "sessionID": "ses_structural_fixture",
            "error": {
                "name": "ProviderModelNotFoundError",
                "message": "internal ref err_structural_fixture at ~/.local/share/opencode/auth.json",
                "data": {
                    "message": "Model lookup failed for ses_structural_fixture err_structural_fixture ~/.local/share/opencode/auth.json"
                },
            },
        }
        runner = FakeRunner.stdout(json.dumps(event) + "\n")
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        check = OpenCodeAdapter(runner).live_check(model, "low", "PONG", 60, self.context)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_provider_model_not_found")
        self.assertIn("Model lookup failed", check.detail)
        self.assertNotIn("ses_structural_fixture", check.detail)
        self.assertNotIn("err_structural_fixture", check.detail)
        self.assertNotIn("auth.json", check.detail)
        self.assertLessEqual(len(check.detail), 240)

    def test_live_event_parser_concatenates_only_text_part_text_for_sentinel(self):
        events = "\n".join((
            '{"type":"text","part":{"text":"PO"}}',
            '{"type":"text","part":{"text":"NG"}}',
            '{"type":"message","text":"PONG should not matter"}',
        ))
        matched, reason = parse_opencode_live_events(events, "PONG")
        self.assertTrue(matched)
        self.assertEqual(reason, "live_sentinel_matched")

    def test_step_start_only_is_empty_response_not_pass(self):
        runner = FakeRunner.stdout('{"type":"step_start","message":"PONG"}\n')
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        check = OpenCodeAdapter(runner).live_check(model, "low", "PONG", 60, self.context)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_empty_response")

    def test_unsupported_variant_fails_without_consuming_runner_response(self):
        runner = FakeRunner.stdout("unused")
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        check = OpenCodeAdapter(runner).live_check(model, "max", "PONG", 60, self.context)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_unsupported_variant")
        self.assertEqual(runner.argv, [])

    def test_live_nonzero_maps_known_model_errors_to_bounded_reason_codes(self):
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        cases = (
            ("model_not_supported: nan/qwen3.6", "live_model_not_supported"),
            ("ProviderModelNotFoundError: nan/qwen3.6", "live_provider_model_not_found"),
        )
        for stderr, reason in cases:
            with self.subTest(reason=reason):
                command = type(_command(""))((), 1, "", stderr, 1, False)
                check = OpenCodeAdapter(FakeRunner((command,))).live_check(model, "low", "PONG", 60, self.context)
                self.assertEqual(check.status, HealthStatus.FAIL)
                self.assertEqual(check.reason_code, reason)
                self.assertLessEqual(len(check.detail), 240)

    def test_timeout_precedes_nonzero_error_and_sentinel_evidence(self):
        command = type(_command(""))((), 2, fixture_text("opencode/live-error.jsonl") + '{"type":"text","part":{"text":"PONG"}}', "", 1, True)
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        check = OpenCodeAdapter(FakeRunner((command,))).live_check(model, "low", "PONG", 1, self.context)
        self.assertEqual(check.status, HealthStatus.HANG)
        self.assertEqual(check.reason_code, "live_timeout")

    def test_bounded_log_tail_enriches_fail_but_cannot_turn_it_into_pass(self):
        log = self.root / ".local" / "share" / "opencode" / "log" / "opencode.log"
        assert_test_path(log, self.root)
        log.parent.mkdir(parents=True)
        log.write_text("token=secret-token\n" + "x" * 400 + "\nProviderModelNotFoundError: missing ses_secret err_secret\n", encoding="utf-8")
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        command = type(_command(""))((), 1, "", "launch failed", 1, False)
        check = OpenCodeAdapter(FakeRunner((command,))).live_check(model, "low", "PONG", 60, self.context)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_provider_model_not_found")
        self.assertIn("ProviderModelNotFoundError", check.detail)
        self.assertNotIn("secret-token", check.detail)
        self.assertNotIn("ses_secret", check.detail)
        self.assertLessEqual(len(check.detail), 240)

    def test_log_tail_uses_bounded_binary_read_and_tail_marker(self):
        log = self.root / ".local" / "share" / "opencode" / "log" / "opencode.log"
        assert_test_path(log, self.root)
        log.parent.mkdir(parents=True)
        tail_marker = "ProviderModelNotFoundError: bounded tail marker ses_tail err_tail\n"
        with log.open("wb") as handle:
            handle.write(b"early ProviderModelNotFoundError should not require full read\n")
            handle.write(b"x" * 20000)
            handle.write(tail_marker.encode("utf-8"))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        command = type(_command(""))((), 1, "", "launch failed", 1, False)
        with patch.object(Path, "read_text", side_effect=AssertionError("full log read forbidden")):
            check = OpenCodeAdapter(FakeRunner((command,))).live_check(model, "low", "PONG", 60, self.context)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_provider_model_not_found")
        self.assertIn("bounded tail marker", check.detail)
        self.assertNotIn("ses_tail", check.detail)
        self.assertNotIn("err_tail", check.detail)
        self.assertLessEqual(len(check.detail), 240)

    def test_inventory_keeps_catalog_when_provider_is_not_ready(self):
        self._write_project_config()
        runner = FakeRunner((
            _command("1.18.18\n"),
            _command(fixture_text("opencode/models-verbose.txt")),
            _command("OpenAI oauth\n"),
        ))
        inventory = OpenCodeAdapter(runner).inventory(self.context)
        self.assertIn("nan/qwen3.6", [model.exact_id for model in inventory.catalog_local])
        exclusions = [item for item in inventory.exclusions if item.subject == "nan/qwen3.6"]
        self.assertEqual(exclusions[0].reason_code, "provider_not_ready")
        self.assertIn("openai/gpt-5.6-terra", [model.exact_id for model in inventory.catalog_local])

    def test_auth_path_and_credential_content_do_not_appear_in_inventory_artifact(self):
        self._write_project_config()
        runner = FakeRunner((
            _command("1.18.18\n"),
            _command(fixture_text("opencode/models-verbose.txt")),
            _command(fixture_text("opencode/auth-list.txt") + '{"apiKey":"sk-do-not-leak"} api\n'),
        ))
        inventory = OpenCodeAdapter(runner).inventory(self.context)
        serialized = json.dumps(inventory.to_dict())
        self.assertNotIn("auth.json", serialized)
        self.assertNotIn("sk-do-not-leak", serialized)
        self.assertNotIn("~/.local/share/opencode", serialized)

    def test_reload_semantics_reports_restart_required_for_config_changes(self):
        semantics = OpenCodeAdapter(FakeRunner.stdout("1.18.18\n")).reload_semantics(self.context)
        self.assertEqual(semantics["config_changes"], "restart required")
        self.assertIn("opencode.json", semantics["applies_to"])


if __name__ == "__main__":
    unittest.main()
