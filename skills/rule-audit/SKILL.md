---
name: rule-audit
description: "Trigger: audita reglas, audit rules, audit AGENTS.md or CLAUDE.md, reglas debiles, weak rules, rule strength, backlog de hardening, por que no sigues mis reglas. Scores rule files 0-10 against strong-rule properties, maps the repo's enforcement harness, and emits a hardening-proposal backlog."
license: Apache-2.0
metadata:
  author: "pablontiv"
  version: "1.1"
---

## Activation Contract

Load when the user asks to audit, score, or strengthen agent rule files (such as AGENTS.md, CLAUDE.md, runtime rule directories, or CONTRIBUTING agent notes) for a repository or user-global configuration, or asks why instructions keep being skipped.

## Hard Rules

- Read `references/rule-strength-rubric.md` BEFORE scoring anything. Do NOT score from memory of the properties, from this file alone, or from intuition — those are the evasions.
- Audit output goes to the SCREEN first. Apply NO rewrites, moves, deletions, or new backstop files in the same pass. If asked to "audit and fix in one go": deliver the audit, then request explicit per-finding approval. Porqué: audits-to-screen-first is the user's standing rule.
- Score every rule BLOCK (not the file as a whole) 0-10 against the rubric (P1-P7 prose, P8-P9 enforcement). Cite file:line for each finding.
- For a repo target, map the enforcement harness (P8) BEFORE judging backstops: survey justfile/Makefile, `.github/workflows/*`, git hooks, maintenance tests, lint config. Do NOT call a rule "prose-only" without confirming no mechanism at any layer.
- Contradiction check is mandatory: any two rules in the corpus that conflict is an automatic finding, regardless of individual scores.
- P8 is layer-aware: a backstop that fires later than the earliest viable layer is a "late backstop" finding, not a pass.

## Decision Gates

| Target argument | Corpus to collect |
|---|---|
| repo path | Agent instruction and rule files present in the repository, including `AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md`, `CONTRIBUTING.md` agent notes, and runtime-specific rule directories |
| "user" / "global" / omitted in non-repo cwd | The active runtime's documented user-level instruction and rule files; discover them rather than assuming one runtime path |
| both requested | both corpora, scored separately, cross-placement findings allowed |

| Evidence available | Action |
|---|---|
| backscroll installed | run `backscroll patterns --kind corrections --min-confidence 0.6 --robot --indexed-only --all-projects`; tag rules with observed violations |
| backscroll absent/stale | note "no violation evidence" — do not guess frequencies |

## Execution Steps

1. Read `references/rule-strength-rubric.md`.
2. Collect the corpus per the target gate; list files found and skipped.
3. For a repo target: map the enforcement harness — enumerate every mechanism (lint config, git hooks, CI workflows, maintenance tests/scripts, release gates) and the layer (1-6) each occupies. Quote exact paths/recipes.
4. Split rule files into blocks; score each 0-10 with a one-line justification per lost point. For P8, match each rule to a harness mechanism from step 3 or mark it prose-only.
5. Run the contradiction check and the placement check (project content in global scope, always-on heavy protocols better served lazy).
6. Build the hardening backlog (P10): for every low-P8 rule, decide backstop-feasible vs review-only; for feasible ones emit {rule, file:line, proposed mechanism, layer, effort}. Skip judgment-only rules.
7. Cross-reference backscroll corrections when available.
8. Report to screen (see Output Contract). STOP. Await per-finding approval before editing any file or writing any backstop.

## Output Contract

Return on screen:
1. Corpus inventory (files found/skipped).
2. Enforcement harness map (repo target only): mechanism → layer → what it blocks.
3. Per-block score table: block, file:line, score /10, missing properties.
4. Contradictions and placement findings.
5. Hardening backlog: ranked table {rule, file:line, proposed backstop, layer, effort}, plus a review-only list for judgment rules. This is the reusable maintainer-proposal deliverable.
6. Top-N rewrites using `assets/rule-template.md`, and the approval question.

No file edits, no new lint/hook/CI files in the audit pass — the backlog is a proposal, not an application.

## References

- `references/rule-strength-rubric.md` — the 7 properties, tests, anti-patterns, evidence notes.
- `assets/rule-template.md` — rewrite template, worked example, placement decision table.
