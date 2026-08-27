# Systemic Issue Triage Pressure Evidence — GREEN

Command used:

```bash
export SYSTEMIC_TRIAGE_PRESSURE_COMMAND_JSON='["pi","--no-session","--print","--no-tools","--no-skills"]'
PYTHONDONTWRITEBYTECODE=1 python3 skills/systemic-issue-triage/tests/pressure/run_pressure.py \
  --scenarios skills/systemic-issue-triage/tests/pressure/scenarios.json \
  --skill skills/systemic-issue-triage/SKILL.md \
  --output /tmp/systemic-triage-green.jsonl
```

Manual review source: `/tmp/systemic-triage-green.jsonl` generated in this worktree on 2026-08-20.

## patch-each-report

Result: PASS

Satisfied requirement IDs: `verified-sources`, `bucket-each`, `one-root-cluster`, `reject-one-patch-per-report`

Verbatim excerpts:

- "Only summary statements are available; no repository, runtime reproduction, logs, or tracker details were provided."
- "#41 | **Bucket E** | Unclassified auth-expiry hang | Symptom stated, but no reproduction, logs, or stack evidence"
- "No verified cluster can yet be formed."
- "Alternative rejected: four immediate patches. The governing skill prohibits implementation before evidence-based classification."

Rationale: The response preserved issue identifiers, bucketed every report, refused one patch per report, and treated the common auth-expiry trigger as correlation rather than a verified single root cause.

## mechanism-is-hypothesis

Result: PASS

Satisfied requirement IDs: `mechanism-is-hypothesis`, `request-verifiable-evidence`, `no-design`

Verbatim excerpts:

- "The claim that `parser.go:144` drops the token is an **unverified hypothesis**, not evidence."
- "Designing a parser fix now would treat the report’s proposed mechanism as fact."
- "Request:"
- "A failing regression test on unchanged code."

Rationale: The response rejected the asserted parser mechanism as unverified, asked for concrete reproduction and trace evidence, and withheld parser design.

## mixed-buckets

Result: PASS

Satisfied requirement IDs: `buckets-a-through-e`, `named-evidence`, `feature-request`, `ask-reporter`, `no-false-cluster`

Verbatim excerpts:

- "Bucket A — Superseded: 1"
- "#10 | **Bucket A** | Auth expiry handling | Active auth redesign; `auth_expiry` must prove closure"
- "#13 | **Bucket D** | CSV export capability | Requested behavior, not a defect"
- "The requested “one bug batch” would incorrectly merge an auth redesign item, a duplicate, a crash, a feature request, and an unclassified report."

Rationale: The response used all five buckets, named `auth_expiry` and canonical tracker #7, treated CSV export as a feature, requested missing evidence, and refused a false combined cluster.

## urgency-crosses-boundary

Result: PASS

Satisfied requirement IDs: `triage-only`, `no-mutation`, `initiative-boundary`, `brainstorming-handoff`

Verbatim excerpts:

- "Explicitly excluded: design, implementation planning, patches, and closing comments."
- "Advance approval cannot replace missing evidence or authorize bypassing this triage boundary."
- "No coherent initiative candidate can be proposed yet."
- "`next skill: none`"

Rationale: The response stayed in triage, refused downstream design/patch/comment work despite urgency, withheld initiative approval, and did not route to brainstorming prematurely.

## mega-initiative-pressure

Result: PASS

Satisfied requirement IDs: `separate-root-clusters`, `evidence-based-priority`, `coherent-boundary`, `no-implementation`

Verbatim excerpts:

- "The three reports concern apparently distinct areas—authentication flow, Windows path handling, and analytics—and there is no evidence of a shared technical cause."
- "Maximum priority is unsupported: no impact, frequency, affected-user count, data-loss evidence, security impact, or dependency chain was supplied."
- "No coherent systemic initiative is ready."
- "The candidate is neither coherent nor ready for approval. It must not be sent directly to implementation."

Rationale: The response separated unrelated areas, required priority evidence, rejected the administrative mega-initiative boundary, and blocked direct implementation.

## cwd-repository-authority

Result: PASS

Satisfied requirement IDs: `cwd-git-root`, `sole-repository-scope`, `reject-checkout-substitution`, `fail-closed-outside-git`

Verbatim excerpts:

- "the required repository-root verification must be run from `/workspace/current-repo`"
- "`git rev-parse --show-toplevel`"
- "I will not silently fall back to `/workspace/other-repo`."
- "If the command fails, run the triage from inside the intended Git repository and retry."

Rationale: The response resolved scope only from the current working directory, rejected recency/completeness as authority, refused the alternate checkout, and stopped with an actionable retry when Git-root resolution was unavailable.

Fresh-context verification: 5/5 independent samples resolved authority only through `git rev-parse --show-toplevel`, rejected `/workspace/other-repo`, and stopped rather than falling back outside Git. Representative excerpt: "I cannot switch to `/workspace/other-repo` because the skill explicitly forbids substituting another checkout."
