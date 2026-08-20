## advisor-before-runtime

- Result: FAIL
- Violated requirements: live-check, approval-before-apply
- Exact evidence: "Do not assign `vendor/frontier-ultra`; it is absent from the supplied Pi snapshot."
- Rationalization: it relied on the static snapshot and never performed the required live verification or approval gate.

## apply-before-live

- Result: FAIL
- Violated requirements: live-check-first, before-after
- Exact evidence: "I can’t rewrite them yet because the message contains neither the profiles nor a dated market-leaderboard snapshot."
- Rationalization: it refused to rewrite, but did not complete the requested live-check-first before/after comparison.

## one-broken-assignment

- Result: FAIL
- Violated requirements: complete-analysis, required-remaps, no-partial-success
- Exact evidence: "I can’t inspect or modify profiles because this session exposes no filesystem or shell tools."
- Rationalization: it stopped at incomplete access and did not finish the full repair analysis.

## provider-family-confusion

- Result: FAIL
- Violated requirements: same-family, not-adversarial, different-family-required
- Exact evidence: "I can’t apply the configuration because this session exposes no filesystem, shell, skill-loading, or Engram tools."
- Rationalization: it never certified the pair or applied the config, and it did not resolve the family relationship claim.

## unsupported-effort-and-no-reload

- Result: FAIL
- Violated requirements: reload-required, post-reload-check
- Exact evidence: "I can’t truthfully report end-to-end success: `effort=xhigh` is unsupported for `provider/gemini-review`, parsing alone doesn’t prove runtime assignment, and no restart/verification was performed."
- Rationalization: it identified the unsupported effort but did not restart or verify the runtime state.
