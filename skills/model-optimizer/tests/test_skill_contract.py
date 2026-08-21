import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.pressure import run_pressure


SKILL = Path(__file__).parents[1] / "SKILL.md"
REFERENCES = SKILL.parent / "references"
PRESSURE = SKILL.parent / "tests" / "pressure"


class SkillContractTests(unittest.TestCase):
    def test_frontmatter_is_trigger_only_and_valid(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?s)^---\nname: model-optimizer\ndescription: Use when .+?\n---")
        description = re.search(r"description: (.+)", text).group(1)
        self.assertLessEqual(len(description), 500)
        self.assertNotIn("inventory then", description.lower())

    def test_skill_requires_concise_task6_workflow(self):
        text = SKILL.read_text(encoding="utf-8")
        for phrase in (
            "one logical optimize flow",
            "at most four",
            "tool-confined role evaluation",
            "FAMILY_PROXY",
            "SOURCE_UNAVAILABLE",
            "retain the incumbent",
            "ABSTAIN",
            "explicit approval",
            "restore the backup",
        ):
            self.assertIn(phrase, text)
        expected_order = (
            "detect Pi/OpenCode",
            "inventory and delta",
            "scope precedence",
            "derive requirements",
            "live-check incumbent",
            "bounded benchmark sources",
            "tool-confined role evaluation",
            "concise proposal",
            "explicit approval",
            "backup, apply minimally, validate, reload",
        )
        position = -1
        for phrase in expected_order:
            found = text.find(phrase)
            self.assertGreater(found, position, phrase)
            position = found

    def test_skill_invokes_existing_read_only_helper_commands_only(self):
        text = SKILL.read_text(encoding="utf-8")
        for command in (
            "model_optimizer.py inventory",
            "model_optimizer.py check",
            "model_optimizer.py evaluate",
            "model_optimizer.py cache-benchmark",
        ):
            self.assertIn(command, text)
        self.assertRegex(text, r"model_optimizer\.py check .+ --timeout \d+")
        self.assertNotRegex(text, r"model_optimizer\.py\s+(apply|write|configure)")

    def test_references_cover_contracts_benchmarks_and_archetype_fallbacks(self):
        contracts = (REFERENCES / "contracts.md").read_text(encoding="utf-8")
        flow = (REFERENCES / "optimization-flow.md").read_text(encoding="utf-8")
        registry = (REFERENCES / "benchmark-sources.md").read_text(encoding="utf-8")
        self.assertIn("model-optimizer.inventory/v1", contracts)
        self.assertIn("model-optimizer.health/v1", contracts)
        self.assertIn("model-optimizer.evaluation/v1", contracts)
        self.assertIn("cache-benchmark", contracts)
        for code in ("0", "2", "3", "4", "5", "6"):
            self.assertIn(f"`{code}`", contracts)
        self.assertIn("The helper never authorizes configuration mutation", contracts)
        for source in (
            "Terminal-Bench latest stable",
            "Terminal-Bench 2.1",
            "Terminal-Bench 3",
            "SWE-bench Pro",
            "SWE-bench Verified Bash Only",
            "Aider Polyglot",
            "METR Time Horizon",
            "SWE-bench Multilingual and Multimodal",
            "ProgramBench",
            "LiveBench",
            "CodeClash",
            "Artificial Analysis",
        ):
            self.assertIn(source, registry)
        for phrase in ("identity", "harness", "effort", "date", "availability", "SOURCE_UNAVAILABLE", "never proof of `ABSENT`"):
            self.assertIn(phrase, registry)
        for archetype in (
            "mechanical",
            "integration",
            "debugger",
            "architecture",
            "reviewer",
            "router/delegator",
            "researcher",
            "scout",
            "context-builder",
        ):
            self.assertIn(archetype, flow)
        self.assertIn("ask the user for one representative task", flow)
        self.assertIn("abstain until supplied", flow)

    def test_public_proposal_and_internal_approval_payload_are_separated(self):
        flow = (REFERENCES / "optimization-flow.md").read_text(encoding="utf-8")
        proposal_match = re.search(r"```proposal\n(?P<body>.*?)\n```", flow, re.DOTALL)
        self.assertIsNotNone(proposal_match, "optimization-flow.md must include a proposal example")
        proposal = proposal_match.group("body")
        allowed_labels = {
            "agent",
            "current_model",
            "current_effort",
            "recommended_model",
            "recommended_effort",
            "reason",
            "uncertainty_or_exclusion",
            "operational_trade_off",
        }
        labels = {line.split(":", 1)[0].strip() for line in proposal.splitlines() if ":" in line}
        self.assertEqual(labels, allowed_labels)
        self.assertIn("recommended_effort", proposal)
        for forbidden in (
            "config_path",
            "apply_target",
            "source_path",
            "cache_key",
            "inventory.json",
            "health.json",
            "evaluation.json",
            "state.json",
            "artifact",
            "plumbing",
        ):
            self.assertNotIn(forbidden, proposal)
        payload_match = re.search(r"```approval-payload\n(?P<body>.*?)\n```", flow, re.DOTALL)
        self.assertIsNotNone(payload_match, "optimization-flow.md must include an internal approval payload example")
        payload = payload_match.group("body")
        self.assertIn("exact_apply_target", payload)
        self.assertIn("source_digest", payload)

    def test_pressure_scenarios_have_executable_assertions(self):
        scenarios = json.loads((PRESSURE / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
        expected_ids = {
            "new-api-key-no-approval",
            "family-benchmark-opaque-alias",
            "stale-cache-current-live-fail",
            "all-candidates-tie-healthy-incumbent",
            "new-agent-no-objective-evaluator",
            "benchmark-site-unavailable",
            "one-provider-fails-unrelated-agents-optimizable",
            "approved-proposal-post-reload-agent-path-fails",
            "pi-ambient-extension-prompt-injection",
            "opencode-ambient-config-permission-escalation",
            "mutation-fixture-no-supported-sandbox",
            "rollback-restores-bytes-runtime-verification-fails",
        }
        self.assertEqual({scenario["id"] for scenario in scenarios}, expected_ids)
        for scenario in scenarios:
            self.assertTrue(scenario.get("required"), scenario["id"])
            self.assertTrue(scenario.get("forbidden"), scenario["id"])
        self.assertTrue((PRESSURE / "assert_pressure.py").exists())


class PressureHarnessTests(unittest.TestCase):
    def test_skill_content_is_injected_while_runtime_skill_loading_stays_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scenarios = root / "scenarios.json"
            skill = root / "SKILL.md"
            output = root / "run.jsonl"
            scenarios.write_text(json.dumps({"scenarios": [{"id": "pressure", "prompt": "Hurry."}]}), encoding="utf-8")
            skill.write_text("BINDING SKILL CONTENT", encoding="utf-8")
            argv = ["run_pressure.py", "--scenarios", str(scenarios), "--skill", str(skill), "--output", str(output)]
            environ = {**os.environ, "MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON": '["pi","--no-skills"]'}
            completed = SimpleNamespace(returncode=0, stdout="ok", stderr="")
            with patch.object(sys, "argv", argv), patch.dict(os.environ, environ, clear=True), patch.object(
                run_pressure.subprocess, "run", return_value=completed
            ) as invoked:
                self.assertEqual(run_pressure.main(), 0)
        command = invoked.call_args.args[0]
        self.assertEqual(command[:2], ["pi", "--no-skills"])
        self.assertNotIn("--skill", command)
        self.assertIn("BINDING SKILL CONTENT", command[-1])
        self.assertIn("Hurry.", command[-1])

    def test_pressure_assertion_script_accepts_required_markers_and_rejects_forbidden_markers(self):
        from tests.pressure import assert_pressure

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scenarios = root / "scenarios.json"
            results = root / "results.jsonl"
            scenarios.write_text(json.dumps({
                "scenarios": [{
                    "id": "case",
                    "required": ["explicit-approval", "no-apply"],
                    "forbidden": ["applied-success"],
                    "prompt": "irrelevant",
                }]
            }), encoding="utf-8")
            results.write_text(json.dumps({
                "scenario": "case",
                "returncode": 0,
                "stdout": "No configuration was changed. Explicit approval is required before writes.",
                "stderr": "",
            }) + "\n", encoding="utf-8")
            self.assertEqual(assert_pressure.main(["--scenarios", str(scenarios), "--results", str(results)]), 0)
            results.write_text(json.dumps({
                "scenario": "case",
                "returncode": 0,
                "stdout": "Explicit approval is required; successfully applied the config.",
                "stderr": "",
            }) + "\n", encoding="utf-8")
            self.assertEqual(assert_pressure.main(["--scenarios", str(scenarios), "--results", str(results)]), 1)
