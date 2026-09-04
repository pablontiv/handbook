# Handbook Identity Foundation Design

**Date:** 2026-09-02

**Status:** Approved design; implementation pending written-spec review

**Governing ADR:** ADR 0022

## Purpose

Establish a truthful, outcome-led documentation contract for this repository as a portable working handbook without claiming that the future `.workspace/` method is already implemented.

## Approved identity

> **Un handbook para convertir el trabajo de desarrollo improvisado en un método reproducible, verificable y adaptable.**
>
> Reúne reglas, skills, herramientas y memoria para orientar el trabajo de personas y agentes.

The wording above was approved verbatim by the repository owner. Brands and agent runtimes do not define the category. Git, worktrees, and workspace structure may appear as mechanisms only when verified and relevant.

## Audience and trigger

The primary audience is developers working with AI agents. The trigger is not team size or a specific runtime; it is the need to replace ad hoc development practices with a method that can be repeated, checked, and adapted to local team rules.

## Boundaries

This foundation:

- does not define the repository as an AI framework;
- does not replace team policy, CI, ticket systems, or design sources;
- does not publish the proposed `.workspace/` lifecycle as implemented behavior;
- does not add empty categories for future content;
- does not rename the local checkout path;
- does not rewrite historical ADRs, specs, plans, or completed records;
- does not change the behavior or distribution contract of an existing skill.

The repository continues to admit only global, portable, publicly distributable artifacts with explicit ownership. Skills remain self-contained under `skills/<name>/` and do not depend on sibling skills.

## Verified foundation

The current repository already contains the ingredients required to support the narrower present-tense support line:

- repository rules in `AGENTS.md`;
- seven Agent Skills under `skills/`;
- deterministic scripts, helpers, assets, references, fixtures, and tests bundled with those skills;
- cross-session memory guidance in `skills/context-save/`;
- an interaction contract in `output-styles/mentor-telemetria.md`;
- versioned governance and design records under `docs/`.

The current repository does not contain an integrated handbook method, `.workspace/` controller, workspace configuration parser, end-to-end acceptance harness, or post-merge lifecycle. Those capabilities are outside this change.

## Requirements

### R1 — Outcome-led entry

`README.md` MUST begin with the approved hero and support line verbatim. It MUST NOT define the repository only as a collection of Agent Skills or by a vendor, runtime, VCS, format, or team size.

**Scenario**

- **GIVEN** a reader opens the repository root,
- **WHEN** they read the first content after the title,
- **THEN** they see the approved transformation and support line before implementation details or inventory.

### R2 — Truthful present-tense proof

The README MUST immediately ground the identity in artifacts that exist on the current branch. It MUST distinguish present capabilities from the unimplemented integrated workspace method and MUST NOT claim complete context, end-to-end orchestration, or full lifecycle enforcement.

**Scenario**

- **GIVEN** the approved identity describes a broad handbook,
- **WHEN** a reader asks what exists today,
- **THEN** the README points to repository rules, skills, bundled tools, memory guidance, output styles, and governance records without asserting the future `.workspace/` design.

### R3 — Concept-first navigation

The README MUST explain what the repository models before explaining runtime-specific mechanics. Its order MUST be:

1. approved outcome;
2. verified proof;
3. core concepts and boundaries;
4. capabilities grouped by use case;
5. optional integrations;
6. references by audience.

**Scenario**

- **GIVEN** a reader who does not use the maintainer's current agent runtime,
- **WHEN** they navigate the README,
- **THEN** they can understand the handbook and find relevant artifacts before encountering runtime-specific details.

### R4 — Complete published inventory

Every directory matching `skills/<name>/SKILL.md` MUST have a README link. The README MUST also link the existing `output-styles/` and governance/reference surfaces. No absent or planned artifact may be listed as available.

**Scenario**

- **GIVEN** the repository contains a published skill or artifact category,
- **WHEN** the documentation contract enumerates the tree,
- **THEN** the README contains a resolving relative link and no documented entry points at a missing target.

### R5 — Capabilities by use case

The README MUST group current artifacts by user need rather than presenting a flat technology catalog. At minimum it MUST cover:

- decisions and calibration: `adr`, `decision-calibrator`;
- continuity and memory: `context-save`;
- repository and portfolio inspection: `sweep`, `systemic-issue-triage`;
- agent configuration evidence: `model-optimizer`;
- safe context cleanup: `remove-gentle-context`;
- interaction contracts: `mentor-telemetria`.

**Scenario**

- **GIVEN** a reader starts from a development need,
- **WHEN** they scan the capabilities section,
- **THEN** they can select the relevant artifact without first knowing its internal directory name.

### R6 — Consumers versus category

AI agents and runtimes MUST be described as consumers or optional integrations, not as the category of the repository. Runtime-specific statements MUST be bounded to verified support in the linked artifact.

**Scenario**

- **GIVEN** a capability has Pi-, Claude-, or OpenCode-specific behavior,
- **WHEN** that behavior appears in the README,
- **THEN** it is subordinate to the capability and matches the artifact's verified contract.

### R7 — Synchronized agent contract

`AGENTS.md` MUST describe the repository as a portable working handbook. It MUST retain the existing safety, portability, ADR, testing, pull-request, and skill self-containment rules. It MUST require new top-level artifact families to document ownership, portability, verification, and their relationship to the handbook.

**Scenario**

- **GIVEN** an agent prepares a new non-skill artifact,
- **WHEN** it reads repository guidance,
- **THEN** it receives enforceable inclusion criteria instead of the obsolete instruction that all content must be a skill.

### R8 — Stale claim removal

The living README MUST remove the wrong `pablontiv/gentle-ai` URL, the claim that pull requests are disabled, and the incomplete “no planned skills” section. No replacement historical narrative may be added.

**Scenario**

- **GIVEN** a claim has a direct counterexample in GitHub or the repository tree,
- **WHEN** the identity foundation is delivered,
- **THEN** the smallest false span is absent and surviving claims remain verified.

### R9 — Documentation contract

A deterministic standard-library test MUST verify the exact approved hero/support text, README coverage of every published skill, required top-level category links, relative Markdown target resolution, removal of known stale claims, and the broadened AGENTS purpose. CI MUST execute this test on Linux, macOS, and Windows.

**Scenario**

- **GIVEN** a later change narrows the repository back to skills or omits a published artifact,
- **WHEN** CI runs,
- **THEN** the documentation contract fails with the missing or stale expectation.

### R10 — Historical integrity

ADR 0016 MUST change only in current-status metadata required to mark it superseded and link ADR 0022. ADR 0022 MUST be accepted and Rootline-valid. Existing ADR bodies, archived specs, plans, and completed records MUST otherwise remain unchanged.

**Scenario**

- **GIVEN** the new identity overturns an accepted decision,
- **WHEN** the change is reviewed,
- **THEN** the old decision remains readable as historical evidence and the successor records the new authority.

### R11 — Public repository rename

After the documentation pull request is merged, the public repository MUST be renamed from `pablontiv/skills` to `pablontiv/handbook` only after a fresh read-only GitHub observation and explicit human authorization of the exact live mutation. The description MUST be synchronized with the approved identity. The local checkout directory MUST remain `/Users/Shared/harness/skills` in this change.

**Scenario**

- **GIVEN** the identity commit is present on the default branch,
- **WHEN** the owner approves the exact rename operation against the freshly observed repository,
- **THEN** GitHub reports `pablontiv/handbook`, the old URL redirects, issues and pull requests remain available, and local `origin` is updated only after the new remote is verified.

## Surface inventory

| Surface | Change | Reason |
|---|---|---|
| `docs/adr/0016-gobernar-propiedad-y-distribucion-de-skills-globales.md` | Status metadata only | Mark the old identity decision superseded. |
| `docs/adr/0022-ampliar-repositorio-a-handbook-de-trabajo.md` | New accepted ADR | Record the broadened identity, boundaries, and rename decision. |
| `docs/superpowers/specs/2026-09-02-handbook-identity-design.md` | New approved design | Bind implementation to reviewed requirements and scenarios. |
| `docs/superpowers/plans/2026-09-02-handbook-identity-foundation.md` | New approved implementation plan | Bind delivery sequencing, tests, and verification evidence to the approved design. |
| `README.md` | Restructure | Make the handbook outcome, proof, concepts, capabilities, integrations, and references discoverable. |
| `AGENTS.md` | Update purpose and artifact inclusion contract | Synchronize executable agent guidance with the new identity. |
| `tests/test_handbook_contract.py` | New deterministic tests | Prevent identity, inventory, link, and stale-claim drift. |
| `.github/workflows/ci.yml` | Add handbook contract step | Execute the contract across the existing OS matrix. |
| GitHub repository name and description | Post-merge live mutation | Complete the public identity transition. |
| Local `origin` URL | Post-rename local mutation | Follow the verified public destination without renaming the checkout directory. |

`LICENSE`, skill implementation files, output-style content, historical spec bodies, and the local checkout directory are deliberately unchanged.

## Delivery slices

### Slice 1 — Governance and executable contract

- Accept ADR 0022 and mark ADR 0016 superseded.
- Add the failing handbook documentation contract.
- Add the CI step.

This slice establishes the authority and measurable acceptance boundary without changing product behavior.

### Slice 2 — Handbook entry and contributor contract

- Restructure `README.md` according to R1–R8.
- Update `AGENTS.md` according to R7.
- Run the ghost and quantifier sweeps.
- Run the complete local suite and diagnostics.

This slice makes every local identity claim true and reviewable before any external mutation.

### Slice 3 — Pull request delivery

- Commit with conventional commits.
- Open a pull request rather than delivering directly to `main`.
- List ADRs reviewed, created, and modified.
- Disclose the pending Waywarden ADR numbering/reference conflict.
- Require green checks and human review before merge.

### Slice 4 — Authorized public rename

- Re-observe the GitHub repository read-only after merge.
- Present the exact rename/description/origin operations.
- Obtain explicit authorization.
- Apply and verify each mutation in dependency order.

This slice is blocked until the merged default branch contains Slices 1–3 and the live authorization gate is satisfied.

## Verification plan

Local verification consists of:

1. the handbook documentation contract;
2. Rootline strict validation for ADRs 0016 and 0022;
3. all current repository suites: 521 Python unittests and 5 shell checks at baseline;
4. LSP and repository diagnostics for modified files;
5. a post-edit Markdown link sweep;
6. a post-edit invocable-unit ghost sweep;
7. a post-edit quantifier sweep.

Live verification consists only of read-only GitHub checks until the owner authorizes the exact post-merge rename payload.

## Known governance conflict

The active Waywarden worktree contains accepted but unmerged ADRs numbered 0019 and 0020, while current `main` already assigns 0019 to `context-save`. ADR 0022 intentionally leaves 0020 and 0021 available for Waywarden's records after rebase. The Waywarden branch must also reconcile its existing `superseded_by` relationship from ADR 0016 with ADR 0022. This identity change does not edit the Waywarden worktree or silently resolve that separate branch's governance.

## Historical records left untouched

Except for the status metadata on ADR 0016, this change does not edit:

- ADR 0014 or any other existing ADR body;
- existing files under `docs/superpowers/specs/`;
- existing files under `docs/superpowers/plans/`;
- completed task records or Git history;
- the proposed `.workspace/` specification supplied during discovery.
