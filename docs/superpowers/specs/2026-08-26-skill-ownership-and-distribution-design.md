# Skill Ownership and Distribution Design

**Date:** 2026-08-26

**Status:** Approved

**Governing ADRs:** ADR 0001, ADR 0014, ADR 0015, ADR 0017, ADR 0020. ADR 0020 supersedes ADR 0019 and ADR 0016 implementation choices; ADR 0016 remains historical ownership and lifecycle evidence.

**Implementation supersession:** ADR 0020 and `docs/superpowers/specs/2026-08-28-waywarden-skill-distribution-design.md` supersede this specification's TypeScript, package, state, command-contract, transaction, release, and executable implementation choices. This document remains authoritative for ownership classification, runtime topology, direct-link intent, and the separation of uninstall from restore.

**OpenCode verification qualification:** ADR 0017 and `docs/superpowers/specs/2026-08-26-opencode-verification-isolation-design.md` govern OpenCode verification: governed verification runs `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` inline for each `opencode debug skill` invocation and uses file-backed capture, while normal OpenCode behavior and required Claude links remain unchanged.

## Purpose

Establish one canonical owner for every installed Agent Skill, eliminate drift between runtime copies, and define how this repository publishes global skills to Pi, OpenCode, and Claude without absorbing repository-local or externally managed skills.

## Goals

- Keep every skill in a version-controlled repository owned by the subsystem that controls its behavior.
- Make this repository canonical only for independent, global, portable, publicly publishable skills.
- Install this repository's skills through direct symlinks rather than copies.
- Preserve product-owned, repository-local, private-host, and externally managed lifecycle boundaries.
- Migrate incrementally, with backup and verification before replacing any real directory.
- Preserve distinct uninstall and restore operations while delegating executable implementation authority to the approved Waywarden Go specification and ADR 0020.

## Non-goals

- Implement an installer in the initial delivery.
- Vendor skills from plugins, extensions, packages, marketplaces, caches, or Git-managed third-party collections.
- Move repository-local skills into a user-global directory.
- Rewrite product-coupled or private skills during the ownership migration.
- Mutate runtime skill directories as part of a repository pull request.

## Verified Current State

The repository currently owns five skills:

- `adr`
- `decision-calibrator`
- `model-optimizer`
- `remove-gentle-context`
- `systemic-issue-triage`

The runtime inventory found four forms of drift:

1. incomplete links from the repository to runtime skill roots;
2. real directories where a repository symlink should exist;
3. divergent copies of product-owned skills across runtimes;
4. globally installed skills with no explicit version-controlled owner.

The most concrete defect is `~/.agents/skills/model-optimizer`: it is a real, older directory that differs substantially from the canonical repository version.

Pi loads global skills from both `~/.pi/agent/skills` and `~/.agents/skills`. OpenCode loads global skills from `~/.config/opencode/skills`, `~/.agents/skills`, and `~/.claude/skills`. Pi keeps the first skill found on a name collision, so duplicate installations are not harmless.

## Ownership Rule

Installation location does not establish ownership. The canonical owner is the repository whose interface or operating policy controls the skill.

A skill belongs in this repository only when all four predicates hold:

1. **Independent:** it is not release-coupled to another product or plugin.
2. **Global:** it applies across repositories rather than to one repository's internal workflow.
3. **Portable:** it does not depend on one host path, one runtime-only API, or an unpackaged local agent.
4. **Publishable:** it can be distributed publicly with verified provenance and licensing.

If a skill fails a predicate, it remains with its product, local repository, private configuration repository, or external manager.

## Classification and Required Movements

### Canonical in this repository

| Skill | Required action |
| --- | --- |
| `adr` | Keep current direct links in `~/.agents` and `~/.claude`. |
| `decision-calibrator` | Keep current direct links in `~/.agents` and `~/.claude`. |
| `model-optimizer` | Back up and replace the stale real directory in `~/.agents`; add the Claude link. |
| `remove-gentle-context` | Add links in `~/.agents` and `~/.claude`. |
| `systemic-issue-triage` | Add the Claude link; remove the Pi-specific duplicate after runtime verification. |

`systemic-issue-triage` remains the explicit third-party adaptation governed by ADR 0001. Its provenance and bundled license must remain intact.

### Approved migration candidates

Each migration is an independent pull request and follows skill TDD when behavior or instructions change.

| Order | Skill | Migration gate |
| --- | --- | --- |
| 1 | `delivering-issues` | Validate Superpowers dependencies and harness dispatch mappings. |
| 1 | `naming-brief` | Verify template licensing and add placeholder-completeness tests. |
| 2 | `docs-northstar` | Refactor oversized instructions, preserve references, make external skills optional, and add contract tests. |
| 2 | `rule-audit` | Make Claude-specific paths examples rather than defaults and verify optional Backscroll behavior. |
| 2 | `session-handover` | Add a license, make the state path harness-neutral or configurable, and keep Rootline and memory optional. |

### Product-owned

| Owner | Skills | Required action |
| --- | --- | --- |
| Backscroll | `backscroll`, `backscroll-doctor` | Reconcile divergent installed copies against the Backscroll repository and replace copies with product-owned links or distribution. |
| Rootline | `rootline` | Reconcile divergent Claude and OpenCode copies against the Rootline repository. |
| roadmapctl | `roadmap`, `integrate`, `retrospective` | Reconcile the OpenCode copies against roadmapctl. |
| Orca | `computer-use`, `orca-cli`, `orchestration` | Keep Orca-managed, version-matched distribution. |
| Orca or private configuration | `orca-usage` | Upstream to Orca only with product acceptance; otherwise keep privately versioned. |
| Poness | `poness` | Establish the Poness repository as owner and separate host-only SOPS and filesystem paths from product guidance. |

### Private host configuration

The following remain outside this public repository:

- `cascade-handover`
- `chezmoi-drift`
- `gh-communication-style`
- `local-fix-engram-hooks`
- `pr-sweep`
- `review-prs`
- `worktree-sweep`

They encode personal policy, host paths, temporary patches, destructive standing authorization, Orca-specific behavior, Claude-specific APIs, or unpackaged agents. Loose directories should be moved into the private dotfiles repository. A generic behavior may be extracted later only through a separately approved and tested adaptation.

### Externally managed

Do not copy skills owned by these families:

- Superpowers;
- Pi Lens, Pi Intercom, Pi MCP Adapter, and Pi Subagents;
- Gentle Pi;
- Claude official plugins and marketplaces;
- Engram, Matt Pocock, OpenAI Codex, and Cloudflare plugin families;
- third-party standalone skills such as `find-skills`, `opensrc`, `qmd`, and `markitdown`.

For ambiguous standalone copies, recover the exact upstream source, version, and license before replacing or removing anything.

### Repository-local

Repository-local families stay where they are, including:

- the nine Wiki skills under `/Users/Shared/wiki/.agents/skills`;
- the `hyperresearch-*` family;
- homeserver, factory, QMK, dsprima documentation, scrivener, modelling, and scrap skills;
- other skills embedded in their owning checkout.

Worktree duplicates, vendor trees, plugin caches, `node_modules`, and virtual environments are artifacts, not canonical sources.

## Initial Manual Distribution

For every `skills/<name>/SKILL.md` in this repository, the desired links are:

```text
~/.agents/skills/<name> -> <repository>/skills/<name>
~/.claude/skills/<name> -> <repository>/skills/<name>
```

`~/.agents/skills` is the shared global root for Pi and OpenCode. `~/.claude/skills` is the Claude root. This repository does not install duplicate copies under `~/.pi/agent/skills` or `~/.config/opencode/skills`.

The initial delivery documents manual commands and checks. It does not ship executable installation tooling.

### Manual mutation protocol

Before replacing any existing path:

1. inventory the path with `lstat`, `readlink`, and a recursive content hash where applicable;
2. record the expected repository source and resolved destination;
3. create a backup outside all runtime discovery roots;
4. verify the backup hash;
5. present the exact operations and observed-state digest for explicit approval;
6. replace only the approved path;
7. verify the symlink target and resolved `SKILL.md`;
8. launch or query each affected runtime to prove discovery;
9. roll back immediately if verification fails.

A textual name match is never authority to remove a path. Unexpected files, symlink targets, ownership, path drift, or duplicate names block the operation.

## Waywarden implementation authority

The lifecycle evidence established here remains:

```text
inventory -> plan -> apply -> verify
                  \-> uninstall -> verify
                  \-> restore   -> verify
```

ADR 0020 and `docs/superpowers/specs/2026-08-28-waywarden-skill-distribution-design.md` now govern the executable implementation. They replace the former TypeScript choice with Waywarden in exact Go 1.26.0 and define the authoritative schemas, state layout, digest binding, physical deployments, runtime bindings, backup sets, transaction journal, receipts, rollback, verification, platform adapters, CI, and release behavior.

The safety concepts preserved from this specification are read-only inventory/planning, exact digest-bound mutation approval, verified backups before replacement, fail-closed ambiguity, ownership-bound uninstall, separate explicit restore, direct symlinks, and temporary-home tests.

## Migration Sequence

### Stage 0: governance

- Preserve ADR 0016 and this specification as historical ownership/lifecycle evidence.
- Accept ADR 0020 and the approved Waywarden specification as implementation authority.
- Do not modify skills or runtime paths before an implementation plan derived from that authority is accepted.

### Stage 1: current portfolio convergence

- Correct `model-optimizer` drift with backup and explicit mutation approval.
- Add missing `remove-gentle-context`, `model-optimizer`, and `systemic-issue-triage` links.
- Verify Pi and OpenCode discovery through `~/.agents`.
- Remove runtime-specific duplicates only after successful discovery verification.

### Stage 2: simple public migrations

Migrate `delivering-issues`, then `naming-brief`, one pull request at a time.

### Stage 3: portability adaptations

Adapt and migrate `docs-northstar`, `rule-audit`, and `session-handover`, one pull request at a time.

### Stage 4: owner-repository cleanup

Reconcile product-owned copies and place private loose skills under private version control. This work occurs in each owning repository, not in the public skills repository pull request.

## Testing Strategy

### Skill migrations

Each migrated skill must follow the `writing-skills` RED-GREEN-REFACTOR workflow:

- run baseline pressure or application scenarios without the migrated skill;
- capture failures and rationalizations;
- add the minimum portable skill content and deterministic tests;
- rerun scenarios with the skill;
- close observed loopholes;
- validate frontmatter, relative references, licensing, and self-containment.

### Manual distribution

Use temporary homes for any reusable validation scripts or test procedures. Tests must never mutate the real home directory. For the live manual operation, verify:

- both expected global links exist for every repository skill;
- every link resolves to the repository source;
- no same-name duplicate exists in Pi or OpenCode runtime-specific roots;
- Pi and OpenCode load the skill from `~/.agents`;
- Claude loads it from `~/.claude`;
- backed-up preimages can be restored.

### Repository verification

Before each commit or pull request:

- validate new or modified ADRs with `rootline validate <record> --strict`;
- run the complete repository test suite;
- run language-server and repository diagnostics for changed files;
- disclose reviewed, created, and modified ADRs and unresolved governance conflicts in the pull request.

## Acceptance Criteria

- Every first-party global skill has a version-controlled canonical owner.
- Every skill name has exactly one canonical owner.
- Every skill in this repository is discoverable once by Pi/OpenCode and once by Claude.
- No runtime-specific duplicate shadows a repository-owned global skill.
- No third-party plugin, package, cache, clone, or marketplace skill is vendored without explicit adaptation approval.
- Every replaced real directory has a verified backup and tested rollback path.
- Repository-local skills remain local.
- Waywarden implementation starts from ADR 0020 and the approved Waywarden specification while preserving ADR 0016's uninstall/restore separation as historical lifecycle evidence.
