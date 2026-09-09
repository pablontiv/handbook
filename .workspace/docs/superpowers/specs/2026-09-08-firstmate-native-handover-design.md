# Native Firstmate Handover Design

**Date:** 2026-09-08
**Status:** Operator-approved direction; runtime completion requires separate evidence.
**Governing ADRs:** 0035, 0036, 0037.
**Owner:** Handbook owns portable operating rules; Homeserver owns G4 implementation and acceptance.

## Decision and authority

Replace the active Handbook-recipe Mission Control and its related agents with native Firstmate on Herdr. Use one Firstmate and its native task workers for the single Homeserver outcome; do not require Secondmate, independent legacy QA/Reviewer agents, or the old Factory hierarchy. Keep native supervision, presentation, and all extensions shipped by the pinned upstream revision, plus the named personal integrations: Herdr, subagents, todo, Backscroll, Engram, Codegraph, and Rootline. Exclude other personal extensions from these agents, without uninstalling them globally.

The Operator authorized all necessary action without repeated approval requests until the production-environment milestone. This is authority for scoped nonproduction preparation and delivery, not permission to cross into production. Product safety checks, identity and ownership verification, backups, exact resource plans and destructive-operation approval checks remain effective. An ambiguous production boundary or ownership is a blocker, not permission to guess. Preserve unrelated sessions, worktrees, data, credentials and configuration. This authority does not authorize publication to third-party upstream repositories.

## Native architecture and cost routing

Source: [Firstmate revision b84e0e362face25f3dd8945297a3df1320d7668c](https://github.com/kunchenguid/firstmate/tree/b84e0e362face25f3dd8945297a3df1320d7668c). Follow its [Herdr adapter](https://github.com/kunchenguid/firstmate/blob/b84e0e362face25f3dd8945297a3df1320d7668c/docs/herdr-backend.md) and [configuration contract](https://github.com/kunchenguid/firstmate/blob/b84e0e362face25f3dd8945297a3df1320d7668c/docs/configuration.md), not an invented compatibility layer. Herdr owns terminal agent execution; Treehouse owns task worktrees. The pinned adapter requires protocol 14 or newer. Labels alone are not unique identities.

Firstmate selects among existing, verified model/provider/harness combinations by task, cost and available quota, instead of inheriting fixed legacy role bindings. Record the observed binding and actual limits; unknown quota is not a claim of quantified headroom and does not by itself exclude an authenticated, catalog-verified model. Disclose that uncertainty and prefer known viable comparable options when available. Do not add providers, accounts or subscriptions, restore Copilot, mutate credentials globally, or silently map a missing model to another family. Do not promise automatic quota switching unless supported and exercised. Use native configuration rather than a second registry or custom scheduler. Personal integrations must not create a competing orchestrator.

## Historical disposition

| Record | Disposition |
| --- | --- |
| ADR 0031 | Superseded by 0035 for the active migration; historical roadmap issues 37–41 and their evidence remain intact, not automatically implemented or closed. |
| ADR 0032 | Superseded by 0036; native presentation replaces the required MC panel and fixed binding. Evidence must still distinguish sent from completed. |
| ADR 0034 | Superseded by 0037; remove mandatory fixed QA choreography while preserving no-Copilot, existing-provider and credential boundaries. |
| ADR 0033 | Unchanged historical health guidance and reusable helper; not a requirement to install its old MC scheduler in Firstmate. |

Only script-managed status/successor metadata changes on historical ADRs. Their bodies, completed specs and plans remain intact. The reusable Pi profile and `.workspace/config.yaml` are not silently rewritten: this approved migration is a scoped operational override, not a universal profile upgrade or removal of unrelated delivery rules.

## Outcome and acceptance

The authoritative backlog remains [Homeserver G4, issue 211](https://github.com/pablontiv/homeserver/issues/211): prove the common executable lifecycle-controller contract across its eleven specified scenarios, with independent oracles, real representative execution, reproducible sanitized evidence and explicit failure behavior. G4 contract acceptance is not candidate-gate acceptance; G5–G10 remain unaccepted. S3 V7 is approved source/design, not proof of implementation or all of G4. No duplicated mutable backlog belongs in this document.

At inspection, issue 211 still names independent QA and Reviewer roles. Reconcile that product-owned acceptance wording with the Operator's native-workflow decision before declaring G4 complete; retain substantive independent validation and exact-revision review using Firstmate's native mechanisms, rather than silently waive evidence requirements or recreate mandatory legacy agents. Handbook documentation alone cannot change Homeserver policy or prove G4 acceptance.

## Handover acceptance

1. Saved and verified checkpoints bind exact old agent identities, scopes, pending work, revisions and restart triggers; unrelated state is preserved.
2. Old related execution and triggers are confirmed inactive; no concurrent old/new dispatcher owns the same work.
3. Firstmate source pin, dependency versions, Herdr session/protocol and native worker routing are observed, not inferred from installation.
4. Actual extension load matches the allowed set; binding selection stays inside the verified existing inventory.
5. The native captain receives the G4 source, safety boundary and acceptance evidence requirements and demonstrably dispatches owned nonproduction work.
6. Product acceptance eventually proves G4 completely; a running agent, a plan, a UI, local tests or S3 alone cannot satisfy it.

Installation, shutdown and dispatch receipts are runtime-owned evidence. This design is not a receipt that those operations happened.
