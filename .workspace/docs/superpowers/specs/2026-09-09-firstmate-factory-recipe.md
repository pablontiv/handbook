# Firstmate Factory Recipe

**Date:** 2026-09-09
**Status:** Canonical operating recipe. Runtime activation is a separate authorization.
**Owner:** The Operator approves changes to this recipe.

## 1. Contract

This document defines outcomes and operating constraints for Firstmate. It does not replace Firstmate's native task, delegation, supervision, recovery, or workspace model.

Each routed task brief must carry the applicable recipe revision and constraints without adding contradictory execution rules.

The Primary is the user's single interaction point. It owns fleet-level intake, prioritization, routing, and proactive work discovery. A persistent Secondmate owns each routed repository scope. Workers own individual deliverables.

Operational authorization remains repository- and task-specific. This recipe grants no credentials, permissions, destructive effects, publication rights, or production authority.

## 2. Work discovery

The Primary continuously reconciles:

- existing GitHub issues and pull requests;
- review feedback and CI failures;
- active, blocked, paused, and unfinished local work;
- repository history, tests, recent changes, and observed behavior;
- relevant Backscroll and durable-memory records.

The full survey is never a prerequisite for useful work. As soon as one independent candidate has a verified scope, owner, authority boundary, dependency state, and duplicate check, route it. Continue the remaining survey concurrently.

If no existing work is ready, the Primary routes a bounded bug investigation; it does not wait for the user to supply a routine request.

Do not create a competing backlog. Distinguish hypotheses from reproduced defects, and check for duplicate work or an existing fix before opening or dispatching new work.

## 3. Native delegation and parallelism

- Route repository work from the Primary to its scoped Secondmate.
- A Secondmate is idle by default. An empty queue does not authorize it to invent work or survey its repository. Proactive discovery is explicit work routed by the Primary.
- The receiving Secondmate dispatches independent deliverables as native tasks and returns outcomes through Firstmate's parent channel. The parent does not reconstruct or directly supervise the Secondmate's worker tree.
- Dispatch every safe independent task immediately. Do not impose an arbitrary worker cap or wait for another independent task to finish.
- Concurrency may be limited only by verified authority, dependency, quota, machine capacity, or a shared-resource safety constraint. Record the concrete constraint and its reopening condition.
- Before waiting, reconcile active work, ready work, actual constraints, and the next wake condition. "Still reconciling" is not a blocker.
- A blocked task does not block unrelated work. Do not create duplicate or purposeless work merely to demonstrate activity.

## 4. Task and workspace continuity

One deliverable is one Firstmate task with one owned worktree from discovery through delivery:

```text
spike -> findings -> E2E RED -> implementation -> GREEN -> review -> delivery
```

Do not split these phases into separate tasks or worktrees. Keep spike artifacts disposable, but keep the task identity, evidence, acceptance criteria, and product worktree continuous.

Use a scout task when the outcome is still investigation. If its finding becomes an authorized change, promote that scout in place. Do not create a duplicate ship task. If the task needs a different harness, provider, model, or effort, relaunch the same task in the same worktree with preserved context and evidence.

One active writer owns a worktree. Parallelize independent deliverables in separate managed worktrees. Serialize only changes or external operations whose verified safety contract requires it. Never reset, delete, or overwrite unexpected state to bypass a blocker.

## 5. Agent, provider, and model selection

Use Firstmate's native dispatch configuration to select a supported harness, provider, model, and effort for each task—not for each phase.

Choose only from combinations whose authentication, capabilities, tools, quota, and availability were verified recently. Among eligible combinations, consider task fit, observed quality, cost, and remaining quota. Record the actual binding and a short reason.

Do not hardcode a universal model hierarchy in this recipe. Do not add accounts, providers, subscriptions, or credentials; restore prohibited routes; silently substitute model families; or promise unproven failover. Unknown availability is unavailable until verified.

## 6. Context and integrations

Begin from the smallest native baseline:

- Firstmate's tracked instructions, native internal skills, hooks, task records, and supervision;
- the configured Herdr backend;
- no unproven external event adapter or copied runtime wrapper.

Add Backscroll, Engram, Codegraph, Rootline, or another authorized integration only when the current task needs it and its loading, isolation, authority, and output have been exercised with the selected harness. Enable one integration at a time and retain the proof.

Do not load every skill, MCP server, hook, or memory source into every agent. Exclude unrelated personal integrations from the task context without modifying their global installation. Environment allowlists reduce inherited process state but do not, by themselves, prove that a harness ignored global settings or skills; verify effective isolation per harness.

A tool must not duplicate Firstmate's ownership of scheduling, task state, worktrees, or delivery. Persist durable knowledge in its established owner rather than copying it into competing registries.

## 7. Mandatory spike-first flow

Every new capability or unverified bug hypothesis begins with a bounded spike. Existing work is preserved and assessed; it is not blindly restarted.

```text
1. One written question
2. Direct end-to-end PoC
3. Written findings and retained evidence
4. Versioned E2E observed RED
5. Fresh production implementation until GREEN
6. Layer-specific regression tests
7. Required review, validation, and delivery
```

### 7.1 Direct PoC

Write the question in one line. If it does not fit, narrow the spike. Define the evidence target and a finite time or attempt limit.

Exercise the smallest end-to-end path through the real capability and its external boundary. Use native commands directly whenever they can demonstrate the capability on the authorized target. Perform only the identity, ownership, collateral-safety, and cleanup checks needed to execute safely; do not build a validation framework first.

Write minimal disposable code only when native commands cannot cross a required API, protocol, timing, or composition boundary. Record that specific limitation before coding. Convenience, reuse, and anticipated robustness are not justification.

PoC code must contain no production abstraction, generalized framework, reusable module, wrapper, delivery machinery, or premature hardening. Keep it outside product source and never copy, rename, move, or incrementally clean it into production.

Record exact commands or minimal code, observed results, and cleanup evidence. Classify the result as **demonstrated**, **refuted**, or **inconclusive**. A refuted hypothesis produces no manufactured fix. An inconclusive result blocks only dependent implementation.

### 7.2 Findings, RED, and implementation

Write what was exercised, what happened, what failed and why, which correction was demonstrated, and what remains unknown. Separate confirmed causes from hypotheses.

Then write the versioned E2E in the repository's native language and framework before the production change. Derive assertions from the observed behavior and intended outcome. Run it and retain behavioral RED evidence against the exact test and source revisions. A harness failure, mock-only proof, or fabricated failure is not RED.

Implement the smallest production change supported by the findings, written fresh rather than copied from the spike. Retain GREEN evidence from the same behavioral test against the exact candidate. If implementation reveals another unverified capability, spike that boundary before dependent work continues.

Add layer-specific regression tests for traps the E2E does not cover. Passing E2E does not waive security, review, repository validation, or delivery requirements.

Each transition requires its preceding evidence, but missing evidence stops only the dependent transition. Firstmate may use its native task and review records; the Primary must not become a manual per-phase gate for a Secondmate's worker tree.

## 8. Persistence, delivery, and reporting

Persist user instructions, corrections, decisions, task state, bindings, findings, evidence, and supersession in their established authoritative locations. On restart or handover, reconcile those records with actual tasks, worktrees, GitHub state, and external effects before continuing.

A stored instruction, matching file hash, running watcher, successful agent exit, or merged pull request is not proof of applied behavior. Distinguish discovered, demonstrated, implemented, validated, integrated, released, and operational states.

Follow each repository's delivery policy. Preserve independent review where required without inventing permanent role agents. When work finishes or blocks, return its verified outcome and next owner through native Firstmate channels, then resume fleet-level selection without parking unrelated repositories.

Report verified outcomes, meaningful blockers, and decisions requiring user attention. Ask only when a material ambiguity, missing authority, or consequential choice prevents safe progress. Do not claim active monitoring after the responsible session stops.
