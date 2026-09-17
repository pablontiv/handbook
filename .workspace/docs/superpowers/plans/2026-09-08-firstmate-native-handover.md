# Native Firstmate Handover Implementation Plan

> **For agentic workers:** Do not execute this historical plan. ADR 0038 and the canonical [Firstmate Factory Recipe](../specs/2026-09-09-firstmate-factory-recipe.md) now govern the single Primary and persistent repository-scoped Secondmate topology.

**Goal:** Transfer safely from the old recipe to native Firstmate/Herdr and deliver the existing Homeserver G4 outcome before any production-environment effect.
**Architecture:** One native Firstmate coordinates native task workers. Herdr owns agent terminals and Treehouse owns task worktrees. Existing verified models are selected dynamically without adding providers.
**Tech Stack:** Pinned Firstmate, Herdr, Treehouse and upstream-required dependencies; approved personal integrations.
**Spec:** [Native Firstmate Handover Design](../specs/2026-09-08-firstmate-native-handover-design.md).
**Status:** Superseded on 2026-09-09 by ADR 0038. Historical body retained unchanged.

## 1. Preserve and stop the old owner

**Owner:** Handover executor, not a new Factory.

- [ ] Read live Herdr inventory using the installed CLI's documented session and JSON options; bind exact session/workspace/pane/agent identities. A name match is insufficient.
- [ ] Ask the existing MC and related owners to checkpoint and quiesce without dispatching more work. Capture current revisions, dirty work, pending deliveries and restart mechanisms; hash and read back checkpoints.
- [ ] Inventory scheduled callbacks and timers, then disable only the verified old-recipe triggers. Preserve their definitions and receipts for recovery.
- [ ] Close only the checkpointed related agents using supported commands; re-read inventory and trigger state to prove they cannot continue. Preserve all unrelated sessions and worktrees.

**Failure behavior:** Stop affected actions on ambiguous ownership or unverified preservation; do not mass-kill processes or remove data. Report the exact blocker without manufacturing another approval loop for already-authorized safe work.

## 2. Install and verify native Firstmate

**Owner:** Handover executor; local Firstmate home, never this Handbook checkout's global profile.

- [ ] Resolve an owned installation path and back up any preexisting configuration before changing it. Fetch and verify upstream revision `b84e0e362face25f3dd8945297a3df1320d7668c`; inspect pinned upstream installation and configuration instructions.
- [ ] Install only the upstream-required dependencies and verify actual versions and Herdr protocol compatibility. Do not update Herdr or unrelated tools implicitly.
- [ ] Select the native Herdr backend. Configure every upstream-native extension plus Herdr/subagents/todo/Backscroll/Engram/Codegraph/Rootline; isolate away other personal extensions without global removal.
- [ ] Build Firstmate's native crew/model configuration from verified existing harness/provider/model availability. Preserve no-Copilot and credential boundaries; record cost/quota inputs without inventing availability.
- [ ] Load the scoped no-repeated-approval/nonproduction authority into native captain preferences. Never interpret a native autonomous-execution switch as production authorization or a bypass of product guardrails.
- [ ] Smoke-test native supervision and a harmless worker task with observed binding, extension load, worktree ownership and result receipt. Verify no old dispatcher remains active.

**Failure behavior:** Keep the new workflow stopped when required integrations or boundaries cannot be verified; retain recoverable configuration. Do not silently substitute providers or fabricate an operational receipt.

## 3. Transfer and execute G4

**Owner:** Native Firstmate; Homeserver owns product changes, tests and evidence.

- [ ] Read issue 211, current Homeserver workspace policy, accepted ADRs, linked source/design and checkpoint evidence at their exact revisions; reconcile against the current worktree and open PRs.
- [ ] Preserve completed work and admitted S3 V7 design; identify remaining work from the existing issue, without a second backlog.
- [ ] Reconcile legacy role-specific acceptance wording through Homeserver's governed process; retain substantive independent validation, exact-revision review, destructive-operation approval checks and product safety while using native Firstmate roles.
- [ ] Dispatch the first owned, bounded nonproduction task. Record actual start and subsequent result, not just prompt delivery.
- [ ] Implement all G4 checks and real representative execution with the issue's evidence contract. Run required local validation without unintended host contact; live experiments require exact resource scope, product safeguards and sanitized evidence.
- [ ] Accept G4 only on complete evidence at the delivered revision, with no missing required scenario, orphan resource/credential or foreign-resource impact. Do not accept G5–G10 by implication.
- [ ] Stop before effects belonging to the production-environment milestone and present readiness plus remaining production boundary; nonproduction authorization does not cross it.

## 4. Verify and deliver this documentation

**Owner:** Handbook documentation worker.

- [ ] Review ADR0031/0032/0033/0034; generate and accept successors 0035/0036/0037 through `skills/adr/adr.sh` only. Back up and verify old records first.
- [ ] Run `rootline validate <each changed ADR> --strict`, batch validation for `.workspace/docs/adr`, `.workspace/docs/superpowers` and `profiles/pablontiv`, and `git diff --check`.
- [ ] Execute every test suite from `.github/workflows/ci.yml` and `.github/workflows/test-model-optimizer.yml` with Python 3.11 and pinned `requirements-test.txt`, including sweep shell tests and cleanup compile/help checks. Report local platform limits and any warnings separately from failures.
- [ ] Obtain independent review, commit conventionally and deliver by PR. List all reviewed/superseded/new ADRs and disclose unresolved product-policy reconciliation. Do not merge or claim runtime completion merely because the documentation PR exists.
