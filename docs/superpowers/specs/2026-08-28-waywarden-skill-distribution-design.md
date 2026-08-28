# Waywarden Skill Distribution Design

**Date:** 2026-08-28
**Status:** Proposed
**Repository:** `pablontiv/skills`
**Issue:** <https://github.com/pablontiv/skills/issues/10>
**Governing ADRs:** ADR 0019 supersedes ADR 0016 for implementation language and release architecture; ADR 0017 continues to govern OpenCode verification isolation.
**Related specifications:** `docs/superpowers/specs/2026-08-26-skill-ownership-and-distribution-design.md` remains the ownership evidence record; `docs/superpowers/specs/2026-08-26-opencode-verification-isolation-design.md` remains the OpenCode verifier constraint.

## Purpose

Waywarden is a cross-runtime Go CLI for distributing the Agent Skills owned by this repository to supported local skill runtimes. It converts repository-owned skill source directories into governed runtime links, verifies runtime discovery, and maintains enough local state to uninstall or restore only the complete aggregate installation that Waywarden can prove it previously managed.

Waywarden exists to make the lifecycle from inventory through restore deterministic, auditable, and safe across Linux, macOS, and Windows. It is not a skill helper, daemon, package manager, registry, runtime replacement, update agent, or configuration manager.

## Governance status and approval gate

This document is a proposed specification pending human approval. It must not be treated as an implemented contract until the explicit governance gate below completes.

After human approval and before any implementation plan is accepted, the repository must:

1. mark this specification `Approved`;
2. amend ADR 0019 so it normatively references this specification for contracts, state, ownership lifecycle, release posture, and rollback requirements;
3. amend both ADR 0019 frontmatter decision metadata and ADR 0019 body text to replace `Go 1.26 o posterior` with exact `Go 1.26.0`, correct ADR 0019's temporal phrase that implies a design is already approved, and correct its Crossbeam release wording so Crossbeam is a CI baseline only and not Waywarden release authority;
4. validate and accept the ADR amendment using the repository ADR validation path;
5. update `docs/superpowers/specs/2026-08-26-skill-ownership-and-distribution-design.md` to mark TypeScript and ADR 0016 implementation sections superseded by ADR 0019 plus this approved Waywarden specification, while preserving ownership, topology, and lifecycle evidence;
6. update issue #10 title and body from the previous TypeScript/ADR 0016 framing to Waywarden Go/ADR 0019 scope.

This specification does not assert that those governance updates have already occurred. It remains `Proposed` until that gate completes.

## Decision summary

| Topic | Decision |
| --- | --- |
| CLI name | `waywarden` |
| Implementation language | Go, implemented and released with exact tested Go version `1.26.0` until a later design amends the version. |
| CLI framework | Cobra v1.10.2 |
| Shared utility library | Selective Picokit v1.0.0 usage only |
| Supported runtimes | Pi, OpenCode, and Claude |
| Pi runtime support | Tested Pi version `0.84.3` only in v1 |
| Distribution primitive | Direct filesystem symlinks or platform ordinary symlink equivalents to repository-owned skill source directories; no fallback copy distribution |
| Mutation authority | Exact approved plan payload digest, byte-identical canonical plan envelope, embedded inventory digest verification, and reobserved preconditions |
| State authority | Versioned local Waywarden state under the selected state root; coordination locks use the canonical owner-private platform lock root independent of `--state-root` |
| Ownership unit | One approved install mutation creates one `installation_id` aggregate covering every governed deployment in the batch |
| Backup unit | One approved install mutation creates one `backup_set_id` covering every governed deployment in the batch |
| Release pipeline | Crossbeam `go-ci.yml` light profile baseline plus project-owned pinned Go quality, security, native test, release, provenance, and smoke jobs |

## Scope and boundaries

### In scope

Waywarden version 1 governs only this repository's first-party global skills that satisfy the ownership predicates recorded in the prior ownership specification: independent, global, portable, and publishable. It inventories configured runtime roots, plans desired links, applies approved install plans, verifies runtime discovery, uninstalls complete Waywarden-managed installation aggregates, and restores complete verified backup sets.

The CLI owns its repository manifest, deterministic planning contracts, local state layout, operation journal, receipts, backup sets, runtime verification adapters, and platform filesystem adapters.

### Non-goals

Waywarden version 1 does not:

- absorb helper programs that belong inside individual skills;
- migrate existing Python helpers or other skill implementation languages as part of issue #10;
- import product-owned, repository-local, private-host, marketplace, plugin, package-cache, or third-party skills;
- install, update, or configure Pi, OpenCode, Claude, Go, shell profiles, environment managers, package managers, credentials, or providers;
- run as a daemon;
- use a database;
- require network access for core inventory, planning, mutation, or verification;
- provide auto-update behavior;
- silently copy skills when links are unavailable;
- delete repository sources, runtime roots, backups, unmanaged directories, third-party entries, or drifted paths;
- implicitly resume interrupted operations;
- implicitly restore a backup during uninstall;
- operate on a subset of an installation aggregate or backup set in v1;
- make future Go adoption decisions for skill helpers or other tooling.

Future movement of skill helpers to Go, additional runtime support, registry integration, update channels, package-manager formulae, network-backed release discovery, partial restore, partial uninstall, or recovery restore over occupied targets require separate issues and designs.

## Initial governed portfolio

The initial `waywarden.manifest/v1` should include only the repository-owned global skills established by the prior ownership evidence specification:

| Skill | Canonical source directory |
| --- | --- |
| `adr` | `skills/adr/` |
| `decision-calibrator` | `skills/decision-calibrator/` |
| `model-optimizer` | `skills/model-optimizer/` |
| `remove-gentle-context` | `skills/remove-gentle-context/` |
| `systemic-issue-triage` | `skills/systemic-issue-triage/` |

`systemic-issue-triage` remains the explicit third-party adaptation governed by ADR 0001 and the existing skill-local provenance. Waywarden distributes it because this repository owns the adapted global skill, not because Waywarden may import arbitrary third-party skills.

## Proposed repository layout

The implementation plan for issue #10 should introduce the following Go layout. These paths are proposed implementation paths; this specification is the only file created by the design commit.

```text
go.mod
cmd/waywarden/
internal/distribution/
├── inventory/
├── planning/
├── apply/
├── verify/
├── uninstall/
├── restore/
├── contracts/
├── filesystem/
└── runtimes/
```

Responsibilities are separated as follows:

| Package | Responsibility |
| --- | --- |
| `cmd/waywarden` | Cobra command tree, flags, version output, output mode selection, artifact emission, and public exit mapping. |
| `internal/distribution/inventory` | Read-only observation of repository manifest, runtime roots, current filesystem state, runtime discovery evidence, and existing Waywarden state snapshots. |
| `internal/distribution/planning` | Deterministic plan construction, embedded inventory canonicalization, blocker calculation, digest calculation, and schema emission. |
| `internal/distribution/apply` | Approved install mutation, backup set creation and verification, journal updates, aggregate receipt emission, rollback orchestration, and applied ownership recording. |
| `internal/distribution/verify` | Link, source, manifest, runtime, collision, receipt, backup set, and aggregate ownership verification. |
| `internal/distribution/uninstall` | Removal of complete Waywarden-managed installation aggregates whose current observations prove the exact governed slot plus managed object recorded by Waywarden, explicitly excluding source digest or resolved content as delete authority. |
| `internal/distribution/restore` | Explicit restoration of a complete selected verified backup set without reclassifying restored paths as managed links. |
| `internal/distribution/contracts` | Versioned JSON schemas, canonical encoding, digest rules, validation, and compatibility checks. |
| `internal/distribution/filesystem` | Cross-platform safe path inspection, descriptor/handle-bound operations, locking, syncing, hashing, backup, no-replace move primitives, quarantine, staging, and rollback helpers. |
| `internal/distribution/runtimes` | Pi, OpenCode, and Claude adapters for machine-readable discovery and verification evidence. |

The package boundaries keep CLI presentation, contracts, runtime evidence, and filesystem mutation in separate packages so tests can inject failures without touching the real home directory.

## Technology choices

Waywarden uses Go `1.26.0` for implementation, CI, release builds, and smoke verification in v1. Other Go versions require an explicit design update and fixture-backed CI proof. The implementation uses Cobra v1.10.2 for the command surface because Cobra is the reviewed CLI convention and supports stable help, subcommands, shell-independent invocation behavior, and predictable flag validation.

Waywarden may use Picokit v1.0.0 selectively for:

- `pathsec`, where its path-cleaning or validation primitives match Waywarden's stricter adapter requirements;
- `hashfile`, for ordinary file hashing where descriptor/handle authority is not weakened;
- `diag`, for structured diagnostics that do not expose private paths;
- `output`, for stable human and JSON output helpers;
- `pkcov`, for coverage enforcement.

Picokit is not authority for repository tree hashing, canonical JSON encoding, transaction semantics, plan digest calculation, backup identity, descriptor-bound or handle-bound filesystem safety, Windows reparse decisions, rollback correctness, or release provenance.

Platform-specific adapters use `golang.org/x/sys` where the Go standard library does not expose the required filesystem or locking primitives. Windows adapters use `golang.org/x/sys/windows` for handles, attributes, reparse metadata, and `LockFileEx`-style locking.

## Command model

Waywarden exposes six primary commands:

```text
waywarden inventory --out /absolute/outside/waywarden-inventory.json
waywarden plan --inventory /absolute/outside/waywarden-inventory.json --intent install --out /absolute/outside/install-plan.json
waywarden apply --plan /absolute/outside/install-plan.json --approve-digest <sha256>
waywarden verify --installation <installation-id>
waywarden inventory --out /absolute/outside/post-install.json
waywarden plan --inventory /absolute/outside/post-install.json --intent uninstall --installation <installation-id> --out /absolute/outside/uninstall-plan.json
waywarden uninstall --plan /absolute/outside/uninstall-plan.json --approve-digest <sha256>
waywarden verify --installation <installation-id>
waywarden inventory --out /absolute/outside/post-uninstall.json
waywarden plan --inventory /absolute/outside/post-uninstall.json --intent restore --backup <backup-set-id> --out /absolute/outside/restore-plan.json
waywarden restore --plan /absolute/outside/restore-plan.json --approve-digest <sha256>
waywarden verify --backup <backup-set-id>
```

All commands accept shared flags for state, artifact, and presentation behavior:

| Flag | Applies to | Meaning |
| --- | --- | --- |
| `--state-root <path>` | all commands | Override the Waywarden state root used for ownership, backups, journals, receipts, copied run artifacts, and recovery workflows. It relocates state artifacts only and never selects the coordination lock namespace. |
| `--output <human | json>` | all commands | Select presentation format. Human summaries go to stderr. JSON mode writes exactly one machine-readable JSON document to stdout except where invalidated by artifact stdout rules below. |
| `--out <path | ->` | inventory, plan | Select the inventory or plan artifact destination. The default is `-`, meaning the artifact occupies stdout. |
| `--inventory <path>` | plan | Required exact canonical inventory artifact consumed by planning. `plan` never inventories implicitly. Mutating commands do not accept `--inventory`; they consume the inventory embedded in the approved plan. |
| `--plan <path>` | apply, uninstall, restore | Required exact canonical plan envelope consumed by the mutating command. |
| `--approve-digest <sha256>` | apply, uninstall, restore | Required exact plan payload digest. |
| `--installation <installation-id>` | plan uninstall, verify | Selects the complete installation aggregate. It never selects a subset in v1. |
| `--backup <backup-set-id>` | plan restore, verify | Selects the complete backup set. It never selects an individual backup entry in v1. |
| `--receipt <path>` | verify | One verification selector for a persisted receipt. |
| `--operator-observation <path>` | verify with `--installation <installation-id>` | Bounded Claude human observation artifact for the active verification challenge. It is invalid with `--receipt` or `--backup`. |
| `--manifest <path>` | inventory, verify | Absolute override of the repository manifest path when executing from test fixtures. The default is exactly `<current-working-directory>/distribution/manifest.json`; no parent, upward, environment, `PATH`, package, or release-archive search is allowed. |
| `--timeout <duration>` | runtime-verifying commands | Bound runtime adapter execution. |

`inventory` is read-only. It emits `waywarden.inventory/v1`, may acquire a shared selected-ledger lock only to snapshot existing Waywarden state into the inventory artifact, and never writes ownership, backup, journal, receipt, verification, runtime, or repository state. It may use private temporary files and runtime captures that are deleted before command exit. Inventory snapshots under the shared ledger lock; no later planning step reopens live ledger or state to reinterpret the artifact.

`plan` is read-only and pure. It requires `--inventory <path>`, strict-parses the exact canonical inventory artifact, embeds the complete canonical inventory object in `payload.inventory`, records its SHA-256 as `payload.inventory_digest`, and emits `waywarden.plan/v1` containing exactly one intent. The plan function depends only on the inventory artifact bytes plus explicit planning flags/selectors; it never implicitly inventories, never opens or rereads live ledger/state, never acquires a shared ledger lock, and never writes ownership, backup, journal, receipt, verification, runtime, or repository state. Mutators, not planning, reobserve live preconditions after approval and locks.

`plan --intent install` requires no installation or backup selector. The install plan contains the deterministic governed deployment set, intended transition, preconditions, blockers, backup requirement shape, verification requirements, and rollback strategy, but it contains no newly generated `operation_id`, `installation_id`, `backup_set_id`, journal path, receipt path, backup storage path, or other event/storage identifier. Planning first canonicalizes and deduplicates physical governed slots before blocker calculation. Same governed slot plus same canonical source identity merges runtime bindings into one deployment; same governed slot plus different canonical source identity, or a merged binding set whose strategies are incompatible, is a blocker. `plan --intent uninstall` requires exactly one installation selector and no backup selector, and it may use only the observed existing installation IDs embedded in the input inventory. `plan --intent restore` requires exactly one backup selector and no installation selector, and it may use only the observed existing backup set IDs embedded in the input inventory. Any selector/intent mismatch is invalid input with exit 2. Missing backup for restore planning is a safe precondition failure with exit 4.

`apply` accepts only a plan whose intent is `install`. `uninstall` accepts only a plan whose intent is `uninstall`. `restore` accepts only a plan whose intent is `restore`. Mutators strict-parse the plan, canonicalize `payload.inventory`, verify `payload.inventory_digest`, verify the plan payload digest and the supplied approval digest, acquire the normative locks, and only then generate cryptographically random event IDs needed for mutation. Install mutators generate fresh `operation_id`, `installation_id`, and `backup_set_id` outside the approved payload; those IDs are ledgered event identifiers, not approved-plan content. Uninstall and restore mutators generate a fresh `operation_id` only and use the existing installation or backup IDs observed in the approved plan's embedded inventory. After ID generation, mutators copy the extracted canonical inventory bytes to `runs/<operation-id>/inventory.json` and copy the exact plan envelope bytes to `runs/<operation-id>/plan.json` before governed filesystem mutation. A noncanonical embedded inventory or divergence between embedded object and canonical bytes is invalid input with exit 2. An inventory digest mismatch, plan digest mismatch, or approval digest mismatch is exit 4.

`verify` is read-only with respect to runtime roots and repository sources. It requires exactly one of `--receipt <path>`, `--installation <installation-id>`, or `--backup <backup-set-id>`. Operator observation is accepted only with `--installation <installation-id>`. Verification may append aggregate verification results and lineage events to Waywarden state when evidence proves the selected aggregate state.

No mutating command may infer approval from a file name, current branch, issue number, terminal prompt, environment variable, textual skill name, or human summary. The required approval primitive is the exact plan payload digest embedded in a byte-identical canonical plan envelope.

## Read-only artifact output confinement

Artifact emission is the only persistent read-only write performed by `inventory` and `plan`. Private temporary files and runtime captures are allowed only as implementation scratch space and are normally cleaned before exit; they are never authoritative artifacts.

For `--out <file>`, the destination must be an absolute path outside repository sources, runtime roots, the selected state root, and the coordination lock root. Every ancestor must be opened no-follow/reparse-safe. Waywarden creates a unique owner-private staging file in the same parent with create-new semantics, writes the complete canonical artifact, fsyncs it, publishes it to the requested destination using a platform no-replace primitive, and syncs the parent directory. The destination is never partial and is never replaced. Existing destination is exit 4 and no authoritative artifact is produced. A crash-left staging file is non-authoritative and user-removable; Waywarden never auto-deletes unknown leftovers that it cannot prove it created in the active invocation. If Waywarden cannot prove path confinement, ancestor safety, same-parent staging, no-replace publication, or parent sync because a platform primitive is missing, the command exits 3; if proof succeeds and the destination already exists or violates a safe precondition, it exits 4.

With `--out -`, the artifact is stdout and the human summary is stderr. A blocker artifact written to stdout contains its typed blockers and exits 3 or 4; Waywarden must not also emit a second stdout error document. `--output json` is invalid for `inventory --out -` and `plan --out -` because the artifact already occupies stdout; that flag combination exits 2. With `--out <file> --output human`, stdout is empty and the summary is stderr. With `--out <file> --output json`, stdout is exactly one `waywarden.command-result/v1` envelope. Completed primary command phases emit exactly one command-result document; failures before a result exists emit exactly one `waywarden.error/v1` envelope. Human summaries always go to stderr. The command-result envelope must not leak arbitrary full paths and must conform to the discriminated union defined in the public output section.

## Repository manifest

The default versioned repository manifest path is exactly:

```text
<current-working-directory>/distribution/manifest.json
```

There is no parent-directory search, upward repository discovery, environment-variable search, `PATH` search, release-archive search, or package-manager search. `--manifest` is accepted only as an absolute path. This is a proposed implementation path. The manifest does not exist in the design-only commit and must be introduced by the implementation plan before executable commands depend on it.

The manifest is the repository checkout's declaration of desired first-party distribution, not delete authority. It lists schema version `waywarden.manifest/v1`, repository identity and expected source root, canonical skill ownership entries, canonical source directories relative to the repository root, required skill entry files including `SKILL.md`, desired runtime roots by adapter, expected link strategy per runtime and platform, runtime adapter names and supported discovery contracts, and issue/ADR references relevant to distribution governance. The manifest source root is the canonical parent of its `distribution/` directory. Inventory requires that source root to match the manifest's expected repository identity and rejects every source path not contained within that canonical root.

Version 1 is checkout-bound. Operators run Waywarden from a repository checkout or pass an absolute fixture manifest. Release archives contain the `waywarden` binary only; they are not a skills bundle and do not contain `skills/`, `distribution/manifest.json`, or package-manager metadata for installing skills. Mutating commands use the canonical source identities embedded in the approved plan's inventory and fail a precondition with exit 4 if the checkout moved, changed identity, or drifted from the approved evidence before mutation.

The manifest may authorize Waywarden to propose creation or replacement of a specific governed runtime path only when inventory evidence and plan preconditions prove that the path is safe to manage. The manifest alone never authorizes deletion. Deletion requires the aggregate ownership ledger and current exact state match defined in the uninstall protocol.

## Aggregate identity vocabulary and cardinality

Waywarden records aggregate lifecycle identity explicitly:

- `operation_id`: one mutating or verifying command invocation and its run directory, journal, receipt, and optional verification artifacts.
- `installation_id`: one lineage aggregate created by an approved install mutator after approval validation and lock acquisition. It covers all governed deployments in the install batch across every governed physical skill path selected by that plan.
- `deployment_id`: `SHA-256` of the canonical tuple `(canonical governed slot identity, canonical source identity)`. The runtime adapter is not part of this digest. There is one deployment per physical governed slot/source pair, not one deployment per adapter.
- `runtime_bindings`: an ordered unique array inside each deployment. Each binding records the runtime adapter plus the expected runtime evidence required to verify that adapter independently against the shared physical deployment. Ordering is canonical and duplicate bindings are rejected before digest calculation.
- `backup_set_id`: the backup set created by an approved install mutator after approval validation and lock acquisition. It contains exactly one backup entry per deployment in the batch, including a typed-missing entry when the physical slot did not exist.

A single physical deployment may have multiple runtime bindings. A Pi and OpenCode configuration that both bind `~/.agents/skills/<skill>` to the same canonical repository source produces one `deployment_id`, one backup entry, one filesystem mutation, and two independently verified `runtime_bindings`. A Claude path is a separate physical slot and therefore a separate deployment even when it points at the same source.

Planning canonicalizes and deduplicates physical slots before constructing the plan. Same governed slot plus same canonical source identity merges bindings into one deployment. Same governed slot plus different canonical source identity is a safe blocker. Same governed slot plus same source but incompatible link strategy, metadata policy, runtime-ignore requirement, or staging/quarantine strategy is also a blocker.

`--installation` always selects the complete `installation_id` aggregate. `--backup` always selects the complete `backup_set_id` aggregate. Version 1 rejects subset uninstall, subset restore, subset verify, and single-entry backup selection as invalid input with exit 2. Restore over fewer than all deployments is outside v1 scope and fails input validation before mutation.

Aggregate state is derived only when every deployment in the aggregate has the required compatible per-deployment state for the selected transition and every ordered runtime binding has the required independent evidence. Mixed deployment state outside an active locked journal is `recovery_required`. A command must not report aggregate success when only a subset reached the requested state.

## State root defaults and layout

Waywarden stores ownership, backups, journals, receipts, copied run artifacts, and verification artifacts under a single selected state root. The default is platform-specific:

| Platform | Default state root |
| --- | --- |
| Linux | `${XDG_STATE_HOME:-~/.local/state}/waywarden` |
| macOS | `~/Library/Application Support/waywarden/state` |
| Windows | `%LOCALAPPDATA%\\waywarden\\state` |

`--state-root` overrides that state root for command artifacts and recovery workflows. It provides state artifact relocation only. Tests and implementation-plan examples must redirect `HOME`, `XDG_STATE_HOME`, and `LOCALAPPDATA` to temporary locations for the platform under test. The current checkout's real home directory must never be mutated by automated tests.

The public state-root override never chooses the coordination lock namespace. Coordination locks are stored under a canonical owner-private platform lock root derived from the platform state area and environment after test redirection, independent of `--state-root`. The lock root must be owner-private and must not be bypassable by using a distinct state root.

The state root must be absolute. On Unix it must be mode `0700` or stricter and owned by the current user. On Windows it must have an owner-only ACL equivalent. Waywarden opens the state root segment-by-segment, rejects symlink or reparse ancestors, and requires it to be disjoint from repository sources, runtime roots, backup discovery roots, and the output artifact destination. Invalid state root configuration is an unsupported-capability failure with exit 3.

The state root layout is:

```text
<state-root>/
├── runs/
│   └── <operation-id>/
│       ├── inventory.json
│       ├── plan.json
│       ├── journal.ndjson
│       ├── receipt.json
│       └── verification/
│           └── <verification-id>.json
├── backups/
│   └── <backup-set-id>/
│       ├── manifest.json
│       └── <deployment-id>/
│           ├── entry.json
│           └── payload/
└── ownership/
    └── installations.ndjson
```

`runs/<operation-id>` groups immutable artifacts for one mutating or verifying invocation. `backups/<backup-set-id>` stores the complete verified backup set outside all runtime discovery roots, with exactly one `<deployment-id>` directory per physical deployment. `ownership/installations.ndjson` is the append-only hash-chained aggregate ledger used by uninstall and restore safety checks.

Run identifiers, installation identifiers, backup set identifiers, journal entries, receipts, backup manifests, and verification artifacts may contain cryptographic randomness or timestamps only when they are event records produced by mutating or verifying commands. Inventory and plan payloads may contain timestamps, random-looking identifiers, file IDs, operation IDs, installation IDs, backup IDs, or journal IDs only when they are observed stable state evidence copied from manifest/runtime/state inventory. Read-only commands never generate new nondeterministic values.

## Versioned JSON contracts and authority

All persisted machine-readable contracts are versioned. Schema names use the literal namespace form `waywarden.<contract>/v1`; there is no space in the actual schema identifier.

| Contract | Schema identifier | Authority |
| --- | --- | --- |
| Manifest | `waywarden.manifest/v1` | Declares repository-owned skills, source directories, desired runtime roots, and adapter contracts. It is not delete authority. |
| Inventory | `waywarden.inventory/v1` | Records read-only observed evidence from the manifest, repository source tree, runtime roots, runtime adapters, and existing Waywarden state snapshot. It is evidence for planning, not mutation authority by itself. |
| Plan | `waywarden.plan/v1` | Envelope with top-level `schema`, `approval_digest`, and `payload`. `payload.inventory` embeds the complete canonical inventory object, `payload.inventory_digest` records its SHA-256, and the payload records deterministic deployments, ordered unique runtime bindings, blockers, preconditions, backup set requirements, verification requirements, rollback strategy, and aggregate lineage transitions. It is mutation authority only when the caller supplies the matching digest, the envelope is byte-identical to canonical serialization, the embedded inventory is canonical and digest-matching, physical slots are canonicalized/deduplicated, and all preconditions are reobserved. |
| Backup manifest | `waywarden.backup-manifest/v1` | Records the complete backup set, one entry per deployment, typed-missing entries, payload hashes, exact identity metadata, source operation, installation lineage, and verification result. It is restore authority only when the complete backup set is selected explicitly and verified. |
| Ownership | `waywarden.ownership/v1` | Append-only hash-chained aggregate ledger entries recording managed installation lineage transitions and artifact references for all deployment IDs in the aggregate. It is uninstall authority only together with exact current governed slot identity plus managed object identity, explicitly excluding source digest and resolved content as delete authority. |
| Receipt | `waywarden.receipt/v1` | Terminal audit evidence published by the acyclic ready/receipt-draft/committed protocol. Its draft records a mutating command's approved plan digest, or a schema-null approval digest for verification-only receipts, plus ledger record hash, ready journal-prefix hash, plan/inventory/backup/verification references available before terminal commit, observed preconditions, per-deployment mutation or verification results, rollback results, aggregate operation result, and required verification status. The later terminal journal entry references the receipt digest; the receipt does not reference that terminal entry. It is audit evidence and not independent delete authority. |
| Verification | `waywarden.verification/v1` | Records canonical immutable read-only verification assertions, runtime adapter evidence, collisions, source resolution, link identity, operator attestation where required, and final aggregate verification status. It may advance aggregate lineage status only through a later ledger event that references a non-null `verification_ref`. |
| Operator observation | `waywarden.operator-observation/v1` | Bounded human declaration for Claude verification challenges. It attests integrity, freshness, and binding of the human declaration, not the truth of the observed UI state. |
| Command result | `waywarden.command-result/v1` | Public stdout discriminated result union for completed artifact, mutation, and verification command phases. Nonapplicable fields are forbidden and nested typed errors appear only on blocked or non-verified variants. |
| Error | `waywarden.error/v1` | Public error envelope for machine-readable failure output. It defines stable error codes, safe messages, exit class, command, and optional redacted evidence references. |

The implementation plan must include JSON schema files or generated equivalents for each contract and contract tests that prove command outputs conform to the declared schemas.

### Artifact reference DAG and nullable references

Artifact references are acyclic and typed:

- `inventory_ref`: relative run path plus the SHA-256 digest of the canonical inventory artifact bytes.
- `plan_ref`: relative run path plus the SHA-256 digest of the canonical plan payload bytes approved for the command.
- `journal_ref`: at each nonterminal ledger boundary, the command records `operation_id`, relative journal path, and a hash of the durable journal prefix up to and including the boundary being referenced.
- `ready_journal_ref`: relative journal path plus the SHA-256 hash of the durable journal prefix ending at the nonterminal `ready_to_commit` entry.
- `terminal_journal_ref`: relative journal path plus the SHA-256 hash of the durable terminal `committed`, `rolled_back`, or `rollback_failed` sequence.
- `backup_set_ref`: `backup_set_id` plus backup manifest digest; it is nullable for operations that have no backup set.
- `verification_ref`: relative run path plus the SHA-256 digest of the canonical immutable `waywarden.verification/v1` bytes; it is non-null for verified ledger events and null for mutator events.

Normal, verification, and compensating ownership ledger records reference `plan_ref`, `inventory_ref`, `journal_ref`, nullable `backup_set_ref`, and nullable `verification_ref` according to the closed nullability rules below. Ledger records never reference receipts and the ledger schema has no `receipt_ref`.

The terminal receipt commit protocol is normative and acyclic:

1. after the normal ledger append/sync and cleanup, append and sync a nonterminal `ready_to_commit` journal boundary;
2. build the canonical receipt draft referencing the ledger record hash, `ready_journal_ref`, and all DAG refs; write and fsync it as an owner-private same-run-directory temporary file, then compute the receipt digest over the canonical draft bytes;
3. append and sync a terminal `committed` journal entry containing the receipt digest and final relative destination `receipt.json`; after `committed`, the normal journal chain is terminal and cannot be extended;
4. publish the draft to `receipt.json` with no-replace semantics, sync the run directory, and then exit 0.

The DAG order is `ledger -> ready journal prefix -> receipt draft -> terminal journal -> receipt publication`. The receipt draft references only the ready journal prefix; the terminal journal references the receipt digest; the published receipt is audit evidence. This prevents a receipt/journal cycle while preserving terminal ownership authority in the ledger plus terminal journal.

Failure before terminal `committed` uses rollback plus compensating ledger and journal evidence. Compensation uses a separate terminal sequence ending in `rolled_back` or `rollback_failed`; an optional failure receipt may be written only after compensation is durably recorded and journaled. Failure or crash after terminal `committed` but before `receipt.json` publication or run-directory sync must never roll back and must never extend the terminal normal chain. Waywarden preserves the draft, reports `receipt_publish_pending` as `recovery_required`, exits 5, and inventory reports that pending state. Version 1 performs no implicit resume.

Nullable reference rules are closed: install normal events require non-null `backup_set_ref` and null `verification_ref`; uninstall normal events use null `backup_set_ref` and null `verification_ref`; restore normal events require non-null `backup_set_ref` and null `verification_ref`; successful verification events require non-null `verification_ref` and use null `backup_set_ref` unless verifying a selected backup set; compensating records use the same backup nullability as the operation they compensate when a backup exists, null otherwise, and null `verification_ref` unless the compensating event is itself a verified-state transition.

### Canonical JSON and digest authority

Authoritative JSON contracts use RFC 8785 JSON Canonicalization Scheme. Allowed values are JSON null, booleans, UTF-8 strings, safe integers in the JCS exact integer domain `[-(2^53-1), 2^53-1]`, arrays, and objects. Floating-point numbers, non-finite values, implementation-dependent numeric forms, binary strings, and integers outside the JCS safe domain are prohibited as JSON numbers.

Sizes, counters, device identifiers, file identifiers, timestamps, and other values that can exceed the JCS safe integer domain are encoded as canonical decimal strings matching `0|[1-9][0-9]*`. Signed decimal strings are allowed only for schema fields that explicitly permit them and must match `0|-?[1-9][0-9]*` with no negative zero. Tests must include RFC 8785 canonical vectors and boundary vectors for `-(2^53-1)`, `2^53-1`, one below, and one above each safe boundary.

The strict parser rejects a byte order mark, duplicate object keys, trailing bytes, invalid UTF-8, disallowed value types, and any representation that is not canonical for contracts that require canonical persistence. The internal canonical encoder implements the applicable RFC 8785 subset. It emits no final newline. It does not normalize Unicode strings or paths; path and string bytes remain exactly as observed and represented by the platform adapter.

The plan envelope has exactly these top-level members:

```json
{
  "schema": "waywarden.plan/v1",
  "approval_digest": "<sha256-hex>",
  "payload": {}
}
```

The approval digest is `SHA-256` over the canonical RFC 8785 bytes of the `payload` member only. Verification re-parses the envelope strictly, canonicalizes `payload.inventory`, verifies `payload.inventory_digest`, re-canonicalizes `payload`, computes the payload digest, compares it with `approval_digest` and `--approve-digest`, and verifies that the complete envelope bytes are byte-identical to the canonical serialization of `schema`, `approval_digest`, and `payload`. Pretty-printing, key reordering, newline insertion, line-ending conversion, or any other noncanonical reserialization is rejected even when the payload is semantically equivalent.

## Determinism and blockers

Inventory and plan output must be deterministic. Given the same manifest bytes, repository source bytes, runtime evidence, Waywarden state snapshot already captured in the inventory artifact, platform adapter observations, command flags, and environment inputs, Waywarden must produce byte-identical inventory and plan JSON. For `plan`, the function is pure over the canonical inventory artifact plus explicit planning flags/selectors.

Required deterministic rules:

1. Inventory and plan payloads contain no newly generated timestamps, random IDs, process IDs, memory addresses, temporary paths, nondeterministic map ordering, or locale-dependent formatting. Observed stable state evidence may include timestamp-like values or random-looking IDs only when read from the manifest, runtime evidence, filesystem identity, backup state, journal state, or ledger snapshot.
2. Read-only commands never create new `operation_id`, `installation_id`, `backup_set_id`, journal ID, verification ID, receipt ID, UUID, nonce, or timestamp for inclusion in inventory or plan.
3. Object keys, arrays of skills, arrays of roots, operations, blockers, diagnostics, and evidence entries use stable lexical ordering unless a schema defines a stricter semantic order.
4. JSON persisted for inventory and plan uses the exact compact canonical encoding owned by `internal/distribution/contracts` and accepted by the strict parser.
5. Path comparison and identity are platform-adapter responsibilities. Unsupported Unicode normalization, case folding, aliasing, or path identity ambiguity fails closed rather than producing platform-dependent success.
6. The plan digest is `SHA-256` of the canonical bytes of the plan envelope's `payload` member only.
7. The persisted plan envelope must itself be byte-identical to its canonical serialization.
8. Receipts, journals, backup manifests, and verification records may include timestamps because they are event records rather than deterministic planning artifacts, but authoritative object substructures inside them still use canonical JSON validation rules.

`inventory` emits evidence and exits 3 when it encounters capability blockers such as unsupported filesystem primitives, unsupported metadata needed for safe observation, unsupported runtime contract shape, or invalid state-root capability. Schema/input errors exit 2. Inventory itself never returns exit 4 for evidence blockers; exit 4 from inventory is reserved for output preconditions such as an existing explicit destination.

`plan` still emits a deterministic plan artifact when blockers exist. Capability blockers produce exit 3. Safe precondition blockers produce exit 4. If both capability and safe precondition blockers are present, capability wins and the command exits 3. A repeated `inventory` or `plan` over unchanged evidence must be byte-identical and return the same exit class when using `--out -` or a fresh explicit destination. Reusing an existing explicit destination exits 4 and produces no artifact, by output precondition rather than evidence. If evidence changed, the changed evidence must appear in the inventory or plan and the plan digest must change.

## Lifecycle

The approved aggregate command and data flow is:

```text
inventory -> plan install -> apply -> verify installation -> inventory -> plan uninstall -> uninstall -> verify installation -> inventory -> plan restore -> restore -> verify backup
```

### Filesystem identity vocabulary

Waywarden records separate filesystem identities and never substitutes one for another:

- `governed_slot_identity`: the canonical parent identity plus the exact lexical basename/path slot governed by the plan. It is stable independent of which object, if any, occupies the slot. It is the path-side identity used for deployment IDs, locking, planning dedupe, and pre-move uninstall authority.
- `managed_object_identity`: the stable object or file ID where the platform exposes one, symlink or reparse kind, exact lexical target, and the closed set of immutable attributes enumerated by the metadata matrix. It is independent of location; moving the object to quarantine intentionally changes the slot, not the managed object.
- `managed_link_identity`: the installed binding of `governed_slot_identity` plus `managed_object_identity` at the installed path. It is the immutable installed-link identity recorded for Waywarden-created managed links.
- `original_preimage`: the object observed at the governed slot before apply mutation and backed up when the slot exists. For an originally missing slot, this is the typed missing observation.
- `source_content_digest`: the resolved source tree digest observed at apply or verify time. It is mutable diagnostic and verification evidence only. It can prove content drift but is never uninstall equality, delete authority, or a reason to block an otherwise authorized uninstall.
- `installed_postimage`: the post-install observation containing `managed_link_identity`, the then-observed resolved canonical source identity, `source_content_digest`, and supported verification evidence. Delete authority uses only exact governed slot plus managed object as described here; it explicitly excludes source digest and resolved content. A recreated equivalent link with different managed object identity is drift and is not deletable.
- `uninstall_observation`: the immediate reobservation during uninstall planning or mutation, split into governed slot, managed object, managed-link, and source-content fields.

Ledger entries and receipts record observed type, stable object identity where available, lexical path, lexical link target, `governed_slot_identity`, `managed_object_identity`, `managed_link_identity`, `source_content_digest`, supported attributes from the metadata matrix, and fingerprint for each identity. Before uninstall moves the installed object, authority requires exact current `governed_slot_identity` plus exact current `managed_object_identity` to match the ledgered installed values. After uninstall moves the object to quarantine, the quarantine slot differs by design, so Waywarden compares only `managed_object_identity` for the moved object. It never requires, compares against, or derives delete authority from `source_content_digest`, resolved source content, `original_preimage`, textual skill names, or operator memory. Normal source edits may make verification report content drift, but they do not block authorized uninstall when the governed slot and immutable managed object still match. `original_preimage` is backup and restore evidence only.

### Normal aggregate lifecycle events

Normal per-deployment events are valid only as part of one aggregate ledger append covering every deployment ID in the installation. The normal state graph is:

```text
applied_unverified -> installed_verified
applied_unverified -> removed_unverified
installed_verified -> removed_unverified
removed_unverified -> removed_verified -> restored_unverified -> restored_verified
```

Uninstall from either `applied_unverified` or `installed_verified` is allowed and always requires exact governed slot plus managed object authority for every deployment before move, then exact managed object authority after quarantine move. Source digest and resolved content are explicitly excluded from delete authority. This enables safe removal after failed runtime verification while still preventing deletion by name, path, content, or memory.

A successful verify returns 0 and advances exactly one proven aggregate event:

- `applied_unverified -> installed_verified` for successful installation verification;
- `removed_unverified -> removed_verified` for successful uninstall verification;
- `restored_unverified -> restored_verified` for successful restore verification.

A verification failure returns 6, preserves the current unverified aggregate event, and performs no automatic rollback.

### Compensating aggregate events and crash boundaries

Compensating events are aggregate ledger records, not per-deployment records:

- `install_rolled_back`: terminal event with no active Waywarden ownership.
- `uninstall_rolled_back`: derived deployment state returns to the exact prior `applied_unverified` or `installed_verified` state recorded in the failed uninstall event.
- `restore_rolled_back`: deployment state returns to `removed_verified` or absent according to the recorded prior event.
- `recovery_required`: any incomplete, mixed, contradictory, or unprovable compensation.

Each normal, verification, or compensating ledger append is one aggregate hash-chained record containing all deployment IDs, before/after observations, per-deployment results, `plan_ref`, `inventory_ref`, `journal_ref`, nullable `backup_set_ref`, nullable `verification_ref`, operation result, aggregate event, and `failure_code` for compensating/failure events. It never contains `receipt_ref`. There is never one ledger append per deployment for a batch transition.

Durability boundaries are normative: journal start durable before backup; backup set manifest and deployment entries durable before filesystem mutation; filesystem mutation reobserved before ledger append; normal ledger append durable before cleanup; cleanup durable before nonterminal `ready_to_commit`; receipt draft durable before terminal `committed`; terminal `committed` durable before no-replace receipt publication and run-directory sync; receipt publication durable before command exit 0. Exit 0 from a mutator is allowed only after aggregate ledger, cleanup, ready boundary, receipt draft, terminal journal, and receipt publication are durable. Failure before terminal `committed` requires rollback, rollback journal entries, and then a compensating aggregate ledger record with `failure_code`. Failure to append or verify the compensating record yields `recovery_required` and exit 5. Failure after terminal `committed` is `receipt_publish_pending`/`recovery_required` exit 5 with no rollback and no journal extension.

A crash after any ledger, journal, cleanup, receipt-draft, receipt-publication, or parent-sync boundary has dedicated failure-injection tests. A crash after filesystem mutation but before durable ledger append is journal evidence for `recovery_required`, not uninstall authority. A failure that prevents receipt publication after terminal `committed` does not invalidate the normal or compensating ledger event; the published receipt is audit evidence, while terminal journal plus ledger remain ownership authority. A crash or cleanup contradiction after command-phase success is `recovery_required` unless the ledger, terminal journal, published receipt or preserved draft, and retained rollback authority prove the exact aggregate state.

### Apply

`apply` installs repository-owned skills by creating or replacing only governed runtime paths listed by the approved install plan. It must:

1. validate plan schema, canonical envelope, embedded inventory canonicality, embedded inventory digest, install intent, plan digest, and approval digest;
2. acquire locks in the normative order;
3. generate cryptographically random `operation_id`, `installation_id`, and `backup_set_id` as event IDs outside the approved plan payload;
4. create `runs/<operation-id>` and durably copy canonical embedded inventory bytes to `inventory.json` and exact plan envelope bytes to `plan.json`;
5. reobserve every precondition for every deployment;
6. create one backup set with exactly one entry per deployment, including typed-missing entries;
7. verify every backup entry before mutating any governed path;
8. append and sync journal boundaries;
9. perform the filesystem install protocol for every deployment, with one filesystem mutation per physical deployment even when multiple runtime bindings share the same slot;
10. append and sync one aggregate ownership event `applied_unverified` containing every deployment ID and DAG references with null `verification_ref`;
11. cleanup staging/quarantine according to the exact cleanup protocol;
12. append and sync nonterminal `ready_to_commit`;
13. durably write the canonical receipt draft, append and sync terminal `committed`, publish `receipt.json` no-replace, sync the run directory; and
14. exit 0 with operation result `verification_required`.

`apply` does not run runtime verification implicitly. Exit 0 from `apply` means command-phase completion, not lifecycle acceptance.

### Verify

`verify` independently checks repository sources, links, runtime discovery, collisions, ownership records, backup set references, receipts, operator observation where required, and selected aggregate outcomes. Verification is read-only toward repository sources and runtime roots, but a successful proof may write immutable verification audit evidence and append one ownership ledger transition.

The verification write protocol is normative:

1. acquire the global mutation lock and selected-ledger lock, allocate `operation_id`, create the run directory, create/open `journal.ndjson`, append `started`, and sync the first journal boundary;
2. collect runtime, filesystem, receipt, backup, and operator evidence without mutating runtime roots;
3. write/fsync an owner-private canonical `waywarden.verification/v1` artifact, publish it no-replace under `runs/<operation-id>/verification/<verification-id>.json`, and sync the run directory before any ledger transition;
4. append one verified ownership event only when evidence proves the selected transition for every deployment and every runtime binding; that event references a non-null `verification_ref`; mutator events always carry null `verification_ref`;
5. complete the same `ready_to_commit` -> receipt draft -> terminal `committed` -> no-replace `receipt.json` publication protocol used by mutators.

Evidence failure exits 6, persists the failed verification artifact when artifact persistence succeeds, and performs no ledger transition. Verification artifact, state, ledger, receipt, write, fsync, publish, or lock I/O failure exits 5. Unsupported verification contract or adapter contract exits 3. If the ledger transition fails after the immutable verification artifact was published, the artifact remains non-authoritative audit evidence and ownership state is unchanged except for recovery evidence.

Repeated verification first detects an existing verified event for the selected aggregate and returns 0 without a second lineage transition. It may create a new audit verification artifact only if there is no recovery-required, pending terminal contradiction, or receipt-publish-pending state for the selected aggregate.

Verification fails closed for missing runtimes during requested verification, timeouts, duplicate governed skill names, wrong discovery winners, invalid runtime output, nonzero runtime exits, nonempty command stderr where the adapter declares stderr fatal, missing or invalid operator observation, path ambiguity, unresolved sources, unexpected links, content drift, mixed deployment state, or unsupported runtime shape.

### Uninstall

`uninstall` removes only complete Waywarden-managed installation aggregates. It requires:

- a valid uninstall plan produced for exactly one `installation_id` selector;
- exact approved plan payload digest, canonical envelope, canonical embedded inventory, and digest matches;
- an aggregate Waywarden ownership ledger entry produced by Waywarden;
- current aggregate state `applied_unverified` or `installed_verified`;
- before move, exact current `governed_slot_identity` plus exact current `managed_object_identity` matching the ledgered installed values for every deployment; after quarantine move, exact `managed_object_identity` match only because the quarantine slot differs by design;
- no path drift, duplicate ambiguity, runtime-root ambiguity, or unsupported filesystem metadata.

Textual skill names, textual paths, matching file content, matching frontmatter names, matching original preimage, and operator memory are never uninstall authority. If Waywarden state is lost, corrupted, insufficient, or mixed outside the active locked journal, uninstall fails closed. The user may remove unmanaged files manually outside Waywarden, but Waywarden must not convert that situation into delete authority.

After durable removal mutation, aggregate ledger append, cleanup, nonterminal ready boundary, receipt draft, terminal `committed`, and receipt publication sync, uninstall records `removed_unverified` and returns exit 0 with operation result `verification_required`. Uninstall never restores a backup implicitly.

### Restore

`restore` is a separate explicit intent. It requires an exact selected `backup_set_id` whose `waywarden.backup-manifest/v1` proves the complete backup set was created and verified by Waywarden for the same installation lineage. Ordinary restore requires the same lineage, aggregate state `removed_verified`, and every governed slot absent. It restores the complete backup set and rejects partial deployment selection as exit 2.

Version 1 does not support recovery restore over other deployment state. If any governed slot is present, any lineage is not `removed_verified`, the backup set belongs to another lineage, or journal evidence indicates unresolved mutation, restore fails with `recovery_required` or the more specific precondition error and performs no mutation.

After durable restoration, aggregate ledger append, cleanup, nonterminal ready boundary, receipt draft, terminal `committed`, and receipt publication sync, restore records `restored_unverified` and returns exit 0 with operation result `verification_required`. A restored real directory, file, or link returns to the user's control unless a later install plan explicitly replaces the complete aggregate again under Waywarden rules.

### Operation results

Operation result is separate from aggregate lineage event:

| Operation result | Meaning |
| --- | --- |
| `verification_required` | A mutating command completed its command phase: durable aggregate ledger, cleanup, `ready_to_commit`, receipt draft, terminal `committed`, and no-replace receipt publication. It now requires explicit `verify`. Mutating command exits 0 with this result only after all boundaries are durable. |
| `verified` | A `verify` command proved the requested aggregate event and advanced exactly one lineage transition. Verify exits 0. |
| `rolled_back` | A failure during mutation or before durable `verification_required` was reversed by rollback and rollback verification succeeded. The initiating command still exits nonzero according to the initiating error class. |
| `recovery_required` | Waywarden cannot prove final success or complete rollback from persisted journal, ledger, receipt, backup, and filesystem evidence. Human recovery planning is required before more mutation. The command exits 5. |

### Idempotency matrix

| Command scenario | Exit | Mutation | Ledger/status effect |
| --- | --- | --- | --- |
| `inventory` repeated over unchanged evidence with `--out -` or a fresh explicit destination | 0 or 3 matching deterministic blocker class | none | byte-identical artifact; no state write except artifact emission |
| `inventory` with an existing explicit destination | 4 | none | no artifact; output precondition failure only |
| `plan` repeated over unchanged canonical inventory with `--out -` or a fresh explicit destination | 0, 3, or 4 matching deterministic blocker class | none | byte-identical artifact; no state write except artifact emission |
| `plan` with an existing explicit destination | 4 | none | no artifact; output precondition failure only |
| `apply` same plan after the install transition was already applied | 4 | none | stale precondition; no duplicate ledger entry |
| `verify` repeated for the same already-proven aggregate event | 0 | none | no duplicate lineage transition; a new verification artifact may be recorded only when no recovery or pending terminal contradiction exists |
| `uninstall` repeated after removal transition | 4 | none | already removed or stale precondition; no duplicate ledger entry |
| `restore` repeated after restore or deployment/lineage changed | 4 | none | deployment or lineage changed; no duplicate ledger entry |
| Any plan reused after the transition it authorized | 4 | none | stale precondition; no mutation |

## Filesystem safety and TOCTOU policy

Portable filesystems cannot atomically compare-and-swap arbitrary directory-entry identity against uncooperative writers. Waywarden safety therefore uses no-clobber moves, post-move identity verification, durable journals, and fail-closed recovery. Waywarden never overwrites an entry that appeared after observation.

Required no-replace primitives are:

- Linux: `renameat2(..., RENAME_NOREPLACE)`. If unavailable, mutation is blocked with exit 3.
- macOS: `renameatx_np(..., RENAME_EXCL)`. If unavailable, mutation is blocked with exit 3.
- Windows: handle-bound observation plus `MoveFileEx` without `MOVEFILE_REPLACE_EXISTING`, or a proven no-replace `SetFileInformationByHandle` path. If no-replace semantics are unavailable for the governed slot's object kind, mutation is blocked with exit 3.

Shared policy is stricter than recursive path APIs:

- inspect each path segment before acting;
- use exact absolute paths from the approved plan;
- reject governed runtime paths outside configured runtime roots and state paths outside the selected state root;
- reject unexpected symlinks, junctions, mount points, reparse points, hardlink ambiguity, case-collision ambiguity, unsupported Unicode behavior, permission ambiguity, or type drift;
- never call `RemoveAll` or equivalent recursive deletion on a governed runtime path;
- create unique quarantine and staging paths on the same filesystem and same parent directory as the governed slot;
- require the runtime adapter to prove the reserved quarantine/staging namespace is ignored by runtime discovery before mutation;
- write or link into staging first;
- hash regular staged content through the open descriptor or handle before replacement;
- sync object data and metadata according to the exact platform primitive contract;
- close, reobserve, and verify staged object identity/fingerprint before any move;
- use only required no-replace rename or move primitives;
- sync the parent directory using the platform adapter's proven parent-directory sync primitive;
- treat precondition drift as stable failure with no best-effort mutation.

### Exact install protocol per deployment

The install protocol is identical for missing governed slots, files, symlinks, empty directories, and nonempty directories except that missing slots have no quarantine object.

For a missing physical slot, Waywarden stages the managed link in a unique same-parent staging namespace, verifies the staged link, no-replace moves it to the governed slot, reobserves the post-install governed slot plus managed object fields, syncs the parent, and journals every boundary.

For every existing governed slot type — regular file, ordinary symlink, empty directory, or nonempty directory — Waywarden:

1. creates and verifies the backup entry before mutation;
2. no-replace moves the existing slot occupant to a unique same-parent quarantine path;
3. reobserves the quarantine object and requires its managed object or backup fingerprint to equal the planned `original_preimage`; the quarantine slot itself is not compared because it differs by design;
4. if the quarantine identity mismatches and the governed slot is absent, restores quarantine to the slot with no-replace semantics, records the stable precondition failure, and exits 4;
5. if the quarantine identity mismatches and the governed slot is occupied, preserves quarantine, records `recovery_required`, and exits 5;
6. only after quarantine identity matches, no-replace moves the staged replacement into the absent governed slot;
7. reobserves exact governed slot plus managed object postimage fields, syncs the parent, and journals every boundary.

Quarantine and staging directories are retained until rollback authority is no longer needed. Cleanup occurs after the normal aggregate ledger record and before `ready_to_commit`, receipt draft, terminal `committed`, and receipt publication. Cleanup is itself journaled. Exit 0 is allowed only after aggregate ledger, cleanup, ready boundary, terminal journal, and receipt publication are durable.

### Symlink and reparse fingerprinting

Unix symlink fingerprint uses no-follow type, lexical `readlinkat` target, `managed_link_identity`, resolved link-target/source identity, `source_content_digest`, and supported attributes from the metadata matrix. It never claims symlink content is hashed through a descriptor and never claims symlink metadata is fsynced through a descriptor. The parent directory is synced after symlink creation, movement, restoration, or deletion.

Windows ordinary symlink fingerprint uses exact symlink reparse tag, lexical substitute target, lexical print target, relative flag, `managed_link_identity`, resolved source identity, `source_content_digest`, and supported attributes from the metadata matrix. Other reparse tags are blocked.

### Exact quarantine cleanup protocol

Waywarden never uses generic recursive deletion such as `RemoveAll`, shell `rm -rf`, or any API that follows links while cleaning a governed quarantine or staging tree. Every deletion branch revalidates immediately before deletion:

- Regular file: reopen by descriptor or handle with no-follow/reparse-safe semantics, rehash the full content through that handle, revalidate metadata and `managed_object_identity`, then unlink with descriptor-relative `unlinkat` on Unix or Windows disposition-by-handle semantics.
- Symlink or Windows reparse symlink: `lstat`/`readlinkat` or reparse inspection revalidates the full symlink/reparse managed-object fingerprint, including kind, exact lexical target, closed attributes, and identity where available, then unlinks handle- or parent-relative without following the link.
- Empty directory: reopen the directory, verify type, metadata, identity, and empty enumeration immediately before removal, then remove it with `unlinkat(..., AT_REMOVEDIR)` or proven Windows handle-bound directory-disposition semantics.
- Nonempty tree: open the root no-follow/reparse-safe; walk entries by stable sorted descriptors; for every file, rehash content, metadata, and identity immediately before unlink; for every symlink/reparse entry, revalidate the full fingerprint immediately before unlink; for every directory, revalidate metadata and empty enumeration immediately before removal. Revalidate the root immediately before final removal.

Any in-place content change, new child, missing child, nonempty directory, mismatched metadata, identity mismatch, alias, hardlink ambiguity, link swap, or unsupported primitive preserves the remainder, journals the contradiction, records `recovery_required`, and requires operator recovery. Parent directories are synced after each deletion boundary required by the platform adapter and after final root removal. Apply rollback, uninstall, restore, and inverse cleanup all use the same branches.

### Apply rollback protocol

Apply rollback runs durably journaled deployment steps in reverse order. A created managed link is moved no-replace to rollback quarantine, then verified by managed object identity only because the rollback quarantine slot differs by design; source content drift is diagnostic only. Waywarden then either moves the original quarantine object back with no-replace semantics or reconstructs the exact backup entry into staging, verifies it, and no-replace moves it to the governed slot. For an original `typed_missing` preimage, rollback returns the slot to absent and performs no payload restoration. Any occupied slot, managed-object identity mismatch, backup reconstruction mismatch, cleanup race, or inability to durably journal/ledger compensation yields preserved evidence and `recovery_required`.

### Normative uninstall protocol

For each deployment in the aggregate, uninstall stages no replacement. Before the move, it requires exact current `governed_slot_identity` plus exact current `managed_object_identity` to match the ledgered installed values. It then no-replace moves the installed managed symlink or ordinary symlink-equivalent to a unique same-parent quarantine path, reobserves the moved object, and compares `managed_object_identity` only because the quarantine slot differs by design. It does not compare `source_content_digest` or resolved source content for delete authority. If identity mismatches and the governed slot is absent, Waywarden restores quarantine to the slot with no-replace semantics and exits 4. If it mismatches and the slot is occupied, Waywarden preserves quarantine, records `recovery_required`, and exits 5. If it matches, Waywarden deletes the exact quarantine object only as a journaled transaction step using the exact cleanup protocol and never uses recursive deletion.

Uninstall rollback restores the quarantined managed link no-replace if it is retained. If cleanup already deleted the link, rollback recreates the exact lexical managed link from ledgered immutable fields and appends an abort or compensating aggregate record containing the newly observed `managed_link_identity`. If that new identity cannot be durably journaled and ledgered, Waywarden preserves evidence and records `recovery_required`. Any occupied governed slot during rollback is never overwritten; Waywarden preserves quarantine or reconstruction staging and records `recovery_required`.

### Normative restore protocol

For each deployment in the complete backup set, restore builds the exact full restored object or tree in a unique same-parent ignored staging namespace, verifies the tree digest and metadata matrix semantics, requires the governed slot to be absent, no-replace moves the staged object into the slot, reobserves exact backup semantics, syncs the parent, and journals every boundary. A `typed_missing` backup entry requires the slot to be absent, creates no payload and no staging object, performs no filesystem action, records the restored postimage as typed missing, and verifies that the slot remains absent. Clean restore slot present or changed is exit 4 before mutation.

Restore rollback moves any newly restored object no-replace to rollback quarantine, verifies that it still satisfies the backup entry semantics, safely cleans it with the exact cleanup protocol, and returns the governed slot to absent. A `typed_missing` restore rollback is a no-op and requires the governed slot to remain absent. Occupied governed slot during rollback yields preserved staging/quarantine evidence and `recovery_required`.

## Backup and identity metadata matrix

All path names recorded by Waywarden must be valid UTF-8. Non-UTF8 names are blocked before planning or mutation. Backup payloads always preserve content, object type, relative path, and link lexical target for symlinks. Unsupported metadata blocks before mutation.

| Platform/object | Required supported semantics | Blocked conditions |
| --- | --- | --- |
| Linux regular files | Owner must be current uid; group must be current effective gid; file type plus mode bits exactly within `0777`; content; inode flags mask must be zero; mtime nanoseconds only if a pre-mutation timestamp round-trip probe proves exact return. atime and ctime are excluded. | Any metadata bit not explicitly allowed, sticky/setuid/setgid, ACL, xattr, hardlink `nlink > 1`, sparse file, mount, device, FIFO, socket, non-current owner/group, nonzero inode flags, timestamp round-trip failure. |
| Linux directories | Owner must be current uid; group must be current effective gid; directory type plus mode bits exactly within `01777`; sticky is the only permitted bit outside `0777`; setuid/setgid are blocked; tree entries; inode flags mask must be zero; mtime nanoseconds only if a pre-mutation timestamp round-trip probe proves exact return. atime and ctime are excluded. Empty and nonempty directories use the same quarantine protocol. | Any metadata bit not explicitly allowed, any mode bit outside `01777`, setuid/setgid, ACL, xattr, hardlink ambiguity where observable, mount, device, FIFO, socket, non-current owner/group, nonzero inode flags, timestamp round-trip failure. |
| macOS regular files | Same mode, owner, group, content, hardlink, and mtime policy as Linux regular files; `st_flags` must be zero. atime, ctime, and birthtime are excluded. | Any metadata bit not explicitly allowed, sticky/setuid/setgid, ACL, xattr, resource fork, hardlink `nlink > 1`, sparse file, mount, device, FIFO, socket, non-current owner/group, nonzero `st_flags`, timestamp round-trip failure. |
| macOS directories | Same owner, group, tree, and mtime policy as Linux directories; directory type plus mode bits exactly within `01777`; sticky is the only permitted bit outside `0777`; setuid/setgid are blocked; `st_flags` must be zero. atime, ctime, and birthtime are excluded. | Any metadata bit not explicitly allowed, any mode bit outside `01777`, setuid/setgid, ACL, xattr, resource fork, hardlink ambiguity where observable, mount, device, FIFO, socket, non-current owner/group, nonzero `st_flags`, timestamp round-trip failure. |
| Unix symlinks | Preserve lexical target. Owner must be current uid and group must be current effective gid. Only symlink type and lexical target are preserved; symlink mode and timestamps are excluded. No extra flags, ACLs, or xattrs are allowed. | Any metadata bit not explicitly allowed, non-current owner/group, observable symlink ACL/xattr, extra flags, unsupported lexical target encoding. |
| Windows regular files | Owner must be current SID; DACL must be inherited/unprotected with no explicit ACE; preserve content and LastWriteTime at 100ns. Attribute mask is closed: either `NORMAL` alone or any subset of `READONLY | HIDDEN | ARCHIVE`;`NORMAL` is semantically empty and must not be combined as authority. | Any other attribute bit, explicit/protected DACL, ADS beyond default data stream, hardlink count > 1, mount, reparse point, non-current owner, timestamp round-trip failure. |
| Windows directories | Owner must be current SID; DACL must be inherited/unprotected with no explicit ACE; preserve tree entries and LastWriteTime at 100ns. Attribute mask requires `DIRECTORY` plus any subset of `READONLY | HIDDEN | ARCHIVE`. | Any other attribute bit, explicit/protected DACL, ADS beyond default data stream, mount, reparse point, non-current owner, timestamp round-trip failure. |
| Windows ordinary file symlink | Preserve exact symlink reparse tag, lexical substitute target, lexical print target, relative flag, owner current SID, and inherited/unprotected DACL with no explicit ACE. Attribute mask requires `REPARSE_POINT` plus any subset of `READONLY | HIDDEN`. Symlink times are excluded. | Any other attribute bit, other reparse tag, explicit/protected DACL, ADS beyond default stream where observable, non-current owner. |
| Windows ordinary directory symlink | Preserve exact symlink reparse tag, lexical substitute target, lexical print target, relative flag, owner current SID, and inherited/unprotected DACL with no explicit ACE. Attribute mask requires `REPARSE_POINT | DIRECTORY` plus any subset of `READONLY | HIDDEN`. Symlink times are excluded. | Any other attribute bit, other reparse tag including junction authority, explicit/protected DACL, ADS beyond default stream where observable, non-current owner. |

The metadata policy is closed: any metadata field, flag, permission bit, attribute bit, stream, ACL, xattr, resource fork, or timestamp not explicitly allowed above is a blocker before planning or mutation. Timestamp round-trip failure blocks before mutation. The backup tree digest commits to ordered canonical entries containing relative path, object type, content digest for regular files, subtree relationship for directories, lexical link target for symlinks, LastWriteTime or Unix mtime only where preserved, and every preserved attribute in this matrix. It explicitly excludes Unix atime/ctime, macOS birthtime, Windows CreationTime, LastAccessTime, ChangeTime, and all symlink times. Unsupported values block before mutation and therefore cannot be silently omitted from equality.

## Backup contract

Version 1 supports only these original preimages for backup and restore:

- typed missing governed slot;
- regular files satisfying the metadata matrix;
- ordinary symlinks satisfying the metadata matrix;
- directory trees containing only ordinary directories, regular files, and ordinary symlinks satisfying the metadata matrix.

A `typed_missing` backup entry records that the governed slot was absent at backup time. It has no payload directory, no staged payload object, and no content hash. Restore of `typed_missing` requires the slot to be absent, performs no filesystem action, records the restored postimage as typed missing, and verifies that the slot is still absent. Rollback of a `typed_missing` restore is also a no-op that verifies absence.

Snapshot creation uses no-follow observation, handle/descriptor-bound reads, before-and-after identity checks, size and mtime checks where applicable, open-no-follow reads, content digest verification, metadata matrix validation, and mutation-during-copy detection. Backup creation, hashing, metadata capture, manifest write, or sync failure before the first governed slot move is exit 4 even if the operation journal has already been opened. Restore reproduces the exact supported semantics and then rehashes/reobserves the restored object or tree, or verifies absence for `typed_missing`, before recording `restored_unverified`.

## Concurrency, ledger trust, and recovery

Waywarden serializes every mutator and every verification state write across state roots using a canonical state-root-independent global mutation lock. Coordination locks are OS-backed descriptor or handle locks stored under the canonical owner-private platform lock root. Unix platforms use an OS file lock on an opened lock file. Windows uses `LockFileEx`-equivalent behavior. Process crashes release the OS lock; stale lock files are not authority to resume or mutate.

Normative lock order is:

1. global mutation lock;
2. individually computed governed-slot locks sorted by key;
3. selected state-root exclusive ledger lock.

Each governed-slot lock key is individually `SHA-256(governed_slot_identity)`. Waywarden does not hash a combined deployment set to obtain slot lock authority. Path aliases, symlinks, reparse aliases, case folding, short names, and other platform aliases must resolve to the same canonical governed slot identity or block. Distinct state roots cannot bypass coordination for the same physical runtime slot identity.

Verification state writes acquire the global mutation lock and then the selected state-root exclusive ledger lock. They do not acquire governed-slot locks. Only after both locks are held may verify allocate `operation_id`, create the run directory, append `started`, and sync the first journal boundary. Inventory that reads Waywarden state acquires a shared selected-ledger lock and consumes a complete snapshot into the inventory artifact. Planning reads only the inventory artifact and acquires no ledger lock. Read-only commands do not acquire governed-slot locks because they do not mutate runtime slots.

`ownership/installations.ndjson` is a strict hash-chained append-only aggregate ledger. A ledger append is one complete newline-framed canonical record, and shared/exclusive locking prevents concurrent chain forks. Strict readers never consume partial append: they accept only complete newline-terminated records whose canonical bytes parse and hash correctly. The record canonical bytes exclude the NDJSON newline and exclude the record's own hash field; the newline is framing only. The previous hash binds the chain.

Each record includes installation ID, operation ID, monotonic sequence number, previous record hash, record hash, `plan_ref`, `inventory_ref`, `journal_ref`, nullable `backup_set_ref`, nullable `verification_ref`, aggregate event, operation result, all deployment IDs, per-deployment before/after observations, ordered runtime binding evidence summaries, `original_preimage`, `installed_postimage`, and a compensating prior-state object for compensating events. It does not include `receipt_ref`. Mutator normal events carry null `verification_ref`, a schema-null compensating prior-state field, and schema-null `failure_code`. Verified events carry non-null `verification_ref`. Compensating events carry `failure_code` and the prior-state object needed to prove rollback or recovery-required status.

Ledger scan is strict. Duplicate sequence, out-of-order sequence, hash mismatch, unknown mandatory field, truncated tail, invalid canonical JSON, contradictory aggregate lineage, missing deployment in an aggregate record, or mixed deployment state outside an active locked journal yields `recovery_required` and no mutation. Version 1 performs no automatic tail repair.

The operation journal is append-only NDJSON. Journal entries include operation identifiers, approved digest, command, intent, state root, deployment references, governed-slot references, backup set references, verification references, timestamps, step names, step states, rollback authority references, terminality, and sync boundaries.

| Journal state | Meaning |
| --- | --- |
| `started` | A command or step began after acquiring required locks, or the first durable verification-state boundary was created. Nonterminal. |
| `ready_to_commit` | Normal ledger and cleanup, or verified ledger transition and verification artifact publication, are durable and the receipt draft can be built from an immutable journal prefix. Nonterminal. |
| `committed` | Terminal normal sequence entry containing the receipt digest and final relative receipt destination. After this entry, the normal journal chain cannot be extended or rolled back. |
| `rolled_back` | Terminal compensation sequence proving the command or step was reversed successfully after a pre-terminal failure. |
| `rollback_failed` | Terminal compensation sequence proving rollback could not be completed or verified and recovery is required. |

Waywarden never performs implicit resume. If an interrupted or contradictory journal is found, commands that would mutate affected paths emit `recovery_required` and exit 5. The operator must run a new inventory and produce a new plan from real current state. The new plan may use journal and backup evidence as inputs, but it must not assume the interrupted operation's intended state.

Rollback runs in reverse order of durably journaled mutation steps only when failure happens before terminal `committed`. Rollback itself is journaled and verified through a separate terminal compensation sequence. Rollback uses no-replace restoration only and never overwrites an occupied slot. Safe restoration after a no-replace race before irreversible mutation is exit 4. Unsafe restoration, occupied rollback slot, failed rollback verification, journal sync failure during rollback, or compensating ledger failure is `recovery_required` and exit 5. After terminal `committed`, rollback is forbidden; receipt publication failure is reported as `receipt_publish_pending`/`recovery_required`.

## Public errors, output, and exits

Machine-readable errors use this envelope:

```json
{
  "schema": "waywarden.error/v1",
  "code": "approval_digest_mismatch",
  "message": "The supplied approval digest does not match the plan digest.",
  "exit": 4,
  "command": "apply",
  "evidence": []
}
```

Public errors must not include Go stack traces, panic output, secrets, tokens, full private home paths, unredacted environment values, or runtime payloads that may contain private configuration. Diagnostics may include redacted path labels, schema pointers, digest prefixes only when sufficient for human correlation, and run artifact references under the selected state root.

Exit codes are stable and map to normative error classes. Error precedence is phase-aware and total. Phases are:

- `read_only_publish`: confined artifact output for `inventory` and `plan`, including destination checks, same-parent staging, fsync, no-replace publication, and parent sync. The existing `--out` destination check precedes evidence blocker evaluation and exits 4 with no artifact.
- `preflight`: mutator or verifier validation through lock acquisition and first journal create/open/write/sync. Lock conflict/timeout and first journal create/write/sync failure are exit 5 in this phase.
- `transaction_open`: operation journal is durable but no governed slot has been moved yet. Backup precondition failures before the first move are exit 4.
- `mutation_active`: after the first governed slot move and before the normal aggregate ledger record is durable; rollback rules apply.
- `ledger_committed`: after the normal or verified aggregate ledger record is durable and before terminal `committed`; failure requires rollback plus a separate compensation terminal sequence and exits 5.
- `terminal_committed`: after terminal `committed`; the normal journal chain cannot be extended and rollback is forbidden. This phase is absorbing and takes priority over every command-specific phase. Receipt publication, no-replace publication, or parent sync failure becomes `receipt_publish_pending`/`recovery_required` exit 5.
- `verification_collect`: runtime, filesystem, receipt, backup, and operator evidence collection before verification artifact publication. Evidence/runtime failures exit 6; unsupported contracts exit 3.
- `verification_state_write`: verification artifact publication, verified ledger transition, ready boundary, receipt draft, and the terminal-journal append/sync attempt up to—but not including—the moment `committed` becomes durable. I/O, write, fsync, publish, state, ledger, receipt-draft, or preterminal journal failure exits 5. Once `committed` is durable, `terminal_committed` applies exclusively.

Named code mappings are closed: each injection maps exactly once by first matching the most specific row below for its phase.

| Code family and condition | Phase | Exit | Persisted state and rollback behavior |
| --- | --- | --- | --- |
| `success` or command phase complete | any | 0 | Read-only commands persist only an explicit artifact selected by `--out`; mutators persist journal, aggregate ledger, cleanup completion, `ready_to_commit`, receipt draft, terminal `committed`, no-replace receipt publication, and `verification_required`; verify may persist verification artifact and aggregate transition. |
| `invalid_input`: invalid flags, malformed JSON, unreadable required input, invalid schema, noncanonical required input/artifact before approval validation, duplicate JSON keys, invalid selector cardinality, intent/selector mismatch, mutator intent mismatch | preflight | 2 | No mutation and no selected artifact except documented deterministic blocker artifacts. |
| `preflight_state_or_lock_failure`: lock conflict/timeout, run directory create failure, first journal create/open/write/sync failure, or selected state-root lock I/O failure before the first durable command boundary | preflight | 5 | No filesystem mutation. If a partial run directory or partial first journal exists, it is non-authoritative recovery evidence and never authorizes implicit resume. |
| `read_only_unsupported`: unsupported output primitive, unsupported no-replace publish primitive, unsupported output confinement capability | read_only_publish | 3 | No artifact is authoritative. |
| `read_only_publish_failed`: output artifact I/O, write, fsync, publish, or parent sync failure after capability proof | read_only_publish | 5 | No authoritative artifact except a fully published destination if the platform reports success before parent-sync failure; that contradiction is reported as state/IO failure. |
| `read_only_destination_exists`: explicit `--out` destination exists or no-replace publication race observes destination existence | read_only_publish | 4 | Destination check precedes evidence blockers; no artifact is produced and no runtime evidence collection is required. |
| `runtime_contract_missing`: unsupported platform primitive, unsupported no-replace mutation primitive, unsupported filesystem capability, unsupported state-root capability, capability blocker in inventory or plan, unsupported Pi version after exact `pi --version` parse, syntactically valid but unsupported Pi response or auxiliary schema/type | preflight, transaction_open, or verification_collect | 3 | No mutation. Inventory and plan emit deterministic blocker artifacts unless artifact emission itself fails. Capability blockers win over safe precondition blockers. |
| `safe_precondition_failed`: canonical plan whose recomputed digest differs from `approval_digest` or `--approve-digest`, stale plan, precondition drift, missing backup for restore planning, unknown user-supplied selector with otherwise healthy state, already removed, deployment/lineage changed, clean restore slot present/changed, no-replace race before mutation, safe precondition blocker in plan | preflight or transaction_open | 4 | No new mutation ledger entry when mutation has not begun. |
| `backup_precondition_failed`: backup create, hash, metadata, manifest write, or backup sync failure before the first governed slot move | transaction_open | 4 | Journal may exist, but no governed slot moved and no rollback is attempted. |
| `safe_race_rolled_back`: no-replace race after moved quarantine with safe no-replace restoration | mutation_active | 4 | Rollback evidence is journaled through a compensation terminal sequence; no normal aggregate ledger entry is created. |
| `state_or_io_failure_preterminal`: state/IO failure after first journal durability and before terminal `committed`, excluding backup precondition failures; unknown deployment inside owned aggregate; ledger inconsistency; unresolved journal; ownership corruption; ledger corruption; journal conflict; journal write/sync failure; ledger append/sync failure; receipt draft write/sync failure; filesystem I/O/sync failure after operation begins; crash after filesystem mutation before durable ledger; rollback failure; failed/unprovable compensation; unsafe restoration after quarantine movement | transaction_open, mutation_active, or ledger_committed | 5 | Before governed-slot mutation, no rollback is attempted except journaling failure evidence when possible. After mutation begins and before terminal `committed`, rollback is attempted. After normal ledger durability but before terminal `committed`, rollback plus compensating aggregate ledger is required. Failed or unprovable rollback records `recovery_required` when durable state is available. |
| `receipt_publish_pending`: crash, no-replace race, write, publish, or parent-sync failure after terminal `committed` and before durable `receipt.json` publication | terminal_committed | 5 | The normal journal chain is terminal and cannot be extended; rollback is forbidden. Preserve receipt draft, ledger, and terminal journal; inventory reports pending receipt publication/recovery-required. |
| `verification_evidence_failed`: runtime verify failure, missing runtime during requested verify, timeout, wrong winner, duplicate governed runtime item, unsupported observation outcome for verification, operator required, operator invalid, operator expired, Claude expected binding not visible, Claude removed binding visible/missing/extra/invalid, Pi malformed JSON, duplicate correlated response, missing correlated response, second correlated response, or missing required correlated fields on supported Pi `0.84.3` | verification_collect | 6 | Failed verification artifact is persisted when artifact I/O succeeds; no ledger transition, mutation, or automatic rollback occurs. |
| `verification_state_io_failure`: verification artifact write/fsync/publish failure, verified ledger append/sync failure, ready boundary failure, receipt draft failure, preterminal journal failure, or verification lock/state I/O failure | verification_state_write | 5 | A published immutable verification artifact remains non-authoritative audit evidence if the later ledger transition fails. Ownership transition occurs only if the verified ledger event is durably appended and referenced by the ready/terminal protocol. Once terminal `committed` is durable, all later receipt publication and parent-sync failures map exclusively to `receipt_publish_pending`. |
| `adapter_contract_unsupported`: unsupported Claude adapter contract version or other unsupported verification contract | verification_collect | 3 | No mutation; verification cannot prove the runtime contract. |

Claude observation failures are exit 6 except unsupported adapter contract version, which is exit 3. Pi malformed JSON, duplicate, missing, or second correlated response on supported `0.84.3` is `verification_evidence_failed` exit 6. Syntactically valid but unsupported Pi response/auxiliary schema or unsupported Pi version is `runtime_contract_missing` exit 3. Unknown user-supplied selectors with otherwise healthy state are exit 4; unknown deployments discovered inside an owned aggregate or ledger inconsistency are exit 5.

These semantics apply equally in human and JSON output modes. JSON mode still emits exactly one stdout JSON document where valid and uses the same exit code classes.

Every failure-injection test must map to exactly one row in this table.

### Command result union

`waywarden.command-result/v1` is a discriminated `kind` union. Nonapplicable fields are forbidden by schema, and redacted labels or references must not expose arbitrary full paths.

- `kind:"artifact"`: emitted by completed `inventory` or `plan` when `--out <file> --output json` is valid. `command` is `inventory` or `plan`; `status` is `success` or `blocked`; the artifact object contains schema identifier, SHA-256 digest, byte length, and a redacted label. A nested typed error object is present only when `status:"blocked"`.
- `kind:"mutation"`: emitted by completed `apply`, `uninstall`, or `restore` command phases. `status` is `verification_required`; it includes `operation_id`, optional `installation_id` or `backup_set_id` only where the command schema applies, aggregate event, and redacted receipt reference plus receipt digest.
- `kind:"verification"`: emitted by completed `verify` command phases. `status` is `verified`, `failed`, or `operator_required`; it includes `operation_id`, redacted selector, `verification_ref` and verification digest, optional receipt reference plus receipt digest, and a nested typed error object only when status is not `verified`.

With `--output json`, every primary command emits exactly one command-result on a completed command phase, or exactly one error envelope if no result exists. Human summaries go to stderr in all modes.

## Runtime adapters

Runtime adapters are evidence collectors and verifiers. They do not mutate runtime configuration, install runtimes, or persist user settings.

### Pi

Version 1 supports tested Pi version `0.84.3` only. Before RPC, the adapter runs `pi --version`, exact-parses the version as `0.84.3`, and exits 3 for any unsupported version or unparseable supported-contract output. Other versions exit 3 until an explicit fixture-backed response shape is added.

The Pi adapter uses:

```text
pi --mode rpc --no-session --offline
```

It sends one JSONL request on stdin:

```json
{"id":"skills","type":"get_commands"}
```

The adapter parses newline-delimited valid JSON frames, not JCS bytes. It requires exactly one correlated response frame with `id:"skills"`, `type:"response"`, `command:"get_commands"`, `success:true`, and `data.commands` as an array. Pi `0.84.3` auxiliary lifecycle frames without id `skills` may be ignored only by schema/type fields from reviewed fixtures; random IDs, text, timestamps, or human message content are never allowlist authority. A malformed JSON frame, duplicate correlated response, missing correlated response, or second correlated response on supported `0.84.3` is invalid runtime output exit 6. A syntactically valid but unsupported response or auxiliary schema/type is runtime contract missing exit 3.

Each governed command item requires `source:"skill"`, `name` exactly `skill:<manifest-name>`, unique name, and strict `sourceInfo.path`. The adapter first requires the lexical `sourceInfo.path` to equal exactly `<planned-runtime-target>/SKILL.md` under platform lexical path rules. Only after that lexical check passes does it resolve the path and require canonical identity equal to `<manifest-source>/SKILL.md`; `source_content_digest` is computed from the source directory parent recorded by the manifest. The adapter strips the `skill:` prefix only after validating the exact form. Missing Pi executable during requested verification exits 6. Unsupported Pi version or unsupported response shape exits 3. Waywarden must not use filesystem-only evidence to claim Pi runtime verification.

### OpenCode

ADR 0017 continues to govern OpenCode verification. Each governed `opencode debug skill` invocation sets `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` inline for that process only. Waywarden must not persist or manage this setting in shell profiles, OpenCode config, runtime roots, or user environment managers.

OpenCode stdout and stderr are captured to files in a private temporary directory outside all runtime roots. File-backed capture is required because prior evidence showed pipe capture can truncate large JSON payloads. The adapter treats timeout, nonzero exit, nonempty stderr, unreadable capture files, invalid JSON, duplicate governed names, missing governed names, and wrong discovery winners as failures. Normal non-governed OpenCode skills may appear in the full inventory, but governed names must resolve exactly as specified by the plan and manifest.

### Claude

The Claude adapter verifies filesystem discovery through the configured Claude skill root and requires explicit `waywarden.operator-observation/v1` evidence for trusted human TUI observation. Waywarden may prove link/source state directly, but Claude runtime UI behavior that lacks a trustworthy machine-readable command must be represented as a bounded operator observation rather than silently assumed.

The first `waywarden verify --installation <installation-id>` requiring Claude observation and lacking `--operator-observation` emits and persists a verification challenge. The challenge contains a random challenge value, plan digest, installation ID, transition enum `install` or `removed`, expected skill bindings, runtime version constraint, creation time, and expiration time. It is bound to the selected installation and transition and cannot be reused for another installation, transition, backup, receipt, plan, or runtime.

The human runs the trusted normal Claude TUI in normal launch mode and supplies bounded JSON via:

```text
waywarden verify --installation <installation-id> --operator-observation <path>
```

The `waywarden.operator-observation/v1` payload must include the exact challenge, plan digest, installation ID, transition enum `install` or `removed`, expected skill bindings, observer value `human`, normal launch mode, and a typed observation union. Install entries use `{"outcome":"visible"}` or `{"outcome":"not_visible"}`. Removed entries in v1 accept only `{"outcome":"not_visible"}` for every governed binding. The payload contains no free text. Waywarden validates schema, challenge binding, plan binding, installation binding, transition binding, skill binding, observer enum, launch mode, outcome union, and expiry.

Attestation schema validity and observation result are separate. A valid observation records `human_attested` regardless of outcome for audit. Install verification advances to `installed_verified` only if every expected binding is `visible` and there is no missing or extra binding. Any `not_visible`, missing binding, extra binding, or removed source winner exits 6 and leaves the aggregate in `applied_unverified`.

Removed verification for Claude, when Claude observation is required, accepts only `not_visible` for every governed binding. The normal Claude TUI cannot prove identity for any alternate visible item, so any visible governed binding, missing binding, extra binding, or unsupported outcome exits 6 and preserves `removed_unverified`. Separate machine filesystem evidence proves the removed source is no longer the winner; human observation is not alternate-winner authority.

Missing Claude runtime during requested verification, unsupported observation mode, timeout, duplicate governed names, wrong winner, unresolved path, unexpected link, ambiguous filesystem metadata, missing observation, invalid observation, expired observation, wrong transition, install observation `not_visible`, visible removed binding, missing removed binding, extra removed binding, or invalid removed outcome fails closed with exit 6 unless the failure is an unsupported adapter contract version classified as exit 3.

### Adapter tests

Runtime adapter tests use fake executables, fixture JSON, fixture stderr, controlled timeouts, and temporary homes. They must not invoke the user's real Pi, OpenCode, or Claude installations unless a separately marked native smoke test explicitly opts into a temporary home and safe runtime boundary.

## Testing strategy

The implementation plan must require tests at several layers.

### Unit, property, and fuzz tests

- canonical JSON encoding, strict parser rejection rules, envelope byte identity, embedded inventory digest, plan payload digest, JCS safe integer boundaries, and decimal-string number fields;
- schema validation and version rejection;
- stable lexical ordering for skills, roots, operations, blockers, diagnostics, evidence, receipts, and aggregate ledger records;
- deterministic inventory and plan bytes over identical evidence, including plan purity over inventory artifact plus flags and proof that planning acquires no ledger lock;
- ID generation tests proving install plans contain deterministic deployment sets and ordered unique `runtime_bindings` but no new operation, installation, backup, journal, verification, or receipt IDs, and mutators/verifiers generate cryptographically random event IDs only after approval and locks;
- physical deployment tests proving shared Pi/OpenCode `~/.agents/skills/<skill>` produces one `deployment_id`, one backup entry, one filesystem mutation, and two independently verified runtime bindings, while Claude uses a separate physical deployment;
- artifact DAG tests proving `plan_ref`, `inventory_ref`, `journal_ref`, `ready_journal_ref`, nullable `backup_set_ref`, nullable/non-null `verification_ref`, receipt draft/terminal/publication edges, and absence of `receipt_ref` from the ledger schema;
- path normalization, root containment, Unicode, case behavior, non-UTF8 rejection, and ambiguity rejection;
- output confinement for `--out`, atomic same-parent staging publication, stdout/stderr behavior, blocker artifacts, command-result discriminated union variants, nonapplicable-field rejection, and path redaction;
- state-root default calculation, `--state-root` override, independent coordination lock root calculation, and shared/exclusive ledger snapshots;
- global mutation lock, governed-slot lock key calculation, sorted slot lock ordering, selected-ledger lock ordering, and state-root bypass prevention;
- manifest parsing, checkout-bound default path, absolute `--manifest`, repository identity, source containment, mutator source drift preconditions, binary-only release archives, and release smoke against an explicit temporary fixture checkout;
- aggregate cardinality for `operation_id`, `installation_id`, `deployment_id`, ordered unique `runtime_bindings`, and `backup_set_id`;
- plan intent matching, selector cardinality, full-aggregate uninstall/restore/verify rejection of subsets, and required selectors;
- public error envelope, phase-aware exhaustive normative error table, stable named codes, precedence, and exit mapping.

### Failure-injection tests

- filesystem drift between plan and mutation;
- source content edits after install followed by authorized uninstall based on exact governed slot plus managed object identity, excluding source digest/resolved content;
- no-replace race before mutation;
- no-replace race after quarantine movement with safe restoration;
- occupied governed slot during rollback producing `recovery_required`;
- backup write failure, backup hash mismatch, backup metadata matrix failure, and timestamp round-trip failure;
- rename/no-replace primitive failure and unsupported primitive mapping to exit 3;
- object sync and parent sync failure;
- scalar and in-place cleanup races for files, symlinks/reparse links, empty directories, and nonempty trees, including new, missing, mismatched, content-mutated, metadata-mutated, link-swapped, and nonempty quarantine entries;
- apply, uninstall, and restore inverse rollback protocols including typed-missing no-op rollback and occupied governed-slot recovery;
- permission denial;
- journal write/sync failure;
- ledger append/sync failure and partial NDJSON append rejection;
- receipt draft write/sync failure, terminal `committed` crash, receipt publication no-replace race, and receipt parent-sync failure;
- process interruption after every journal, ledger, ready, receipt-draft, terminal, receipt-publication, cleanup, and parent-sync boundary;
- rollback success with compensating aggregate event;
- rollback failure and crash after filesystem mutation before ledger durability;
- concurrent mutator attempts, verification write contention, sorted multi-slot lock acquisition, and state-root bypass attempts;
- stale or contradictory journal detection;
- mixed per-deployment state outside active locked journal;
- recovery-required classification for every unprovable compensation.

### Native platform tests

Native Ubuntu, macOS, and Windows tests cover files, directories, symlinks, directory links, junctions, reparse points, Unicode names, non-UTF8 blockers where representable by the platform, case collisions, locks, binary payloads, same-filesystem temporary replacement, no-replace primitives, parent sync behavior, typed-missing backup/restore, exact metadata masks, and unsupported capability reporting. Windows tests must distinguish ordinary file symlinks, ordinary directory symlinks, junctions, and other reparse behavior, and must prove closed attribute masks and 100ns LastWriteTime preservation. Unix tests must prove closed mode/flag masks, owner/group constraints, xattr/ACL/resource-fork blockers, and symlink lexical target preservation.

### Runtime and contract tests

- Pi `0.84.3` fixture frames: exact `pi --version` parse, valid response, unsupported version exit 3, malformed JSON exit 6, unknown unsupported schema/type exit 3, second correlated response exit 6, missing correlated response exit 6, missing `sourceInfo.path`, wrong lexical `sourceInfo.path`, wrong resolved `SKILL.md` identity, wrong `source`, wrong name prefix, duplicate name, wrong source identity, and missing executable verify exit 6;
- OpenCode fixture capture failures, stderr fatality, duplicate/wrong winners, and ADR 0017 environment isolation;
- Claude install observation requiring every governed binding `visible`, valid `human_attested` with `not_visible` that does not advance install verification, removed observation accepting only `not_visible`, visible removed binding, missing binding, extra binding, wrong transition, expired challenge, wrong challenge, unsupported adapter contract version exit 3, and invalid schema;
- verify DAG tests proving verification artifact publication before ledger transition, non-null `verification_ref` on verified events, null `verification_ref` on mutator events, evidence failure exit 6 with failed artifact and no ledger transition, state/write failures exit 5, unsupported contracts exit 3, idempotent repeated verify, and immutable artifact audit behavior after ledger transition failure;
- command output examples conform to JSON schemas, including all `waywarden.command-result/v1` union variants;
- documentation-command-schema contract tests prove documented command examples, flags, schemas, exits, status names, asset names, and lifecycle names stay synchronized;
- failure-injection tests map every scenario to the public error table.

### Repository quality tests

- all existing Python suites continue to pass;
- Go tests run with race detection on supported native runners;
- `go vet` passes;
- `golangci-lint` v2.13.1 passes;
- `govulncheck` v1.1.4 passes;
- `pkcov` enforces at least 85% coverage for the Go distribution code;
- CodeQL and gitleaks pass;
- Rootline validates ADR records strictly when the governance gate amends ADR 0019.

All automated tests that exercise lifecycle behavior use temporary homes, temporary runtime roots, fake runtime executables, temporary state roots, and temporary coordination lock roots. The current checkout's real home directory is never mutated by tests.

## CI and release

Waywarden reuses only the Crossbeam `go-ci.yml` light profile as a baseline. The implementation plan must reference `pablontiv/crossbeam/.github/workflows/go-ci.yml` pinned to inspected commit `9feddefac77e2bd8dde05f5e493031f965f791c5`, profile `light`, exact `go-version: 1.26.0`, and coverage threshold `85`, with nearby comment `v2 reviewed 2026-08-28`. The inspected Crossbeam full and release workflows contain floating `govulncheck`, floating Go, floating GoReleaser, and best-effort checksum-only attestation; therefore they are not release authority for Waywarden.

Project-owned pinned jobs must add race detection, `go vet`, `golangci-lint` v2.13.1, `govulncheck` v1.1.4, CodeQL, gitleaks, native OS tests, release builds, attestations, and smoke tests. The implementation must pin `actions/setup-go` and every release-critical action by SHA. GoReleaser version is exactly v2.18.0 and Go version is exactly 1.26.0.

The final accepted ADR 0019 amendment must clarify that releases use a Crossbeam CI baseline plus project-owned release and GoReleaser jobs. It must not say Waywarden releases are performed by Crossbeam `go-release`.

Required release behavior:

- GoReleaser builds with `CGO_ENABLED=0`;
- exactly six release archives are produced with these literal names, where `VERSION` excludes a leading `v`:
  - `waywarden_${VERSION}_linux_amd64.tar.gz`
  - `waywarden_${VERSION}_linux_arm64.tar.gz`
  - `waywarden_${VERSION}_darwin_amd64.tar.gz`
  - `waywarden_${VERSION}_darwin_arm64.tar.gz`
  - `waywarden_${VERSION}_windows_amd64.zip`
  - `waywarden_${VERSION}_windows_arm64.zip`
- `checksums.txt` covers every archive digest;
- mandatory GitHub provenance attests each of the six archives and `checksums.txt` with no `continue-on-error`;
- ldflags inject version, commit, date, and dirty-state metadata for `waywarden --version`;
- build date comes from `SOURCE_DATE_EPOCH`, set to the release commit timestamp;
- clean and commit metadata are deterministic;
- no GPG signing in version 1;
- no Homebrew formula in version 1;
- no auto-update in version 1.

Native runtime smoke is required for linux/amd64, darwin/arm64, and windows/amd64. Cross-architecture linux/arm64, darwin/amd64, and windows/arm64 receive archive and checksum validation plus `go version -m` and archive-format inspection. Those cross-architecture binaries execute only if a native hosted runner exists for that architecture; absence of such a runner must not be described as native coverage.

Post-release native smoke tests download the release asset, verify the published checksum, run `waywarden --version`, create an explicit temporary fixture checkout containing `distribution/manifest.json` and governed source paths, and run inventory against that absolute manifest and temporary runtime roots. Release binaries alone are not a skills bundle or package manager. Smoke tests must not mutate the real user home.

## Acceptance criteria

Issue #10 is accepted only when all of the following are true:

1. The governance gate has marked this specification Approved, amended ADR 0019 to normatively reference this specification, changed both ADR 0019 frontmatter decision metadata and body from `Go 1.26 o posterior` to exact `Go 1.26.0`, corrected ADR 0019 temporal and Crossbeam release wording, updated the prior ownership specification to mark TypeScript/ADR 0016 implementation sections superseded while preserving evidence, validated/accepted the ADR amendment, and updated issue #10 from TypeScript/ADR 0016 framing to Waywarden Go/ADR 0019 framing.
2. The implementation follows ADR 0019 as amended by the governance gate and preserves ADR 0017 OpenCode verification isolation.
3. Every issue criterion is mapped in the implementation plan and final pull request evidence.
4. The repository contains `waywarden` Go source under the approved layout or a reviewed equivalent that preserves the same package boundaries.
5. `distribution/manifest.json` exists, validates as `waywarden.manifest/v1`, and lists only repository-owned skills.
6. Inventory and plan are read-only except explicit confined artifact emission, write no state automatically, and are byte-deterministic for unchanged evidence; `plan` is a pure function of the inventory artifact plus flags and never rereads live ledger/state.
7. Plan embeds the complete canonical inventory object in `payload.inventory`, stores `payload.inventory_digest`, and mutators require the embedded inventory and plan envelope checks before mutation.
8. Plan approval uses the exact `SHA-256` digest of canonical RFC 8785 bytes of the plan envelope's `payload` member only, and the complete envelope is byte-identical to canonical reserialization.
9. `plan` requires `--inventory`; uninstall planning requires exactly one installation selector; restore planning requires exactly one backup set selector; verify requires exactly one of receipt, installation, or backup.
10. Mutating commands reject mismatched intents before mutation, acquire locks before event ID generation, generate install `operation_id`, `installation_id`, and `backup_set_id` outside the approved payload, and copy canonical embedded inventory bytes plus exact plan envelope bytes into the run directory.
11. Aggregate cardinality tests prove one approved install mutation creates one `installation_id`, one `backup_set_id`, and one deployment entry per physical slot/source pair after approval and locks; shared Pi/OpenCode `~/.agents/skills/<skill>` yields one deployment with two runtime bindings, one backup entry, and one filesystem mutation; Claude physical paths are separate deployments; subset operations fail input validation.
12. Apply records one aggregate `applied_unverified` event after successful durable mutation, then completes cleanup, `ready_to_commit`, receipt draft, terminal `committed`, no-replace receipt publication, and exits 0 with `verification_required`; ledger records reference plan/inventory/journal/backup with null `verification_ref` but never receipt.
13. Verify publishes immutable `waywarden.verification/v1` evidence before appending aggregate `installed_verified`, `removed_verified`, or `restored_verified`; verified events require non-null `verification_ref`; independent verification must succeed for every deployment and runtime binding; evidence failure exits 6 and preserves the unverified aggregate event without a ledger transition.
14. Uninstall is allowed from `applied_unverified` or `installed_verified`, requires Waywarden-produced ledger evidence plus exact governed slot and managed object before move, compares managed object only after quarantine move, ignores `source_content_digest` and resolved content as delete authority, and records one aggregate `removed_unverified` event.
15. Restore selects a complete verified backup set from the same lineage, requires aggregate `removed_verified` and every governed slot absent, records one aggregate `restored_unverified` event, handles `typed_missing` entries as absence-only no-ops, and returns restored objects to user ownership after verify.
16. Complete temporary lifecycle tests pass with the aggregate sequence: `inventory -> plan install -> apply -> verify installation -> inventory -> plan uninstall -> uninstall -> verify installation -> inventory -> plan restore -> restore -> verify backup`.
17. Backup set verification, nullable DAG references including `verification_ref`, typed-missing restore, rollback, compensating events, interrupted-journal recovery, terminal receipt crash/recovery, ledger corruption, partial NDJSON append rejection, and `recovery_required` behavior are covered by tests after every journal, cleanup, ledger, ready, receipt-draft, terminal, receipt-publication, and receipt sync point.
18. Platform filesystem tests pass natively on Ubuntu, macOS, and Windows without mutating real homes and prove no-replace primitives, quarantine/staging behavior, TOCTOU races, rollback no-overwrite behavior, parent sync, and support/blocking for missing, regular file, symlink, empty directory, and nonempty directory targets.
19. Metadata matrix tests cover UTF-8 names, non-UTF8 blockers, closed POSIX file modes, directory mode mask exactly `01777` with sticky as the only allowed bit outside `0777`, inode/st_flags masks, owner/group/SID constraints, ACL/xattr/resource fork blockers, closed Windows DACL/attribute masks, LastWriteTime 100ns preservation, excluded timestamp fields, hardlink blockers, sparse blockers, mount/device/FIFO/socket/reparse blockers, and backup tree digest content.
20. Runtime adapters fail closed for missing runtime during requested verify, timeout, duplicate governed name, wrong winner, invalid runtime output, nonzero exit, unsupported observation mode, missing machine-readable contract, and unsupported Pi version/shape.
21. Claude verification records valid `human_attested` observations regardless of outcome for audit, final `installed_verified` requires every expected binding `visible` and no missing or extra binding, and removed verification accepts only `not_visible` for every governed binding with no alternate-winner acceptance.
22. Pi verification supports only exact `pi --version` parse `0.84.3`, uses `pi --mode rpc --no-session --offline` with the one JSONL `get_commands` request, parses newline-delimited JSON frames, enforces the exact correlated response shape, requires lexical `sourceInfo.path == <planned-runtime-target>/SKILL.md` before resolved `<manifest-source>/SKILL.md` identity, and never claims runtime verification from filesystem-only evidence.
23. Existing Python suites continue to pass.
24. Go race, vet, `golangci-lint` v2.13.1, `govulncheck` v1.1.4, CodeQL, gitleaks, native OS tests, and at least 85% `pkcov` coverage pass.
25. Rootline strict ADR validation passes for the repository's ADR set after the ADR 0019 governance amendment.
26. Documentation-command-schema contract tests pass for command examples, contracts, status names, state graph, deployment/runtime-binding cardinality, artifact DAG refs/nullability, terminal receipt protocol, verification DAG, phase-aware error table with exactly one row per injection, command-result union schemas, output confinement and atomic publication, release assets, and acceptance sequence.
27. CI uses Crossbeam `go-ci.yml` only in profile `light` pinned to `9feddefac77e2bd8dde05f5e493031f965f791c5` with exact `go-version: 1.26.0` and coverage threshold `85`; project-owned pinned jobs provide release, GoReleaser v2.18.0, attestations, security, and smokes.
28. Releases produce exactly the six literal binary-only archives, `checksums.txt`, and mandatory GitHub provenance for each archive and `checksums.txt` with no best-effort attestation path; release archives do not include skills or manifests and release smoke uses an explicit temporary fixture checkout.
29. Native smoke coverage is reported only for linux/amd64, darwin/arm64, and windows/amd64 unless additional native hosted runners execute the cross-architecture binaries.
30. Independent review confirms no implementation mutates the current checkout's real home during tests.
31. The pull request discloses governing ADRs, ADR 0019's supersession of ADR 0016, ADR 0017's continuing OpenCode authority, and any unresolved conflicts.

## Failure semantics

Waywarden fails closed. A command must prefer a stable, explainable failure over best-effort mutation whenever authority, path identity, runtime evidence, schema validity, plan freshness, backup integrity, lock state, ledger integrity, journal integrity, or verification is uncertain.

Important failure rules:

- noncanonical required input/artifact before approval validation: exit 2;
- canonical plan whose recomputed digest differs from the plan field or approve argument: exit 4;
- mismatched intent or selector mismatch: exit 2;
- plan emits deterministic artifact with blockers; capability blocker exits 3, safe precondition blocker exits 4, and capability wins when both exist;
- inventory emits evidence and exits 3 for capability blockers; schema/input failures exit 2; inventory evidence blockers do not produce exit 4 except output preconditions such as existing explicit destination;
- clean restore slot present or changed: exit 4;
- unresolved journal, unresolved ownership, unknown deployment inside an owned aggregate, ledger inconsistency, lock conflict/timeout, journal write/sync failure, ledger/receipt failure, and filesystem I/O/sync after journal durability except backup precondition failures: exit 5; unknown user-supplied selector with otherwise healthy state: exit 4;
- before any governed-slot mutation no rollback is attempted; after pre-terminal mutation rollback is attempted; after terminal `committed` rollback is forbidden;
- successful rollback persists `rolled_back` or a compensating aggregate event, but the initiating command still exits 5 for infrastructure failure or 4 for safe precondition race as defined in the error table;
- failed or unprovable rollback records `recovery_required` and exits 5;
- backup create/hash/metadata/manifest/sync failure before the first governed slot move: exit 4 even when the journal is already durable;
- no-replace race/precondition drift before mutation: exit 4;
- race after moved quarantine with safe restoration: exit 4;
- race after moved quarantine with unsafe restoration: exit 5;
- requested runtime verification failures, including missing executable during requested verify: exit 6;
- Pi malformed JSON, duplicate/missing/second correlated response on supported `0.84.3`: exit 6; syntactically valid unsupported Pi schema/type or unsupported version: exit 3;
- Claude invalid/missing/expired/wrong transition/wrong outcome: exit 6; unsupported Claude adapter contract version only: exit 3;
- unsupported primitive, unsupported runtime version, or unsupported response shape as classified by the phase table: exit 3;
- textual name/path/content match, matching original preimage, or operator memory without ledger authority: failure, never delete authority.

These semantics apply equally in human and JSON output modes subject to the artifact stdout restrictions. Every failure-injection test must assert the exact exit class.

## Governance notes

ADR 0019 is the architecture decision intended to govern implementing the distributor in Go after the approval gate amends it to reference this specification, changes both frontmatter decision metadata and body from `Go 1.26 o posterior` to exact `Go 1.26.0`, and corrects its temporal and Crossbeam release wording. ADR 0016's ownership classification and lifecycle evidence remain preserved through ADR 0019 and the prior ownership evidence specification, but its TypeScript implementation framing is superseded only after the gate updates that prior spec. ADR 0017 remains the authority for OpenCode verification isolation.

This design intentionally creates no Go implementation, no manifest, no CI workflow, no release configuration, and no ADR changes. It is the proposed specification pending human approval.
