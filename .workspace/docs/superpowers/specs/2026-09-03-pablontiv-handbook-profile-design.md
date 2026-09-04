# Pablontiv Handbook Profile Design

**Date:** 2026-09-03

**Status:** Approved design; awaiting written-spec review

**Governing ADR:** ADR 0021, currently at `docs/adr/0021-adoptar-perfil-pablontiv-gobernado-por-workspace.md` and destined for `.workspace/docs/adr/` during the governed migration

**Base specification:** `engineering-handbook-v1.4.md`, version 1.4, SHA-256 `f5455e3eced13690358b02823053a1e00a6c7c06de5f17d9716805bf0a0cff26`

## Purpose

Publish a reusable Pablontiv profile that specializes Engineering Handbook v1.4, then dogfood it through one prose-first workspace configuration for `pablontiv/handbook`.

## Existing identity

This design preserves the repository identity approved in ADR 0022 verbatim:

> **Un handbook para convertir el trabajo de desarrollo improvisado en un método reproducible, verificable y adaptable.**
>
> Reúne reglas, skills, herramientas y memoria para orientar el trabajo de personas y agentes.

The profile adds a concrete, reusable way of working. It does not replace the approved hero or redefine the repository around Pi, Rootline, Backscroll, Git, or another adjacent tool.

## Source authority

The supplied version 1.4 specification is the semantic source. The implementation MUST preserve a byte-faithful snapshot at `profiles/pablontiv/references/engineering-handbook-v1.4.md` and bind the derived profile to its version and digest.

The profile MUST preserve the source specification's sixteen-section structure:

1. Purpose
2. Design principles
3. Workspace model
4. Configuration resolution
5. Control contract
6. Configurable axes
7. Defaults
8. Workflow
9. Invariants
10. Minimum repository configuration
11. Non-normative binding example
12. Precedence against steering and automation
13. Security and external systems
14. Adoption
15. Acceptance criteria
16. Out of scope

The profile may specialize choices left open by the base specification. It MUST NOT silently remove a base invariant, configurable axis, control state, merge rule, workflow phase, or safety gate.

## Conceptual model

```text
engineering-handbook-v1.4.md
            ↓ specialization
profiles/pablontiv/PROFILE.md
            ↓ bootstrap
.workspace/config.yaml
            ↓ operation
.workspace/docs/ and .workspace/worktrees/
```

- The base specification defines the generic contract.
- `PROFILE.md` is a reusable reference, analogous to a partial implementation of that contract.
- `bootstrap.md` guides Pi through producing a consumer workspace instance.
- `.workspace/config.yaml` is the operational instance. Pi operates from the workspace instance, not directly from `PROFILE.md`.
- `.workspace/docs/` is the only final authority for durable workspace knowledge.
- `.workspace/worktrees/` is the workspace-managed isolation root when the effective strategy requires it.

## Target tree

```text
handbook/
├── profiles/pablontiv/
│   ├── .stem
│   ├── PROFILE.md
│   ├── bootstrap.md
│   ├── config.template.yaml
│   └── references/
│       └── engineering-handbook-v1.4.md
├── .workspace/
│   ├── config.yaml
│   ├── docs/
│   │   ├── .stem
│   │   ├── adr/
│   │   │   ├── .stem
│   │   │   └── *.md
│   │   └── superpowers/
│   │       ├── specs/
│   │       │   └── *.md
│   │       └── plans/
│   │           └── *.md
│   └── worktrees/
├── skills/
├── output-styles/
├── tests/
├── .github/workflows/ci.yml
├── AGENTS.md
├── README.md
└── LICENSE
```

The final tree MUST NOT retain `docs/` as a second active authority. Existing ADRs, specs, and plans move to `.workspace/docs/` without rewriting historical body content.

## Profile specialization

Version 1 of the Pablontiv profile makes these choices:

- Pi is the only declared compatible runtime.
- Rootline is mandatory and non-substitutable for governed Markdown knowledge.
- Backscroll is mandatory and non-substitutable for episodic history retrieval.
- Every skill, Pi agent, and output style published by this repository is part of the official tool catalog.
- Applicable official tools cannot be replaced by equivalents.
- Tool activation remains conditional; catalog membership never means invocation on every task.
- Configuration and controls start as prose organized by the base specification's fields.
- Deterministic executors, schemas, and a control-plane CLI are deferred.

Adding another runtime requires full verified parity across the profile's mandatory capabilities. Partial compatibility MUST NOT be advertised.

## Prose-first configuration

### Physical layout

The base specification distributes workspace, group, and repository configuration across files. The approved profile flattens that physical layout into one file:

```text
.workspace/config.yaml
```

The logical resolution order remains unchanged:

```text
workspace defaults → group → repository
```

The file MUST contain the logical layers `workspace`, `groups`, and `repositories`. Flattening files MUST NOT flatten or discard precedence, origin, inheritance, `unknown`, list replacement, recursive map merge, or repository identity semantics.

### Required axes

The template and dogfood instance MUST preserve all configurable axes from version 1.4:

- `context_sources`
- `base_branch`
- `sync_strategy`
- `isolation_strategy`
- `development_workflow`
- `commit_policy`
- `delivery_mode`
- `delivery_gate`
- `pre_checks`
- `acceptance_checks`
- `review_checks`
- `post_checks`
- `monitoring`
- `external_effects`
- `credential_policy`
- `knowledge_policy`
- `cleanup_policy`
- `custom_rules`

### Prose maturity

Version 1 expresses these axes in prose, prose lists, and explicit `unknown` values. It MUST NOT invent executable bindings merely to appear deterministic.

Examples include:

- multiple prose items under `pre_checks` and `post_checks`;
- a prose development workflow;
- prose commit and delivery policies;
- prose knowledge, credential, monitoring, external-effect, and cleanup policies;
- `custom_rules` for additional rules that genuinely do not belong to a defined axis.

Prose guidance is not automatic evidence. Until an item is later migrated to the concrete control model from section 5 of the base specification, it MUST NOT be reported as automatically executed or passed.

`custom_rules` remains part of the profile because version 1.4 defines it. It MUST NOT replace a more specific field.

### Future deterministic migration

A future version may migrate one prose control at a time to the exact logical model from section 5:

```text
id, phase, when, required, mode, executor,
timeout_seconds, success, on_failure
```

Such migration is outside version 1. No shorthand identifier may be treated as executable without a complete approved binding.

## Rootline governance

Rootline is the mandatory governance authority for the profile itself and for Markdown knowledge under this profile.

The design MUST:

- establish `profiles/pablontiv/.stem` as the governance boundary for `PROFILE.md`, `bootstrap.md`, and profile references;
- establish `.workspace/docs/.stem` as the workspace knowledge boundary;
- move the ADR schema to `.workspace/docs/adr/.stem` and make its inheritance valid;
- validate new and modified ADRs through Rootline;
- govern applicable links, anchors, relationships, and cycles;
- make Rootline availability a prose pre-check in version 1;
- treat unavailable or failed Rootline governance as `unknown` and stop before governed writes;
- update the repository's `adr` skill to resolve `.workspace/docs/adr/` when the profile is active;
- forbid silent fallback to `docs/adr/` or `.adr/` inside an adopted workspace.

Rootline does not validate `.workspace/config.yaml` in version 1. The design MUST NOT claim otherwise.

## Backscroll memory contract

Backscroll is the mandatory episodic-memory source for this profile.

The profile MUST require:

- preflight through the official Backscroll workflow;
- project-scoped search first;
- one broader search when project search returns no result;
- tool-content search for command, path, or execution-error recall;
- bounded machine-readable output for agent use;
- `unknown` when a required history source is unavailable or unusable.

Backscroll retrieval belongs under `context_sources` and phase 0. It does not replace durable decisions, Rootline records, or repository source inspection.

## Official tool routing

The version 1 profile MUST inventory every currently published artifact:

- `adr`
- `context-save`
- `decision-calibrator`
- `model-optimizer`
- `remove-gentle-context`
- `sweep`
- `systemic-issue-triage`
- Pi agents `pr-investigator`, `sweep-scout`, and `sweep-triage`
- output style `mentor-telemetria`

Each artifact MUST retain its own trigger and scope. The profile composes and routes tools; it does not duplicate their implementation.

In particular, `remove-gentle-context` activates only for clearing or removing active Gentle AI context or suspected stale generated registrations. It does not run routinely and does not uninstall packages, binaries, source, or the framework installation.

A newly published artifact MUST be added to the profile's prose routing before the profile claims complete catalog coverage.

## Bootstrap wizard

`profiles/pablontiv/bootstrap.md` turns the adoption sequence from section 14 into a Pi-executed conversational wizard.

It MUST:

1. identify the canonical workspace and repository identities;
2. load the profile and base-spec provenance;
3. inspect real repository interfaces and controls read-only;
4. inspect global tooling, inherited steering, repository steering, hooks, plugins, CI, provider policy, and observable practice;
5. ask only for material facts that cannot be observed safely;
6. preserve unresolved values as `unknown`;
7. prepare the proposed `.workspace/config.yaml` without treating it as active;
8. show inherited values, overrides, conflicts, and blockers;
9. obtain explicit human approval before the first durable write;
10. write and reread the approved configuration;
11. validate governed knowledge with Rootline;
12. stop before mutation or delivery when required facts remain `unknown`.

The wizard is prose executed by Pi. Version 1 has no bootstrap CLI, generated schema, or automatic effective-config resolver.

## Dogfood instance

`.workspace/config.yaml` MUST instantiate the profile for `pablontiv/handbook`.

It MUST include:

- stable repository identity;
- a relocatable repository locator or an explicit unresolved path rather than a published personal absolute path;
- `AGENTS.md` as repository-local steering, not reusable profile content;
- the observed base branch;
- freshness and isolation policy;
- development, commit, delivery, and approval policy;
- prose pre-, acceptance-, review-, and post-checks;
- Rootline knowledge governance;
- Backscroll context retrieval;
- read-only external effects by default;
- credential, cleanup, monitoring, and custom-rule policy;
- explicit conflicts and `unknown` values.

`AGENTS.md` remains local to this repository. It MUST NOT become part of the reusable profile or be copied into consumer repositories.

## Knowledge migration

### Canonical destination

The final canonical destinations are:

```text
.workspace/docs/adr/
.workspace/docs/superpowers/specs/
.workspace/docs/superpowers/plans/
```

### Historical integrity

The implementation MUST move existing historical records without rewriting their bodies. Historical references to former paths remain historical facts and do not become current instructions.

ADR 0002 is superseded because it selected `docs/adr/` as the canonical versioned store. ADR 0022 remains the source of the repository identity.

### Living consumers

Current consumers of old paths MUST be updated, including:

- `AGENTS.md`
- `README.md`
- `skills/adr/SKILL.md`
- `skills/adr/adr.sh`
- ADR skill tests
- `tests/test_handbook_contract.py`
- CI validation paths
- living ownership catalogs or tests that use `docs/adr/` as current authority

Archived ADR, spec, and plan bodies MUST NOT be rewritten solely to modernize their path examples.

## Error handling

- Missing required context remains `unknown`.
- Missing Rootline blocks governed Markdown writes.
- Missing Backscroll blocks only work whose required episodic source cannot be consulted.
- A false tool trigger is `not_applicable`, not failure.
- An applicable but unavailable official tool is `unknown`; no substitute is selected.
- A conflict between central configuration and active steering is explicit and blocks the affected phase.
- Failed live mutation requires renewed observation, failing reproduction, correction, review, and authorization before retry.
- Completion signals do not replace verified postconditions.

## Requirements and scenarios

### R1 — Preserve the base contract

The profile MUST preserve the sixteen-section structure and all invariants, axes, states, and merge semantics of Engineering Handbook v1.4.

**Scenario**

- **GIVEN** the source snapshot and derived profile,
- **WHEN** their normative section inventory is compared,
- **THEN** every base section and contract category is represented without silent deletion.

### R2 — Separate reference from operation

`PROFILE.md` MUST be reusable reference content, while `.workspace/config.yaml` MUST hold the operational instance.

**Scenario**

- **GIVEN** Pi starts work in an adopted workspace,
- **WHEN** it resolves applicable policy,
- **THEN** repository-specific values come from `.workspace/config.yaml`, not from modifications to `PROFILE.md`.

### R3 — Flatten storage only

The workspace configuration MUST use one `.workspace/config.yaml` while preserving workspace, group, and repository layers.

**Scenario**

- **GIVEN** a repository belongs to a configured group,
- **WHEN** effective values are reasoned about,
- **THEN** origin remains distinguishable as workspace, group, or repository.

### R4 — Start with prose

Version 1 MUST express controls as prose and MUST NOT claim deterministic execution.

**Scenario**

- **GIVEN** a prose pre-check,
- **WHEN** no concrete executor exists,
- **THEN** it is followed manually by Pi and is never reported as automatically passed.

### R5 — Govern knowledge with Rootline

Rootline MUST be required for the reusable profile and for governed Markdown under `.workspace/docs/`.

**Scenario**

- **GIVEN** a new or modified profile document, ADR, spec, or plan,
- **WHEN** Rootline is missing or validation fails,
- **THEN** the durable write does not proceed as successful.

### R6 — Retrieve history with Backscroll

Backscroll MUST be a required phase-0 context source where prior work may affect the task.

**Scenario**

- **GIVEN** feature, bug, test, refactor, or decision work,
- **WHEN** Pi loads required context,
- **THEN** it performs the bounded Backscroll workflow before re-deriving prior decisions.

### R7 — Route the complete official catalog

Every published skill, Pi agent, and output style MUST appear in the profile with its real conditional scope.

**Scenario**

- **GIVEN** an artifact is added or removed,
- **WHEN** the handbook contract runs,
- **THEN** catalog/profile drift fails verification.

### R8 — Centralize durable knowledge

`.workspace/docs/` MUST be the only final active durable-knowledge authority.

**Scenario**

- **GIVEN** migration completes,
- **WHEN** living guidance and tools resolve ADR, spec, or plan destinations,
- **THEN** they resolve `.workspace/docs/` and no active `docs/` fallback remains.

### R9 — Bootstrap safely

The wizard MUST preserve observation, uncertainty, approval, and post-write verification.

**Scenario**

- **GIVEN** a repository has unresolved delivery policy,
- **WHEN** bootstrap reaches activation,
- **THEN** `unknown` remains visible and delivery stays blocked.

### R10 — Preserve repository-local steering

`AGENTS.md` MUST remain local contribution guidance and MUST NOT be adopted as reusable profile content.

**Scenario**

- **GIVEN** another repository adopts the profile,
- **WHEN** bootstrap produces its instance,
- **THEN** it inspects that repository's steering without copying this repository's `AGENTS.md`.

## Verification plan

Implementation verification MUST include:

1. byte comparison and SHA-256 verification of the base-spec snapshot;
2. Rootline strict validation of the superseding ADR before and after migration;
3. byte comparisons for moved historical ADRs, specs, and plans;
4. a profile contract test for sixteen-section coverage;
5. a workspace configuration contract test for every v1.4 axis and all three logical layers;
6. official-tool inventory and routing coverage;
7. tests that reject active old-path authority;
8. tests for Rootline and Backscroll requirements;
9. Markdown link checks for living documentation;
10. complete existing Python and shell suites;
11. LSP and repository diagnostics for changed files;
12. CI on the repository's supported operating systems.

Tests validate the prose contract and structural presence. They MUST NOT pretend prose controls have deterministic runtime execution.

## Delivery boundaries

This change does not:

- implement a control-plane executor;
- implement a config merge engine;
- implement a bootstrap CLI;
- add generated JSON schemas;
- declare Claude Code or OpenCode compatibility;
- replace official tools with equivalents;
- install or mutate user-global Pi configuration;
- mutate GitHub, merge a pull request, or deploy an external system without a separate live gate.

## Historical records deliberately preserved

The implementation may change current-state metadata required to supersede ADR 0002 and move historical files. It MUST NOT rewrite historical ADR, spec, or plan bodies to match the new paths or current product behavior.
