# Federated Skill Ownership and Distribution Design

**Date:** 2026-09-04

**Status:** Approved

**Governing ADRs:** ADR 0018, ADR 0019, ADR 0022, ADR 0030

**Relationship to prior design:** This specification supersedes the operational ownership and distribution model in `2026-08-26-skill-ownership-and-distribution-design.md`. The prior specification remains historical and is not rewritten.

## Purpose

Give every globally consumed Agent Skill one explicit, version-controlled owner while allowing Pi, Claude Code, and OpenCode to discover the same canonical content without divergent runtime copies.

The handbook is not the universal owner of all skills. It owns only independent, global, portable, publicly distributable skills that have no more appropriate product or upstream owner.

## Goals

- Preserve the repository that controls each skill's contract as its canonical owner.
- Absorb orphaned portable skills into the handbook only when no product or upstream repository owns them.
- Project repository-owned skills into runtime directories through direct symlinks.
- Consume external upstream skills through their supported manager with provenance and integrity verification.
- Merge overlapping continuity behavior instead of publishing competing skills.
- Make every handbook-owned skill declare `metadata.author: pablontiv`.
- Back up and verify every live path before replacement, then require approval bound to the observed operation digest.

## Non-goals

- Centralize product-owned or vendor-owned skills in the handbook.
- Implement `skills/registry.json`, an installer, or an auditor in this migration.
- Treat a user runtime directory or `.skill-lock.json` as the source of truth.
- Modify live runtime paths as part of a repository pull request.
- Delete a local copy merely because its name matches a proposed owner.
- Rewrite the historical ownership specification or completed ADRs.

## Verified Baseline

The handbook currently publishes eight skills:

- `adr`
- `context-save`
- `decision-calibrator`
- `evidence-driven-development`
- `model-optimizer`
- `remove-gentle-context`
- `sweep`
- `systemic-issue-triage`

No registry, manifest, or catalog exists under `skills/`. Ownership is currently implicit in `skills/<name>/`. Of the eight current `SKILL.md` files, only `systemic-issue-triage` declares `metadata.author: pablontiv`.

The inspected user installation also contains loose directories and symlinks whose sources are absent, unversioned, product-owned, or externally managed. Installation location does not establish ownership.

## Ownership Model

Each active skill name has exactly one canonical owner. Runtime locations are projections and never become owners.

A skill belongs in the handbook only when all of these hold:

1. **Independent:** its release is not coupled to another product or plugin.
2. **Global:** it applies across repositories rather than to one repository's internal workflow.
3. **Portable:** it has no required host path, private runtime API, or unpackaged local agent.
4. **Publishable:** its instructions, provenance, and licensing permit public distribution.
5. **Unowned elsewhere:** no product or official upstream repository is the better authority.

### Handbook-owned portfolio

The eight existing handbook skills remain owned here. The following migrations are approved, subject to their individual implementation and verification gates:

| Skill | Required outcome |
| --- | --- |
| `naming-brief` | Adapt the loose local skill as a portable, tested handbook skill. |
| `docs-northstar` | Remove host/runtime assumptions, preserve useful references, and add contract tests. |
| `rule-audit` | Generalize Claude-specific paths and make optional integrations explicit. |
| `gh-communication-style` | Extract a publishable, provider-neutral communication skill without private standing policy. |
| `markitdown` | Write an original portable adaptation around Microsoft MarkItDown with explicit provenance; do not present it as an official Microsoft Agent Skill. |
| `context-save` | Absorb the non-duplicative safety and continuity controls from loose `session-handover`; do not publish a second overlapping skill. |

Every handbook-owned `SKILL.md`, existing or new, must contain:

```yaml
metadata:
  author: pablontiv
```

For an adaptation, this identifies the handbook adaptation's author or maintainer. It does not replace original authorship. The skill must separately preserve upstream attribution, license, and provenance where applicable.

### Product-owned skills

| Owner | Skill | Gate before local replacement |
| --- | --- | --- |
| Poness | `poness` | Poness must first publish and validate a canonical Agent Skill in its own repository. |
| Wiki | `qmd` | Wiki must first publish and validate a canonical Agent Skill in its own repository. |

The handbook may document these owners but does not copy their skill bodies. Until each canonical source exists and is committed, its loose local copy remains protected from removal.

### Upstream-managed skill

`opensrc` remains owned by `vercel-labs/opensrc`, which publishes `skills/opensrc/SKILL.md`. The inspected local body matched the reviewed upstream Git blob `2bde4af4e8ba8e26b6820d19a7826692d09314b2`.

`opensrc` is installed and updated with the supported `npx skills` workflow, without `--copy`. The manager-controlled canonical copy lives under `~/.agents/skills/opensrc`; runtime-specific locations receive links where required. The local `.skill-lock.json` is an installation receipt, not repository authority.

Before each update:

1. identify the exact upstream commit and skill path;
2. review the upstream diff from the currently accepted content;
3. record and verify a content SHA-256 independently of the manager;
4. run the manager operation only after approval;
5. verify the resulting lock entry, local content, links, and runtime discovery;
6. roll back if any observation differs from the approved plan.

Managed upstream content is never edited locally. If a change is required, contribute upstream or create a separately approved adaptation with distinct provenance.

### Retirements and replacements

| Local artifact | Required outcome |
| --- | --- |
| `local-fix-engram-hooks` | Retire after a verified backup; do not migrate the temporary patch into handbook. |
| `poness-workspace` snapshot | Retire after a verified backup; it is a nested snapshot, not an active skill source. |
| `session-handover` | Retire only after its approved controls are present and verified in `context-save`. |
| broken `cascade-handover` link | Remove or repair only after ownership is resolved and a digest-bound live plan is approved. |

Absence from the target portfolio is not deletion authority. Each retirement still requires path identity, ownership evidence, backup, approval, and postcondition verification.

## Distribution Model

This model describes where portable skill artifacts are projected for user-global discovery. It does not expand the `pablontiv/handbook` workspace profile beyond its declared Pi-only process compatibility, nor does it authorize this workspace to operate through Claude Code or OpenCode. Live projection into any runtime remains a separate user-global operation governed by the mutation protocol below.

### Repository-owned skills

For handbook-, Poness-, and Wiki-owned global skills, the desired projection is:

```text
<owner-repository>/skills/<name>
        ├── ~/.agents/skills/<name>   # shared by Pi and OpenCode
        └── ~/.claude/skills/<name>   # Claude Code
```

The runtime entries are direct directory symlinks to the owner repository. No duplicate is installed under `~/.pi/agent/skills` or `~/.config/opencode/skills` unless a separately verified runtime contract makes the shared root insufficient.

Repository identities and source-relative paths are portable. Documentation and tests must not hard-code one user's absolute checkout path.

### External upstream skills

For supported external sources such as `opensrc`:

```text
official upstream
      │ supported manager + lock
      ▼
~/.agents/skills/<name>
      │ runtime link when required
      ▼
~/.claude/skills/<name>
```

This managed local copy is not a fork. Exactness is established through upstream identity, reviewed revision, independent digest, manager receipt, and post-install verification.

## Deferred Registry Idea

A future `skills/registry.json` may provide a machine-readable desired-state catalog containing skill name, canonical owner, source-relative path, projection mode, targets, and upstream integrity evidence.

It is deliberately deferred because the current handbook has no registry convention and no installer or auditor consumes one. Creating it now would duplicate this specification without enforcing behavior.

The idea may be reconsidered only together with:

- a real installer or auditor use case;
- a versioned schema;
- deterministic validation;
- desired-state versus observed-state semantics;
- migration and compatibility rules;
- evidence that its maintenance cost is lower than reconstructing ownership from approved documentation.

Until then, this specification is the normative ownership map and runtime state is observed directly.

## Migration Sequence

### Stage 0 — Governance

- Accept the governing ADR.
- Commit this specification through a pull request.
- Preserve the earlier ADR and specification as historical records.
- Do not mutate live runtime paths in this stage.

### Stage 1 — Existing handbook consistency

- Add `metadata.author: pablontiv` to the seven existing handbook skills that lack it.
- Add or update tests that enforce the author contract for every first-party skill.
- Verify the existing eight source directories and their current runtime projections.

### Stage 2 — Handbook document copy

Copy `naming-brief`, `docs-northstar`, `rule-audit`, `gh-communication-style`, and `markitdown` into their handbook directories in one batch. Preserve supporting files and change only text required for portability, authorship, provenance, and removal of missing sibling-skill dependencies. Copy the non-duplicative continuity rules from `session-handover` into `context-save` rather than publishing a second skill. Verify the resulting frontmatter, links, and repository discovery without creating a separate design, plan, or bespoke test suite for each text document.

### Stage 3 — Owner-repository establishment

- Add the canonical `poness` skill to the Poness repository and validate it there.
- Add the canonical `qmd` skill to the Wiki repository and validate it there.
- Commit and review those owner-repository changes before touching loose user copies.

### Stage 4 — Upstream manager convergence

- Reconcile `opensrc` through `npx skills` against reviewed upstream content.
- Verify that Pi and OpenCode discover the managed shared copy and Claude resolves the intended link.
- Preserve the manager receipt and independent content digest as live-operation evidence.

### Stage 5 — Live projection and cleanup

For every affected runtime path, prepare a fresh inventory and a separate mutation plan. Apply only the exact user-approved plan. Do not combine unresolved paths into a bulk cleanup.

## Live Mutation Protocol

Before replacing, removing, or repairing any user path:

1. use `lstat`, `readlink`, and bounded recursive hashing to identify the exact preimage;
2. resolve the canonical owner and verify that its source is committed and readable;
3. detect same-name entries in every runtime discovery root;
4. create a backup outside all discovery roots;
5. verify backup type, content digest, and restorability;
6. render the exact operations and a digest over the observed preconditions and planned operations;
7. obtain explicit approval for that digest;
8. apply only while every precondition still matches;
9. verify link target, resolved `SKILL.md`, frontmatter name, content digest, and runtime discovery;
10. roll back immediately when a required postcondition fails.

A textual match, broken symlink, or planned retirement is never sufficient authority to delete. Path drift, unexpected files, unsupported structures, symlinks or junctions in a real directory, ambiguous ownership, or changed digests block mutation.

## Testing and Verification

### Handbook source changes

- Validate frontmatter name and `metadata.author` for every handbook-owned skill.
- Validate relative references and ensure each skill remains self-contained.
- Preserve and test required attribution and licenses.
- Run skill-specific tests and the complete handbook test suite.
- Validate all new or modified governed Markdown with Rootline.

### Distribution procedures

Reusable tests operate only in temporary homes and never mutate the real home directory. They cover:

- direct links for repository-owned skills;
- shared `~/.agents/skills` discovery for Pi and OpenCode;
- Claude discovery through `~/.claude/skills`;
- collision detection in runtime-specific roots;
- backup and restore behavior;
- changed-precondition refusal;
- upstream content and lock verification;
- failure without silent copy fallback.

### Pull requests

Each pull request lists the ADRs reviewed, created, superseded, or modified and discloses unresolved governance conflicts. Live runtime mutation remains a separately approved operation after the owning source is merged and verified.

## Acceptance Criteria

- Every migrated skill has exactly one committed canonical owner.
- Handbook contains only skills that meet its ownership predicates.
- All handbook-owned skills declare `metadata.author: pablontiv`.
- Adaptations preserve provenance and do not claim official upstream status.
- Poness and Wiki own their skills before loose copies are replaced.
- `opensrc` remains traceable to exact reviewed upstream content and a manager receipt.
- Repository-owned runtime entries resolve directly to their owner repositories.
- Pi and OpenCode have no same-name runtime-specific duplicate shadowing the shared entry.
- No live path is mutated without verified backup and digest-bound approval.
- Retired artifacts remain recoverable until cleanup is independently verified.
- The registry idea is documented but creates no initial implementation obligation.
