# Mission Event Line Design

**Date:** 2026-09-08

**Status:** Approved design; pilot emission pending after merge readback of this record

**Governing ADR:** ADR 0031

**Roadmap issue:** issue 37 of this repository (iteration 1 of 5)

## Purpose

Give the Operator one line per Factory cycle, produced by the project Orchestrator and relayed unchanged by Mission Control, that is enough to decide adopt, adjust, discard, or continue without opening any Factory pane.

## Boundary

Mission Control is the Operator's sole attention interface and is not accountable for Factory outcomes. The project Orchestrator owns its Factory, its delivery, and this report. The Operator owns the decision. This record covers the Handbook Factory pilot only; no other project adopts it by this record, and nothing here authorizes a later roadmap issue.

## Message shape

Exactly one line, no line breaks, five fields in this order:

```
MISSION_EVENT project=<id> work_item=<id> outcome=<delivered|blocked> evidence=<PR/receipt> next_action=<...>
```

- `project`: the repository or project identifier the Orchestrator serves.
- `work_item`: the identifier the Operator used when authorizing the work.
- `outcome`: `delivered` only after the configured delivery has completed and been read back from the remote, as required by the authorization gate of issue 37; otherwise `blocked`.
- `evidence`: resolvable references only, such as a pull request URL, a merge commit, or a concrete blocker description.
- `next_action`: the decision or action the Operator is asked for.

The line is transport-neutral text. It is not a schema, and no field is added without adjusting this record through a later authorized issue.

## Emission point

The Orchestrator emits the line once per cycle, as its final action, at exactly one of two moments: after the configured delivery has been read back from the remote, or at a real blocker the Orchestrator cannot resolve within its authorization.

Procedure:

1. Wait until the `mission_control` agent has settled and is ready for input: `herdr agent wait mission_control --until idle --until done --timeout <ms>`. Both states mean ready for input; `done` is the same state reached while the tab was unseen, so waiting on `idle` alone can time out on an available pane. A line sent while Mission Control is working or while the Operator is typing in that pane can be lost.
2. Send the line once through the Herdr 0.8.2 agent prompt surface: `herdr agent prompt mission_control "<line>"` without `--wait`. `agent_blocked` or `agent_prompt_stalled` returned by Herdr means the line was not accepted; do not resend blindly.
3. Verify arrival by reading the pane (`herdr agent read mission_control --source recent-unwrapped`) or the Mission Control session record, and keep that read as evidence. Do not use `--source detection` for this check; it is the bottom-buffer snapshot used for agent detection and can lose the line once Mission Control starts responding.
4. If arrival cannot be verified, record it as a blocker for the Operator instead of emitting a second line. Retries, acknowledgements, and durable inboxes are deferred by issue 37.

No other Orchestrator-to-Mission-Control traffic is part of this design. Worker callbacks stay inside the Factory and never reach Mission Control.

## Pilot evidence

Baseline before this design, 2026-09-08: the Handbook roadmap delivery merged as commit `adc6149` at 02:54:27 UTC and the Orchestrator emitted its line shortly afterwards, while Mission Control was running a delegate and the Operator was typing in that pane. The Mission Control session record shows lines from another project arriving as user messages at 02:50 UTC and 02:53 UTC, and shows no user message carrying the Handbook line at any point. Mission Control learned the outcome through its own delegate at 03:04 UTC. The line shape was sufficient; the emission moment was not.

Pilot: the Handbook Factory cycle that delivers this record emits its line with the procedure above after merge readback. Its arrival evidence is recorded as a comment on issue 37, because the issues are the authoritative status record and this design record is not rewritten after delivery.

## Observable acceptance mapping

| Issue 37 criterion | Observable evidence |
| --- | --- |
| Exactly one line is emitted per cycle | The Orchestrator's own cycle log shows a single `herdr agent prompt mission_control` invocation for this work item, and the Mission Control read below shows exactly one matching user message |
| The line reaches the `mission_control` pane | `herdr agent read mission_control --source recent-unwrapped` taken after emission, or the corresponding Mission Control session record entry, captured and cited on issue 37 |
| The Operator decides from the line alone, with no Factory pane opened | The Operator states at decision time that the line and its cited evidence were sufficient and that no Factory pane was opened; that statement is recorded on issue 37 |
| The evidence reference resolves | For `outcome=delivered`, the pull request URL and merge commit named in the line resolve; for `outcome=blocked`, the blocker description names a concrete condition the Operator can act on |

## Stop or discard rule

Discard this design if, after the pilot, the Operator still had to open a Factory pane to decide, or if the line was emitted more than once or not at all. If it is adjusted, adjust only the field set. Never add a second channel between the Orchestrator and Mission Control.

## Deferred

Event schema, mailbox or durable inbox, retries, acknowledgement, multi-project aggregation, any Coordinator role, fleet-wide adoption, and the later roadmap issues 38 to 41.

## Provenance

Homeserver Factory protocol V2 and V2.1 session evidence (2026-09-07) and the Incubadora delivery of its Factory proof of concept (2026-09-07) established the single-line callback shape inside a Factory. Wiki, Incubadora, A4S, Drive, and Homeserver material remain provenance and evidence only.
