---
name: model-optimizer
description: Use when optimizing, assigning, validating, or refreshing models for agents in Pi or OpenCode, especially when availability, authentication, live response, cost, quotas, cache, vision, effort, or adversarial review independence may affect routing.
---

## Core principle

Catalog is not a live response. Runtime-local live evidence outranks catalogs, advisors, aliases, and stale snapshots. Only an exact runtime model ID with a live PASS through the selected runtime is assignable. Without that evidence, do not produce a final mapping or claim success.

## Runtime gate

Resolve Pi versus OpenCode before runtime reads. If both are plausible, ask one concise question. If no runtime/tool access is available, state checks are not executed, fill the output contract with pending evidence, give the exact next commands, and stop before changes.

## Evidence sets

Use nested sets: catalog-local IDs advertised by the runtime; ready-local IDs with ready credentials; live-local IDs that respond through the runtime. FAIL/HANG, unauthenticated, catalog-only, advisor-only, and never-responded IDs are exclusions for this run.

## Helper usage

Use only read-only helpers:

```bash
python scripts/model_optimizer.py inventory --runtime auto --output inventory.json
python scripts/model_optimizer.py check --inventory inventory.json --model provider/model --timeout 60 --output health.json
```

The helper never mutates configuration.

## Selection criteria

Classify every agent assignment before naming models: workload, context/output, tool use, vision, reasoning criticality, speed, cost, quotas, cache, supported options, and current assignment health. Analyze all assignments and list every required remap, including prompt-stated unauthenticated or catalog-only assignments; never repair one profile and ship.

## Adversarial pairs

Adversarial independence requires different model families. Different providers serving the same family are not an adversarial pair. Treat `claude-x` and `claude-y` as the same Claude family unless live metadata proves otherwise. Require different model families when enough live-local PASS families exist.

## Online reconciliation

Use official or advisor metadata only after runtime-local inventory/readiness/live checks. Advisor-only or catalog-only models stay excluded. Preserve conflicts and use runtime-local values for IDs, options, context, and modalities.

## Proposal contract

Proposals include before/after mappings, exclusions, evidence, and exact config fields. If profiles are absent, show before/after as pending, not final. Include effort/options only when supported by the runtime/provider. Unsupported effort is omitted from config and may appear only as prompt-level intent.

## Approval and apply

Stop for explicit approval before writes. A request to optimize, hurry, apply, certify, or explain changes is not approval to mutate configuration.

## Reload confirmation

After approved native apply, state hot-reload, `/reload`, restart, or new-session semantics. Require post-reload responses from affected agent paths before claiming success.

## Red flags

Stop on urgency overriding checks, catalog prestige, aliases, partial remap, unsupported effort, success-before-reload, or provider-name independence claims.

## Output contract

Report exactly: Target runtime; Evidence status; Complete assignment analysis; Candidate health PASS/FAIL/HANG; Exclusions; Proposed before/after; Options versus prompt intent; Approval gate; Reload and post-reload plan.
