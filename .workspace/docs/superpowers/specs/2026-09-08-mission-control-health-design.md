# Mission Control Health Separation Design

**Date:** 2026-09-08

**Status:** Approved design; helper delivered with this record, runtime delta proposed to its owner

**Governing ADR:** ADR 0033

**Tracking issue:** issue 45 of this repository

## Purpose

Make a Mission Control outage visible and attributable without depending on the Mission Control model, by observing schedule execution, receipt delivery, and Mission Control processing as three separate layers, and by stopping useless repeated inference attempts only through the runtime that forces them.

## Incident this answers

On 2026-09-08, 06:12:14Z to 13:17:47Z, the Mission Control session received 31 top-level `429 quota exceeded` errors. The pi-subagents schedule `mc-orchestrator-observation` kept running: 28 receipts reached the session, each forcing an inference turn that failed within 1 to 2 seconds. Mission Control made 0 tool calls and 0 todo updates. Observation outputs were preserved on disk (46 files at inspection time). Nothing visible separated "delivery healthy" from "processing failing".

## Verified runtime boundary

- Schedule runtime: `pi-subagents` 0.64.0 installed under the Pi npm directory, upstream `nicobailon/pi-subagents`. Store: `<project>/.pi/subagents/schedules/<id>/` with `schedule.json`, `history.json`, `events.jsonl`, `runs/`.
- Delivery: completions are sent as `subagent-notify` custom messages with `triggerTurn: true`. `schedule.create` accepts `at`, `every`, `sessionOnly`, `overlap`, `catchUp`, `timeoutMs`, mission fields; no notification or trigger option. Extension configuration has no such switch. Inline workflow scripts cannot call `runs.host`.
- Consequence: Handbook cannot stop the forced turns. The minimal runtime delta is a per-schedule option (for example `notify: "quiet"`) that delivers a scheduled completion with `display: true` and `triggerTurn: false`, so the receipt is visible and preserved but no turn is forced; Mission Control reads it on its next natural turn. Owner: the pi-subagents package. Handbook proposes the delta through Mission Control and does not edit that runtime.
- Visible alert surface: `herdr notification show <title> --body <text>`, model-independent.

## Handbook deliverable

`skills/mission-control-health/` with a Python standard library helper and offline tests. The helper reads the schedule store and the session record read-only and reports:

| Layer | Source | Signals |
| --- | --- | --- |
| Schedule execution | `schedule.json`, `history.json` | runs in window by state, last completion, stale against `stale_factor` intervals, failing ratio; paused schedules are never stale |
| Receipt delivery | session record | scheduled receipts in window, terminal runs (completed or failed) whose receipt never reached the session |
| Processing and acknowledgement | session record | per receipt: processed (non-error turn), recorded (acknowledgement tool call), errored, unprocessed; trailing error streak; last error excerpt |

Verdict `OK` or `ALERT`, exit `0` or `2`, one notification per run when alerting. Defaults: 60 minute window, acknowledgement tool `todo`, 600 s grace, alert at 2 receipts not processed, counting both error turns and receipts with no turn, or 3 consecutive error turns.

## What the helper never does

Retry a turn, probe quota, pause or resume a schedule, restart or replay Factory work, switch provider, model, or account, or modify any input. Those remain explicit Operator decisions taken through Mission Control.

## Running it

Inside Herdr, from a plain shell loop in a pane or a deterministic timer the Operator approves, at the schedule interval. The pilot for this record runs the helper against the real incident window and against a healthy window, and sends one real Herdr notification for the incident window. Durable scheduling outside Herdr (system timers) needs separate Operator approval and is not part of this record.

## Deferred

Runtime delta implementation (owner: pi-subagents), any system timer, dashboards, persistence beyond existing stores, roadmap issues 38 to 41.
