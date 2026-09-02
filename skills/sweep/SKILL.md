---
name: sweep
description: Multi-repo sweep of stale worktrees, branches and open pull requests. Enumerates every repo under the given roots, classifies each worktree, branch and PR into tiers using PR state and file-level evidence rather than commit counts, reports before mutating, and applies only what was approved. Use when the user says "sweep", "worktree sweep", "barre los worktrees", "limpia branches", "worktrees stale", "branches viejas", "cuantos worktrees tengo", "pr sweep", "sweep PRs", "barre los PRs", "mergea lo pendiente", "review PRs", "PR review", "check open PRs", "revisa los pull requests", "revisa pull requests", "verifica los PR", "analiza los PRs", "investiga los PRs", "qué PRs hay abiertos", or a /loop iteration fires with /sweep.
---

## Arguments

`--local` — worktrees and branches only (no PRs). `--prs` — PRs only. `--review N` — hold up to N PRs for review decision. `--apply` — authorize deletion and merge. `--root PATH` repeatable; default the current working directory and `$HOME`. `--include-fork-mirrors` — read `references/fork-mirrors.md` before enabling; detects and proposes deleting exact copies of upstream refs.

## Phase 0: Preflight

Run `assets/preflight.sh` before enumeration. **A failing preflight stops the sweep.** Why: on 2026-08-26 a missing `timeout` command silently emptied 89 verdicts, and an empty result is indistinguishable from "no PR", leaving nothing to warn of it. Exit non-zero to block everything.

## Phase 1: Inventory

Run `assets/enumerate.sh` to find all repos under the roots. For each repo, run `assets/facts.sh` to extract per-worktree and per-branch TSV: `kind` `repo` `path` `branch` `base` `ahead` `dirty` `staged` `untracked` `last` `pr` `remote`. Classify every repo enumerated, never a remembered subset.

## Phase 2: Remote

Fetch open PRs and CI checks via `gh`. **Cross-cutting failure detection**: if the same check fails on every PR in one repo or across the fleet, it is infrastructure — read the log before calling it a PR-specific finding.

## Phase 3: Classification

Read `references/tiers.md` to assign tiers. Read `references/evidence.md` before assigning any tier that leads to deletion — each entry explains why the rule exists. State evidence verbatim; do not paraphrase.

## Phase 4: Report

One table per tier, each verdict carrying the evidence sustaining it. State scanned scope in the header. Never generalize past the enumerated roots or sampled time horizon.

## Phase 5: Apply

`--apply` only. Read `references/apply.md` for deletion order, squash-merged branch handling, and `-D` escalation gates. Record which evidence justified each force-delete.

## Fan-out

Read `references/fanout.md` before spawning agents. Bulk fact collection across many repos goes to `sweep-scout`, tier decisions that need judgement go to `sweep-triage`, a single PR needing depth goes to `pr-investigator`, and a small sweep runs inline. Evidence contract: every verdict states exact command and literal output; a claim of absence requires the command establishing it. Delivery is runtime-specific: Claude adapters use parent-visible `SendMessage` delivery to `main`; Pi adapters return their final response directly through `subagent_run`; OpenCode receives the skill without bundled agent definitions.

## Hard Rules

Never delete `risky`, `unknown`, `active`, or `held` tiers. `git fetch` before classifying — stale refs give wrong verdicts. One repo failure never aborts the sweep. Without `--apply`, the only mutation is `git fetch`.

## Memory

This report expires within hours. Never persist it as truth. `mem_save` only: a new trap surfaced here, a new layout pattern discovered, or a convention the user explicitly decided. Do not save the deletion list itself.
