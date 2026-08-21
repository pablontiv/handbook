import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from helper.adapters import RuntimeContext
from helper.adapters.opencode import (
    OpenCodeAdapter,
    parse_opencode_auth,
    parse_opencode_live_events,
    parse_opencode_models_verbose,
)
from helper.evaluator import (
    AllowedCommand,
    FixturePolicy,
    PreparedWorkspace,
    ProbeObservation,
    RoleEvalRequest,
    SandboxAttestation,
    canonical_fixture_digest,
    prepare_workspace_marker,
    effective_config_matches,
    isolated_opencode_env,
    opencode_eval_config,
    probe_observation_from_result,
    sandbox_attestation_digest,
)
from helper.models import HealthStatus, ModelRecord, ReadinessStatus, RuntimeKind
from helper.optimizer import AgentContract, PermissionRule, RoleRequirements, RouteKey
from helper.runner import MAX_STDOUT_LIMIT_CHARS, CompletedCommand
from tests.support import FakeRunner, _command, assert_test_path, fixture_text


class EnvCapturingRunner(FakeRunner):
    def __init__(self, responses):
        super().__init__(responses)
        self.env_overlays = []
        self.cwd_values = []

    def run(self, argv, timeout, cwd, env_overlay=None, *, stdout_limit=None, env_replacement=None, stdin_text=None):
        self.env_overlays.append(dict(env_overlay or {}))
        self.cwd_values.append(Path(cwd))
        return super().run(argv, timeout, cwd, env_overlay=env_overlay, stdout_limit=stdout_limit, env_replacement=env_replacement, stdin_text=stdin_text)


def _probe_agent_name(token: str) -> str:
    return f"model-optimizer-probe-{token}"


def _debug_config_command(
    agent_name: str,
    *,
    payload: dict | str | None = None,
    returncode: int | None = 0,
    timed_out: bool = False,
    stdout_truncated: bool = False,
) -> CompletedCommand:
    if payload is None:
        stdout = json.dumps({"agent": {agent_name: {"permission": "deny"}}})
    elif isinstance(payload, str):
        stdout = payload
    else:
        stdout = json.dumps(payload)
    return CompletedCommand((), returncode, stdout, "", 1, timed_out, stdout_truncated, False)


class OpenCodeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = RuntimeContext(home=self.root, cwd=self.root / "project", env={})
        self.context.cwd.mkdir()
        self._which_patch = patch("helper.evaluator.shutil.which", return_value="/fake/bwrap")
        self._identity_patch = patch("helper.evaluator._executable_identity", return_value="bwrap:/fake/bwrap:1:2:3:sha256:" + ("0" * 64))
        self._which_patch.start()
        self._identity_patch.start()

    def tearDown(self):
        self._identity_patch.stop()
        self._which_patch.stop()
        self.temp.cleanup()

    def _write_project_config(self, text: str | None = None) -> Path:
        target = self.context.cwd / "opencode.json"
        assert_test_path(target, self.root)
        target.write_text(text or fixture_text("opencode/opencode.json"), encoding="utf-8")
        return target

    def _live_check_with_token(
        self,
        runner,
        model: ModelRecord,
        effort: str | None,
        sentinel: str,
        timeout: float,
        context: RuntimeContext,
        token: str = "a" * 32,
    ):
        with patch("helper.adapters.opencode.secrets.token_hex", return_value=token):
            return OpenCodeAdapter(runner).live_check(model, effort, sentinel, timeout, context)

    def test_auth_parser_strips_ansi_and_returns_provider_ids(self):
        ready = parse_opencode_auth(fixture_text("opencode/auth-list.txt"))
        self.assertEqual({r.provider for r in ready}, {"openai", "minimax-coding-plan", "nan"})
        self.assertTrue(all(r.status is ReadinessStatus.READY for r in ready))

    def test_auth_parser_ignores_opencode_framing_lines(self):
        text = "\n".join((
            "┌  Credentials \x1b[90m~/.local/share/opencode/auth.json",
            "│",
            "●  OpenAI \x1b[90moauth",
            "│",
            "●  MiniMax Token Plan (minimax.io) \x1b[90mapi",
            "│",
            "●  Z.AI Coding Plan \x1b[90mapi",
            "│",
            "●  nan \x1b[90mapi",
            "│",
            "└  4 credentials",
        ))
        ready = parse_opencode_auth(text)
        self.assertEqual(len(ready), 4)
        self.assertTrue(all(item.status is ReadinessStatus.READY for item in ready))
        self.assertEqual({item.provider for item in ready}, {"openai", "minimax-coding-plan", "zai-coding-plan", "nan"})
        self.assertEqual({item.auth_type for item in ready}, {"oauth", "api"})
        self.assertFalse(any(item.provider == "UNKNOWN" for item in ready))

    def test_auth_parser_unknown_bullet_label_is_still_unknown(self):
        ready = parse_opencode_auth("●  Mystery Provider \x1b[90mapi\n")
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].provider, "UNKNOWN")
        self.assertEqual(ready[0].status, ReadinessStatus.UNKNOWN)
        self.assertEqual(ready[0].reason_code, "auth_unknown_provider_label")
        self.assertIsNone(ready[0].auth_type)

    def test_auth_parser_legacy_fixture_behavior_is_unchanged(self):
        ready = parse_opencode_auth(fixture_text("opencode/auth-list.txt"))
        self.assertEqual(
            [(item.provider, item.auth_type, item.status, item.reason_code) for item in ready],
            [
                ("openai", "oauth", ReadinessStatus.READY, "auth_ready"),
                ("minimax-coding-plan", "api", ReadinessStatus.READY, "auth_ready"),
                ("nan", "api", ReadinessStatus.READY, "auth_ready"),
            ],
        )

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
        ready = parse_opencode_auth('{"apiKey":"' + "sk" + '-do-not-leak","provider":"mystery"} api\n')
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].provider, "UNKNOWN")
        self.assertEqual(ready[0].status, ReadinessStatus.UNKNOWN)
        self.assertEqual(ready[0].reason_code, "auth_unknown_provider_label")
        self.assertIsNone(ready[0].auth_type)
        self.assertNotIn("sk" + "-do-not-leak", json.dumps([item.to_dict() for item in ready]))

    def test_auth_type_uses_safe_vocabulary_and_unknown_provider_never_persists_method(self):
        cases = (
            ("OpenAI oauth\n", "openai", "oauth"),
            ("OpenAI api\n", "openai", "api"),
            ("OpenAI " + "sk" + "-live-api-key-shaped-value\n", "openai", None),
            ("Mystery api\n", "UNKNOWN", None),
            ("Mystery " + "sk" + "-live-api-key-shaped-value\n", "UNKNOWN", None),
        )
        for text, provider, auth_type in cases:
            with self.subTest(text=text):
                ready = parse_opencode_auth(text)
                self.assertEqual(ready[0].provider, provider)
                self.assertEqual(ready[0].auth_type, auth_type)
                self.assertNotIn("sk" + "-live-api-key-shaped-value", json.dumps(ready[0].to_dict()))

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

    def test_verbose_models_require_positive_limits_and_non_negative_costs(self):
        huge_json_integer = "1" + ("0" * 400)
        text = f"""\
openai/gpt-zero
{{"id":"gpt-zero","providerID":"openai","limit":{{"context":0,"output":-5}},"cost":{{"input":0,"output":-0.25,"cache":{{"read":-1,"write":0}}}}}}
nan/qwen-path
{{"id":"qwen-path","providerID":"nan","limit":{{"context":{huge_json_integer},"output":Infinity}},"cost":{{"input":{huge_json_integer},"output":NaN,"cache":{{"read":{huge_json_integer},"write":Infinity}}}}}}
"""
        models = parse_opencode_models_verbose(text)
        by_id = {model.exact_id: model for model in models}
        zero = by_id["openai/gpt-zero"]
        self.assertIsNone(zero.context_window)
        self.assertIsNone(zero.max_output)
        self.assertEqual(zero.input_cost, 0)
        self.assertIsNone(zero.output_cost)
        self.assertIsNone(zero.cache_read)
        self.assertEqual(zero.cache_write, 0)
        pathological = by_id["nan/qwen-path"]
        self.assertIsNone(pathological.context_window)
        self.assertIsNone(pathological.max_output)
        self.assertIsNone(pathological.input_cost)
        self.assertIsNone(pathological.output_cost)
        self.assertIsNone(pathological.cache_read)
        self.assertIsNone(pathological.cache_write)
        json.dumps([model.to_dict() for model in models], allow_nan=False)

    def test_verbose_models_reject_non_integral_positive_limits_without_truncation(self):
        text = """\
openai/gpt-fractional
{"id":"gpt-fractional","providerID":"openai","limit":{"context":0.5,"output":2.0}}
"""
        models = parse_opencode_models_verbose(text)
        self.assertEqual(len(models), 1)
        self.assertIsNone(models[0].context_window)
        self.assertEqual(models[0].max_output, 2)

    def test_verbose_models_exclude_non_active_and_invalid_status_with_stable_warnings(self):
        secret = "sk" + "-status-secret"
        text = f"""\
openai/gpt-active
{{"id":"gpt-active","providerID":"openai","status":"active"}}
openai/gpt-missing
{{"id":"gpt-missing","providerID":"openai"}}
openai/gpt-old
{{"id":"gpt-old","providerID":"openai","status":"deprecated"}}
nan/qwen-old
{{"id":"qwen-old","providerID":"nan","status":"inactive"}}
nan/qwen-invalid
{{"id":"qwen-invalid","providerID":"nan","status":{{"value":"{secret}"}}}}
"""
        adapter = OpenCodeAdapter(FakeRunner.stdout(text))
        models = adapter.list_models(self.context)
        self.assertEqual([model.exact_id for model in models], ["openai/gpt-active", "openai/gpt-missing"])
        self.assertIn("inventory_model_status_excluded:openai/gpt-old", adapter.warnings)
        self.assertIn("inventory_model_status_excluded:nan/qwen-old", adapter.warnings)
        self.assertIn("inventory_model_status_invalid:nan/qwen-invalid", adapter.warnings)
        serialized_warnings = json.dumps(adapter.warnings)
        self.assertNotIn("deprecated", serialized_warnings)
        self.assertNotIn("inactive", serialized_warnings)
        self.assertNotIn("sk" + "-status-secret", serialized_warnings)

    def test_verbose_models_report_identity_mismatch_before_inactive_status(self):
        text = """\
openai/gpt-old
{"id":"wrong-id","providerID":"openai","status":"deprecated"}
"""
        adapter = OpenCodeAdapter(FakeRunner.stdout(text))
        self.assertEqual(adapter.list_models(self.context), ())
        self.assertIn("inventory_model_id_mismatch:openai/gpt-old", adapter.warnings)
        self.assertNotIn("inventory_model_status_excluded:openai/gpt-old", adapter.warnings)

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

    def test_list_models_uses_structured_stdout_limit_and_keeps_large_catalog_complete(self):
        ids = tuple(f"openai/gpt-{index:03d}" for index in range(72))
        blocks: list[str] = []
        for exact_id in ids:
            provider, model = exact_id.split("/", 1)
            metadata = {
                "id": model,
                "providerID": provider,
                "family": "gpt",
                "description": "x" * 180,
            }
            blocks.append(f"{exact_id}\n{json.dumps(metadata)}\n")
        verbose = "".join(blocks)
        self.assertGreater(len(verbose), 8192)

        runner = FakeRunner((_command(verbose),))
        adapter = OpenCodeAdapter(runner)
        models = adapter.list_models(self.context)

        self.assertEqual(runner.stdout_limits, [MAX_STDOUT_LIMIT_CHARS])
        parsed_ids = [model.exact_id for model in models]
        self.assertEqual(parsed_ids[0], ids[0])
        self.assertEqual(parsed_ids[-1], ids[-1])

    def test_list_models_warns_when_structured_stdout_is_still_truncated(self):
        text = """\
openai/gpt-first
{"id":"gpt-first","providerID":"openai"}
openai/gpt-second
{"id":"gpt-second","providerID":"openai"}
"""
        runner = FakeRunner((CompletedCommand((), 0, text, "", 1, False, True, False),))
        adapter = OpenCodeAdapter(runner)

        models = adapter.list_models(self.context)

        self.assertEqual([item.exact_id for item in models], ["openai/gpt-first", "openai/gpt-second"])
        self.assertIn("inventory_list_models_truncated", adapter.warnings)

    def test_snapshot_reads_project_agents_and_preserves_only_present_options(self):
        self._write_project_config()
        snapshot = OpenCodeAdapter(FakeRunner.stdout("1.18.18\n")).snapshot(self.context)
        by_agent = {assignment.agent: assignment for assignment in snapshot.current_assignments}
        self.assertEqual(by_agent["worker"].model, "openai/gpt-5.6-terra")
        self.assertEqual(by_agent["worker"].options, {"variant": "high", "steps": 80})
        self.assertEqual(by_agent["reviewer"].options, {"temperature": 0.1})
        self.assertIn("project:opencode.json", snapshot.sources)

    def test_snapshot_honors_xdg_config_home_for_global_opencode_json(self):
        xdg = self.root / "xdg"
        global_config = xdg / "opencode" / "opencode.json"
        assert_test_path(global_config, self.root)
        global_config.parent.mkdir(parents=True)
        global_config.write_text(json.dumps({
            "agent": {"scout": {"model": "openai/gpt-5.6-terra", "variant": "high"}}
        }), encoding="utf-8")
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"XDG_CONFIG_HOME": str(xdg)})

        snapshot = OpenCodeAdapter(FakeRunner.stdout("1.18.18\n")).snapshot(context)

        scout = next(item for item in snapshot.current_assignments if item.agent == "scout")
        self.assertEqual(scout.model, "openai/gpt-5.6-terra")
        self.assertEqual(scout.options, {"variant": "high"})
        self.assertEqual(scout.source, "global:opencode.json")
        self.assertIn("global:opencode.json", snapshot.sources)

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

    def test_snapshot_recursively_prunes_secret_named_keys_from_structural_options(self):
        self._write_project_config(json.dumps({
            "agent": {
                "worker": {
                    "model": "nan/qwen3.6",
                    "textVerbosity": {
                        "safe": "keep",
                        "apiKey": "secret-nested",
                        "nested": [
                            {"token": "tok-secret", "safe": "sibling"},
                            {"authorization": "Bearer secret"},
                            {"list": [{"safe": []}, {"clientSecret": "secret-value"}]},
                        ],
                    },
                    "reasoningEffort": [{"password": "pw-secret", "safe": "low"}, {"credential": "cred-secret"}],
                }
            }
        }))
        snapshot = OpenCodeAdapter(FakeRunner.stdout("1.18.18\n")).snapshot(self.context)
        assignment = snapshot.current_assignments[0].to_dict()
        self.assertEqual(assignment["options"], {
            "reasoningEffort": [{"safe": "low"}, {}],
            "textVerbosity": {
                "nested": [{"safe": "sibling"}, {}, {"list": [{"safe": []}, {}]}],
                "safe": "keep",
            },
        })
        serialized = json.dumps(assignment)
        for secret in ("secret-nested", "tok-secret", "Bearer secret", "secret-value", "pw-secret", "cred-secret"):
            self.assertNotIn(secret, serialized)

    def test_live_check_uses_json_events_supported_variant_and_dedicated_deny_all_agent(self):
        token = "a" * 32
        agent_name = _probe_agent_name(token)
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name),
            _command('{"type":"text","part":{"text":"PONG"}}\n'),
        ))
        model = ModelRecord(
            exact_id="openai/gpt-5.6-terra",
            provider="openai",
            model="gpt-5.6-terra",
            variants=("high", "max"),
        )
        original_env = {
            "OPENCODE_CONFIG_CONTENT": json.dumps({
                "theme": "dark",
                "permission": {"read": "ask"},
                "agent": {
                    "worker": {"model": "openai/gpt-5.6-terra"},
                    "model-optimizer-probe": {"model": "attacker/model", "permission": "allow"},
                },
            }),
            "OPENCODE_PERMISSION": '{"write":"allow"}',
        }
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env=original_env)

        check = self._live_check_with_token(runner, model, "high", "PONG", 60, context, token=token)

        self.assertEqual(check.status, HealthStatus.PASS)
        self.assertEqual(runner.argv[0], ("opencode", "debug", "config"))
        self.assertEqual(runner.stdout_limits[0], MAX_STDOUT_LIMIT_CHARS)
        self.assertEqual(runner.argv[-1], (
            "opencode", "run", "--format", "json", "--model",
            "openai/gpt-5.6-terra", "--variant", "high", "--agent", agent_name,
            "Reply exactly: PONG",
        ))
        self.assertEqual(context.env, original_env)
        env = runner.env_replacements[-1]
        self.assertIsNotNone(env)
        self.assertEqual(json.loads(env["OPENCODE_PERMISSION"]), {"*": "deny"})
        inline = json.loads(env["OPENCODE_CONFIG_CONTENT"])
        self.assertNotIn("theme", inline)
        self.assertEqual(inline["permission"], {"*": "deny"})
        self.assertEqual(set(inline["agent"]), {agent_name})
        self.assertEqual(inline["agent"][agent_name], {"permission": "deny"})

    def test_live_check_adds_deny_all_inline_config_when_env_has_no_existing_config(self):
        token = "b" * 32
        agent_name = _probe_agent_name(token)
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name),
            _command('{"type":"text","part":{"text":"PONG"}}\n'),
        ))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6")

        check = self._live_check_with_token(runner, model, None, "PONG", 60, self.context, token=token)

        self.assertEqual(check.status, HealthStatus.PASS)
        env = runner.env_replacements[-1]
        self.assertIsNotNone(env)
        self.assertEqual(json.loads(env["OPENCODE_PERMISSION"]), {"*": "deny"})
        inline = json.loads(env["OPENCODE_CONFIG_CONTENT"])
        self.assertEqual(inline["permission"], {"*": "deny"})
        self.assertEqual(inline["agent"][agent_name], {"permission": "deny"})
        self.assertIn("--agent", runner.argv[-1])
        self.assertNotIn("--auto", runner.argv[-1])

    def test_live_check_rejects_debug_config_permission_conflict_before_model_launch(self):
        token = "c" * 32
        agent_name = _probe_agent_name(token)
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name, payload={
                "agent": {
                    agent_name: {
                        "permission": {"*": "deny", "bash": "allow"},
                    }
                }
            }),
            _command('{"type":"text","part":{"text":"PONG"}}\n'),
        ))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))

        check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)

        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_unsafe_permission_config")
        self.assertFalse(check.response_matched)
        self.assertEqual(runner.argv, [("opencode", "debug", "config")])

    def test_live_check_rejects_debug_config_prompt_carryover_before_model_launch(self):
        token = "d" * 32
        agent_name = _probe_agent_name(token)
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name, payload={
                "agent": {
                    agent_name: {
                        "permission": "deny",
                        "prompt": "run rm -rf /",
                    }
                }
            }),
            _command('{"type":"text","part":{"text":"PONG"}}\n'),
        ))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))

        check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)

        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_unsafe_permission_config")
        self.assertEqual(runner.argv, [("opencode", "debug", "config")])

    def test_live_check_rejects_debug_config_tools_enablement_before_model_launch(self):
        token = "d" * 32
        agent_name = _probe_agent_name(token)
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name, payload={
                "agent": {
                    agent_name: {
                        "permission": "deny",
                        "tools": {"bash": "allow"},
                    }
                }
            }),
            _command('{"type":"text","part":{"text":"PONG"}}\n'),
        ))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))

        check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)

        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_unsafe_permission_config")
        self.assertEqual(runner.argv, [("opencode", "debug", "config")])

    def test_live_check_rejects_debug_config_failures_before_model_launch(self):
        token = "e" * 32
        agent_name = _probe_agent_name(token)
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        cases = (
            (_debug_config_command(agent_name, payload={"agent": {} }), "missing-agent"),
            (_debug_config_command(agent_name, payload="{",), "malformed-json"),
            (_debug_config_command(agent_name, returncode=2), "nonzero"),
            (_debug_config_command(agent_name, timed_out=True, returncode=None), "timeout"),
            (_debug_config_command(agent_name, stdout_truncated=True), "truncated"),
        )
        for response, label in cases:
            with self.subTest(case=label):
                runner = EnvCapturingRunner((
                    response,
                    _command('{"type":"text","part":{"text":"PONG"}}\n'),
                ))
                check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)
                self.assertEqual(check.status, HealthStatus.FAIL)
                self.assertEqual(check.reason_code, "live_unsafe_permission_config")
                self.assertFalse(check.response_matched)
                self.assertEqual(runner.argv, [("opencode", "debug", "config")])

    def test_live_check_accepts_normalized_deny_permission_and_then_runs_model(self):
        token = "f" * 32
        agent_name = _probe_agent_name(token)
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name, payload={
                "agent": {
                    agent_name: {
                        "permission": {"*": "deny"},
                        "tools": {
                            "bash": "deny",
                            "nested": {"http": False},
                        },
                        "options": {},
                    }
                }
            }),
            _command('{"type":"text","part":{"text":"PONG"}}\n'),
        ))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))

        check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)

        self.assertEqual(check.status, HealthStatus.PASS)
        self.assertEqual([item[:3] for item in runner.argv], [
            ("opencode", "debug", "config"),
            ("opencode", "run", "--format"),
        ])

    def test_live_check_uses_unique_agent_name_per_invocation_with_no_fixed_reuse(self):
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        first_token = "1" * 32
        second_token = "2" * 32
        first_agent = _probe_agent_name(first_token)
        second_agent = _probe_agent_name(second_token)
        runner = EnvCapturingRunner((
            _debug_config_command(first_agent),
            _command('{"type":"text","part":{"text":"PONG"}}\n'),
            _debug_config_command(second_agent),
            _command('{"type":"text","part":{"text":"PONG"}}\n'),
        ))
        adapter = OpenCodeAdapter(runner)

        with patch("helper.adapters.opencode.secrets.token_hex", side_effect=[first_token, second_token]):
            first = adapter.live_check(model, "low", "PONG", 60, self.context)
            second = adapter.live_check(model, "low", "PONG", 60, self.context)

        self.assertEqual(first.status, HealthStatus.PASS)
        self.assertEqual(second.status, HealthStatus.PASS)
        run_agents = [argv[argv.index("--agent") + 1] for argv in runner.argv if argv[:2] == ("opencode", "run")]
        self.assertEqual(len(run_agents), 2)
        self.assertNotEqual(run_agents[0], run_agents[1])
        self.assertTrue(all(name.startswith("model-optimizer-probe-") for name in run_agents))
        self.assertTrue(all(len(name) == len("model-optimizer-probe-") + 32 for name in run_agents))
        self.assertNotIn("model-optimizer-probe", run_agents)

    def test_live_check_debug_config_secret_output_never_leaks_into_health_detail(self):
        token = "9" * 32
        agent_name = _probe_agent_name(token)
        secret = "sk" + "-debug-config-should-not-leak"
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name, payload={
                "agent": {
                    agent_name: {
                        "permission": "deny",
                        "prompt": secret,
                    }
                }
            }),
        ))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))

        check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)

        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_unsafe_permission_config")
        self.assertNotIn(secret, check.detail)

    def test_live_check_omits_malformed_ambient_inline_config_without_leak(self):
        token = "7" * 32
        agent_name = _probe_agent_name(token)
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name),
            _command('{"type":"text","part":{"text":"PONG"}}\n'),
        ))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6")
        secret_config = '{"apiKey":"' + "sk" + '-inline-secret"'
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"OPENCODE_CONFIG_CONTENT": secret_config})

        check = self._live_check_with_token(runner, model, None, "PONG", 60, context, token=token)

        self.assertEqual(check.status, HealthStatus.PASS)
        self.assertEqual(context.env["OPENCODE_CONFIG_CONTENT"], secret_config)
        env = runner.env_replacements[-1]
        self.assertIsNotNone(env)
        self.assertNotIn("sk" + "-inline-secret", json.dumps(env))
        self.assertNotIn("OPENCODE_CONFIG_CONTENT", check.detail)

    def test_error_event_is_fail_even_when_process_exit_is_zero(self):
        token = "a" * 32
        agent_name = _probe_agent_name(token)
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name),
            _command(fixture_text("opencode/live-error.jsonl")),
        ))
        model = ModelRecord(
            exact_id="nan/qwen3.6", provider="nan", model="qwen3.6", variants=("low",),
        )
        check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_runtime_error")
        self.assertIn("Unexpected server error", check.detail)
        self.assertNotIn("ses_fixture", check.detail)
        self.assertNotIn("err_fixture", check.detail)

    def test_error_event_structural_name_maps_known_reason_with_generic_message(self):
        token = "a" * 32
        agent_name = _probe_agent_name(token)
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
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name),
            _command(json.dumps(event) + "\n"),
        ))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_provider_model_not_found")
        self.assertIn("Model lookup failed", check.detail)
        self.assertNotIn("ses_structural_fixture", check.detail)
        self.assertNotIn("err_structural_fixture", check.detail)
        self.assertNotIn("auth.json", check.detail)
        self.assertLessEqual(len(check.detail), 240)

    def test_session_and_ref_redaction_accepts_case_insensitive_dash_or_underscore_forms(self):
        token = "a" * 32
        agent_name = _probe_agent_name(token)
        event = {
            "type": "error",
            "error": {
                "data": {
                    "message": "refs SES-DASH Err_Dash ses_under err-under should be redacted",
                },
            },
        }
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name),
            _command(json.dumps(event) + "\n"),
        ))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_runtime_error")
        for token in ("SES-DASH", "Err_Dash", "ses_under", "err-under"):
            self.assertNotIn(token, check.detail)

    def test_live_event_parser_concatenates_only_text_part_text_for_sentinel(self):
        events = "\n".join((
            '{"type":"text","part":{"text":"PO"}}',
            '{"type":"text","part":{"text":"NG"}}',
            '{"type":"message","text":"PONG should not matter"}',
        ))
        matched, reason = parse_opencode_live_events(events, "PONG")
        self.assertTrue(matched)
        self.assertEqual(reason, "live_sentinel_matched")

    def test_live_event_parser_rejects_empty_sentinel(self):
        matched, reason = parse_opencode_live_events('{"type":"text","part":{"text":"anything"}}\n', "")
        self.assertFalse(matched)
        self.assertEqual(reason, "live_invalid_sentinel")

    def test_live_event_parser_rejects_whitespace_only_sentinel(self):
        matched, reason = parse_opencode_live_events('{"type":"text","part":{"text":"   "}}\n', "   ")
        self.assertFalse(matched)
        self.assertEqual(reason, "live_invalid_sentinel")

    def test_primitive_jsonl_events_are_ignored_without_masking_later_text(self):
        primitive_only = '123\ntrue\n"PONG"\n["PONG"]\n'
        matched, reason = parse_opencode_live_events(primitive_only, "PONG")
        self.assertFalse(matched)
        self.assertEqual(reason, "live_empty_response")

        mixed = primitive_only + '{"type":"text","part":{"text":"PONG"}}\n'
        matched, reason = parse_opencode_live_events(mixed, "PONG")
        self.assertTrue(matched)
        self.assertEqual(reason, "live_sentinel_matched")

    def test_step_start_only_is_empty_response_not_pass(self):
        token = "a" * 32
        agent_name = _probe_agent_name(token)
        runner = EnvCapturingRunner((
            _debug_config_command(agent_name),
            _command('{"type":"step_start","message":"PONG"}\n'),
        ))
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_empty_response")

    def test_unsupported_variant_fails_without_consuming_runner_response(self):
        runner = FakeRunner.stdout("unused")
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        check = OpenCodeAdapter(runner).live_check(model, "max", "PONG", 60, self.context)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_unsupported_variant")
        self.assertEqual(runner.argv, [])

    def test_empty_sentinel_fails_without_consuming_runner_response(self):
        runner = FakeRunner.stdout('{"type":"text","part":{"text":"anything"}}\n')
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        check = OpenCodeAdapter(runner).live_check(model, "low", "", 60, self.context)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_invalid_sentinel")
        self.assertFalse(check.response_matched)
        self.assertEqual(runner.argv, [])

    def test_whitespace_only_sentinel_fails_without_consuming_runner_response(self):
        runner = FakeRunner.stdout('{"type":"text","part":{"text":"   "}}\n')
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        check = OpenCodeAdapter(runner).live_check(model, "low", "   ", 60, self.context)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_invalid_sentinel")
        self.assertFalse(check.response_matched)
        self.assertEqual(runner.argv, [])

    def test_live_nonzero_maps_known_model_errors_to_bounded_reason_codes(self):
        token = "a" * 32
        agent_name = _probe_agent_name(token)
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        cases = (
            ("model_not_supported: nan/qwen3.6", "live_model_not_supported"),
            ("ProviderModelNotFoundError: nan/qwen3.6", "live_provider_model_not_found"),
        )
        for stderr, reason in cases:
            with self.subTest(reason=reason):
                command = type(_command(""))((), 1, "", stderr, 1, False)
                runner = EnvCapturingRunner((_debug_config_command(agent_name), command))
                check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)
                self.assertEqual(check.status, HealthStatus.FAIL)
                self.assertEqual(check.reason_code, reason)
                self.assertLessEqual(len(check.detail), 240)

    def test_timeout_precedes_nonzero_error_and_sentinel_evidence(self):
        token = "a" * 32
        agent_name = _probe_agent_name(token)
        command = type(_command(""))((), 2, fixture_text("opencode/live-error.jsonl") + '{"type":"text","part":{"text":"PONG"}}', "", 1, True)
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        runner = EnvCapturingRunner((_debug_config_command(agent_name), command))
        check = self._live_check_with_token(runner, model, "low", "PONG", 1, self.context, token=token)
        self.assertEqual(check.status, HealthStatus.HANG)
        self.assertEqual(check.reason_code, "live_timeout")

    def test_bounded_log_tail_enriches_fail_but_cannot_turn_it_into_pass(self):
        token = "a" * 32
        agent_name = _probe_agent_name(token)
        log = self.root / ".local" / "share" / "opencode" / "log" / "opencode.log"
        assert_test_path(log, self.root)
        log.parent.mkdir(parents=True)
        log.write_text("token=secret-token\n" + "x" * 400 + "\nProviderModelNotFoundError: missing ses_secret err_secret\n", encoding="utf-8")
        model = ModelRecord("nan/qwen3.6", "nan", "qwen3.6", variants=("low",))
        command = type(_command(""))((), 1, "", "launch failed", 1, False)
        runner = EnvCapturingRunner((_debug_config_command(agent_name), command))
        check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)
        self.assertEqual(check.status, HealthStatus.FAIL)
        self.assertEqual(check.reason_code, "live_provider_model_not_found")
        self.assertIn("ProviderModelNotFoundError", check.detail)
        self.assertNotIn("secret-token", check.detail)
        self.assertNotIn("ses_secret", check.detail)
        self.assertLessEqual(len(check.detail), 240)

    def test_log_tail_uses_bounded_binary_read_and_tail_marker(self):
        token = "a" * 32
        agent_name = _probe_agent_name(token)
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
        runner = EnvCapturingRunner((_debug_config_command(agent_name), command))
        with patch.object(Path, "read_text", side_effect=AssertionError("full log read forbidden")):
            check = self._live_check_with_token(runner, model, "low", "PONG", 60, self.context, token=token)
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
            _command(fixture_text("opencode/auth-list.txt") + '{"apiKey":"sk" + "-do-not-leak"} api\n'),
        ))
        inventory = OpenCodeAdapter(runner).inventory(self.context)
        serialized = json.dumps(inventory.to_dict())
        self.assertNotIn("auth.json", serialized)
        self.assertNotIn("sk" + "-do-not-leak", serialized)
        self.assertNotIn("~/.local/share/opencode", serialized)

    def _role_eval_request(self):
        workspace_root = self.root / "eval-workspace"
        workspace_root.mkdir()
        (workspace_root / "src").mkdir()
        observed_at = datetime.now(timezone.utc).replace(microsecond=0)
        executable_identity = "bwrap:/fake/bwrap:1:2:3:sha256:" + ("0" * 64)
        profile_identity = f"bwrap:{workspace_root.resolve()}:network=none:env=minimal"
        outside_probe = workspace_root.resolve().parent / ".model-optimizer-outside-token-opencode.txt"
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
                    "/fake/bwrap",
                    "--unshare-net",
                    "--bind",
                    str(workspace_root.resolve()),
                    str(workspace_root.resolve()),
                    "--chdir",
                    str(workspace_root.resolve()),
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
        workspace = PreparedWorkspace(workspace_root, "token-opencode", SandboxAttestation(
            backend="bwrap",
            workspace_root=str(workspace_root.resolve()),
            workspace_token="token-opencode",
            profile_identity=profile_identity,
            profile_digest=sandbox_attestation_digest("bwrap", workspace_root, "token-opencode", executable_identity, profile_identity, observations),
            observed_at=observed_at.isoformat().replace("+00:00", "Z"),
            probe_observations=observations,
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
        model = ModelRecord("openai/gpt-5.6-terra", "openai", "gpt-5.6-terra", variants=("high",), tool_call=True)
        route = RouteKey(RuntimeKind.OPENCODE, "1.18.18", "openai/gpt-5.6-terra", "high")
        agent = AgentContract(
            name="worker",
            description="",
            mode=None,
            model="openai/gpt-5.6-terra",
            effort="high",
            tools=("read", "edit"),
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
            required_tools=("read", "edit"),
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

    def test_opencode_provider_auth_matrix_preserves_only_exact_route_provider_auth(self):
        xdg_config = self.root / "xdg-config"
        xdg_data = self.root / "xdg-data"
        env = {
            "OPENAI_API_KEY": "openai-token",
            "OPENCODE_TOKEN": "opencode-token",
            "NAN_API_KEY": "nan-token",
            "MINIMAX_API_KEY": "minimax-token",
            "ZAI_API_KEY": "zai-token",
            "OPENCODE_CONFIG_CONTENT": "hostile",
        }
        openai = isolated_opencode_env(env, xdg_config, xdg_data, "openai")
        self.assertEqual(openai.get("OPENAI_API_KEY"), "openai-token")
        self.assertNotIn("OPENCODE_TOKEN", openai)
        self.assertNotIn("OPENCODE_CONFIG_CONTENT", openai)
        nan = isolated_opencode_env(env, xdg_config, xdg_data, "nan")
        self.assertEqual(nan.get("OPENCODE_TOKEN"), "opencode-token")
        self.assertEqual(nan.get("NAN_API_KEY"), "nan-token")
        self.assertNotIn("OPENAI_API_KEY", nan)
        minimax = isolated_opencode_env(env, xdg_config, xdg_data, "minimax-coding-plan")
        self.assertEqual(minimax.get("MINIMAX_API_KEY"), "minimax-token")
        self.assertNotIn("OPENAI_API_KEY", minimax)
        zai = isolated_opencode_env(env, xdg_config, xdg_data, "zai-coding-plan")
        self.assertEqual(zai.get("ZAI_API_KEY"), "zai-token")
        self.assertNotIn("OPENAI_API_KEY", zai)
        self.assertIsNone(isolated_opencode_env(env, xdg_config, xdg_data, "unknown-provider"))
        self.assertIsNone(isolated_opencode_env({}, xdg_config, xdg_data, "openai"))

    def test_effective_config_matrix_rejects_execution_affecting_top_level_drift(self):
        request = self._role_eval_request()
        agent_name = "model-optimizer-eval-" + "d" * 32
        expected = opencode_eval_config(request, agent_name)
        safe = {
            **expected,
            "mode": {},
            "username": "unknown",
            "plugin": [],
            "plugins": [],
            "instructions": [],
            "mcp": {},
            "tool": {},
            "tools": {},
            "provider": {},
            "model": {},
            "share": "manual",
            "autoshare": False,
            "compaction": {},
        }
        self.assertTrue(effective_config_matches(safe, expected, agent_name))
        for key, value in {
            "mode": {"build": True},
            "username": "attacker",
            "plugin": ["ambient"],
            "plugins": ["ambient"],
            "instructions": ["do unsafe thing"],
            "mcp": {"server": "ambient"},
            "tool": {"bash": "allow"},
            "tools": {"bash": "allow"},
            "provider": {"openai": {}},
            "model": {"openai/gpt": {}},
            "share": "auto",
            "autoshare": True,
            "compaction": {"enabled": True},
        }.items():
            with self.subTest(key=key):
                hostile = dict(safe)
                hostile[key] = value
                self.assertFalse(effective_config_matches(hostile, expected, agent_name))

    def test_role_eval_uses_isolated_pure_config_and_trusted_manifest_tests(self):
        request = self._role_eval_request()
        agent_name = "model-optimizer-eval-" + "a" * 32
        debug_payload = {
            "permission": {"*": "deny", "external_directory": "deny"},
            "agent": {
                agent_name: {
                    "description": "isolated model optimizer evaluation",
                    "prompt": request.agent.body,
                    "model": request.route.model,
                    "variant": request.route.effort,
                    "permission": {
                        "*": "deny",
                        "external_directory": "deny",
                        "read": {"*": "deny", f"{request.workspace.root.resolve()}/**": "allow"},
                        "edit": {"*": "deny", f"{(request.workspace.root / 'src').resolve()}/**": "allow"},
                        "bash": "deny",
                    },
                }
            },
        }
        runner = EnvCapturingRunner((
            _command("1.18.18\n"),
            _command(json.dumps(debug_payload)),
            _command('{"type":"tool_use","part":{"type":"tool","tool":"edit","state":{"status":"completed","input":{"path":"src/out.txt"}}}}\n'),
            _command("tests ok"),
            _command("?? src/out.txt\x00"),
        ))
        original_env = {
            "OPENCODE_CONFIG_CONTENT": json.dumps({"plugin": ["ambient"], "permission": {"bash": "allow"}}),
            "OPENAI_API_KEY": "runtime-auth-token",
        }
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env=original_env)
        with patch("helper.adapters.opencode.secrets.token_hex", return_value="a" * 32), patch("helper.evaluator.shutil.which", side_effect=lambda name: f"/fake/{name}" if name == "bwrap" else None):
            result = OpenCodeAdapter(runner).role_eval(request, context)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(context.env, original_env)
        self.assertEqual(runner.argv[0], ("opencode", "--version"))
        self.assertEqual(runner.argv[1], ("opencode", "debug", "config", "--pure"))
        self.assertEqual(runner.argv[2], (
            "opencode", "run", "--pure", "--format", "json", "--model", request.route.model,
            "--variant", request.route.effort, "--agent", agent_name, "--dir", str(request.workspace.root), request.task,
        ))
        debug_env = runner.env_replacements[1]
        self.assertIsNotNone(debug_env)
        self.assertIn("XDG_CONFIG_HOME", debug_env)
        self.assertIn("XDG_DATA_HOME", debug_env)
        self.assertNotIn("OPENCODE_CONFIG_CONTENT", debug_env)
        self.assertNotIn("OPENCODE_PERMISSION", debug_env)
        self.assertEqual(debug_env["OPENAI_API_KEY"], "runtime-auth-token")
        self.assertNotIn("OPENCODE_TOKEN", debug_env)
        config_path = Path(debug_env["XDG_CONFIG_HOME"]) / "opencode" / "opencode.json"
        self.assertFalse(config_path.exists(), "isolated config root should be cleaned after role_eval")
        self.assertEqual(result.audit.command_runs[-1].command_id, "cmd-test")
        self.assertEqual(runner.argv[3][0], "/fake/bwrap")
        self.assertIn("--unshare-net", runner.argv[3])
        self.assertEqual(runner.argv[-1], ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"))
        self.assertNotIn(None, runner.stdout_limits)

    def test_role_eval_manifest_timeout_is_hang(self):
        request = self._role_eval_request()
        agent_name = "model-optimizer-eval-" + "e" * 32
        debug_payload = {
            "permission": {"*": "deny", "external_directory": "deny"},
            "agent": {agent_name: {"description": "isolated model optimizer evaluation", "prompt": request.agent.body, "model": request.route.model, "variant": request.route.effort, "permission": {"*": "deny", "external_directory": "deny", "read": {"*": "deny", f"{request.workspace.root.resolve()}/**": "allow"}, "edit": {"*": "deny", f"{(request.workspace.root / 'src').resolve()}/**": "allow"}, "bash": "deny"}}},
        }
        manifest_timeout = CompletedCommand((), None, "", "", 31, True, False, False)
        runner = EnvCapturingRunner((_command("1.18.18\n"), _command(json.dumps(debug_payload)), _command('{"type":"tool_use","part":{"type":"tool","tool":"edit","state":{"status":"completed","input":{"path":"src/out.txt"}}}}\n'), manifest_timeout, _command("?? src/out.txt\x00")))
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"OPENAI_API_KEY": "runtime-auth-token"})
        with patch("helper.adapters.opencode.secrets.token_hex", return_value="e" * 32):
            result = OpenCodeAdapter(runner).role_eval(request, context)
        self.assertEqual(result.status, "HANG")
        self.assertIn("eval_timeout", result.reason_codes)

    def test_role_eval_runtime_timeout_is_hang_before_manifest(self):
        request = self._role_eval_request()
        agent_name = "model-optimizer-eval-" + "1" * 32
        debug_payload = {
            "permission": {"*": "deny", "external_directory": "deny"},
            "agent": {agent_name: {"description": "isolated model optimizer evaluation", "prompt": request.agent.body, "model": request.route.model, "variant": request.route.effort, "permission": {"*": "deny", "external_directory": "deny", "read": {"*": "deny", f"{request.workspace.root.resolve()}/**": "allow"}, "edit": {"*": "deny", f"{(request.workspace.root / 'src').resolve()}/**": "allow"}, "bash": "deny"}}},
        }
        runtime_timeout = CompletedCommand((), None, "", "", 31, True, False, False)
        runner = EnvCapturingRunner((_command("1.18.18\n"), _command(json.dumps(debug_payload)), runtime_timeout))
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"OPENAI_API_KEY": "runtime-auth-token"})
        with patch("helper.adapters.opencode.secrets.token_hex", return_value="1" * 32):
            result = OpenCodeAdapter(runner).role_eval(request, context)
        self.assertEqual(result.status, "HANG")
        self.assertIn("eval_timeout", result.reason_codes)
        self.assertEqual(runner.argv, [
            ("opencode", "--version"),
            ("opencode", "debug", "config", "--pure"),
            ("opencode", "run", "--pure", "--format", "json", "--model", request.route.model, "--variant", request.route.effort, "--agent", agent_name, "--dir", str(request.workspace.root), request.task),
        ])

    def test_role_eval_required_command_failure_maps_to_fail(self):
        request = self._role_eval_request()
        agent_name = "model-optimizer-eval-" + "2" * 32
        debug_payload = {
            "permission": {"*": "deny", "external_directory": "deny"},
            "agent": {agent_name: {"description": "isolated model optimizer evaluation", "prompt": request.agent.body, "model": request.route.model, "variant": request.route.effort, "permission": {"*": "deny", "external_directory": "deny", "read": {"*": "deny", f"{request.workspace.root.resolve()}/**": "allow"}, "edit": {"*": "deny", f"{(request.workspace.root / 'src').resolve()}/**": "allow"}, "bash": "deny"}}},
        }
        runner = EnvCapturingRunner((_command("1.18.18\n"), _command(json.dumps(debug_payload)), _command('{"type":"tool_use","part":{"type":"tool","tool":"edit","state":{"status":"completed","input":{"path":"src/out.txt"}}}}\n'), _command("tests failed", returncode=2), _command("?? src/out.txt\x00")))
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"OPENAI_API_KEY": "runtime-auth-token"})
        with patch("helper.adapters.opencode.secrets.token_hex", return_value="2" * 32):
            result = OpenCodeAdapter(runner).role_eval(request, context)
        self.assertEqual(result.status, "FAIL")
        self.assertIn("eval_required_command_failed", result.reason_codes)

    def test_role_eval_cleanup_matrix_preserves_primary_reason(self):
        request = self._role_eval_request()

        def debug_payload(agent_name: str) -> dict[str, object]:
            return {
                "permission": {"*": "deny", "external_directory": "deny"},
                "agent": {
                    agent_name: {
                        "description": "isolated model optimizer evaluation",
                        "prompt": request.agent.body,
                        "model": request.route.model,
                        "variant": request.route.effort,
                        "permission": {
                            "*": "deny",
                            "external_directory": "deny",
                            "read": {"*": "deny", f"{request.workspace.root.resolve()}/**": "allow"},
                            "edit": {"*": "deny", f"{(request.workspace.root / 'src').resolve()}/**": "allow"},
                            "bash": "deny",
                        },
                    }
                },
            }

        class StatusErrorRunner(EnvCapturingRunner):
            def run(self, argv, timeout, cwd, env_overlay=None, *, stdout_limit=None, env_replacement=None, stdin_text=None):
                if tuple(argv) == ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"):
                    raise OSError("status failed")
                return super().run(argv, timeout, cwd, env_overlay=env_overlay, stdout_limit=stdout_limit, env_replacement=env_replacement, stdin_text=stdin_text)

        cases = (
            (
                "config_write",
                EnvCapturingRunner((_command("1.18.18\n"),)),
                patch("pathlib.Path.write_bytes", side_effect=OSError("write failed")),
                "eval_opencode_config_write_failed",
                "3" * 32,
            ),
            (
                "debug",
                EnvCapturingRunner((_command("1.18.18\n"), _command("{", returncode=0))),
                None,
                "eval_opencode_effective_config_mismatch",
                "4" * 32,
            ),
            (
                "run",
                EnvCapturingRunner((_command("1.18.18\n"), _command(json.dumps(debug_payload("model-optimizer-eval-" + "5" * 32))), _command("runtime boom", returncode=2))),
                None,
                "eval_runtime_nonzero",
                "5" * 32,
            ),
            (
                "manifest",
                EnvCapturingRunner((_command("1.18.18\n"), _command(json.dumps(debug_payload("model-optimizer-eval-" + "6" * 32))), _command('{"type":"tool_use","part":{"type":"tool","tool":"edit","state":{"status":"completed","input":{"path":"src/out.txt"}}}}\n'), _command("tests failed", returncode=2), _command("?? src/out.txt\x00"))),
                None,
                "eval_required_command_failed",
                "6" * 32,
            ),
            (
                "status",
                StatusErrorRunner((_command("1.18.18\n"), _command(json.dumps(debug_payload("model-optimizer-eval-" + "7" * 32))), _command('{"type":"tool_use","part":{"type":"tool","tool":"edit","state":{"status":"completed","input":{"path":"src/out.txt"}}}}\n'), _command("tests ok"))),
                None,
                "eval_opencode_runtime_exception",
                "7" * 32,
            ),
        )

        for label, runner, primary_patch, primary_reason, token in cases:
            with self.subTest(case=label):
                context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"OPENAI_API_KEY": "runtime-auth-token"})
                token_patch = patch("helper.adapters.opencode.secrets.token_hex", return_value=token)
                cleanup_patch = patch("helper.adapters.opencode.shutil.rmtree", side_effect=OSError("cleanup failed"))
                with token_patch, cleanup_patch:
                    if primary_patch is None:
                        result = OpenCodeAdapter(runner).role_eval(request, context)
                    else:
                        with primary_patch:
                            result = OpenCodeAdapter(runner).role_eval(request, context)
                self.assertEqual(result.status, "INCONCLUSIVE")
                self.assertIn(primary_reason, result.reason_codes)
                self.assertIn("eval_opencode_cleanup_failed", result.reason_codes)

    def test_role_eval_cleanup_failure_is_explicit_inconclusive_reason(self):
        request = self._role_eval_request()
        agent_name = "model-optimizer-eval-" + "f" * 32
        debug_payload = {
            "permission": {"*": "deny", "external_directory": "deny"},
            "agent": {agent_name: {"description": "isolated model optimizer evaluation", "prompt": request.agent.body, "model": request.route.model, "variant": request.route.effort, "permission": {"*": "deny", "external_directory": "deny", "read": {"*": "deny", f"{request.workspace.root.resolve()}/**": "allow"}, "edit": {"*": "deny", f"{(request.workspace.root / 'src').resolve()}/**": "allow"}, "bash": "deny"}}},
        }
        runner = EnvCapturingRunner((_command("1.18.18\n"), _command(json.dumps(debug_payload)), _command('{"type":"tool_use","part":{"type":"tool","tool":"edit","state":{"status":"completed","input":{"path":"src/out.txt"}}}}\n'), _command("tests ok"), _command("?? src/out.txt\x00")))
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"OPENAI_API_KEY": "runtime-auth-token"})
        with patch("helper.adapters.opencode.secrets.token_hex", return_value="f" * 32), patch("helper.adapters.opencode.shutil.rmtree", side_effect=OSError("cleanup failed")):
            result = OpenCodeAdapter(runner).role_eval(request, context)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertIn("eval_opencode_cleanup_failed", result.reason_codes)

    def test_role_eval_cleans_isolated_roots_when_debug_raises(self):
        request = self._role_eval_request()
        class RaisingDebugRunner(EnvCapturingRunner):
            def run(self, argv, timeout, cwd, env_overlay=None, *, stdout_limit=None, env_replacement=None, stdin_text=None):
                self.argv.append(tuple(argv))
                self.stdout_limits.append(stdout_limit)
                self.env_overlays.append(dict(env_overlay or {}))
                self.env_replacements.append(dict(env_replacement) if env_replacement is not None else None)
                self.cwd_values.append(Path(cwd))
                if tuple(argv) == ("opencode", "debug", "config", "--pure"):
                    raise OSError("debug failed")
                return super().run(argv, timeout, cwd, env_overlay=env_overlay, stdout_limit=stdout_limit, env_replacement=env_replacement, stdin_text=stdin_text)
        runner = RaisingDebugRunner((_command("1.18.18\n"),))
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"OPENAI_API_KEY": "runtime-auth-token"})
        with patch("helper.adapters.opencode.secrets.token_hex", return_value="c" * 32):
            result = OpenCodeAdapter(runner).role_eval(request, context)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertIn("eval_opencode_runtime_exception", result.reason_codes)
        debug_env = next(env for env in runner.env_replacements if env and "XDG_CONFIG_HOME" in env)
        self.assertFalse((Path(debug_env["XDG_CONFIG_HOME"]) / "opencode" / "opencode.json").exists())
        self.assertFalse(Path(debug_env["XDG_DATA_HOME"]).exists())

    def test_role_eval_rejects_hostile_effective_global_config_before_launch(self):
        request = self._role_eval_request()
        agent_name = "model-optimizer-eval-" + "b" * 32
        hostile = {"agent": {agent_name: {"prompt": request.agent.body, "model": request.route.model, "variant": request.route.effort, "permission": {"bash": "allow"}}}}
        runner = EnvCapturingRunner((_command("1.18.18\n"), _command(json.dumps(hostile)),))
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"OPENAI_API_KEY": "runtime-auth-token"})
        with patch("helper.adapters.opencode.secrets.token_hex", return_value="b" * 32):
            result = OpenCodeAdapter(runner).role_eval(request, context)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertIn("eval_opencode_effective_config_mismatch", result.reason_codes)
        self.assertEqual(runner.argv, [("opencode", "--version"), ("opencode", "debug", "config", "--pure")])

    def test_role_eval_status_collection_exception_preserves_runtime_exception_reason(self):
        request = self._role_eval_request()
        agent_name = "model-optimizer-eval-" + "9" * 32
        debug_payload = {
            "permission": {"*": "deny", "external_directory": "deny"},
            "agent": {agent_name: {"description": "isolated model optimizer evaluation", "prompt": request.agent.body, "model": request.route.model, "variant": request.route.effort, "permission": {"*": "deny", "external_directory": "deny", "read": {"*": "deny", f"{request.workspace.root.resolve()}/**": "allow"}, "edit": {"*": "deny", f"{(request.workspace.root / 'src').resolve()}/**": "allow"}, "bash": "deny"}}},
        }

        class StatusErrorRunner(EnvCapturingRunner):
            def run(self, argv, timeout, cwd, env_overlay=None, *, stdout_limit=None, env_replacement=None, stdin_text=None):
                if tuple(argv) == ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"):
                    raise OSError("status failed")
                return super().run(argv, timeout, cwd, env_overlay=env_overlay, stdout_limit=stdout_limit, env_replacement=env_replacement, stdin_text=stdin_text)

        runner = StatusErrorRunner((_command("1.18.18\n"), _command(json.dumps(debug_payload)), _command('{"type":"tool_use","part":{"type":"tool","tool":"edit","state":{"status":"completed","input":{"path":"src/out.txt"}}}}\n'), _command("tests ok")))
        context = RuntimeContext(home=self.root, cwd=self.context.cwd, env={"OPENAI_API_KEY": "runtime-auth-token"})
        with patch("helper.adapters.opencode.secrets.token_hex", return_value="9" * 32):
            result = OpenCodeAdapter(runner).role_eval(request, context)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertIn("eval_opencode_runtime_exception", result.reason_codes)

    def test_reload_semantics_reports_restart_required_for_config_changes(self):
        semantics = OpenCodeAdapter(FakeRunner.stdout("1.18.18\n")).reload_semantics(self.context)
        self.assertEqual(semantics["config_changes"], "restart required")
        self.assertIn("opencode.json", semantics["applies_to"])


if __name__ == "__main__":
    unittest.main()
