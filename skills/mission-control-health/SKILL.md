---
name: mission-control-health
metadata:
  author: pablontiv
description: Use when Mission Control receipts stop turning into acknowledgements, when a scheduled observation may be failing, delivering, or being processed differently, or when the Operator needs a visible alert that does not depend on the Mission Control model. Reports schedule execution, receipt delivery, and processing separately from read-only records and never retries, pauses, or switches anything.
---

# Mission Control health

Deterministic, model-independent health report for a Mission Control session fed by a pi-subagents schedule. It reads two records without modifying them and reports three layers separately, because each layer failed or survived independently in the 2026-09-08 quota incident:

1. **Schedule execution** from the schedule store (`schedule.json`, `history.json`): runs planned, completed, failed, staleness against the interval.
2. **Receipt delivery** from the session record (`.jsonl`): scheduled receipts that reached the session, compared with terminal runs, completed or failed, since both deliver a receipt.
3. **Processing and acknowledgement** from the session record: for each receipt, whether a non-error turn followed (processed), whether an acknowledgement tool such as `todo` was called (recorded), whether the turn errored, or whether no turn happened; plus the trailing streak of error turns and the last error excerpt.

The helper decides `OK` or `ALERT`, exits `0` or `2`, and optionally sends one visible notification through `herdr notification show`. It performs no inference, no retry, no probe, no pause, no restart, and no provider or model change.

## Run

Use a Python 3.11+ executable as `python`, `python3`, or an equivalent platform command.

```bash
python skills/mission-control-health/helper/mc_health.py \
  --schedule-dir <project>/.pi/subagents/schedules/<schedule-id> \
  --session <mission-control-session>.jsonl \
  --window-minutes 60 --notify
```

Options: `--ack-tool` (repeatable, default `todo`), `--ack-grace-seconds` (default 600), `--max-unacked` (default 2), `--max-consecutive-errors` (default 3), `--stale-factor` (default 2 intervals), `--now` for replaying a past window, `--json`, `--notify-command` to replace the notification command, `--title`. The notification command is split on whitespace, so its executable path must not contain spaces.

`--notify` sends only when the verdict is `ALERT`. With the default command it requires `HERDR_ENV=1` and is skipped otherwise, so the alert is visible in Herdr and never depends on the session's model. Inside Herdr, this runs as a plain-shell loop in a pane or from any deterministic timer the Operator approves. Nothing here decides an outcome for the Operator; the alert is a signal.

## Boundaries

- Read-only. Inputs are never written; the tests verify their digests.
- No automatic action follows an alert. Pausing a schedule, switching a model, or replaying work stays an explicit Operator decision.
- Preserving reports is the runtime's job; pi-subagents already stores each observation output and receipt. This helper points at gaps, it does not copy or resend.
- Stopping forced inference turns on scheduled receipts is a runtime change owned by the schedule runtime, not by this skill.

## Verify

```bash
python -m unittest discover -s skills/mission-control-health/tests -t skills/mission-control-health -p "test_*.py" -v
```

The tests inject offline `429` error turns, delivery gaps, stale and paused schedules, and a fake notification command. They never contact a provider.
