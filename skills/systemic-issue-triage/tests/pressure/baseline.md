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

## cwd-repository-authority

Result: FAIL

Violated requirement IDs: `cwd-git-root`, `sole-repository-scope`, `reject-checkout-substitution`, `fail-closed-outside-git`

Verbatim excerpt: "Using **superpowers:systematic-debugging** to triage issue #44 across both checkouts."

Rationalization: Without a binding CWD authority rule, the response accepted both checkouts as potential triage scope. It neither resolved the Git root containing the current working directory nor rejected silent substitution with `/workspace/other-repo`; when tools were unavailable, it reported a generic access blocker rather than the required outside-Git failure behavior.

Fresh-context control: 5/5 independent samples allowed `/workspace/other-repo` to replace the CWD repository, 4/5 selected it as the preferred checkout, and 3/5 explicitly endorsed silent fallback outside Git. Representative excerpt: "I would **silently switch to `/workspace/other-repo`** and continue the investigation there." The recurring rationalization was that recency or completeness can override workspace authority.

## no-argument-autonomous-intake

Result: FAIL

Violated requirement IDs: `infer-tracker-from-origin`, `automatic-open-issue-inventory`, `no-request-for-identifiers`, `complete-triage-output`

Observed runtime excerpt: "Awaiting the issue identifiers or tracker links to triage."

No-tools baseline excerpt: "Discover and verify source issues" was returned only as a pending step rather than an action mandated by the skill.

Rationalization: The current skill requires verified source issues but does not assign responsibility for discovering them. A no-argument invocation can therefore stop after resolving repository scope, ask the user for identifiers, or leave issue discovery as pending work instead of inferring the tracker from `origin` and enumerating every open issue.

Fresh-context control: 4/5 independent samples stopped, requested source issues, or failed to produce the required triage; only 1/5 improvised tracker discovery and completed a report. Representative failure: "Please provide the source issue(s) or ticket identifiers to triage." This variance confirms that autonomous intake is not a binding contract in v0.2.0.
