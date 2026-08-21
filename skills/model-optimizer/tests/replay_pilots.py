#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from helper.adapters import RuntimeContext, adapter_for
from helper.evaluator import (
    AllowedCommand,
    CommandAudit,
    EvalFixture,
    FixturePolicy,
    PreparedWorkspace,
    ProbeObservation,
    RoleEvalRequest,
    RoleEvalResult,
    SandboxAttestation,
    ToolAudit,
    canonical_fixture_digest,
    cited_lines,
    grade_fixture,
    load_fixture,
    prepare_fixture,
    prepare_workspace_marker,
    sandbox_attestation_digest,
    select_sandbox_backend,
)
from helper.models import HealthCheck, HealthStatus, ModelRecord, RuntimeKind
from helper.optimizer import AgentContract, CandidateEvidence, FixtureEvidence, IdentityMatch, PermissionRule, RoleRequirements, RouteKey, RunObservation, choose_mapping
from helper.runner import CommandRunner
from tests.support import FAKE_BWRAP_PATH

MECHANICAL = ("mechanical-slugify", "mechanical-duration")
REGRESSION = ("regression-timeout", "regression-retry-delay")
CASE_FIXTURES = {"mechanical": MECHANICAL, "regression": REGRESSION}
_MAX_EVIDENCE_CHARS = 240

SLUGIFY_SOLUTION = '''import re
import unicodedata


def slugify(value: str) -> str:
    """Return a lowercase ASCII slug separated by single hyphens."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
'''

DURATION_SOLUTION = r'''import re


def parse_duration(value: str) -> int:
    """Return the duration in seconds for tokens such as '1h 30m 5s'."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    if not re.fullmatch(r"\s*(?:\d+\s*[hms]\s*)+", value, re.IGNORECASE):
        raise ValueError("invalid duration")
    factors = {"h": 3600, "m": 60, "s": 1}
    return sum(int(number) * factors[unit.lower()] for number, unit in re.findall(r"(\d+)\s*([hms])", value, re.IGNORECASE))
'''

DIAGNOSES = {
    "regression-timeout": '''status: diagnosed
root_cause: client.py returns timeout_ms without converting milliseconds to seconds
evidence: client.py:8 and test_service.py:7
proposed_fix: divide config["timeout_ms"] by 1000
confidence: high
''',
    "regression-retry-delay": '''status: diagnosed
root_cause: worker.py passes RETRY_DELAY_MS directly to sleep, which expects seconds
evidence: worker.py:6 and settings.py:1
proposed_fix: divide RETRY_DELAY_MS by 1000 before calling sleep
confidence: high
''',
}


def _route() -> RouteKey:
    return RouteKey(RuntimeKind.PI, "0.84.2", "nan/qwen3.6", "high")


def _result(fixture, *, status: str, text: str = "", changed=(), command_exit: int | None = 0) -> RoleEvalResult:
    return RoleEvalResult(
        _route(), fixture.fixture_id, fixture.version, fixture.manifest_digest, status, 1, text,
        ToolAudit(("bash",), (CommandAudit("python-unittest", command_exit, 1, "bwrap"),), tuple(changed), 0, ()),
        0, 0, 0, None, (),
    )


def _run_tests(workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-m", "unittest", "discover", "-v"],
        cwd=workspace,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=15,
    )


def _verify_fixture(fixture_id: str) -> None:
    fixture = load_fixture(ROOT, fixture_id)
    prepared = prepare_fixture(fixture)
    try:
        baseline = _run_tests(prepared.root)
        if baseline.returncode == 0:
            raise SystemExit(f"{fixture_id}: expected baseline RED")
    finally:
        shutil.rmtree(prepared.root, ignore_errors=True)

    prepared = prepare_fixture(fixture)
    try:
        if fixture_id == "mechanical-slugify":
            (prepared.root / "slugify.py").write_text(SLUGIFY_SOLUTION, encoding="utf-8")
            green = _run_tests(prepared.root)
            grade = grade_fixture(fixture, prepared.root, _result(fixture, status="PASS", changed=("slugify.py",), command_exit=0))
        elif fixture_id == "mechanical-duration":
            (prepared.root / "duration.py").write_text(DURATION_SOLUTION, encoding="utf-8")
            green = _run_tests(prepared.root)
            grade = grade_fixture(fixture, prepared.root, _result(fixture, status="PASS", changed=("duration.py",), command_exit=0))
        else:
            green = _run_tests(prepared.root)
            if green.returncode == 0:
                raise SystemExit(f"{fixture_id}: regression baseline unexpectedly passed")
            grade = grade_fixture(fixture, prepared.root, _result(fixture, status="FAIL", text=DIAGNOSES[fixture_id], changed=(), command_exit=1))
            if grade.status != "PASS":
                raise SystemExit(f"{fixture_id}: accepted diagnosis did not grade green: {grade}")
            return
        if green.returncode != 0:
            raise SystemExit(f"{fixture_id}: known solution did not pass tests\n{green.stdout}")
        if grade.status != "PASS" or grade.role_score != 1.0:
            raise SystemExit(f"{fixture_id}: known solution did not grade green: {grade}")
    finally:
        shutil.rmtree(prepared.root, ignore_errors=True)


def _verify_selection() -> None:
    role = RoleRequirements("mechanical", (), (), False, False, None, None, (), False, None, ("latency", "cost"))
    route_i = _route()
    route_c = replace(route_i, model="nan/challenger")
    model_i = ModelRecord(route_i.model, "nan", "qwen3.6", variants=("high",), tool_call=True)
    model_c = ModelRecord(route_c.model, "nan", "challenger", variants=("high",), tool_call=True)
    health_i = HealthCheck(route_i.model, "high", HealthStatus.PASS, 1, "ok", True, "ok")
    health_c = HealthCheck(route_c.model, "high", HealthStatus.PASS, 1, "ok", True, "ok")

    def fixture(fid: str, score: float, elapsed: int = 1000, reliable: bool = True, interventions: int = 0) -> FixtureEvidence:
        return FixtureEvidence(fid, "1", True, score, True, (RunObservation(fid, elapsed, reliable, interventions, 1.0),), ())

    incumbent = CandidateEvidence(route_i, model_i, health_i, IdentityMatch.EXACT, (fixture("one", 0.60), fixture("two", 0.60)), None, None, None, None, True)
    challenger = CandidateEvidence(route_c, model_c, health_c, IdentityMatch.EXACT, (fixture("one", 0.71), fixture("two", 0.72)), None, None, None, None)
    if choose_mapping(role, (incumbent, challenger), route_i).status != "CHANGE":
        raise SystemExit("selection: two-fixture material quality advantage did not win")

    one_only = replace(challenger, fixtures=(fixture("one", 0.71), fixture("two", 0.60)))
    if choose_mapping(role, (incumbent, one_only), route_i).status == "CHANGE":
        raise SystemExit("selection: one-fixture-only advantage changed mapping")

    faster = replace(challenger, fixtures=(fixture("one", 0.60, 790), fixture("two", 0.60, 790)))
    tied = replace(incumbent, fixtures=(fixture("one", 0.60, 1000), fixture("two", 0.60, 1000)))
    if choose_mapping(role, (tied, faster), route_i).reasons != ("material_operational_advantage",):
        raise SystemExit("selection: two-run latency advantage did not win")

    unreliable = replace(faster, fixtures=(fixture("one", 0.60, 790, reliable=False), fixture("two", 0.60, 790)))
    if choose_mapping(role, (tied, unreliable), route_i).status == "CHANGE":
        raise SystemExit("selection: reliability regression changed mapping")


def fixtures_only() -> int:
    for fixture_id in (*MECHANICAL, *REGRESSION):
        _verify_fixture(fixture_id)
    if cited_lines("client.py:4-9 client.py:5,8 worker.py:6", "client.py") != {4, 5, 6, 7, 8, 9}:
        raise SystemExit("semantic line parsing failed")
    _verify_selection()
    print("fixtures-only: PASS")
    return 0


def FAKE_SANDBOX_ATTESTATION(workspace: PreparedWorkspace) -> SandboxAttestation:
    observed = datetime.now(timezone.utc).replace(microsecond=0)
    executable_identity = f"bwrap:{FAKE_BWRAP_PATH}:1:1:1:sha256:" + ("0" * 64)
    profile_identity = f"bwrap:{workspace.root.resolve()}:network=none:env=minimal"
    observations = tuple(
        ProbeObservation(probe_id, (FAKE_BWRAP_PATH, "probe", probe_id), executable_identity, profile_identity, expected, "PASS", 0, False, False, False, "sha256:test", "sha256:test", observed.isoformat().replace("+00:00", "Z"))
        for probe_id, expected in (
            ("workspace_write", "ok"),
            ("outside_read_denied", "denied"),
            ("secret_env_denied", "absent"),
            ("network_denied", "denied"),
        )
    )
    return SandboxAttestation(
        "bwrap",
        str(workspace.root.resolve()),
        workspace.token,
        profile_identity,
        sandbox_attestation_digest("bwrap", workspace.root, workspace.token, executable_identity, profile_identity, observations),
        observed.isoformat().replace("+00:00", "Z"),
        observations,
        executable_identity,
    )


def _bounded(text: str) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= _MAX_EVIDENCE_CHARS else compact[: _MAX_EVIDENCE_CHARS - 1] + "…"


def _runtime_kind(value: str) -> RuntimeKind:
    return RuntimeKind.PI if value == "pi" else RuntimeKind.OPENCODE


def _parse_route_arg(value: str, runtime_kind: RuntimeKind, runtime_version: str) -> RouteKey:
    if "@" in value:
        model, effort = value.rsplit("@", 1)
        effort = effort or None
    else:
        model, separator, effort_value = value.rpartition(":")
        if separator and "/" in model:
            effort = effort_value or None
        else:
            model, effort = value, None
    if not model or "/" not in model:
        raise SystemExit(f"invalid route: {value}")
    return RouteKey(runtime_kind, runtime_version, model, effort)


def _requirements(case: str) -> RoleRequirements:
    if case == "mechanical":
        return RoleRequirements("mechanical", ("read", "edit"), (), False, True, None, None, (), False, None, ("quality", "latency", "cost"))
    return RoleRequirements("debugger", ("read",), (), False, False, None, None, (), True, None, ("quality", "latency", "cost"))


def _agent(case: str, route: RouteKey) -> AgentContract:
    if case == "mechanical":
        tools = ("read", "edit", "bash")
        permissions = (PermissionRule("edit", "**", "allow"),)
        authority = "confined"
        body = "Solve the fixture using only the allowed workspace and manifest commands."
    else:
        tools = ("read", "bash")
        permissions = ()
        authority = "denied"
        body = "Diagnose the regression with structured fields and do not modify files."
    return AgentContract(
        name="model-optimizer-live-replay",
        description="isolated replay pilot agent",
        mode=None,
        model=route.model,
        effort=route.effort,
        tools=tools,
        permissions=permissions,
        mutation_authority=authority,
        body=body,
        scope="project",
        definition_source="tests/replay_pilots.py",
        assignment_source=None,
        inheritance_sources=(),
        apply_target=None,
        digest="sha256:live-replay",
    )


def _policy_from_fixture(fixture: EvalFixture) -> FixturePolicy:
    base = FixturePolicy(
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.version,
        manifest_digest="",
        grader_id=fixture.grader_id,
        allowed_read_paths=(".",),
        allowed_write_paths=fixture.allowed_changed_files,
        allowed_commands=fixture.allowed_commands,
        requires_code_execution=fixture.requires_code_execution,
        capability_attestations=(),
    )
    return replace(base, manifest_digest=canonical_fixture_digest(base))


def _result_for_grading(fixture: EvalFixture, result: RoleEvalResult) -> RoleEvalResult:
    return replace(result, fixture_id=fixture.fixture_id, fixture_version=fixture.version, manifest_digest=fixture.manifest_digest)


def _fixture_evidence(fixture: EvalFixture, result: RoleEvalResult, grade: Any) -> FixtureEvidence:
    return FixtureEvidence(
        fixture.fixture_id,
        fixture.version,
        grade.status == "PASS",
        grade.role_score,
        grade.contract_success,
        (RunObservation(fixture.fixture_id, max(0, result.elapsed_ms), result.status == "PASS", 0, result.metered_cost),),
        tuple(result.reason_codes) or tuple(grade.reason_codes),
    )


def _emit_decision(decision: Any, candidates: tuple[CandidateEvidence, ...]) -> None:
    payload = {
        "status": decision.status,
        "selected_route": None if decision.selected_route is None else {
            "runtime": decision.selected_route.runtime_kind.value,
            "runtime_version": decision.selected_route.runtime_version,
            "model": decision.selected_route.model,
            "effort": decision.selected_route.effort,
        },
        "reasons": list(decision.reasons),
        "candidates": [
            {
                "model": candidate.route.model,
                "effort": candidate.route.effort,
                "fixtures": [
                    {
                        "id": fixture.fixture_id,
                        "score": fixture.role_score,
                        "success": fixture.success,
                        "contract_success": fixture.contract_success,
                        "reasons": [_bounded(reason) for reason in fixture.reason_codes],
                    }
                    for fixture in candidate.fixtures
                ],
            }
            for candidate in candidates
        ],
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def run_live_replay(
    *,
    runtime: str,
    case: str,
    route_args: tuple[str, ...],
    adapter: Any | None = None,
    context: RuntimeContext | None = None,
    sandbox_attestor: Any = select_sandbox_backend,
    emit: bool = False,
):
    runtime_kind = _runtime_kind(runtime)
    context = context or RuntimeContext(Path.home(), ROOT, dict(os.environ))
    runner = CommandRunner()
    adapter = adapter or adapter_for(runtime_kind, runner)
    runner_for_attestation = getattr(adapter, "runner", runner)

    try:
        inventory = adapter.inventory(context)
    except Exception as exc:  # pragma: no cover - production infrastructure guard
        raise SystemExit(f"infrastructure failure during inventory: {_bounded(str(exc))}") from exc

    catalog = {record.exact_id: record for record in inventory.catalog_local}
    routes = tuple(_parse_route_arg(value, runtime_kind, inventory.runtime.version) for value in route_args)
    live: list[tuple[RouteKey, ModelRecord, HealthCheck]] = []
    for route in routes:
        record = catalog.get(route.model)
        if record is None:
            continue
        try:
            check = adapter.live_check(record, route.effort, "MODEL_OPTIMIZER_REPLAY_SENTINEL", 60, context)
        except Exception as exc:  # pragma: no cover - production infrastructure guard
            raise SystemExit(f"infrastructure failure during live check: {_bounded(str(exc))}") from exc
        if check.status is HealthStatus.PASS and check.response_matched:
            live.append((route, record, check))
    if len(live) < 2:
        raise SystemExit("fewer than two live candidates")

    requirements = _requirements(case)
    fixture_ids = CASE_FIXTURES[case]
    candidates: list[CandidateEvidence] = []
    for route, record, health in live:
        fixture_evidence: list[FixtureEvidence] = []
        conclusive = 0
        for fixture_id in fixture_ids:
            fixture = load_fixture(ROOT, fixture_id)
            prepared = prepare_fixture(fixture)
            try:
                attestation = sandbox_attestor(runner_for_attestation, prepared)
                if fixture.requires_code_execution and attestation is None:
                    raise SystemExit("infrastructure failure: eval_sandbox_unavailable")
                prepared = replace(prepared, sandbox_attestation=attestation)
                policy = _policy_from_fixture(fixture)
                prepare_workspace_marker(prepared, policy)
                request = RoleEvalRequest(route, record, _agent(case, route), requirements, prepared, policy, fixture.task, 900)
                result = adapter.role_eval(request, context)
                grade = grade_fixture(fixture, prepared.root, _result_for_grading(fixture, result))
                if result.status in {"PASS", "FAIL"} and grade.status in {"PASS", "FAIL"}:
                    conclusive += 1
                fixture_evidence.append(_fixture_evidence(fixture, result, grade))
            finally:
                shutil.rmtree(prepared.root, ignore_errors=True)
        if conclusive < 2:
            raise SystemExit("insufficient conclusive fixtures")
        candidates.append(CandidateEvidence(route, record, health, IdentityMatch.EXACT, tuple(fixture_evidence), None, None, None, None, incumbent=route == live[0][0]))

    decision = choose_mapping(requirements, tuple(candidates), live[0][0])
    if emit:
        _emit_decision(decision, tuple(candidates))
    return decision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-only", action="store_true")
    parser.add_argument("--runtime", choices=("pi", "opencode"))
    parser.add_argument("--case", choices=("mechanical", "regression"))
    parser.add_argument("--model", action="append", default=[])
    args = parser.parse_args(argv)
    if args.fixtures_only:
        return fixtures_only()
    if not args.runtime or not args.case:
        parser.error("--runtime and --case are required unless --fixtures-only is used")
    if len(args.model) < 2:
        print("replay requires at least two live candidates", file=sys.stderr)
        return 2
    run_live_replay(runtime=args.runtime, case=args.case, route_args=tuple(args.model), emit=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
