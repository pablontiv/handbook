import hashlib
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


ROOT = Path(__file__).parents[1]
SKILL = ROOT / "SKILL.md"
LICENSE = ROOT / "LICENSE"
SCENARIOS = ROOT / "tests" / "pressure" / "scenarios.json"


class SkillContractTests(unittest.TestCase):
    def test_frontmatter_declares_personal_and_upstream_provenance_as_strings(self):
        text = SKILL.read_text(encoding="utf-8")
        expected = {
            "name": "systemic-issue-triage",
            "license": "Apache-2.0",
            "author": "pablontiv",
            "created": "2026-08-20",
            "updated": "2026-08-27",
            "version": "0.2.0",
            "upstream-author": "Alan-TheGentleman",
            "upstream-repository": "https://github.com/Gentleman-Programming/gentle-ai",
            "upstream-commit": "d1e1777faafc91a34656ba94bd712972dbe427a1",
            "ownership": "personal",
        }
        for key, value in expected.items():
            self.assertRegex(text, rf'(?m)^\s*{re.escape(key)}: "?{re.escape(value)}"?$')
        description_match = re.search(r'(?m)^description: "(.+)"$', text)
        self.assertIsNotNone(description_match)
        assert description_match is not None
        description = description_match.group(1)
        self.assertIn("Use when", description)
        self.assertLessEqual(len(description), 1024)

    def test_input_contract_binds_triage_to_git_repository_containing_cwd(self):
        text = SKILL.read_text(encoding="utf-8")
        input_contract = text.split("## Input Contract", 1)[1].split("## Root-Class Buckets", 1)[0]
        for phrase in (
            "git rev-parse --show-toplevel",
            "repository that contains the current working directory",
            "sole repository scope",
            "cannot be resolved unambiguously",
            "Do not substitute",
        ):
            self.assertIn(phrase, input_contract)

    def test_skill_preserves_root_class_clustering_and_named_evidence(self):
        text = SKILL.read_text(encoding="utf-8")
        for phrase in (
            "Bucket A",
            "Bucket B",
            "Bucket C",
            "Bucket D",
            "Bucket E",
            "root-cause cluster",
            "named test evidence",
            "mechanism as a hypothesis",
            "One root cause produces one cluster",
        ):
            self.assertIn(phrase, text)

    def test_output_names_brainstorming_and_stops_before_delivery(self):
        text = SKILL.read_text(encoding="utf-8")
        output = text.split("## Output Contract", 1)[1].split("## Scope Boundary", 1)[0]
        boundary = text.split("## Scope Boundary", 1)[1]
        for phrase in (
            "verified source issues",
            "bucket counts",
            "root-cause clusters",
            "initiative boundary",
            "priority and dependency evidence",
            "urgent flags",
            "brainstorming",
        ):
            self.assertIn(phrase, output)
        for phrase in (
            "Do not design",
            "Do not plan",
            "Do not implement",
            "Do not mutate issues",
        ):
            self.assertIn(phrase, boundary)

    def test_pressure_schema_covers_all_required_boundaries(self):
        payload = json.loads(SCENARIOS.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "systemic-issue-triage.pressure-scenarios/v1")
        self.assertEqual(len(payload["scenarios"]), 6)
        required = {item for scenario in payload["scenarios"] for item in scenario["required"]}
        self.assertTrue(
            {
                "one-root-cluster",
                "mechanism-is-hypothesis",
                "brainstorming-handoff",
                "no-implementation",
                "cwd-git-root",
                "sole-repository-scope",
                "fail-closed-outside-git",
            }
            <= required
        )

    def test_apache_license_is_canonical(self):
        content = LICENSE.read_bytes()
        self.assertIn(b"Apache License", content)
        self.assertIn(b"Version 2.0, January 2004", content)
        self.assertEqual(hashlib.sha256(content).hexdigest(), "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30")


class PressureHarnessTests(unittest.TestCase):
    def test_runner_injects_skill_while_runtime_discovery_stays_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scenarios = root / "scenarios.json"
            skill = root / "SKILL.md"
            output = root / "run.jsonl"
            scenarios.write_text(json.dumps({"scenarios": [{"id": "pressure", "prompt": "Patch now."}]}), encoding="utf-8")
            skill.write_text("BINDING TRIAGE SKILL", encoding="utf-8")
            argv = ["run_pressure.py", "--scenarios", str(scenarios), "--skill", str(skill), "--output", str(output)]
            environ = {**os.environ, "SYSTEMIC_TRIAGE_PRESSURE_COMMAND_JSON": '["pi","--no-skills"]'}
            completed = SimpleNamespace(returncode=0, stdout="ok", stderr="")
            with patch.object(sys, "argv", argv), patch.dict(os.environ, environ, clear=True), patch.object(
                run_pressure.subprocess, "run", return_value=completed
            ) as invoked:
                self.assertEqual(run_pressure.main(), 0)
        command = invoked.call_args.args[0]
        self.assertEqual(command[:2], ["pi", "--no-skills"])
        self.assertIn("BINDING TRIAGE SKILL", command[-1])
        self.assertIn("Patch now.", command[-1])
