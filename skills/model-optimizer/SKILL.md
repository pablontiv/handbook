---
name: model-optimizer
description: Use when optimizing, assigning, validating, or refreshing models for agents in Pi or OpenCode, especially when availability, authentication, live response, cost, quotas, cache, vision, effort, or adversarial review independence may affect routing.
metadata:
  author: pablontiv
---

## Core principle

Run one logical optimize flow. Catalog is not a live response: only exact runtime-local model IDs with current live evidence may become assignments. Public benchmarks are priors, aliases are uncertainty, and native config edits happen only after human approval.

## Concise workflow

1. **detect Pi/OpenCode** before runtime reads. If both are plausible, ask one concise question; if neither can be checked, report pending evidence and stop before changes.
2. Run **inventory and delta** with the read-only helper, then identify newly ready providers/models, changed or new agents, missing/unhealthy incumbents, and materially affected routes only; do not sweep a full matrix.
3. Read all affected agent definitions using **scope precedence** for Pi/OpenCode, including inherited tools, permission rules, mutation authority, source scope, and the internal apply target.
4. **derive requirements** and priorities: archetype, tools, context/output, vision, structured output, reasoning/effort, latency, cost, reliability, cache, and adversarial-family independence.
5. **live-check incumbent** routes and plausible challengers. The shortlist is at most four complete routes per agent, including the incumbent when present.
6. Reconcile **bounded benchmark sources** only for affected roles. Preserve identity classes exactly: `EXACT`, `MODEL_EQUIVALENT`, `FAMILY_PROXY`, `ABSENT`, `UNKNOWN`, and `SOURCE_UNAVAILABLE`; search failure is `SOURCE_UNAVAILABLE`, not absence.
7. Run runtime-exact, **tool-confined role evaluation** adaptively for finalists. Do not expose ambient extensions, unrestricted host tools, credentials, arbitrary project paths, raw prompts, raw responses, tool arguments, source code, transcripts, or config paths.
8. Render a **concise proposal**, `NEEDS_MORE_EVIDENCE`, no-op, or `ABSTAIN`. A challenger must materially improve; ties or unresolved evidence retain the incumbent.
9. Stop for **explicit approval**. Requests to hurry, optimize, apply, certify, or explain are not approval to mutate configuration.
10. After approval: **backup, apply minimally, validate, reload**, verify affected agent paths, and on any write/validation/reload/path failure restore the backup, validate again, reload again, and verify restored agent paths before reporting rollback success.

Detailed rules live in `references/optimization-flow.md`, `references/benchmark-sources.md`, and `references/contracts.md`.

## Read-only helper examples

Use existing helper commands only for evidence before approval:

```bash
python scripts/model_optimizer.py inventory --runtime auto --output inventory.json
python scripts/model_optimizer.py check --inventory inventory.json --model provider/model --effort high --timeout 60 --output health.json
python scripts/model_optimizer.py evaluate --inventory inventory.json --agent implementer --model provider/model --effort high --fixture mechanical-slugify --timeout 180 --output evaluation.json
python scripts/model_optimizer.py cache-benchmark --inventory inventory.json --model provider/model --effort high --identity EXACT --source-name Terminal-Bench --benchmark Terminal-Bench --benchmark-version latest-stable --source-url https://example.invalid/replace-with-source --evaluated-model-identity provider/model --harness-or-agent terminal-bench --reasoning-mode high --observed-at 2026-08-20T00:00:00Z --metric-name score --metric-value omit
```

The helper never mutates configuration. Do not invent or call helper mutation subcommands named `apply`, `write`, or `configure`.

## Decision and approval surface

Return exactly one decision per affected route: `CHANGE`, `NO_CHANGE`, `NEEDS_MORE_EVIDENCE`, or `ABSTAIN`. The public proposal may show only agent, current/recommended model and effort, concise reason, important uncertainty/exclusion, and operational trade-off. Keep exact config targets, source paths, cache keys, and artifact plumbing internal to the approval payload.

## Red flags

Stop on urgency overriding checks, benchmark-only aliases, stale cached PASS with current live failure, unsupported sandbox for mutation fixtures, ambient Pi/OpenCode permission escalation, partial remap claims, provider-name independence claims, success-before-reload, or rollback success based only on restored bytes. If a mutation/code-execution fixture has no supported sandbox backend, return `ABSTAIN`; do not certify it from host execution.
