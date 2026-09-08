"""Deterministic Mission Control health report.

Reads a pi-subagents schedule store and a Pi session record read-only and
reports three separate layers: schedule execution, receipt delivery, and
Mission Control processing or acknowledgement. Emits an optional visible
alert through an external notification command. Performs no inference,
no retries, no pauses, and never modifies its inputs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_ALERT = 2

DEFAULT_ACK_TOOLS = ("todo",)
DEFAULT_NOTIFY_COMMAND = ("herdr", "notification", "show")


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


@dataclass
class ScheduleHealth:
    schedule_id: str
    name: str
    paused: bool
    interval_ms: int | None
    runs_in_window: int = 0
    states: dict[str, int] = field(default_factory=dict)
    last_completed_at: datetime | None = None
    last_failed_at: datetime | None = None
    terminal_runs_in_window: int = 0
    stale: bool = False
    alerts: list[str] = field(default_factory=list)


@dataclass
class DeliveryHealth:
    receipts_in_window: int = 0
    last_receipt_at: datetime | None = None
    terminal_runs_in_window: int = 0
    undelivered_completions: int = 0
    alerts: list[str] = field(default_factory=list)


@dataclass
class ProcessingHealth:
    processed: int = 0
    recorded: int = 0
    errored: int = 0
    unprocessed: int = 0
    consecutive_errors: int = 0
    last_error_at: datetime | None = None
    last_error_excerpt: str | None = None
    last_ack_at: datetime | None = None
    alerts: list[str] = field(default_factory=list)


def load_schedule(schedule_dir: Path, now: datetime, window: timedelta, stale_factor: float) -> ScheduleHealth:
    record = read_json(schedule_dir / "schedule.json")
    trigger = record.get("trigger") if isinstance(record.get("trigger"), dict) else {}
    interval = trigger.get("everyMs") if isinstance(trigger.get("everyMs"), int) else None
    health = ScheduleHealth(
        schedule_id=str(record.get("id", schedule_dir.name)),
        name=str(record.get("name", "")),
        paused=bool(record.get("paused", False)),
        interval_ms=interval,
    )
    history_path = schedule_dir / "history.json"
    runs: list[dict[str, Any]] = []
    if history_path.exists():
        history = read_json(history_path)
        candidates = history.get("runs") if isinstance(history, dict) else history
        if isinstance(candidates, list):
            runs = [run for run in candidates if isinstance(run, dict)]
    start = now - window
    for run in runs:
        planned = parse_time(run.get("plannedAt")) or parse_time(run.get("startedAt"))
        completed = parse_time(run.get("completedAt"))
        state = str(run.get("state", "unknown"))
        if planned is not None and start <= planned <= now:
            health.runs_in_window += 1
            health.states[state] = health.states.get(state, 0) + 1
        if completed is not None and completed > now:
            continue
        if completed is not None and start <= completed and state in ("completed", "failed_run"):
            health.terminal_runs_in_window += 1
        if state == "completed" and completed is not None:
            if health.last_completed_at is None or completed > health.last_completed_at:
                health.last_completed_at = completed
        if state.startswith("failed") and completed is not None:
            if health.last_failed_at is None or completed > health.last_failed_at:
                health.last_failed_at = completed
    if not health.paused and interval:
        limit = timedelta(milliseconds=interval * stale_factor)
        reference = health.last_completed_at
        if reference is None or now - reference > limit:
            health.stale = True
            health.alerts.append(
                f"schedule stale: no completed run within {limit.total_seconds():.0f}s"
                + (f" (last completed {iso(reference)})" if reference else " (never completed)")
            )
    failed = sum(count for state, count in health.states.items() if state.startswith("failed"))
    if failed and failed >= max(1, health.runs_in_window // 2):
        health.alerts.append(f"schedule failing: {failed} of {health.runs_in_window} runs in window failed")
    return health


def receipt_marker(schedule_id: str) -> str:
    return f"(schedule {schedule_id})"


def load_session(
    session: Path,
    schedule_id: str,
    now: datetime,
    window: timedelta,
    ack_tools: tuple[str, ...],
    ack_grace: timedelta,
    terminal_runs_in_window: int,
    max_unacked: int,
    max_consecutive_errors: int,
) -> tuple[DeliveryHealth, ProcessingHealth]:
    start = now - window
    receipts: list[datetime] = []
    assistant: list[tuple[datetime, str, bool, str | None]] = []
    marker = receipt_marker(schedule_id)
    for record in read_jsonl(session):
        stamp = parse_time(record.get("timestamp"))
        if stamp is None or stamp < start or stamp > now:
            continue
        if record.get("type") == "custom_message" and record.get("customType") == "subagent-notify":
            content = record.get("content")
            if isinstance(content, str) and marker in content:
                receipts.append(stamp)
            continue
        message = record.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        stop = str(message.get("stopReason") or "")
        acked = False
        for part in message.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "toolCall" and str(part.get("name")) in ack_tools:
                acked = True
                break
        excerpt = None
        if stop == "error":
            raw = message.get("errorMessage") or message.get("error") or ""
            if isinstance(raw, str) and raw:
                excerpt = raw.strip().splitlines()[0][:80]
        assistant.append((stamp, stop, acked, excerpt))
    receipts.sort()
    assistant.sort(key=lambda item: item[0])

    delivery = DeliveryHealth(
        receipts_in_window=len(receipts),
        last_receipt_at=receipts[-1] if receipts else None,
        terminal_runs_in_window=terminal_runs_in_window,
    )
    delivery.undelivered_completions = max(0, terminal_runs_in_window - len(receipts))
    if delivery.undelivered_completions:
        delivery.alerts.append(
            f"delivery gap: {delivery.undelivered_completions} terminal run(s) without a receipt in the session"
        )

    processing = ProcessingHealth()
    for received in receipts:
        outcome = "unprocessed"
        deadline = received + ack_grace
        for stamp, stop, acked, _ in assistant:
            if stamp < received:
                continue
            if stamp > deadline:
                break
            if stop == "error":
                if outcome == "unprocessed":
                    outcome = "errored"
                break
            outcome = "recorded" if acked else "processed"
            if acked:
                break
        if outcome == "recorded":
            processing.recorded += 1
            processing.processed += 1
        elif outcome == "processed":
            processing.processed += 1
        elif outcome == "errored":
            processing.errored += 1
        else:
            processing.unprocessed += 1
    for stamp, stop, acked, excerpt in assistant:
        if acked and stop != "error":
            processing.last_ack_at = stamp
        if stop == "error":
            processing.last_error_at = stamp
            processing.last_error_excerpt = excerpt
    streak = 0
    for _, stop, _, _ in reversed(assistant):
        if stop == "error":
            streak += 1
        else:
            break
    processing.consecutive_errors = streak
    pending = processing.errored + processing.unprocessed
    if pending >= max_unacked and pending > 0:
        processing.alerts.append(
            f"processing gap: {pending} receipt(s) not processed in window ({processing.errored} followed by an error turn, {processing.unprocessed} with no turn)"
        )
    if streak >= max_consecutive_errors and streak > 0:
        processing.alerts.append(
            f"model turns failing: {streak} consecutive error turns"
            + (f", last {processing.last_error_excerpt!r}" if processing.last_error_excerpt else "")
        )
    return delivery, processing


def build_report(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    window = timedelta(minutes=args.window_minutes)
    schedule = load_schedule(Path(args.schedule_dir), now, window, args.stale_factor)
    delivery, processing = load_session(
        Path(args.session),
        schedule.schedule_id,
        now,
        window,
        tuple(args.ack_tool),
        timedelta(seconds=args.ack_grace_seconds),
        schedule.terminal_runs_in_window,
        args.max_unacked,
        args.max_consecutive_errors,
    )
    alerts = schedule.alerts + delivery.alerts + processing.alerts
    return {
        "generated_at": iso(now),
        "window_minutes": args.window_minutes,
        "schedule": {
            "id": schedule.schedule_id,
            "name": schedule.name,
            "paused": schedule.paused,
            "interval_ms": schedule.interval_ms,
            "runs_in_window": schedule.runs_in_window,
            "states": schedule.states,
            "last_completed_at": iso(schedule.last_completed_at),
            "last_failed_at": iso(schedule.last_failed_at),
            "stale": schedule.stale,
            "alerts": schedule.alerts,
        },
        "delivery": {
            "receipts_in_window": delivery.receipts_in_window,
            "terminal_runs_in_window": delivery.terminal_runs_in_window,
            "undelivered_completions": delivery.undelivered_completions,
            "last_receipt_at": iso(delivery.last_receipt_at),
            "alerts": delivery.alerts,
        },
        "processing": {
            "processed": processing.processed,
            "recorded": processing.recorded,
            "errored": processing.errored,
            "unprocessed": processing.unprocessed,
            "consecutive_errors": processing.consecutive_errors,
            "last_ack_at": iso(processing.last_ack_at),
            "last_error_at": iso(processing.last_error_at),
            "last_error_excerpt": processing.last_error_excerpt,
            "alerts": processing.alerts,
        },
        "alerts": alerts,
        "verdict": "ALERT" if alerts else "OK",
    }


def format_text(report: dict[str, Any]) -> str:
    schedule = report["schedule"]
    delivery = report["delivery"]
    processing = report["processing"]
    lines = [
        f"Mission Control health {report['verdict']} at {report['generated_at']} (window {report['window_minutes']} min)",
        "",
        f"1. Schedule execution: {schedule['id']} paused={schedule['paused']} runs={schedule['runs_in_window']} states={schedule['states']} last_completed={schedule['last_completed_at']} stale={schedule['stale']}",
        f"2. Receipt delivery: receipts={delivery['receipts_in_window']} terminal_runs={delivery['terminal_runs_in_window']} undelivered={delivery['undelivered_completions']} last_receipt={delivery['last_receipt_at']}",
        f"3. Processing/ack: processed={processing['processed']} recorded={processing['recorded']} errored={processing['errored']} unprocessed={processing['unprocessed']} consecutive_errors={processing['consecutive_errors']} last_ack={processing['last_ack_at']} last_error={processing['last_error_at']}",
    ]
    if report["alerts"]:
        lines.append("")
        lines.append("Alerts:")
        lines.extend(f"- {alert}" for alert in report["alerts"])
    return "\n".join(lines)


def notify(report: dict[str, Any], command: list[str], title: str) -> str:
    body = "; ".join(report["alerts"])[:900]
    argv = [*command, title, "--body", body]
    try:
        completed = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"notify failed: {error}"
    if completed.returncode != 0:
        return f"notify failed: exit {completed.returncode} {completed.stderr.strip()[:200]}"
    return "notify sent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schedule-dir", required=True, help="pi-subagents schedule directory containing schedule.json and history.json")
    parser.add_argument("--session", required=True, help="Pi session record (.jsonl) of the Mission Control session")
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--ack-tool", action="append", default=None, help="tool call name that counts as acknowledgement (repeatable; default: todo)")
    parser.add_argument("--ack-grace-seconds", type=int, default=600)
    parser.add_argument("--max-unacked", type=int, default=2)
    parser.add_argument("--max-consecutive-errors", type=int, default=3)
    parser.add_argument("--stale-factor", type=float, default=2.0, help="multiples of the schedule interval without a completed run before the schedule is stale")
    parser.add_argument("--now", default=None, help="ISO-8601 reference time (default: current UTC time)")
    parser.add_argument("--json", action="store_true", help="print the JSON report instead of text")
    parser.add_argument("--notify", action="store_true", help="send a visible notification when the verdict is ALERT")
    parser.add_argument("--notify-command", default=None, help="notification command (default: herdr notification show)")
    parser.add_argument("--title", default="Mission Control health ALERT")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.ack_tool is None:
        args.ack_tool = list(DEFAULT_ACK_TOOLS)
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        parser.error("--now must be ISO-8601")
    try:
        report = build_report(args, now)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"mc_health: cannot read inputs: {error}", file=sys.stderr)
        return EXIT_USAGE
    notice = None
    if args.notify and report["alerts"]:
        command = args.notify_command.split() if args.notify_command else list(DEFAULT_NOTIFY_COMMAND)
        if command[:1] == ["herdr"] and os.environ.get("HERDR_ENV") != "1":
            notice = "notify skipped: not inside Herdr (HERDR_ENV != 1)"
        else:
            notice = notify(report, command, args.title)
    if notice:
        report["notification"] = notice
    print(json.dumps(report, indent=2) if args.json else format_text(report) + (f"\n{notice}" if notice else ""))
    return EXIT_ALERT if report["alerts"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
