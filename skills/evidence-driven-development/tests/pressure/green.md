# Evidence-Driven Development pressure evidence — GREEN

Guided replay of the same scenarios recorded in `baseline.md`, under identical
conditions. Scoring was manual against each scenario's `pass` contract; the runner
records raw output only.

## Approved inputs

- Skill under evaluation (SHA-256):
  `3b620f0dd6a9811ab21760efe11133ae4412ddee244d48db6eda2c30c4555816` — the bytes
  published as `../../SKILL.md`.
- Runtime trigger (SHA-256):
  `f517f304fef0de78835cdc393d431096cef3334de7dcc0b87e1cf0e5652a2880` — the bytes
  published as `runtime-trigger.md`.
- `test_published_assets_match_the_reviewed_campaign_inputs` pins the trigger and both
  scenario files, so this report cannot silently drift away from the inputs it describes.

## Arms

- **Trigger only:** the exact runtime trigger, no EDD skill registration.
- **Trigger plus skill:** the runtime trigger with the EDD skill registered and loaded.

## Historical pressure results

| Scenario | No guidance | Trigger only | Trigger + skill |
| --- | ---: | ---: | ---: |
| unstable-ordering | 0/5 | 5/5 | 5/5 |
| permissive-mock | 0/5 | 5/5 | 5/5 |
| invented-fixture | 0/5 | 5/5 | 5/5 |
| proxy-state | 0/5 | 5/5 | 5/5 |
| wrong-causal-class | 0/5 | 5/5 | 5/5 |
| **Material total** | **0/25** | **25/25** | **25/25** |
| simple-local (proportional) | 5/5 | 5/5 | 5/5 |

Manual review found no false-positive passes. After the static publication hardening
that produced the digest above (`Use when` description, `## Quick reference`, and
`## Example`), the complete guided arm passed again at `30/30`.

## Skill loading

The JSON-traced load check was recorded before the static hardening, so it proves
progressive skill loading for the pre-hardening skill variant, not for the published
digest. The post-hardening 30/30 guided arm was re-run against the published bytes and
reviewed from its raw per-run outputs, but only the reviewed campaign summary is
versioned here; the raw transcripts live in the ephemeral campaign directory and are not
preserved in this repository.

An earlier harness variant with `read` disabled could not load the progressively
disclosed skill resource; that defect was fixed before the arms above were recorded.

## Differential content results

| Scenario | No guidance | Trigger only | Trigger + skill |
| --- | ---: | ---: | ---: |
| permanent-ledger | 5/5 | 5/5 | 5/5 |
| stop-value-calibration | 5/5 | 5/5 | 5/5 |
| causal-rca | 5/5 | 5/5 | 5/5 |

These probes are non-discriminating: the base model already behaves correctly, so they
supply no evidence for or against incremental skill value.

## Evidence states

- `VERIFIED`: the no-guidance base model fails all 25 material historical runs.
- `VERIFIED`: the runtime trigger passes all 25 material runs and preserves `5/5`
  proportional local behavior.
- `VERIFIED`: integrated runtime behavior — registering and loading this skill
  alongside the trigger passes all 25 material runs, preserves `5/5` proportional local
  behavior, and reached `30/30` after static hardening. This satisfies the approved
  integrated-runtime replay criterion.
- `VERIFIED`: at least one JSON-traced guided replay read the full skill before
  deciding, for the pre-hardening skill variant.
- `UNKNOWN`: incremental behavioral uplift of the skill beyond the runtime trigger. No
  tested scenario distinguishes the two arms.
- `UNKNOWN`: behavior in a real multi-turn implementation pilot.

## Interpretation

Trigger-only parity is diagnostic, not a publication gate. The approved design assigns
concise activation and the strict live-system policy to the runtime trigger, and
reusable method detail to the skill; it never required the historical replay set to
isolate the skill's independent contribution. The owner accepted this reading, so
publication proceeds with the residual `UNKNOWN` disclosed rather than resolved.

Do not restate integrated-runtime evidence as measured skill-only uplift. A new replay
is warranted only when the skill bytes or the runtime trigger change.
