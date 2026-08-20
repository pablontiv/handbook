---
name: systemic-issue-triage
description: "Use when evaluating issues, bug reports, backlog items, duplicated fixes, blocked users, or proposed systemic initiatives; classify verified reports by root cause before any design or implementation."
license: Apache-2.0
metadata:
  author: "pablontiv"
  created: "2026-08-20"
  updated: "2026-08-20"
  version: "0.1.0"
  upstream-author: "Alan-TheGentleman"
  upstream-repository: "https://github.com/Gentleman-Programming/gentle-ai"
  upstream-commit: "d1e1777faafc91a34656ba94bd712972dbe427a1"
  ownership: "personal"
---

# Systemic Issue Triage

## Purpose

Triage verified issues by root class. Shrink the system by grouping shared causes instead of proposing one patch per report. Produce a bounded initiative candidate, then stop before design or delivery.

## Input Contract

- Verify source issues or tickets before classifying them. Preserve their identifiers and evidence references.
- Treat an issue's stated mechanism is a hypothesis; the observed symptom is evidence.
- If evidence is missing or the report cannot be classified, use Bucket E and ask the reporter. Do not guess.
- Reproduce claims when repository or runtime access exists. If access does not exist, mark the evidence pending and name the exact verification needed.

## Root-Class Buckets

Every source issue belongs to exactly one bucket:

- **Bucket A — Superseded:** covered by an in-flight design change. Name the change and the named test evidence that will prove closure.
- **Bucket B — Duplicate:** another tracker owns the same known root class. Name the canonical tracker.
- **Bucket C — New defect:** a reproducible bug assigned to a root-cause cluster, never a standalone patch by default.
- **Bucket D — Feature request:** requested behavior rather than a defect. Keep it outside defect clusters unless evidence establishes one shared root.
- **Bucket E — Unclear:** insufficient evidence. Ask the reporter for the missing input instead of inventing a diagnosis.

Use the explicit labels `Bucket A`, `Bucket B`, `Bucket C`, `Bucket D`, and `Bucket E` in the output.

## Clustering Rules

- One root cause produces one cluster. Two or more issues with the same root become one candidate fix boundary.
- N issues do not justify N patches. A root-cause cluster must name every member and the evidence that binds them.
- Do not merge unrelated subsystems merely to reduce tracker count.
- Close issues against named test evidence, not promises or self-reported fixes.
- If a test for the issue's proposed mechanism already passes on unchanged code, the mechanism is wrong; strengthen reproduction around the observed symptom.
- A thread containing two distinct failure modes remains open until both are named and accounted for.
- A dead end without a runnable continuation is primarily a message/exit defect; do not build state machinery around it.

## System-Reduction Check

Before recommending an initiative boundary, ask whether the implied fix adds a state, verb, flag, gate, or parallel representation of existing truth. If it does, flag the growth and seek a boundary that deletes, relaxes, or consolidates instead.

Urgent flags include:

- a wrong or non-runnable exit;
- a gate shipped before the capability that satisfies it;
- a blocked user with no self-service continuation;
- production failure hidden by tests or fixtures taught to accept the defect.

## Output Contract

Return:

1. verified source issues and evidence references;
2. bucket counts;
3. a per-issue table with issue, bucket, root-cause cluster, and evidence;
4. root-cause clusters and their member issues;
5. the proposed initiative boundary, explicitly excluding unrelated clusters;
6. priority and dependency evidence;
7. urgent flags;
8. unresolved questions or pending verification;
9. `next skill: brainstorming` only when a coherent initiative candidate is ready for human approval; otherwise `next skill: none`.

Do not call a candidate approved on the user's behalf. After human approval, route the candidate to `brainstorming`.

## Scope Boundary

- Do not design the solution.
- Do not plan implementation.
- Do not implement fixes.
- Do not mutate issues, tickets, labels, comments, milestones, or project state.
- Do not reproduce `brainstorming`, `writing-plans`, or delivery workflows.
- Stop after reporting the triage result and recommended next skill.
