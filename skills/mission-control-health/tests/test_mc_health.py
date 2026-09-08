"""Offline tests for the deterministic Mission Control health helper.

Every scenario injects synthetic records, including 429 error turns, into a
temporary directory. No provider, model, Herdr session, or real quota is used.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "helper" / "mc_health.py"
sys.path.insert(0, str(HELPER.parent))

import mc_health  # noqa: E402

SCHEDULE_ID = "mc-observation"
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
INTERVAL_MS = 900_000


def stamp(minutes_before: float) -> str:
    return (NOW - timedelta(minutes=minutes_before)).isoformat().replace("+00:00", "Z")


def run_record(index: int, minutes_before: float, state: str = "completed") -> dict:
    record = {
        "schemaVersion": 1,
        "id": f"run{index:02d}",
        "scheduleId": SCHEDULE_ID,
        "plannedAt": stamp(minutes_before),
        "dueReason": "timer",
        "state": state,
        "startedAt": stamp(minutes_before),
    }
    if state != "running":
        record["completedAt"] = stamp(minutes_before - 0.5)
    return record


def receipt(minutes_before: float) -> dict:
    return {
        "type": "custom_message",
        "customType": "subagent-notify",
        "timestamp": stamp(minutes_before),
        "content": f"Background task completed: **workflow**\n\nScheduled run from **Observation** (schedule {SCHEDULE_ID}).\n\nWorkflow completed.",
    }


def assistant(minutes_before: float, stop: str = "stop", tool: str | None = None, error: str | None = None) -> dict:
    content = []
    if tool:
        content.append({"type": "toolCall", "id": "call", "name": tool, "arguments": {"action": "update"}})
    else:
        content.append({"type": "text", "text": "noted"})
    message = {"role": "assistant", "content": content, "stopReason": stop}
    if error:
        message["errorMessage"] = error
    return {"type": "message", "id": "m", "timestamp": stamp(minutes_before), "message": message}


class Fixture:
    def __init__(self, root: Path, runs: list[dict], session: list[dict], paused: bool = False) -> None:
        self.schedule_dir = root / "schedules" / SCHEDULE_ID
        self.schedule_dir.mkdir(parents=True)
        (self.schedule_dir / "schedule.json").write_text(json.dumps({
            "schemaVersion": 1,
            "id": SCHEDULE_ID,
            "name": "Observation",
            "trigger": {"kind": "interval", "every": "15m", "everyMs": INTERVAL_MS},
            "paused": paused,
        }), encoding="utf-8")
        (self.schedule_dir / "history.json").write_text(json.dumps({"schemaVersion": 1, "runs": runs}), encoding="utf-8")
        self.session = root / "session.jsonl"
        with self.session.open("w", encoding="utf-8") as handle:
            for record in session:
                handle.write(json.dumps(record) + "\n")
            handle.write("not json\n")

    def digest(self) -> str:
        hasher = hashlib.sha256()
        for path in sorted(self.schedule_dir.rglob("*")) + [self.session]:
            if path.is_file():
                hasher.update(path.read_bytes())
        return hasher.hexdigest()


def healthy_runs() -> list[dict]:
    return [run_record(i, 55 - 15 * i) for i in range(4)]


def healthy_session() -> list[dict]:
    records = []
    for i in range(4):
        received = 55 - 15 * i - 0.5
        records.append(receipt(received))
        records.append(assistant(received - 0.3, "toolUse", tool="todo"))
        records.append(assistant(received - 0.6, "stop"))
    return records


class McHealthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_helper(self, fixture: Fixture, *extra: str) -> tuple[int, dict]:
        argv = [
            "--schedule-dir", str(fixture.schedule_dir),
            "--session", str(fixture.session),
            "--window-minutes", "60",
            "--now", NOW.isoformat().replace("+00:00", "Z"),
            "--json",
            *extra,
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = mc_health.main(argv)
        return code, json.loads(buffer.getvalue())

    def test_healthy_window_is_ok_and_inputs_are_untouched(self) -> None:
        fixture = Fixture(self.root, healthy_runs(), healthy_session())
        before = fixture.digest()
        code, report = self.run_helper(fixture)
        self.assertEqual(code, mc_health.EXIT_OK)
        self.assertEqual(report["verdict"], "OK")
        self.assertEqual(report["schedule"]["runs_in_window"], 4)
        self.assertEqual(report["delivery"]["receipts_in_window"], 4)
        self.assertEqual(report["processing"]["processed"], 4)
        self.assertEqual(report["processing"]["recorded"], 4)
        self.assertEqual(fixture.digest(), before)

    def test_injected_429_storm_alerts_on_processing_without_touching_schedule(self) -> None:
        session = []
        for i in range(4):
            received = 55 - 15 * i - 0.5
            session.append(receipt(received))
            session.append(assistant(received - 0.03, "error", error="OpenAI API error (429): 429 quota exceeded"))
        fixture = Fixture(self.root, healthy_runs(), session)
        code, report = self.run_helper(fixture)
        self.assertEqual(code, mc_health.EXIT_ALERT)
        self.assertFalse(report["schedule"]["alerts"], "schedule layer must stay healthy")
        self.assertFalse(report["delivery"]["alerts"], "delivery layer must stay healthy")
        self.assertEqual(report["processing"]["errored"], 4)
        self.assertEqual(report["processing"]["consecutive_errors"], 4)
        self.assertIn("429", report["processing"]["last_error_excerpt"])
        self.assertEqual(len(report["processing"]["alerts"]), 2)

    def test_delivery_gap_is_reported_separately(self) -> None:
        session = healthy_session()[:6]
        fixture = Fixture(self.root, healthy_runs(), session)
        code, report = self.run_helper(fixture)
        self.assertEqual(code, mc_health.EXIT_ALERT)
        self.assertEqual(report["delivery"]["undelivered_completions"], 2)
        self.assertTrue(report["delivery"]["alerts"])
        self.assertFalse(report["schedule"]["alerts"])
        self.assertFalse(report["processing"]["alerts"])

    def test_stale_schedule_alerts_unless_paused(self) -> None:
        old_runs = [run_record(0, 200)]
        fixture = Fixture(self.root, old_runs, [])
        code, report = self.run_helper(fixture)
        self.assertEqual(code, mc_health.EXIT_ALERT)
        self.assertTrue(report["schedule"]["stale"])
        paused = Fixture(self.root / "paused", old_runs, [], paused=True)
        code, report = self.run_helper(paused)
        self.assertFalse(report["schedule"]["stale"])
        self.assertFalse(report["schedule"]["alerts"])

    def test_replay_ignores_runs_completed_after_reference_time(self) -> None:
        runs = healthy_runs() + [run_record(9, -30)]
        fixture = Fixture(self.root, runs, healthy_session())
        _, report = self.run_helper(fixture)
        self.assertEqual(report["schedule"]["runs_in_window"], 4)
        self.assertLessEqual(report["schedule"]["last_completed_at"], NOW.isoformat().replace("+00:00", "Z"))

    def test_unprocessed_receipts_without_any_turn_alert(self) -> None:
        session = [receipt(55 - 15 * i - 0.5) for i in range(4)]
        fixture = Fixture(self.root, healthy_runs(), session)
        code, report = self.run_helper(fixture)
        self.assertEqual(code, mc_health.EXIT_ALERT)
        self.assertEqual(report["processing"]["unprocessed"], 4)
        self.assertEqual(report["processing"]["consecutive_errors"], 0)

    def test_notify_runs_command_only_on_alert(self) -> None:
        log = self.root / "notify.log"
        script = self.root / "fake_notify.py"
        script.write_text(
            "import sys, pathlib\n"
            f"pathlib.Path({str(log)!r}).write_text('\\n'.join(sys.argv[1:]))\n",
            encoding="utf-8",
        )
        command = f"{sys.executable} {script}"
        fixture = Fixture(self.root, healthy_runs(), healthy_session())
        code, report = self.run_helper(fixture, "--notify", "--notify-command", command)
        self.assertEqual(code, mc_health.EXIT_OK)
        self.assertFalse(log.exists())
        self.assertNotIn("notification", report)
        storm = [receipt(40), assistant(39.9, "error", error="429 quota exceeded"), receipt(25), assistant(24.9, "error", error="429 quota exceeded"), assistant(20, "error", error="429 quota exceeded")]
        fixture = Fixture(self.root / "storm", healthy_runs(), storm)
        code, report = self.run_helper(fixture, "--notify", "--notify-command", command, "--title", "MC ALERT")
        self.assertEqual(code, mc_health.EXIT_ALERT)
        self.assertEqual(report["notification"], "notify sent")
        argv = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(argv[0], "MC ALERT")
        self.assertEqual(argv[1], "--body")
        self.assertIn("429", argv[2])

    def test_herdr_notify_is_skipped_outside_herdr(self) -> None:
        storm = [receipt(40), assistant(39.9, "error", error="429"), receipt(25), assistant(24.9, "error", error="429"), assistant(20, "error", error="429")]
        fixture = Fixture(self.root, healthy_runs(), storm)
        env = dict(os.environ)
        env.pop("HERDR_ENV", None)
        env["PATH"] = str(self.root)
        completed = subprocess.run(
            [sys.executable, str(HELPER), "--schedule-dir", str(fixture.schedule_dir), "--session", str(fixture.session), "--window-minutes", "60", "--now", NOW.isoformat().replace("+00:00", "Z"), "--notify", "--json"],
            capture_output=True, text=True, env=env, check=False,
        )
        self.assertEqual(completed.returncode, mc_health.EXIT_ALERT)
        self.assertIn("notify skipped", json.loads(completed.stdout)["notification"])

    def test_missing_inputs_fail_closed(self) -> None:
        code = mc_health.main(["--schedule-dir", str(self.root / "missing"), "--session", str(self.root / "missing.jsonl")])
        self.assertEqual(code, mc_health.EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
