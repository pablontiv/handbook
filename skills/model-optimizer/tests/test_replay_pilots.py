from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from helper.evaluator import CommandAudit, RoleEvalResult, ToolAudit
from helper.models import HealthCheck, HealthStatus, Inventory, ModelRecord, RuntimeInfo, RuntimeKind
from helper.optimizer import RouteKey
from tests import replay_pilots


class FakeReplayAdapter:
    def __init__(self, *, live_status=HealthStatus.PASS, inconclusive_fixture: str | None = None):
        self.live_status = live_status
        self.inconclusive_fixture = inconclusive_fixture
        self.inventory_calls = 0
        self.live_checks: list[tuple[str, str | None]] = []
        self.role_evals: list[tuple[str, str]] = []
        self.records = (
            ModelRecord("nan/incumbent", "nan", "incumbent", variants=("high",), tool_call=True),
            ModelRecord("nan/challenger", "nan", "challenger", variants=("high",), tool_call=True),
        )

    def inventory(self, context):
        self.inventory_calls += 1
        return Inventory(
            "model-optimizer.inventory/v1",
            "2026-08-21T00:00:00Z",
            RuntimeInfo(RuntimeKind.PI, "0.84.2", str(context.cwd)),
            (),
            (),
            self.records,
            (),
            (),
            (),
            "sha256:test",
        )

    def live_check(self, model_record, effort, sentinel, timeout, context):
        self.live_checks.append((model_record.exact_id, effort))
        matched = self.live_status is HealthStatus.PASS
        return HealthCheck(model_record.exact_id, effort, self.live_status, 25, "live_sentinel_matched" if matched else "live_unavailable", matched, "ok" if matched else "no")

    def role_eval(self, request, context):
        self.role_evals.append((request.route.model, request.fixture.fixture_id))
        if request.fixture.fixture_id == self.inconclusive_fixture:
            return RoleEvalResult(
                request.route,
                request.fixture.fixture_id,
                request.fixture.fixture_version,
                request.fixture.manifest_digest,
                "INCONCLUSIVE",
                50,
                "",
                ToolAudit((), (), (), 0, ()),
                0,
                0,
                0,
                None,
                ("eval_sandbox_unavailable",),
            )
        exit_code = 0 if request.route.model.endswith("challenger") else 1
        status = "PASS" if exit_code == 0 else "FAIL"
        # Mechanical graders derive score from command/result evidence.
        return RoleEvalResult(
            request.route,
            request.fixture.fixture_id,
            request.fixture.fixture_version,
            request.fixture.manifest_digest,
            status,
            100,
            "",
            ToolAudit(("bash",), (CommandAudit("python-unittest", exit_code, 10, "bwrap"),), (request.fixture.allowed_write_paths[0],) if request.fixture.allowed_write_paths else (), 0, ()), 
            0,
            0,
            0,
            None,
            (),
        )


class ReplayPilotLiveTests(unittest.TestCase):
    def test_live_replay_runs_inventory_checks_two_fixtures_and_choose_mapping(self):
        adapter = FakeReplayAdapter()
        with TemporaryDirectory() as td:
            decision = replay_pilots.run_live_replay(
                runtime="pi",
                case="mechanical",
                route_args=("nan/incumbent@high", "nan/challenger@high"),
                adapter=adapter,
                context=replay_pilots.RuntimeContext(Path(td), replay_pilots.ROOT, {}),
                sandbox_attestor=lambda runner, workspace: replay_pilots.FAKE_SANDBOX_ATTESTATION(workspace),
            )
        self.assertEqual(adapter.inventory_calls, 1)
        self.assertEqual(adapter.live_checks, [("nan/incumbent", "high"), ("nan/challenger", "high")])
        self.assertEqual(len(adapter.role_evals), 4)
        self.assertEqual(decision.status, "CHANGE")
        self.assertEqual(decision.selected_route, RouteKey(RuntimeKind.PI, "0.84.2", "nan/challenger", "high"))

    def test_live_replay_accepts_task8_colon_effort_route_syntax(self):
        adapter = FakeReplayAdapter()
        with TemporaryDirectory() as td:
            decision = replay_pilots.run_live_replay(
                runtime="pi",
                case="mechanical",
                route_args=("nan/incumbent:high", "nan/challenger:high"),
                adapter=adapter,
                context=replay_pilots.RuntimeContext(Path(td), replay_pilots.ROOT, {}),
                sandbox_attestor=lambda runner, workspace: replay_pilots.FAKE_SANDBOX_ATTESTATION(workspace),
            )
        self.assertEqual(adapter.live_checks, [("nan/incumbent", "high"), ("nan/challenger", "high")])
        self.assertEqual(decision.selected_route, RouteKey(RuntimeKind.PI, "0.84.2", "nan/challenger", "high"))

    def test_live_replay_exits_nonzero_when_fewer_than_two_live_candidates(self):
        adapter = FakeReplayAdapter(live_status=HealthStatus.FAIL)
        with TemporaryDirectory() as td, self.assertRaisesRegex(SystemExit, "fewer than two live candidates"):
            replay_pilots.run_live_replay(
                runtime="pi",
                case="mechanical",
                route_args=("nan/incumbent@high", "nan/challenger@high"),
                adapter=adapter,
                context=replay_pilots.RuntimeContext(Path(td), replay_pilots.ROOT, {}),
                sandbox_attestor=lambda runner, workspace: replay_pilots.FAKE_SANDBOX_ATTESTATION(workspace),
            )

    def test_live_replay_exits_nonzero_on_insufficient_conclusive_fixtures(self):
        adapter = FakeReplayAdapter(inconclusive_fixture="mechanical-duration")
        with TemporaryDirectory() as td, self.assertRaisesRegex(SystemExit, "insufficient conclusive fixtures"):
            replay_pilots.run_live_replay(
                runtime="pi",
                case="mechanical",
                route_args=("nan/incumbent@high", "nan/challenger@high"),
                adapter=adapter,
                context=replay_pilots.RuntimeContext(Path(td), replay_pilots.ROOT, {}),
                sandbox_attestor=lambda runner, workspace: replay_pilots.FAKE_SANDBOX_ATTESTATION(workspace),
            )


if __name__ == "__main__":
    unittest.main()
