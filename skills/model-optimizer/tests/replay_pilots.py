#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from helper.evaluator import CommandAudit, RoleEvalResult, ToolAudit, cited_lines, grade_fixture, load_fixture, prepare_fixture
from helper.models import HealthCheck, HealthStatus, ModelRecord, RuntimeKind
from helper.optimizer import CandidateEvidence, FixtureEvidence, IdentityMatch, RoleRequirements, RouteKey, RunObservation, choose_mapping

MECHANICAL = ("mechanical-slugify", "mechanical-duration")
REGRESSION = ("regression-timeout", "regression-retry-delay")

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
            returncode_ok = True
            if grade.status != "PASS" or not returncode_ok:
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
    print("live replay is intentionally unavailable in this unit harness without runtime credentials", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
