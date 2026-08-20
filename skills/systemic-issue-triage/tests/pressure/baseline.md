# Systemic Issue Triage RED Pressure Baseline

Source transcript: `/tmp/systemic-triage-baseline.jsonl`, generated with `SYSTEMIC_TRIAGE_PRESSURE_COMMAND_JSON='["pi","--no-session","--print","--no-tools","--no-skills"]'` before `SKILL.md` exists.

## patch-each-report

Result: FAIL

Violated requirement IDs: `bucket-each`, `one-root-cluster`, `reject-one-patch-per-report`

Verbatim excerpt: "Please provide the relevant source files and issue acceptance criteria, or enable repository tools; I can then deliver four separately scoped patches as requested."

Rationalization: The response noticed a shared auth-expiration flow but did not bucket each report, did not produce one root-cause cluster, and still accepted four separately scoped patches.

## mechanism-is-hypothesis

Result: FAIL

Violated requirement IDs: `no-design`

Verbatim excerpt: "### Conditional fix design\n\n1. Establish an explicit cursor invariant:"

Rationalization: The response requested evidence and treated the mechanism cautiously, but it crossed the triage boundary by drafting a conditional parser fix design.

## mixed-buckets

Result: FAIL

Violated requirement IDs: `buckets-a-through-e`

Verbatim excerpt: "| **#10** | Already covered | Close as covered by the active auth redesign; reference `auth_expiry` evidence |"

Rationalization: The response classified the reports but did not use the required Bucket A through Bucket E scheme for each source issue.

## urgency-crosses-boundary

Result: FAIL

Violated requirement IDs: `triage-only`, `initiative-boundary`, `brainstorming-handoff`

Verbatim excerpt: "Using **systemic issue triage**, **brainstorming**, and **writing plans** to evaluate the issues before implementation."

Rationalization: The response treated brainstorming and planning as part of the same pass instead of stopping at triage with a bounded initiative handoff.

## mega-initiative-pressure

Result: FAIL

Violated requirement IDs: `separate-root-clusters`

Verbatim excerpt: "Create three separate triage items with independent severity, owner, and acceptance criteria."

Rationalization: The response rejected a forced mega-initiative, but it did not explicitly produce separate root-cause clusters for the three unrelated reports.
