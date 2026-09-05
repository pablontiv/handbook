from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
PRESSURE = ROOT / "tests" / "pressure"
RUNNER = PRESSURE / "run_pressure.py"
SCENARIOS = PRESSURE / "scenarios.json"
DIFFERENTIAL_SCENARIOS = PRESSURE / "differential-scenarios.json"
RUNTIME_TRIGGER = PRESSURE / "runtime-trigger.md"

REQUIRED_SECTIONS = (
    "## Quick reference",
    "## Example",
    "## Required passes",
    "## Evidence states",
    "## Calibration",
    "## Strict live-system profile",
    "## Optional handoff",
    "## Red flags",
)
DISCOVERY_HEADING = "### Discovery — before brainstorming"
TEST_BASIS_HEADING = "### Test basis — after approved design or plan, before TDD"
STRICT_LIVE_SEQUENCE = textwrap.dedent(
    """\
    observe read-only reality
    → characterize semantics and variability
    → write a failing test from sanitized real evidence
    → implement minimally
    → validate locally
    → obtain explicit live authorization
    → mutate"""
)
OPTIONAL_HANDOFF_FIELDS = textwrap.dedent(
    """\
    Decision:
    Verified:
    Material unknown:
    Test consequence:"""
)

# Approved campaign artifacts. The published pressure evidence in `baseline.md`
# and `green.md` is only valid for these exact inputs; changing either one
# requires a new replay campaign before the reports can be trusted again.
APPROVED_RUNTIME_TRIGGER_DIGEST = (
    "f517f304fef0de78835cdc393d431096cef3334de7dcc0b87e1cf0e5652a2880"
)
APPROVED_SCENARIOS_DIGEST = (
    "35064d42ef6e8178fb42b51e8f94850f26d32a3e1b30bbc6ad299fcef60700e0"
)
APPROVED_DIFFERENTIAL_SCENARIOS_DIGEST = (
    "74cc20458bacf2f1345053065e5569729ec11129f2ec8b6c6da6f3c7f7993271"
)

HISTORICAL_SCENARIO_IDS = {
    "unstable-ordering",
    "permissive-mock",
    "invented-fixture",
    "proxy-state",
    "wrong-causal-class",
    "simple-local",
}
DIFFERENTIAL_SCENARIO_IDS = {
    "permanent-ledger",
    "stop-value-calibration",
    "causal-rca",
}


def canonical_digest(scenarios: list[dict]) -> str:
    canonical = json.dumps(
        scenarios, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def echo_prompt_command() -> list[str]:
    """Child that prints the prompt it received so injection is observable."""
    return [sys.executable, "-c", "import sys; print(sys.argv[1])"]


def stdin_probe_command() -> list[str]:
    """Child that reports whether it could consume the enumerator's stdin."""
    source = (
        "import sys;"
        "data = sys.stdin.read();"
        "print('stdin-eof' if data == '' else 'stdin-leak:' + data.strip())"
    )
    return [sys.executable, "-c", source]


def write_scenarios(path: Path, scenario_ids: list[str], prompt: str = "Patch now.") -> None:
    payload = {
        "schema": "evidence-driven-development.pressure-scenarios/v1",
        "scenarios": [{"id": scenario_id, "prompt": prompt} for scenario_id in scenario_ids],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def read_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class SkillContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(
            SKILL.is_file(),
            f"the canonical evidence-driven development skill is not published at {SKILL}",
        )
        self.text = SKILL.read_text(encoding="utf-8")
        self.frontmatter = self.text.split("---", 2)[1]

    def section(self, heading: str) -> str:
        body = self.text.split(f"\n{heading}\n", 1)[1]
        return body.split("\n## ", 1)[0]

    def test_frontmatter_declares_the_canonical_skill_name(self) -> None:
        self.assertIn("\nname: evidence-driven-development\n", self.frontmatter)

    def test_description_declares_discoverable_triggers_within_the_length_budget(self) -> None:
        description = self.frontmatter.split("description:", 1)[1].strip()
        self.assertTrue(
            description.startswith("Use when"),
            f"description must start with the discoverable trigger form: {description!r}",
        )
        self.assertLessEqual(len(description), 1024)
        for trigger in (
            "features",
            "bug fixes",
            "refactors",
            "tests",
            "mocks",
            "fixtures",
            "causal claims",
            "brainstorming",
            "test-driven development",
        ):
            with self.subTest(trigger=trigger):
                self.assertIn(trigger, description)

    def test_required_sections_are_present(self) -> None:
        for heading in REQUIRED_SECTIONS:
            with self.subTest(heading=heading):
                self.assertIn(f"\n{heading}\n", self.text)

    def test_discovery_precedes_brainstorming_and_test_basis_precedes_tdd(self) -> None:
        self.assertIn(DISCOVERY_HEADING, self.text)
        self.assertIn(TEST_BASIS_HEADING, self.text)
        self.assertLess(
            self.text.index(DISCOVERY_HEADING),
            self.text.index(TEST_BASIS_HEADING),
            "discovery must be documented before the test-basis pass",
        )

    def test_evidence_states_are_complete(self) -> None:
        states = self.section("## Evidence states")
        for state in ("VERIFIED", "INFERRED", "UNKNOWN", "CONFLICTING"):
            with self.subTest(state=state):
                self.assertIn(f"`{state}`:", states)

    def test_material_unknown_stops_only_the_dependent_path(self) -> None:
        self.assertIn(
            "stop the dependent test or implementation path",
            self.section("## Required passes"),
        )
        self.assertIn(
            "An unknown is material when another answer could change the next decision",
            self.section("## Evidence states"),
        )

    def test_consequential_oracles_must_be_independent_of_spec_mock_fixture_and_code(self) -> None:
        self.assertIn(
            "independent of the specification, mock, fixture, and code under test",
            self.section("## Required passes"),
        )

    def test_runtime_effects_require_executable_boundary_observation(self) -> None:
        self.assertIn(
            "runtime effects require observation at the executable boundary",
            self.section("## Evidence states"),
        )

    def test_strict_live_sequence_is_exact(self) -> None:
        self.assertIn(STRICT_LIVE_SEQUENCE, self.section("## Strict live-system profile"))

    def test_retry_after_failed_live_mutation_requires_a_renewed_gate(self) -> None:
        profile = self.section("## Strict live-system profile")
        for requirement in (
            "root cause is verified",
            "a regression test reproduces it",
            "the fix is independently reviewed",
            "the user explicitly reauthorizes mutation",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, profile)

    def test_no_permanent_evidence_ledger_is_required(self) -> None:
        self.assertIn("Create no permanent evidence ledger", self.section("## Optional handoff"))

    def test_optional_handoff_is_limited_to_four_fields(self) -> None:
        handoff = self.section("## Optional handoff")
        block = handoff.split("```text\n", 1)[1].split("\n```", 1)[0]
        self.assertEqual(block.strip(), OPTIONAL_HANDOFF_FIELDS)

    def test_calibration_preserves_proportional_simple_local_work(self) -> None:
        calibration = self.section("## Calibration")
        self.assertIn(
            "Simple, reversible local work may need only a one-sentence pass", calibration
        )
        self.assertIn(
            "Stop research when plausible new evidence cannot change the next decision",
            calibration,
        )

    def test_red_flags_name_every_replayed_failure_class(self) -> None:
        red_flags = self.section("## Red flags")
        for phrase in (
            "Treating a specification or plan as proof of external behavior",
            "Deriving a fixture only from documentation or the code under test",
            "Letting a permissive mock establish a real interface",
            "Substituting internal state for the observable effect",
            "Treating correlation as root-cause evidence",
            "Converting `UNKNOWN` into a requirement to keep moving",
            "Producing a longer checklist without changing a decision",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, red_flags)


class PressureAssetContractTests(unittest.TestCase):
    def load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_historical_scenarios_cover_every_replayed_failure_class(self) -> None:
        payload = self.load(SCENARIOS)
        self.assertEqual(payload["schema"], "evidence-driven-development.pressure-scenarios/v1")
        ids = [scenario["id"] for scenario in payload["scenarios"]]
        self.assertEqual(set(ids), HISTORICAL_SCENARIO_IDS)
        self.assertEqual(len(ids), len(set(ids)))

    def test_differential_scenarios_cover_every_discrimination_probe(self) -> None:
        payload = self.load(DIFFERENTIAL_SCENARIOS)
        self.assertEqual(
            payload["schema"],
            "evidence-driven-development.differential-pressure-scenarios/v1",
        )
        ids = [scenario["id"] for scenario in payload["scenarios"]]
        self.assertEqual(set(ids), DIFFERENTIAL_SCENARIO_IDS)
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_scenario_declares_a_reviewable_contract(self) -> None:
        for path in (SCENARIOS, DIFFERENTIAL_SCENARIOS):
            for scenario in self.load(path)["scenarios"]:
                for field in ("class", "pressures", "prompt", "pass"):
                    with self.subTest(path=path.name, scenario=scenario["id"], field=field):
                        self.assertTrue(scenario[field])

    def test_published_assets_match_the_reviewed_campaign_inputs(self) -> None:
        self.assertEqual(
            canonical_digest(self.load(SCENARIOS)["scenarios"]), APPROVED_SCENARIOS_DIGEST
        )
        self.assertEqual(
            canonical_digest(self.load(DIFFERENTIAL_SCENARIOS)["scenarios"]),
            APPROVED_DIFFERENTIAL_SCENARIOS_DIGEST,
        )
        self.assertEqual(
            hashlib.sha256(RUNTIME_TRIGGER.read_bytes()).hexdigest(),
            APPROVED_RUNTIME_TRIGGER_DIGEST,
        )


class PressureHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.scenarios = self.workspace / "scenarios.json"
        self.output = self.workspace / "runs.jsonl"

    def run_runner(
        self,
        arguments: list[str],
        command_json: str | None,
        stdin_payload: str = "",
    ) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.pop("EDD_PRESSURE_COMMAND_JSON", None)
        if command_json is not None:
            environment["EDD_PRESSURE_COMMAND_JSON"] = command_json
        return subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            input=stdin_payload,
            capture_output=True,
            text=True,
            timeout=120,
            env=environment,
            check=False,
        )

    def base_arguments(self) -> list[str]:
        return ["--scenarios", str(self.scenarios), "--output", str(self.output)]

    def test_missing_command_environment_is_rejected(self) -> None:
        write_scenarios(self.scenarios, ["unstable-ordering"])
        result = self.run_runner(self.base_arguments(), command_json=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("EDD_PRESSURE_COMMAND_JSON is required", result.stderr)
        self.assertFalse(self.output.exists())

    def test_malformed_command_environment_is_rejected(self) -> None:
        write_scenarios(self.scenarios, ["unstable-ordering"])
        for command_json in ('not json', '{"pi": true}', "[]", '["pi", 7]'):
            with self.subTest(command_json=command_json):
                result = self.run_runner(self.base_arguments(), command_json=command_json)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("EDD_PRESSURE_COMMAND_JSON", result.stderr)
                self.assertFalse(self.output.exists())

    def test_every_scenario_runs_for_each_repetition_and_is_recorded(self) -> None:
        write_scenarios(self.scenarios, ["unstable-ordering", "proxy-state"])
        result = self.run_runner(
            [*self.base_arguments(), "--repetitions", "3"],
            command_json=json.dumps(echo_prompt_command()),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        records = read_records(self.output)
        self.assertEqual(
            [(record["scenario"], record["repetition"]) for record in records],
            [
                ("unstable-ordering", 1),
                ("unstable-ordering", 2),
                ("unstable-ordering", 3),
                ("proxy-state", 1),
                ("proxy-state", 2),
                ("proxy-state", 3),
            ],
        )
        for record in records:
            self.assertEqual(record["returncode"], 0)
            self.assertIn("Patch now.", record["stdout"])
            self.assertEqual(record["stderr"], "")

    def test_non_positive_repetitions_and_timeout_are_rejected(self) -> None:
        write_scenarios(self.scenarios, ["unstable-ordering"])
        for flag, value in (("--repetitions", "0"), ("--timeout", "0"), ("--timeout", "-1")):
            with self.subTest(flag=flag, value=value):
                result = self.run_runner(
                    [*self.base_arguments(), flag, value],
                    command_json=json.dumps(echo_prompt_command()),
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("positive integer", result.stderr)

    def test_skill_and_runtime_trigger_are_injected_into_the_governed_prompt(self) -> None:
        write_scenarios(self.scenarios, ["invented-fixture"], prompt="SCENARIO-SENTINEL")
        skill = self.workspace / "SKILL.md"
        trigger = self.workspace / "runtime-trigger.md"
        skill.write_text("SKILL-SENTINEL", encoding="utf-8")
        trigger.write_text("TRIGGER-SENTINEL", encoding="utf-8")
        result = self.run_runner(
            [*self.base_arguments(), "--skill", str(skill), "--runtime-trigger", str(trigger)],
            command_json=json.dumps(echo_prompt_command()),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        [record] = read_records(self.output)
        for sentinel in ("TRIGGER-SENTINEL", "SKILL-SENTINEL", "SCENARIO-SENTINEL"):
            with self.subTest(sentinel=sentinel):
                self.assertIn(sentinel, record["stdout"])

    def test_unguided_control_prompt_is_the_untouched_scenario(self) -> None:
        write_scenarios(self.scenarios, ["simple-local"], prompt="SCENARIO-SENTINEL")
        result = self.run_runner(
            self.base_arguments(), command_json=json.dumps(echo_prompt_command())
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        [record] = read_records(self.output)
        self.assertEqual(record["stdout"].strip(), "SCENARIO-SENTINEL")

    def test_child_cannot_consume_the_scenario_enumerator_stdin(self) -> None:
        write_scenarios(self.scenarios, ["permissive-mock"])
        result = self.run_runner(
            self.base_arguments(),
            command_json=json.dumps(stdin_probe_command()),
            stdin_payload="ENUMERATOR-STDIN\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        [record] = read_records(self.output)
        self.assertEqual(record["stdout"].strip(), "stdin-eof")

    def test_bounded_timeout_stops_a_hanging_child(self) -> None:
        write_scenarios(self.scenarios, ["wrong-causal-class"])
        hanging = [sys.executable, "-c", "import time; time.sleep(60)"]
        result = self.run_runner(
            [*self.base_arguments(), "--timeout", "1"],
            command_json=json.dumps(hanging),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TimeoutExpired", result.stderr)


if __name__ == "__main__":
    unittest.main()
