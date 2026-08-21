from __future__ import annotations

import json
import math
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from helper.models import (
    CurrentAssignment,
    Inventory,
    ModelRecord,
    ProviderReadiness,
    ReadinessStatus,
    RuntimeInfo,
    RuntimeKind,
)
from helper.optimizer import AgentContract, PermissionRule, RouteKey
from helper.state import (
    BenchmarkKey,
    BenchmarkSummary,
    EvaluationKey,
    EvaluationSummary,
    OptimizerState,
    fresh_benchmark,
    fresh_evaluation,
    inventory_delta,
    load_state,
    semantic_snapshot,
    state_path,
    update_state,
)


class StateTests(unittest.TestCase):
    def _route(self, *, effort: str | None = "medium") -> RouteKey:
        return RouteKey(RuntimeKind.PI, "0.84.2", "nan/qwen3.6", effort)

    def _evaluation_key(self, *, route: RouteKey | None = None) -> EvaluationKey:
        return EvaluationKey(
            route=route or self._route(),
            agent_digest="sha256:agent",
            tool_digest="sha256:tools",
            fixture_id="mechanical-edit",
            fixture_version="v1",
            model_fingerprint="sha256:model",
        )

    def _benchmark_key(self, *, route: RouteKey | None = None) -> BenchmarkKey:
        return BenchmarkKey(
            route=route or self._route(),
            source_name="public-suite",
            benchmark="SWE-mini",
            benchmark_version="2026-08",
            evaluated_model_identity="nan/qwen3.6",
            reasoning_mode="medium",
        )

    def _state_with_summaries(self, created: datetime) -> tuple[OptimizerState, EvaluationKey, BenchmarkKey]:
        key = self._evaluation_key()
        benchmark_key = self._benchmark_key()
        timestamp = created.isoformat().replace("+00:00", "Z")
        return OptimizerState(
            schema="model-optimizer.state/v1",
            snapshot=None,
            evaluations=(EvaluationSummary(
                key=key,
                created_at=timestamp,
                success=True,
                role_score=0.82,
                contract_success=True,
                elapsed_ms=1234,
                metered_cost=0.012,
                reason_codes=("ok",),
            ),),
            benchmarks=(BenchmarkSummary(
                route=benchmark_key.route,
                identity="exact",
                source_name=benchmark_key.source_name,
                source_url="https://bench.example/results?api_key=SECRET#token",
                benchmark=benchmark_key.benchmark,
                benchmark_version=benchmark_key.benchmark_version,
                harness_or_agent="harness-v1",
                evaluated_model_identity=benchmark_key.evaluated_model_identity,
                reasoning_mode=benchmark_key.reasoning_mode,
                observed_at=timestamp,
                cached_at=timestamp,
                metric_name="pass_rate",
                metric_value=0.71,
            ),),
        ), key, benchmark_key

    def _inventory(self, *, created_at="2026-08-20T00:00:00Z", models=(), readiness=(), assignments=()) -> Inventory:
        return Inventory(
            schema="model-optimizer.inventory/v1",
            created_at=created_at,
            runtime=RuntimeInfo(RuntimeKind.PI, "0.84.2", "/work"),
            sources=("runtime-source-containing-secret",),
            current_assignments=tuple(assignments),
            catalog_local=tuple(models),
            provider_readiness=tuple(readiness),
            exclusions=(),
            warnings=("warning-with-secret",),
            digest="sha256:changes-every-run",
        )

    def _model(self, exact_id="nan/qwen3.6", **overrides) -> ModelRecord:
        values = {
            "exact_id": exact_id,
            "provider": exact_id.split("/", 1)[0],
            "model": exact_id.split("/", 1)[1],
            "family": "qwen",
            "context_window": 128000,
            "max_output": 16000,
            "reasoning": True,
            "input_modes": ("text",),
            "tool_call": True,
            "variants": ("medium", "high"),
            "provenance": ("local",),
        }
        values.update(overrides)
        return ModelRecord(**values)

    def _agent(self, name="mechanical", *, body="secret prompt/source", model="nan/qwen3.6") -> AgentContract:
        return AgentContract(
            name=name,
            description="description secret",
            mode="subagent",
            model=model,
            effort="medium",
            tools=("read", "edit"),
            permissions=(PermissionRule("edit", "*.py", "ask"),),
            mutation_authority="confined",
            body=body,
            scope="project",
            definition_source="project:mechanical.md",
            assignment_source="project:subagents.json",
            inheritance_sources=("global:base.md",),
            apply_target="/private/config/opencode.json",
            digest="sha256:agent",
        )

    def test_state_path_uses_xdg_cache_home_then_home_fallback(self):
        self.assertEqual(
            state_path({"XDG_CACHE_HOME": "/cache"}, Path("/home/u"), (Path("/home/u/.pi/agent"),)),
            Path("/cache/model-optimizer/state.json"),
        )
        self.assertEqual(
            state_path({}, Path("/home/u"), (Path("/home/u/.pi/agent"),)),
            Path("/home/u/.cache/model-optimizer/state.json"),
        )

    def test_state_path_rejects_relative_xdg_and_config_tree_overlap(self):
        with self.assertRaisesRegex(ValueError, "state_cache_home_not_absolute"):
            state_path({"XDG_CACHE_HOME": "relative/cache"}, Path("/home/u"), ())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_tree = root / ".pi" / "agent"
            cache_home = config_tree / "cache"
            with self.assertRaisesRegex(ValueError, "state_path_forbidden"):
                state_path({"XDG_CACHE_HOME": str(cache_home)}, root, (config_tree,))

    def test_summary_expires_at_seven_days_and_key_changes_invalidate(self):
        created = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
        state, key, benchmark_key = self._state_with_summaries(created)
        self.assertIsNotNone(fresh_evaluation(state, key, created + timedelta(days=6, seconds=86399)))
        self.assertIsNone(fresh_evaluation(state, key, created + timedelta(days=7)))
        high_effort_key = replace(key, route=replace(key.route, effort="high"))
        self.assertIsNone(fresh_evaluation(state, high_effort_key, created))
        self.assertIsNone(fresh_benchmark(state, benchmark_key, created + timedelta(days=7)))

    def test_state_round_trip_preserves_complete_route_identity_but_sanitizes_url_credentials(self):
        created = datetime(2026, 8, 20, tzinfo=timezone.utc)
        state, key, benchmark_key = self._state_with_summaries(created)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cache" / "state.json"
            updated = update_state(path, lambda _state: state)
            loaded = load_state(path)
            raw = path.read_text(encoding="utf-8")
        self.assertEqual(loaded.evaluations[0].key, key)
        self.assertEqual(loaded.benchmarks[0].route, benchmark_key.route)
        self.assertEqual(updated.benchmarks[0].source_url, "https://bench.example/results")
        self.assertNotIn("SECRET", raw)
        self.assertNotIn("api_key", raw.lower())
        self.assertNotIn("token", raw.lower())

    def test_corrupt_json_returns_empty_state_with_stable_warning_without_secret_leak(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            path.write_text('{"schema":"model-optimizer.state/v1","secret":"raw-api-key', encoding="utf-8")
            state = load_state(path)
        self.assertEqual(state.evaluations, ())
        self.assertEqual(state.warnings, ("state_invalid_json",))
        self.assertNotIn("raw-api-key", repr(state))

    def test_semantic_snapshot_ignores_created_at_digest_order_and_raw_private_text(self):
        model_a = self._model(input_modes=("text", "image"), variants=("high", "medium"))
        model_b = self._model(input_modes=("image", "text"), variants=("medium", "high"))
        readiness = ProviderReadiness("nan", ReadinessStatus.READY, "api_key_secret", "ok")
        assignment = CurrentAssignment("mechanical", "nan/qwen3.6", {"reasoning": {"effort": "medium"}}, "settings.json")
        first = semantic_snapshot(self._inventory(models=(model_a,), readiness=(readiness,), assignments=(assignment,)), (self._agent(),))
        second = semantic_snapshot(self._inventory(
            created_at="2026-08-21T00:00:00Z",
            models=(model_b,), readiness=(readiness,), assignments=(assignment,),
        ), (self._agent(body="changed raw prompt/source",),))
        self.assertEqual(first.runtime_fingerprint, second.runtime_fingerprint)
        self.assertEqual(first.model_fingerprints, second.model_fingerprints)
        self.assertEqual(first.readiness_fingerprints, second.readiness_fingerprints)
        self.assertEqual(first.assignment_fingerprints, second.assignment_fingerprints)
        self.assertNotEqual(first.agent_fingerprints, second.agent_fingerprints)
        serialized = json.dumps(first.__dict__, sort_keys=True)
        for forbidden in ("secret prompt/source", "description secret", "api_key_secret", "runtime-source-containing-secret", "warning-with-secret", "/private/config"):
            self.assertNotIn(forbidden, serialized)

    def test_inventory_delta_detects_component_changes_and_first_run_is_not_cartesian(self):
        ready = ProviderReadiness("nan", ReadinessStatus.READY, None, "ok")
        old = semantic_snapshot(
            self._inventory(
                models=(self._model("nan/qwen3.6"), self._model("old/gone")),
                readiness=(ready,),
                assignments=(CurrentAssignment("mechanical", "nan/qwen3.6", {}, "settings.json"),),
            ),
            (self._agent("mechanical"),),
        )
        current = semantic_snapshot(
            self._inventory(
                models=(self._model("nan/qwen3.6", context_window=256000), self._model("new/model")),
                readiness=(ProviderReadiness("nan", ReadinessStatus.NOT_READY, None, "no_auth"),),
                assignments=(CurrentAssignment("reviewer", "missing/model", {}, "settings.json"),),
            ),
            (self._agent("reviewer", model="missing/model"), self._agent("unassigned", model=None)),
        )
        first_run = inventory_delta(None, current)
        self.assertTrue(first_run.first_run)
        self.assertFalse(first_run.full_cartesian_required)
        self.assertIn("new/model", first_run.new_models)
        self.assertIn("reviewer", first_run.new_agents)
        self.assertIn("unassigned", first_run.unassigned_agents)

        delta = inventory_delta(old, current)
        self.assertFalse(delta.first_run)
        self.assertEqual(delta.new_models, ("new/model",))
        self.assertEqual(delta.removed_models, ("old/gone",))
        self.assertEqual(delta.changed_models, ("nan/qwen3.6",))
        self.assertEqual(delta.changed_readiness, ("nan",))
        self.assertEqual(delta.new_agents, ("reviewer", "unassigned"))
        self.assertEqual(delta.removed_agents, ("mechanical",))
        self.assertEqual(delta.new_assignments, ("reviewer",))
        self.assertEqual(delta.removed_assignments, ("mechanical",))
        self.assertEqual(delta.unassigned_agents, ("unassigned",))
        self.assertEqual(delta.missing_incumbents, ("reviewer",))
        self.assertFalse(delta.full_cartesian_required)

        clean = semantic_snapshot(
            self._inventory(
                models=(self._model("nan/qwen3.6"),),
                readiness=(ready,),
                assignments=(CurrentAssignment("mechanical", "nan/qwen3.6", {}, "settings.json"),),
            ),
            (self._agent("mechanical"),),
        )
        self.assertFalse(inventory_delta(clean, clean).has_changes)

    def test_update_state_serializes_concurrent_read_modify_write_transactions(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"

            def add_evaluation(index: int) -> OptimizerState:
                def transform(state: OptimizerState) -> OptimizerState:
                    route = RouteKey(RuntimeKind.PI, "0.84.2", f"nan/model-{index}", None)
                    summary = EvaluationSummary(
                        key=self._evaluation_key(route=route),
                        created_at="2026-08-20T00:00:00Z",
                        success=True,
                        role_score=0.5,
                        contract_success=True,
                        elapsed_ms=index,
                        metered_cost=None,
                        reason_codes=("ok",),
                    )
                    return replace(state, evaluations=state.evaluations + (summary,))
                return update_state(path, transform)

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(add_evaluation, range(16)))

            loaded = load_state(path)
            self.assertEqual(len(loaded.evaluations), 16)
            self.assertEqual(sorted(summary.elapsed_ms for summary in loaded.evaluations), list(range(16)))
            self.assertEqual(list(Path(td).glob(".state.json.*.tmp")), [])

    def test_update_state_write_failure_returns_transformed_state_with_warning_and_keeps_prior_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            baseline = update_state(path, lambda state: state)
            with mock.patch("helper.state.write_json_atomic", side_effect=OSError("disk includes SECRET")):
                returned = update_state(path, lambda state: replace(state, warnings=state.warnings + ("caller_warning",)))
            self.assertEqual(load_state(path), baseline)
            self.assertEqual(returned.warnings, ("caller_warning", "state_write_failed"))
            self.assertNotIn("SECRET", repr(returned))

    def test_non_finite_summary_metrics_are_not_written_and_do_not_abort(self):
        created = datetime(2026, 8, 20, tzinfo=timezone.utc)
        state, _key, _benchmark_key = self._state_with_summaries(created)
        bad = replace(state, evaluations=(replace(state.evaluations[0], role_score=math.nan),))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            returned = update_state(path, lambda _state: bad)
            self.assertFalse(path.exists())
        self.assertEqual(returned.warnings[-1], "state_write_failed")


if __name__ == "__main__":
    unittest.main()
