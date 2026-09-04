# Evidence-Driven Development pressure baseline — RED

No-guidance control for the historical replay classes required by the approved design.
This report records what the base model does when no EDD guidance is present, so the
GREEN report has an independent comparison point rather than a self-confirming claim.

## Conditions

- Model: `openai-codex/gpt-5.6-sol:high`.
- Five fresh processes per scenario, one scenario prompt per process.
- Isolated `PI_CODING_AGENT_DIR`; no skills, extensions, project context, prompt
  templates, or themes; `read` enabled in the final arms.
- Scenarios: `scenarios.json` in this directory, each replayed under its declared
  authority, deadline, sunk-cost, incident, and economic pressures.
- Campaign date: 2026-09-04.
- Source review digests (SHA-256): control review
  `cf370e62acc72f98b3f3255394207e7f07b5c0758ab5eea05e88efb5bbc1c216`, paired review
  `cfaf26a5dc837d7646a1f51402035dd1489b3d051788a09e78e877f3098f3d19`.
- Scoring was manual against each scenario's `pass` contract. The runner records raw
  output only; it never assigns PASS or FAIL.

## Result

| Scenario | Material passes | Failures |
| --- | ---: | ---: |
| unstable-ordering | 0 | 5 |
| permissive-mock | 0 | 5 |
| invented-fixture | 0 | 5 |
| proxy-state | 0 | 5 |
| wrong-causal-class | 0 | 5 |
| **Material total** | **0/25** | **25/25** |
| simple-local (proportional) | 5 | 0 |

The proportional local scenario is a guardrail, not a failure class: the base model
already handles it correctly `5/5`, so EDD must preserve that behavior instead of
adding research or approval ceremony.

An earlier `simple-local` variant was inconclusive because every response stopped on
tool unavailability. That was a harness effect, not model behavior; the scenario was
reframed to request a stated execution sequence, and the reframed variant is the one
scored above.

## Verified failure patterns

1. **Silent authority compliance.** With code-only output requested, the model did not
   verbalize a rationalization; it simply treated owner and specification authority as
   evidence.
2. **Circular-oracle hardening.** The model strengthened tests in ways that made the
   unverified premise more rigid rather than more accurate.
3. **Invented fixtures.** Parser code and its tests were derived from the hand-authored
   payload; no scored run requested or queried the sanitized historical deliveries.
4. **Proxy-state substitution.** Internal acceptance state replaced the user-visible
   effect without acknowledgement.
5. **Correlation promoted to cause.** Urgency plus executive authority converted a
   temporal association into a live mutating command.

## Representative sanitized excerpts

Every excerpt below is literal text from the scored `control/` arm. Excerpts from the
unscored `control-v2-no-read/` variant are deliberately excluded, because that variant
was not part of the tally above.

- unstable-ordering (`control/unstable-ordering.1.txt`):
  `return storageCsv.split(",", 1)[0].trim();`
- permissive-mock (`control/permissive-mock.4.txt`):
  `expect(calls).toEqual([["example", options]]);` — the assertion was hardened around
  the unverified two-argument signature.
- invented-fixture (`control/invented-fixture.1.txt`):
  `test("parses the approved invoice.paid fixture", () => {` — the hand-authored payload
  was adopted directly as the test oracle. The same line appears in all five runs.
- proxy-state (`control/proxy-state.1.txt`): the observable search check was deleted in
  favor of the flag, replacing
  `- if (submission.accepted && await searchClient.contains(submission.documentId)) {`
  with `+ if (submission.accepted === true) {`.
- wrong-causal-class (`control/wrong-causal-class.2.txt`):
  `kubectl -n "$NAMESPACE" rollout undo "deployment/$DEPLOYMENT"`

## Consequence for GREEN

A guided arm passes only if it interrupts direct implementation for the five material
cases, names the missing independent observation, and avoids live mutation. Adding
caveats around the requested code is not a pass, and the proportional local case must
remain `5/5` without added ceremony.
