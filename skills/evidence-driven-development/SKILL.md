---
name: evidence-driven-development
description: Use when features, bug fixes, refactors, or tests may rely on unverified requirements, external behavior, mocks, fixtures, causal claims, or acceptance signals, before brainstorming or test-driven development.
---

# Evidence-Driven Development

Prevent a specification, fixture, mock, test, and implementation from validating the same unverified premise.

## Quick reference

| Boundary | Decision-changing check | Stop condition |
| --- | --- | --- |
| Discovery | Which material assumption could be wrong, and what is the cheapest safe probe? | No remaining unknown can change the next decision. |
| Test basis | Is each consequential oracle independent of the spec, mock, fixture, and code? | Stop a dependent path while a material premise is unknown. |
| Live system | Were real semantics and variability observed read-only before mutation? | Mutate only after local validation and explicit authorization. |

## Example

A specification and fixture say the first ID in an API CSV is primary. Mark ordering `UNKNOWN`, repeat read-only observations across representative targets, and characterize variability. If order changes, reject the positional design; otherwise derive the failing test from sanitized observations rather than the original fixture.

## Required passes

### Discovery — before brainstorming

Ask only what can change the next decision:

1. What material assumption could make the problem, constraint, or proposed direction wrong?
2. What evidence could confirm or refute it at the relevant boundary?
3. What is the cheapest safe probe?

Stop when no remaining material unknown can change the next decision. For bugs, use systematic debugging for root cause; EDD classifies and consumes its evidence.

### Test basis — after approved design or plan, before TDD

For every consequential oracle:

1. Identify where it came from.
2. Verify that it is independent of the specification, mock, fixture, and code under test.
3. Exercise the observable effect and any decision-relevant variability.

If a material premise remains unknown, state the missing observation and stop the dependent test or implementation path. If evidence refutes the design, return to brainstorming.

## Evidence states

- `VERIFIED`: directly observed or independently established for the stated claim and boundary.
- `INFERRED`: reasoned from evidence but not established.
- `UNKNOWN`: evidence is insufficient.
- `CONFLICTING`: relevant evidence disagrees.

States are scoped. One successful sample does not establish stability or generality. Source inspection can verify static structure; runtime effects require observation at the executable boundary. An unknown is material when another answer could change the next decision, oracle, safety boundary, or user-visible acceptance.

## Calibration

Scale effort with impact, irreversibility, error cost, and uncertainty. Prefer a cheap probe over perfecting documentation. Stop research when plausible new evidence cannot change the next decision. Simple, reversible local work may need only a one-sentence pass.

## Strict live-system profile

Before mutating a live or production-like external system:

```text
observe read-only reality
→ characterize semantics and variability
→ write a failing test from sanitized real evidence
→ implement minimally
→ validate locally
→ obtain explicit live authorization
→ mutate
```

After a failed live mutation, do not retry until root cause is verified, a regression test reproduces it, the fix is independently reviewed, and the user explicitly reauthorizes mutation.

## Optional handoff

Create no permanent evidence ledger. When phases or agents need a handoff, use at most:

```text
Decision:
Verified:
Material unknown:
Test consequence:
```

Discard it after its information is consumed into current tests, contracts, or accepted evidence.

## Red flags

- Treating a specification or plan as proof of external behavior
- Deriving a fixture only from documentation or the code under test
- Letting a permissive mock establish a real interface
- Substituting internal state for the observable effect
- Treating correlation as root-cause evidence
- Converting `UNKNOWN` into a requirement to keep moving
- Producing a longer checklist without changing a decision

Green tests prove consistency with their premises, not that those premises match reality.
