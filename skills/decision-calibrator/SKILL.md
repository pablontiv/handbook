---
name: decision-calibrator
metadata:
  author: pablontiv
description: 'Use after a concrete trigger, not by default: (1) a user correction that contradicts a prior assumption, (2) a re-asked question or "ya te dije" signal, (3) resumed work after compaction, handover, or context loss, (4) a third research round on the same decision with no new decision-changing unknown, (5) choosing between tools or architectures with ongoing operating cost. Not for routine edits or single-step tasks.'
---

# Decision Calibrator

## Overview

Maximize decision quality per unit of effort. Preserve rigor, evidence, traceability, and accumulated state while preventing unnecessary precision, search, rigidity, rework, and cognitive overhead.

**Core principle:** spend rigor where it can still change the outcome.

## Operating State

For non-trivial work, track:

- **Phase:** `EXPLORE | CONVERGE | DECIDE | EXECUTE | RECOVER`
- **Criteria:** `HARD | STRONG | OPTIMIZATION | NICE`
- **Evidence:** `VERIFIED | INFERRED | UNKNOWN | CONFLICTING`
- **Risk:** impact, reversibility, cost of error, uncertainty
- **Canonical state:** decisions, constraints, unknowns, rejected options + reasons, next decision

Keep this internal unless it clarifies work or recovery.

## Ten Controls

1. **STOP-VALUE** — Before more research, identify what remaining information could materially change the decision. If none can, converge.
2. **CONSTRAINT-TYPING** — Never silently promote a preference into a hard requirement. State material reclassifications.
3. **RIGOR-BUDGET** — Scale rigor with impact × irreversibility × cost of error. Reversible low-cost choices get lighter analysis unless depth itself is the goal.
4. **PROBE-BEFORE-PERFECT** — When a cheap experiment can resolve uncertainty, prefer provisional model → probe → refine over perfecting the model first.
5. **RECOVERY-CIRCUIT** — After lost context, contradiction, or repeated invalid assumptions: restore the last reliable state from accepted ADRs (`adr` skill, list), identify affected conclusions, and continue without re-asking known facts.
6. **EARLY-CHECKPOINT** — Before complexity becomes fragile, record the decision as `proposed` via the `adr` skill (decided, constraints, unknowns as `pendientes`, rejected + why as `alternativas`). No in-head checkpoints and no other store.
7. **SEARCH-SATURATION** — Distinguish coverage from exhaustive enumeration. Broaden only while a plausible unseen class could materially outperform current candidates, unless exhaustiveness is required.
8. **ERROR-BLAST-RADIUS** — When an error is found, trace the affected rule and dependent results. Revalidate that subset; neither patch only the visible instance nor invalidate everything.
9. **INTUITION-DIFF** — If evidence and persistent preference diverge, inspect for omitted criteria, weighting errors, or bias. Intuition is a diagnostic signal, not authority.
10. **COGNITIVE-OPEX** — Include recurring mental/operational burden: exceptions, maintenance, supervision, coordination, recovery, and remembered rules.

## Intervention Rules

- **DON'T NAG:** absorb the calibration work silently. Surface it only when it changes the next action, conclusion, or confidence.
- **USER OVERRIDE:** explicit requests for exhaustive research, deeper exploration, or a constraint override optimization rules.
- **NO FAKE SIMPLICITY:** do not close a decision while material uncertainty remains.
- **EVIDENCE DISCIPLINE:** absence of evidence is not evidence of absence. Preserve `UNKNOWN` when appropriate.
- **STATE IS CUMULATIVE:** corrections update the canonical model; never revive an option listed in an ADR's `alternativas` or a superseded ADR without a new ADR.

## Decision Gate

Before recommending closure, answer internally:

1. Are all hard constraints satisfied?
2. Could a material unknown change the winner or invalidate the plan?
3. Is more research worth its expected decision value?
4. Did any recent error contaminate dependent results?
5. Is the chosen option's cognitive operating cost acceptable?

If 1 is no or 2/4 is yes, continue investigation or recover. Otherwise converge, recommend a decision, and on approval mark the ADR `accepted` via the `adr` skill. A correction that invalidates an accepted ADR goes through `supersede`, never a silent edit.

## Red Flags

- Treating undocumented as “no”.
- Re-asking a settled fact.
- Continuing search with no decision-changing unknown.
- Discarding options on a criterion never established as hard.
- Rebuilding the entire analysis after a local error.
- Perfecting an ontology that a cheap probe could test.
- Choosing a technically elegant system whose operating burden dominates its benefit.
