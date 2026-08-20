from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from helper.models import HealthCheck, HealthStatus, ModelRecord, RuntimeKind
from helper.optimizer import (
    BenchmarkObservation,
    CandidateEvidence,
    FixtureEvidence,
    IdentityMatch,
    RoleRequirements,
    RouteKey,
    RunObservation,
    choose_mapping,
    classify_identity,
    discover_agent_contracts,
    gate_candidate,
    parse_agent_definition,
    shortlist_candidates,
)


class AgentContractTests(unittest.TestCase):
    def test_parses_inline_and_sequence_tool_allowlists_without_yaml_dependency(self):
        samples = (
            "---\nname: mechanical\ndescription: Small edits\ntools: read, edit, bash\n---\nBody\n",
            "---\nname: mechanical\ndescription: Small edits\ntools:\n  - read\n  - edit\n  - bash\n---\nBody\n",
        )
        for text in samples:
            with self.subTest(text=text), TemporaryDirectory() as td:
                path = Path(td) / "agent.md"
                path.write_text(text, encoding="utf-8")
                contract = parse_agent_definition(
                    path,
                    scope="global",
                    config_path=Path(td) / "subagents.json",
                )
                self.assertEqual(contract.name, "mechanical")
                self.assertEqual(contract.description, "Small edits")
                self.assertEqual(contract.tools, ("read", "edit", "bash"))
                self.assertEqual(contract.body, "Body")
                self.assertTrue(contract.digest.startswith("sha256:"))

    def test_rejects_invalid_bounded_frontmatter_with_stable_errors(self):
        too_large_body = "x" * (65_537)
        cases = (
            ("missing_delimiters", "name: mechanical\nBody\n", "agent_definition_missing_frontmatter"),
            ("duplicate_key", "---\nname: one\nname: two\n---\nBody\n", "agent_definition_duplicate_key:name"),
            ("unsafe_tool", "---\nname: bad\ntools: read, ../bash\n---\nBody\n", "agent_definition_unsafe_tool:../bash"),
            ("duplicate_tool", "---\nname: bad\ntools: read, read\n---\nBody\n", "agent_definition_duplicate_tool:read"),
            ("nested_frontmatter", "---\nname: bad\n---\nBody\n---\n", "agent_definition_nested_frontmatter"),
            ("yaml_tag", "---\nname: !secret bad\n---\nBody\n", "agent_definition_unsupported_yaml"),
            ("yaml_anchor", "---\nname: &n bad\n---\nBody\n", "agent_definition_unsupported_yaml"),
            ("oversized_body", f"---\nname: big\n---\n{too_large_body}\n", "agent_definition_body_too_large"),
        )
        for label, text, expected in cases:
            with self.subTest(label=label), TemporaryDirectory() as td:
                path = Path(td) / "agent.md"
                path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, f"^{expected}"):
                    parse_agent_definition(path, scope="project", config_path=Path(td) / "subagents.json")

    def test_rejects_non_utf8_definition_with_stable_error(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "agent.md"
            path.write_bytes(b"---\nname: bad\n---\n\xff")
            with self.assertRaisesRegex(ValueError, "^agent_definition_non_utf8"):
                parse_agent_definition(path, scope="global", config_path=Path(td) / "subagents.json")


class SelectionPolicyTests(unittest.TestCase):
    def _role(self, **overrides):
        values = {
            "archetype": "mechanical",
            "required_tools": (),
            "essential_custom_tools": (),
            "requires_vision": False,
            "requires_mutation": False,
            "min_context": None,
            "min_output": None,
            "allowed_efforts": (),
            "structured_output": False,
            "adversarial_against_family": None,
            "priority_order": ("quality", "latency", "cost"),
        }
        values.update(overrides)
        return RoleRequirements(**values)

    def _route(self, model="nan/qwen3.6", effort="medium"):
        return RouteKey(RuntimeKind.PI, "0.84.2", model, effort)

    def _model(self, exact_id="nan/qwen3.6", **overrides):
        values = {
            "exact_id": exact_id,
            "provider": exact_id.split("/", 1)[0],
            "model": exact_id.split("/", 1)[1],
            "family": "qwen",
            "context_window": 128_000,
            "max_output": 16_000,
            "reasoning": True,
            "input_modes": ("text",),
            "tool_call": True,
            "variants": ("minimal", "medium", "high"),
        }
        values.update(overrides)
        return ModelRecord(**values)

    def _health(self, model="nan/qwen3.6", effort="medium", status=HealthStatus.PASS):
        return HealthCheck(model, effort, status, 1000, "live_sentinel_matched", status is HealthStatus.PASS, "ok")

    def _fixture(self, fixture_id, score, *, contract=True, success=True, elapsed=1000, reliable=True, interventions=0, cost=1.0):
        return FixtureEvidence(
            fixture_id,
            "v1",
            success,
            score,
            contract,
            (RunObservation(f"run-{fixture_id}", elapsed, reliable, interventions, cost),),
            (),
        )

    def _candidate(self, route=None, model=None, fixtures=(), incumbent=False, health=None, **metrics):
        route = route or self._route()
        model = model or self._model(route.model)
        health = health or self._health(route.model, route.effort)
        return CandidateEvidence(
            route,
            model,
            health,
            IdentityMatch.EXACT,
            tuple(fixtures),
            metrics.get("benchmark_score"),
            metrics.get("reliability_rate"),
            metrics.get("median_elapsed_ms"),
            metrics.get("metered_cost"),
            incumbent,
        )

    def test_gate_candidate_enforces_mandatory_model_health_and_role_requirements(self):
        text_route = self._route("nan/qwen3.6", "medium")
        text_only_model = self._model("nan/qwen3.6", input_modes=("text",))
        passing_health = self._health("nan/qwen3.6", "medium")
        vision_role = self._role(requires_vision=True)
        self.assertEqual(gate_candidate(vision_role, text_route, text_only_model, passing_health), ("required_vision_missing",))

        role = self._role(min_context=200_000, min_output=20_000, adversarial_against_family="qwen")
        self.assertEqual(gate_candidate(role, text_route, text_only_model, passing_health), (
            "context_window_too_small",
            "max_output_too_small",
            "adversarial_family_conflict",
        ))
        failing = self._health("nan/qwen3.6", "medium", HealthStatus.FAIL)
        self.assertEqual(gate_candidate(self._role(), text_route, text_only_model, failing), ("route_live_unavailable",))
        wrong_effort = self._route("nan/qwen3.6", "max")
        self.assertEqual(gate_candidate(self._role(allowed_efforts=("minimal", "medium")), wrong_effort, text_only_model, passing_health), (
            "unsupported_effort",
            "disallowed_effort",
        ))

    def test_shortlist_filters_unavailable_routes_preserves_incumbent_and_effort(self):
        role = self._role()
        current_route = self._route("nan/current", "minimal")
        candidates = [
            self._candidate(self._route("nan/current", "minimal"), self._model("nan/current"), [self._fixture("a", 0.60)], True),
            self._candidate(self._route("nan/new-1", "high"), self._model("nan/new-1"), [self._fixture("a", 0.90)]),
            self._candidate(self._route("nan/new-2", "medium"), self._model("nan/new-2"), [self._fixture("a", 0.80)]),
            self._candidate(self._route("nan/new-3", None), self._model("nan/new-3", variants=()), [self._fixture("a", 0.70)]),
            self._candidate(self._route("nan/new-4", "medium"), self._model("nan/new-4"), [self._fixture("a", 0.65)]),
            self._candidate(
                self._route("nan/failing", "medium"),
                self._model("nan/failing"),
                [self._fixture("a", 1.0)],
                health=self._health("nan/failing", "medium", HealthStatus.FAIL),
            ),
        ]
        shortlist = shortlist_candidates(role, candidates, incumbent=current_route, limit=4)
        self.assertEqual(len(shortlist), 4)
        self.assertIn(current_route, [item.route for item in shortlist])
        self.assertNotIn("nan/failing", [item.route.model for item in shortlist])
        self.assertIn("high", [item.route.effort for item in shortlist])

    def test_choose_mapping_handles_ties_abstention_and_material_fixture_advantage(self):
        role = self._role()
        current_route = self._route("nan/current", "medium")
        current_one = self._candidate(current_route, self._model("nan/current"), [self._fixture("one", 0.80)], True)
        challenger_one = self._candidate(self._route("nan/challenger", "high"), self._model("nan/challenger"), [self._fixture("one", 0.80)])
        self.assertEqual(choose_mapping(role, (current_one, challenger_one), current_route).status, "NEEDS_MORE_EVIDENCE")

        current_two = self._candidate(current_route, self._model("nan/current"), [self._fixture("one", 0.80), self._fixture("two", 0.80)], True)
        challenger_two = self._candidate(self._route("nan/challenger", "high"), self._model("nan/challenger"), [self._fixture("one", 0.80), self._fixture("two", 0.80)])
        self.assertEqual(choose_mapping(role, (current_two, challenger_two), current_route).status, "NO_CHANGE")

        failing = self._candidate(
            self._route("nan/failing", "medium"),
            self._model("nan/failing"),
            [self._fixture("one", 1.0)],
            health=self._health("nan/failing", "medium", HealthStatus.FAIL),
        )
        self.assertEqual(choose_mapping(role, (failing,), None).status, "ABSTAIN")

        material = self._candidate(self._route("nan/material", "high"), self._model("nan/material"), [self._fixture("one", 0.91), self._fixture("two", 0.92)])
        decision = choose_mapping(role, (current_two, material), current_route)
        self.assertEqual(decision.status, "CHANGE")
        self.assertEqual(decision.selected_route, material.route)
        self.assertEqual(decision.selected_route.effort, "high")

    def test_choose_mapping_ignores_unsupported_aggregate_advantage(self):
        role = self._role()
        current_route = self._route("nan/current", "medium")
        current = self._candidate(current_route, self._model("nan/current"), [self._fixture("one", 0.80), self._fixture("two", 0.80)], True, benchmark_score=0.1)
        challenger = self._candidate(self._route("nan/challenger", "high"), self._model("nan/challenger"), [self._fixture("one", 0.80), self._fixture("two", 0.80)], benchmark_score=0.99)
        self.assertEqual(choose_mapping(role, (current, challenger), current_route).status, "NO_CHANGE")

    def test_identity_classification_distinguishes_source_and_model_match_quality(self):
        route = self._route("openai/gpt-5.6-terra", "high")
        self.assertEqual(classify_identity(route, BenchmarkObservation(exact_id="openai/gpt-5.6-terra", effort="high"), True), IdentityMatch.EXACT)
        self.assertEqual(classify_identity(route, BenchmarkObservation(exact_id="azure/gpt-5.6-terra", model="gpt-5.6-terra"), True), IdentityMatch.MODEL_EQUIVALENT)
        self.assertEqual(classify_identity(route, BenchmarkObservation(family="gpt"), True), IdentityMatch.FAMILY_PROXY)
        self.assertEqual(classify_identity(route, None, True), IdentityMatch.ABSENT)
        self.assertEqual(classify_identity(route, BenchmarkObservation(identity_unknown=True), True), IdentityMatch.UNKNOWN)
        self.assertEqual(classify_identity(route, None, False), IdentityMatch.SOURCE_UNAVAILABLE)


class AgentDiscoveryTests(unittest.TestCase):
    def test_pi_discovery_merges_definition_assignment_and_scope_precedence(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            cwd = root / "project"
            global_root = root / "pi-root"
            home.mkdir()
            cwd.mkdir()
            (global_root / "agents").mkdir(parents=True)
            (global_root / "subagents").mkdir()
            (cwd / ".pi" / "subagents").mkdir(parents=True)
            (global_root / "agents" / "worker.md").write_text("---\nname: worker\ndescription: global\ntools: read\n---\nGlobal\n", encoding="utf-8")
            (cwd / ".pi" / "subagents" / "worker.md").write_text(
                "---\nname: worker\ndescription: project\nmode: subagent\nmodel: nan/qwen3.6\nvariant: medium\ntools:\n  read: true\n  edit: true\npermissions:\n  edit:\n    '*.py': ask\n---\nProject\n",
                encoding="utf-8",
            )
            (cwd / ".pi" / "subagents.json").write_text(json.dumps({
                "model_profiles": {"worker": {"model": "nan/qwen3.6", "effort": "medium"}}
            }), encoding="utf-8")

            contracts = discover_agent_contracts(RuntimeKind.PI, home, cwd, {"PI_CODING_AGENT_DIR": str(global_root)})

            self.assertEqual([contract.name for contract in contracts], ["worker"])
            worker = contracts[0]
            self.assertEqual(worker.scope, "project")
            self.assertEqual(worker.description, "project")
            self.assertEqual(worker.mode, "subagent")
            self.assertEqual(worker.model, "nan/qwen3.6")
            self.assertEqual(worker.effort, "medium")
            self.assertEqual(worker.tools, ("read", "edit"))
            self.assertEqual([(rule.capability, rule.pattern, rule.action) for rule in worker.permissions], [("edit", "*.py", "ask")])
            self.assertEqual(worker.assignment_source, "project:subagents.json")
            self.assertEqual(worker.inheritance_sources, ("global:agents/worker.md",))
            self.assertEqual(worker.apply_target, str(cwd / ".pi" / "subagents.json"))

    def test_opencode_discovery_reads_xdg_markdown_project_markdown_and_inline_agents(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            cwd = root / "project"
            xdg = root / "xdg"
            home.mkdir()
            cwd.mkdir()
            (xdg / "opencode" / "agents").mkdir(parents=True)
            (cwd / ".opencode" / "agents").mkdir(parents=True)
            (xdg / "opencode" / "agents" / "scout.md").write_text("---\nname: scout\ndescription: global scout\ntools: read\n---\nScout\n", encoding="utf-8")
            (cwd / ".opencode" / "agents" / "builder.md").write_text("---\nname: builder\ndescription: edits\ntools: read, edit\n---\nBuilder\n", encoding="utf-8")
            (xdg / "opencode" / "opencode.json").write_text(json.dumps({
                "agent": {
                    "scout": {"model": "openai/gpt-5.6-terra", "variant": "high"},
                    "inline": {"description": "inline global", "permission": {"bash": "deny"}},
                }
            }), encoding="utf-8")
            (cwd / "opencode.json").write_text(json.dumps({
                "agent": {
                    "builder": {"model": "nan/qwen3.6", "variant": "medium", "permission": {"edit": {"*.py": "ask"}}},
                    "inline": {"description": "inline project", "mode": "primary", "tools": ["read"]},
                }
            }), encoding="utf-8")

            contracts = discover_agent_contracts(RuntimeKind.OPENCODE, home, cwd, {"XDG_CONFIG_HOME": str(xdg)})
            by_name = {contract.name: contract for contract in contracts}

            self.assertEqual(set(by_name), {"builder", "inline", "scout"})
            self.assertEqual(by_name["builder"].scope, "project")
            self.assertEqual(by_name["builder"].model, "nan/qwen3.6")
            self.assertEqual(by_name["builder"].effort, "medium")
            self.assertEqual(by_name["builder"].apply_target, str(cwd / "opencode.json"))
            self.assertEqual([(rule.capability, rule.pattern, rule.action) for rule in by_name["builder"].permissions], [("edit", "*.py", "ask")])
            self.assertEqual(by_name["inline"].scope, "project")
            self.assertIsNone(by_name["inline"].model)
            self.assertEqual(by_name["inline"].mode, "primary")
            self.assertEqual(by_name["inline"].inheritance_sources, ("global:opencode.json#agent.inline",))
