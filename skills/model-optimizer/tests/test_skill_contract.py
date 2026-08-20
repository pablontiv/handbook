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


class SkillContractTests(unittest.TestCase):
    def test_frontmatter_is_trigger_only_and_valid(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?s)^---\nname: model-optimizer\ndescription: Use when .+?\n---")
        description = re.search(r"description: (.+)", text).group(1)
        self.assertLessEqual(len(description), 500)
        self.assertNotIn("inventory then", description.lower())

    def test_skill_requires_runtime_local_live_authority_and_approval(self):
        text = SKILL.read_text(encoding="utf-8")
        for phrase in (
            "Catalog is not a live response",
            "exact runtime model ID",
            "different model families",
            "before/after",
            "explicit approval",
            "post-reload",
        ):
            self.assertIn(phrase, text)

    def test_skill_invokes_only_read_only_helper_commands(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("model_optimizer.py inventory", text)
        self.assertIn("model_optimizer.py check", text)
        self.assertRegex(text, r"model_optimizer\.py check .+ --timeout \d+")
        self.assertNotRegex(text, r"model_optimizer\.py\s+(apply|write|configure)")


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
