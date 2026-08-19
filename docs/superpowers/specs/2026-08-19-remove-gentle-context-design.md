# Remove Gentle context safely across supported clients

`remove-gentle-context` is an independent Agent Skill that inventories, backs up, removes, and verifies active Gentle AI context without modifying or depending on Gentle AI. It supports macOS, Linux, and Windows, preserves infrastructure and history by default, and refuses destructive work whose ownership or preimage cannot be proven.

## Decision summary

| Topic | Decision |
|---|---|
| Repository | Public `pablontiv/skills`, locally developed outside the Gentle AI repository |
| Skill | `skills/remove-gentle-context/` |
| Runtime | Python 3.11+, standard library only |
| Architecture | Hybrid engine: four programmatic core adapters plus declarative adapters |
| Core clients | Claude, Codex/ChatGPT, OpenCode, Pi |
| Declarative clients | Gemini, Kimi, Hermes, VS Code Copilot, and future simple clients |
| Default scope | Active context, active runtime state, generated artifacts, and broken registrations |
| Preserved | MCP, Engram, packages, binaries, source, backups, `.git/gentle-ai`, messages, and archived sessions |
| Approval | Exact SHA-256 digest of a canonical plan |
| Repository policy | MIT license; GitHub Pull Requests disabled; Issues enabled |

## Goals

1. Find active Gentle-owned context without broad text-match deletion.
2. Explain every proposed mutation with ownership evidence.
3. Produce a machine-readable inventory and immutable, digest-bound plan.
4. Back up every governed preimage before mutation.
5. Apply changes atomically or roll them back.
6. Sanitize live runtime selections and restart affected clients when required.
7. Prove that active residue is gone and preserved data is unchanged.
8. Behave consistently on macOS, Linux, and Windows.
9. Let future clients use declarative adapters when their operations are simple and safe.

## Non-goals

- Uninstalling Gentle AI, Gentle Pi, Engram, CodeGraph, or other packages.
- Deleting binaries, source repositories, caches, memories, backups, or `.git/gentle-ai` authority.
- Rewriting archived conversations or historical prompt snapshots by default.
- Editing the Gentle AI repository or adding capabilities to its binary.
- Deleting files based only on names or textual references.
- Offering unrestricted declarative mutation of TOML, SQLite, or arbitrary text.

## Repository layout

```text
skills/
├── README.md
├── LICENSE
├── AGENTS.md
├── docs/
│   └── superpowers/specs/
└── skills/
    └── remove-gentle-context/
        ├── SKILL.md
        ├── scripts/
        │   └── cleanup.py
        ├── helper/
        │   ├── engine.py
        │   ├── models.py
        │   ├── paths.py
        │   ├── transaction.py
        │   └── clients/
        │       ├── claude.py
        │       ├── codex.py
        │       ├── opencode.py
        │       └── pi.py
        ├── adapters/
        │   ├── gemini.json
        │   ├── kimi.json
        │   ├── hermes.json
        │   └── vscode-copilot.json
        ├── references/
        │   └── contracts.md
        └── tests/
            ├── fixtures/
            └── test_*.py
```

The installed skill remains self-contained. `scripts/cleanup.py` is the sole executable entrypoint and imports only sibling modules and the Python standard library.

## User flow

The skill leads the user through five explicit phases:

```bash
python scripts/cleanup.py inventory --output inventory.json
python scripts/cleanup.py plan --inventory inventory.json --output plan.json
python scripts/cleanup.py apply --plan plan.json --approve sha256:<digest>
python scripts/cleanup.py verify --receipt receipt.json
python scripts/cleanup.py restore --manifest manifest.json --approve sha256:<manifest-digest>
```

### Inventory

`inventory` is read-only. It resolves platform paths, invokes each adapter, records candidates, and reports unsupported or ambiguous surfaces. It never creates a deletion plan implicitly.

### Plan

`plan` is read-only. It selects only proven, in-scope candidates, captures preimage hashes and lifecycle requirements, emits canonical JSON, and prints its SHA-256 digest. Ambiguous findings remain visible but blocked.

### Apply

`apply` requires the exact digest. It repeats all safety checks, creates and verifies a backup, executes the transaction, restarts approved clients, and writes a receipt. Any mismatch before the first mutation aborts the entire operation.

### Verify

`verify` independently reads the receipt and live filesystem. It checks active residue, syntax, preserved values, packages, histories, MCP equality, and restart outcomes. It does not trust the apply process's success claim.

### Restore

`restore` validates a backup manifest, allowed roots, current state, and the exact canonical manifest digest supplied through `--approve` before restoring. It never trusts paths declared only by the manifest.

## Inventory model

Every candidate has a stable identifier and the following fields:

| Field | Meaning |
|---|---|
| `candidate_id` | SHA-256-derived stable identifier |
| `client` | Adapter that discovered the candidate |
| `path` | Absolute native path on the inventoried machine |
| `artifact_class` | Context, runtime, generated, registration, historical, infrastructure, or ambiguous |
| `evidence` | Structured ownership and activation evidence |
| `ownership` | `proven`, `ambiguous`, or `preserved` |
| `proposed_action` | Typed action or `report_only` |
| `preimage` | File type, mode, size, and SHA-256 when applicable |
| `dependencies` | Other candidates or lifecycle steps required for safe mutation |
| `reason` | Human-readable classification explanation |

### Artifact classes

- `active-source`: prompts, skills, agents, hooks, profiles, defaults, or configuration loaded by a client.
- `runtime-state`: live or resumable client state that selects Gentle behavior.
- `generated-artifact`: generated indexes and registries that can be recreated.
- `broken-registration`: an active configuration entry pointing to a missing Gentle-owned artifact.
- `historical`: archived sessions, messages, logs, receipts, and stored prompt snapshots.
- `preserved-infrastructure`: MCP, Engram, packages, binaries, source, backups, and repository authority.
- `ambiguous`: a hit without sufficient ownership or activation proof.

### Ownership rules

A textual match is evidence for review, not deletion authority. A mutation requires one or more strong signals whose combination is defined by the owning adapter:

- exact managed path;
- balanced Gentle marker pair;
- recognized content fingerprint;
- active reference from a structured configuration;
- managed-state provenance;
- linked profile and selector, such as `permissions.gentle-dev` plus `default_permissions`;
- generated-file signature plus an approved generated-artifact location.

When evidence conflicts, `ambiguous` wins and the candidate is blocked.

## Adapter architecture

### Core adapters

Claude, Codex, OpenCode, and Pi use Python adapters because their cleanup requires structured semantics or lifecycle coordination.

Each core adapter implements:

```text
inventory(context) -> candidates
plan(candidate, context) -> typed operations
preflight(operations, context) -> result
verify(receipt, context) -> checks
```

Core adapters may define narrowly scoped parsers and serializers. They may not issue broad recursive deletions.

### Declarative adapters

Declarative adapters are versioned JSON documents. They can:

- resolve paths from approved platform roots;
- match exact files or directories;
- identify balanced marker blocks;
- inspect simple JSON keys and arrays;
- remove an exact JSON key, array value, file, or empty directory;
- declare preserved subtrees and history exclusions;
- define postconditions.

They cannot directly mutate:

- TOML;
- SQLite or other databases;
- arbitrary text ranges without balanced markers;
- runtime state requiring client shutdown;
- symlinks, junctions, or reparse points;
- candidates with ambiguous ownership.

A client needing those capabilities must be promoted to a core adapter.

## Core client behavior

### Claude

The adapter inventories managed marker blocks, skills, agents, commands, hooks, output styles, and Gentle-owned visual artifacts. Usage counters, project histories, third-party marketplaces, Engram, and unrelated skills remain preserved. Pi owns generated Gentle Pi skill registries so only one adapter can authorize each registry mutation.

### Codex and ChatGPT

The adapter treats the permission profile and its selector as one dependency group. It removes all `permissions.gentle-dev` TOML tables, including separated nested tables, and removes the matching default selector. It sanitizes active runtime profile objects in place without deleting conversations or messages. Recovery files are sanitized to prevent resurrection. Archived sessions remain report-only.

When ChatGPT/Codex is running and runtime mutation is planned, the adapter must stop it gracefully before backup revalidation and restart it afterward. If graceful lifecycle control is unavailable, preflight fails before mutation.

### OpenCode

The adapter inventories agents, prompts, commands, skills, default-agent values, local Gentle plugins, and TUI registrations. A missing plugin file with a surviving registration is a `broken-registration`. Third-party packages remain installed unless a future explicit package-removal scope is introduced.

### Pi

The adapter removes active Gentle Pi registration while preserving its installed npm package. It inventories generated skill registries and distinguishes already-running sessions that may regenerate them. Verification requires the package to remain disabled and governed registries to remain absent after affected sessions restart.

## Platform path resolution

The helper never embeds a personal home path. It derives locations from:

- `Path.home()` and explicit test overrides;
- XDG variables on Linux and where clients honor them;
- `APPDATA` and `LOCALAPPDATA` on Windows;
- macOS Application Support conventions;
- client-specific environment variables documented by the adapter.

Inventory records the resolved roots. Apply rejects a plan created for a different home, operating system, or path layout.

Tests receive an explicit temporary home and platform profile. Production apply rejects test-only path overrides unless the plan was created with the same declared test context.

## Plan and approval contract

The plan is canonical UTF-8 JSON with sorted keys and normalized separators. Its digest covers:

- schema version;
- inventory digest;
- platform and resolved roots;
- every preimage hash;
- ordered operations;
- lifecycle actions;
- preservation assertions;
- expected postconditions.

Approval is content-bound:

```text
--approve sha256:<exact-plan-digest>
```

A changed plan, changed preimage, or changed lifecycle requirement invalidates approval.

## Transaction safety

### Preflight

Before the first mutation, the engine:

1. validates schema versions and plan digest;
2. validates every path against adapter-owned roots;
3. rejects unexpected symlinks, junctions, and Windows reparse points;
4. recomputes every preimage hash;
5. confirms parsers accept all structured files;
6. confirms required clients can stop and restart;
7. confirms the backup destination is outside governed roots;
8. resolves every rollback target independently of manifest-provided roots.

### Backup

Backups use the operating system's user-state location:

- XDG state directory on Linux;
- Application Support on macOS;
- local application data on Windows.

Each backup contains a manifest, root-relative payload, file metadata, and hashes. The engine verifies payload hashes before mutation.

### Mutation

Structured files are written to a temporary file in the same directory, flushed, permissioned, parsed, and atomically replaced. Deletes accept only exact regular files or adapter-approved empty directories. Operations append to a journal before advancing.

### Failure and rollback

A preflight failure mutates nothing. A failure after mutation triggers reverse-order rollback. The receipt distinguishes:

- `completed`;
- `rolled_back`;
- `manual_recovery_required`.

Manual recovery includes exact paths and verified backup locations. The engine never reports success when rollback or verification is incomplete.

## Client lifecycle

Lifecycle operations are part of the approved plan. An adapter records whether a client was running during inventory and rechecks at apply time.

- macOS uses application bundle identity and graceful application quit/open mechanisms.
- Linux uses discovered process and desktop-entry metadata with graceful termination.
- Windows uses discovered process and executable metadata with non-forced termination first.

Forced termination is not part of version 1. If graceful shutdown cannot be confirmed, apply aborts before mutation and instructs the user to close the client manually.

Only clients stopped by the transaction are restarted automatically.

## Preservation contract

The following remain unchanged by default:

- MCP server definitions and tool policy;
- Engram configuration, stores, memories, and packages;
- installed packages and package-manager declarations;
- Gentle AI and Gentle Pi binaries and source;
- CodeGraph binaries, MCP configuration, and indexes;
- backups and cleanup receipts;
- `.git/gentle-ai` repository authority;
- conversation messages and archived sessions;
- unrelated skills, agents, hooks, plugins, and themes.

For structured files containing MCP, the receipt stores a normalized before value and verification requires deep equality afterward.

## Verification contract

Verification runs from live state and checks:

1. every planned postcondition;
2. absence of active Gentle selectors, profiles, markers, registrations, and governed files;
3. JSON and TOML parsing;
4. MCP deep equality;
5. package and binary presence;
6. history and message preservation;
7. client restart state;
8. absence of regenerated governed artifacts;
9. expected ambiguity and report-only findings remain untouched.

The result is a versioned JSON artifact with a terminal `passed` or `failed` status. Any failed required check makes the command exit nonzero.

## Error handling

Errors use stable codes grouped by phase:

- `inventory_*` for unreadable or unsupported surfaces;
- `plan_*` for ambiguous or unsatisfied dependencies;
- `preflight_*` for drift, path, parser, backup, or lifecycle failures;
- `apply_*` for mutation failures;
- `rollback_*` for incomplete recovery;
- `verify_*` for failed postconditions.

Human output explains the next safe action. Machine output never hides blocked candidates or partial recovery.

## Testing strategy

Tests use `unittest`, temporary homes, and no network access. Linux CI covers Python 3.11, 3.12, 3.13, and 3.14. macOS and Windows CI cover the minimum supported version, 3.11, and the latest supported version, 3.14.

### Regression fixtures

Fixtures reproduce:

- a Codex profile split across noncontiguous TOML tables;
- active runtime profiles alongside `null` profiles;
- current, backup, and temporary recovery state;
- an OpenCode registration whose plugin file is missing;
- a surviving Gentle-owned Claude theme;
- regenerated `.atl/skill-registry.md` files;
- active Pi registration with an installed package that must remain;
- preserved MCP sections in each mixed configuration;
- archived sessions containing historical Gentle text.

### Required test groups

- inventory classification and ownership;
- canonical plan digest and approval binding;
- preimage drift rejection;
- JSON and TOML structural mutation;
- atomic-write failure and rollback;
- symlink, junction, reparse-point, and traversal rejection;
- lifecycle preflight and restart decisions;
- MCP and package preservation;
- history preservation;
- idempotent apply and verify;
- declarative adapter schema and capability restrictions;
- golden inventory, plan, receipt, and verification artifacts.

No test may read or mutate the developer's real home. A guard fails the suite if a target resolves outside the temporary test root.

## Skill behavior

`SKILL.md` must:

1. explain the preserved scope before inventory;
2. run inventory and summarize active, historical, preserved, ambiguous, and blocked counts;
3. show the exact plan and lifecycle effects;
4. ask the user to approve the displayed digest;
5. pass only that digest to apply;
6. run independent verification;
7. report the rollback path and any required client restart;
8. never improvise deletion commands outside the helper.

The skill treats a missing Python 3.11 runtime as a preflight blocker and provides installation guidance without installing software automatically.

## Distribution and governance

The repository is public and MIT-licensed. Each skill is self-contained under `skills/<name>/` for compatibility with Agent Skills consumers and manual copying.

GitHub configuration:

- Pull Requests disabled;
- Issues enabled;
- default branch `main`;
- GitHub Actions enabled for the test matrix;
- maintainer-only direct delivery.

The repository README lists stable skills and their prerequisites. A skill is not listed as stable until its full platform matrix passes.

## Acceptance criteria

- `remove-gentle-context` can inventory, plan, apply, verify, and restore in temporary macOS, Linux, and Windows homes.
- Claude, Codex, OpenCode, and Pi use tested programmatic adapters.
- Gemini, Kimi, Hermes, and VS Code Copilot load validated declarative adapters.
- No destructive action occurs without exact digest approval and verified backup.
- The known `gentle-dev`, OpenCode TUI, Claude theme, and regenerated-registry incidents have passing regression tests.
- Runtime selections are sanitized without deleting messages; archived sessions remain unchanged.
- MCP, Engram, packages, binaries, source, backups, and `.git/gentle-ai` remain unchanged.
- Ambiguous ownership always blocks mutation.
- Apply is idempotent and verification is independent.
- Repository CI passes on macOS, Linux, and Windows.
- GitHub Pull Requests are disabled for `pablontiv/skills`.
