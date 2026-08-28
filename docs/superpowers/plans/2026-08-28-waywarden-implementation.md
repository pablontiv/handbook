# Waywarden Governed Skill Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Goal

Implement `waywarden`, a governed Go CLI that inventories repository-owned global skills, plans deterministic physical deployments, applies approved aggregate installs, verifies Pi/OpenCode/Claude runtime discovery, uninstalls only complete Waywarden-managed aggregates, and restores only complete verified backup sets. Core commands must be deterministic, auditable, cross-platform, and safe across Linux, macOS, and Windows.

## Architecture

- `cmd/waywarden`: Cobra root, exactly six primary subcommands, `--version`, public output routing, and exit mapping.
- `internal/distribution/contracts`: sole authority for canonical JSON, digests, schemas, schema IDs, public result/error contracts, selectors, and all persisted contract structs.
- `internal/distribution/manifest`, `inventory`, and `planning`: read-only manifest loading, observation, physical deployment dedupe, pure plan creation, and digest-bound approval.
- `internal/distribution/state`: state roots, owner-private lock roots, hash-chained aggregate ledger, operation journals, receipts, run artifacts, ID allocation, and recovery classification.
- `internal/distribution/filesystem`: memory fake first, then native adapters with handle/descriptor-bound observation, locks, no-replace publication, staging, quarantine, parent sync, hashing, and exact cleanup.
- `internal/distribution/backup`, `apply`, `uninstall`, `restore`, `verify`, and `runtimes`: backup set creation, mutation engines, verification engine, Pi/OpenCode machine adapters, and Claude bounded operator attestation.

## Tech Stack

- Go toolchain and module directive: `go1.26.0` / `go 1.26.0`.
- Cobra: `github.com/spf13/cobra v1.10.2`.
- Picokit: `github.com/pablontiv/picokit v1.0.0`, selective usage only.
- Platform syscalls: `golang.org/x/sys v0.47.0`, pinned from the reviewed peer-module compatibility evidence; it is not authority for JSON, digests, transactions, backups, or release provenance.
- Release: GoReleaser v2.18.0, six binary-only archives, mandatory checksums and build provenance.

## Spec and ADR Authority

- Normative spec: `docs/superpowers/specs/2026-08-28-waywarden-skill-distribution-design.md`.
- ADR 0020 adopts the spec, supersedes ADR 0019 for implementation contracts, and keeps ADR 0017 as OpenCode verification isolation authority.
- ADR 0016 and the earlier ownership spec retain ownership, topology, and lifecycle evidence only where not superseded by ADR 0020.

## Global Constraints

- The only primary subcommands are `inventory`, `plan`, `apply`, `verify`, `uninstall`, and `restore`; version is `waywarden --version`, not a subcommand.
- Schema IDs are exact literals with hyphens: `waywarden.manifest/v1`, `waywarden.inventory/v1`, `waywarden.plan/v1`, `waywarden.backup-manifest/v1`, `waywarden.ownership/v1`, `waywarden.receipt/v1`, `waywarden.verification/v1`, `waywarden.operator-observation/v1`, `waywarden.command-result/v1`, and `waywarden.error/v1`. The approved spec does not define a separate journal schema ID; journal entries are canonical contract values inside state.
- Runtime topology: five governed skills produce fifteen runtime bindings and ten physical deployments. Pi and OpenCode share five `.agents/skills/<skill>` physical deployments; Claude has five `.claude/skills/<skill>` physical deployments. Desired runtime roots never target `.pi/agent/skills` or `.config/opencode/skills`.
- Read-only commands do not generate event IDs, acquire governed-slot locks, mutate state, or inspect live state after planning consumes an inventory artifact.
- Mutators generate IDs only after approval digest validation and normative locks.
- Ledger records never contain `receipt_ref`; receipts are audit evidence in an acyclic DAG.
- Restore is owned by the restore engine. Backup code may stage and verify backup payload semantics, but it must not publish restored objects into governed slots.
- Each task must compile conceptually at completion, must include a focused test, a relevant full test, and a conventional commit command for future implementation execution.
- Implementation execution must create no repository implementation files outside the files listed in the active task.
- Waywarden v1 is checkout-bound. Release archives contain only the binary; they never bundle skills or the manifest.
- Existing Python helpers remain autonomous and are not migrated into, wrapped by, or made dependent on the Go binary.
- Runtime deployments are direct symlinks only. There is no copy fallback, implicit resume, partial aggregate operation, auto-update, Homebrew formula, or GPG signing in v1.
- Every automated filesystem or runtime test uses temporary `HOME`, `XDG_STATE_HOME`, `LOCALAPPDATA`, state root, lock root, runtime roots, and fake executables; tests never mutate the real user home.

## Task 1: Go module, Cobra root, six command stubs, and version flag foundation

**File scope**

New files:

- `go.mod`
- `go.sum`
- `.coverage-floors.toml`
- `cmd/waywarden/main.go`
- `cmd/waywarden/root.go`
- `cmd/waywarden/root_test.go`
- `cmd/waywarden/version_test.go`
- `internal/distribution/cli/exit.go`
- `internal/distribution/cli/output.go`
- `internal/distribution/cli/output_test.go`

**Contract slice**

- Initialize module with Go `1.26.0`, Cobra `v1.10.2`, Picokit `v1.0.0`, and `golang.org/x/sys v0.47.0`; add `tool github.com/pablontiv/picokit/cmd/pkcov` and `.coverage-floors.toml` with `default = 85`.
- `Execute(args []string, stdout io.Writer, stderr io.Writer) int` must expose exactly six primary commands: `inventory`, `plan`, `apply`, `verify`, `uninstall`, and `restore`.
- `waywarden --version` exits `0` and emits human version `0.0.0-dev` until release injection exists. Task 2 adds the contract-owned `--output json` form after `contracts.CommandResult` exists.
- There is no `version` subcommand.
- Stub subcommands may return invalid-input or not-implemented errors until their engines are introduced, but they must keep the command tree stable and stack-trace-free.
- `internal/distribution/cli` may contain presentation helpers and exit constants only; it must not define `CommandResult` because the contracts package owns public contract structs.

**Steps**

- [ ] Red: add `version_test.go` asserting `Execute([]string{"--version"}, stdout, stderr)` exits `0`, writes `waywarden 0.0.0-dev` to stdout, and leaves stderr empty.
- [ ] Red: add `root_test.go` asserting command names are exactly the six primary subcommands and unsupported commands exit `2` without Go stack traces.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./cmd/waywarden ./internal/distribution/cli` and confirm the module or commands are absent.
- [ ] Minimal: add module, `pkcov` tool directive, coverage floor, Cobra root, global `--output=human|json`, `--version`, six command stubs, and stable exit mapping through `internal/distribution/cli`; run `GOTOOLCHAIN=go1.26.0 go mod tidy` to create `go.sum`.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./cmd/waywarden ./internal/distribution/cli -run 'TestVersion|TestRoot' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./cmd/waywarden ./internal/distribution/cli -count=1` and `GOTOOLCHAIN=go1.26.0 go run ./cmd/waywarden --version`.
- [ ] Commit: `git add go.mod go.sum .coverage-floors.toml cmd/waywarden internal/distribution/cli && git commit -m "feat(waywarden): add cobra foundation"`.

## Task 2: Contract package, canonical JSON, schemas, contract structs, and selectors

**File scope**

New files:

- `internal/distribution/contracts/canonical.go`
- `internal/distribution/contracts/canonical_test.go`
- `internal/distribution/contracts/digest.go`
- `internal/distribution/contracts/digest_test.go`
- `internal/distribution/contracts/schema.go`
- `internal/distribution/contracts/schema_test.go`
- `internal/distribution/contracts/types.go`
- `internal/distribution/contracts/types_test.go`
- `internal/distribution/contracts/manifest.go`
- `internal/distribution/contracts/inventory.go`
- `internal/distribution/contracts/plan.go`
- `internal/distribution/contracts/backup.go`
- `internal/distribution/contracts/ownership.go`
- `internal/distribution/contracts/receipt.go`
- `internal/distribution/contracts/verification.go`
- `internal/distribution/contracts/operator_observation.go`
- `internal/distribution/contracts/command_result.go`
- `internal/distribution/contracts/error.go`
- `internal/distribution/contracts/exit.go`
- `internal/distribution/contracts/output.go`
- `internal/distribution/contracts/schemas/manifest.schema.json`
- `internal/distribution/contracts/schemas/inventory.schema.json`
- `internal/distribution/contracts/schemas/plan.schema.json`
- `internal/distribution/contracts/schemas/backup-manifest.schema.json`
- `internal/distribution/contracts/schemas/ownership.schema.json`
- `internal/distribution/contracts/schemas/receipt.schema.json`
- `internal/distribution/contracts/schemas/verification.schema.json`
- `internal/distribution/contracts/schemas/operator-observation.schema.json`
- `internal/distribution/contracts/schemas/command-result.schema.json`
- `internal/distribution/contracts/schemas/error.schema.json`
- `internal/distribution/contracts/testdata/rfc8785.jsonl`
- `internal/distribution/contracts/testdata/noncanonical.jsonl`

Existing files to modify:

- `cmd/waywarden/root.go`
- `internal/distribution/cli/output.go`

**Contract slice**

- Define `SchemaID` constants with the exact literals listed in Global Constraints.
- Define the persisted types consumed by every package: manifest, inventory, physical deployments, runtime bindings, blockers, plan payload/envelope, selectors, preconditions, backup requirements, backup manifest, ownership record, ledger refs, journal entries, receipt, verification, operator observation, public command result, and public error.
- Define selectors as validated discriminated unions in `contracts`: install has no selector; uninstall selects exactly one `installation_id`; restore selects exactly one `backup_set_id`; verify selects exactly one receipt, installation, or backup selector.
- Export these exact canonical interfaces and reuse them without aliases in later tasks:

```go
func StrictParseCanonical(data []byte, dst any) error
func CanonicalBytes(value any) ([]byte, error)
func SHA256(data []byte) SHA256Hex
func PayloadDigest(payload PlanPayload) (SHA256Hex, error)
func ParseCanonicalInventory(data []byte) (Inventory, error)
func ParseCanonicalPlanEnvelope(data []byte) (PlanEnvelope, error)
func VerifyPlanEnvelope(data []byte, approved SHA256Hex) (PlanEnvelope, error)
func ValidateSchema(schema SchemaID, canonical []byte) error
```

- Define `ArtifactRef` as relative path, SHA-256, and decimal-string byte length; nullable DAG refs are pointers and must be non-null exactly where the spec requires them. Define `PlanEnvelope` as `{schema, approval_digest, payload}`, `PlanPayload` with complete embedded `Inventory`, inventory digest, intent, selector union, deployments, blockers, preconditions, backup requirement, verification requirements, rollback strategy, and lineage transition. Define `CommandResult` as a closed discriminated union of artifact, mutation, and verification results; define `PublicError` with schema, stable code, exit, command, redacted evidence, and no arbitrary private path.
- Reject BOM, duplicate keys, trailing bytes, invalid UTF-8, floats, non-finite numbers, binary strings, and integers outside the RFC 8785 safe range. Encode larger numeric values as decimal strings.
- Every schema file uses JSON Schema draft 2020-12, exact `$id`, top-level `schema.const`, `required`, and `additionalProperties:false`.
- `cmd/waywarden` and `internal/distribution/cli` consume `contracts.CommandResult` and `contracts.PublicError`; they do not define duplicate result structs. Extend the Task 1 version test here so `waywarden --version --output json` emits one canonical `waywarden.command-result/v1` with `version:"0.0.0-dev"`.

**Steps**

- [ ] Red: add RFC 8785 vectors, duplicate-key vectors, safe-integer boundary vectors, and payload digest tests.
- [ ] Red: add schema-loading tests validating a minimal canonical artifact for each exact schema ID.
- [ ] Red: add selector union tests for install, uninstall, restore, and verify cardinality.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/contracts -count=1`.
- [ ] Minimal: implement strict parser, canonical encoder, digest helpers, embedded schema loading, schema validation, public error/result serialization, and all named persisted contract structs.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/contracts -run 'Canonical|Digest|Schema|Selector|CommandResult|Error' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/contracts ./cmd/waywarden ./internal/distribution/cli -count=1`.
- [ ] Commit: `git add internal/distribution/contracts cmd/waywarden/root.go internal/distribution/cli/output.go && git commit -m "feat(waywarden): add contract schemas"`.

## Task 3: Checkout-bound manifest, path identity, and physical deployment dedupe

**File scope**

New files:

- `distribution/manifest.json`
- `internal/distribution/manifest/load.go`
- `internal/distribution/manifest/load_test.go`
- `internal/distribution/planning/deployment.go`
- `internal/distribution/planning/deployment_test.go`
- `internal/distribution/planning/blocker.go`
- `internal/distribution/planning/blocker_test.go`
- `internal/distribution/filesystem/path_identity.go`
- `internal/distribution/filesystem/path_identity_unix.go`
- `internal/distribution/filesystem/path_identity_windows.go`
- `internal/distribution/filesystem/path_identity_test.go`

Existing files to modify:

- `internal/distribution/contracts/manifest.go`
- `internal/distribution/contracts/inventory.go`
- `internal/distribution/contracts/plan.go`

**Contract slice**

- `distribution/manifest.json` is canonical compact JSON, validates as `waywarden.manifest/v1`, and lists only `adr`, `decision-calibrator`, `model-optimizer`, `remove-gentle-context`, and `systemic-issue-triage`.
- Runtime roots are exactly Pi `.agents/skills`, OpenCode `.agents/skills`, and Claude `.claude/skills`, each with direct symlink strategy.
- Default manifest loading is only `cwd/distribution/manifest.json`; `--manifest` is accepted only as an absolute fixture or test path.
- Reject parent search, upward repository discovery, environment search, `PATH` search, release archive search, and package-manager search.
- Build ten physical deployments and fifteen runtime bindings: five shared Pi/OpenCode deployments with two runtime bindings each, and five Claude deployments with one runtime binding each.
- Emit typed blockers for same physical slot mapped to different canonical source identity or incompatible strategy.
- Manifest and planning models use `contracts.Manifest`, `contracts.RuntimeRoot`, `contracts.Deployment`, and `contracts.RuntimeBinding`; no duplicate manifest or planning contract models are introduced.

**Steps**

- [ ] Red: add loader tests for default path, absolute override, relative override rejection, source escape rejection, and absence of upward search.
- [ ] Red: add deployment tests proving five skills produce fifteen runtime bindings and ten physical deployments.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/manifest ./internal/distribution/planning ./internal/distribution/filesystem -count=1`.
- [ ] Minimal: implement checkout-bound loading, canonical source checks, path identity, deployment ID hashing from governed slot plus source identity, stable lexical ordering, and blockers.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/manifest ./internal/distribution/planning -run 'Manifest|Deployment|Binding|Blocker' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/manifest ./internal/distribution/planning ./internal/distribution/filesystem ./internal/distribution/contracts -count=1`.
- [ ] Commit: `git add distribution/manifest.json internal/distribution/manifest internal/distribution/planning internal/distribution/filesystem internal/distribution/contracts && git commit -m "feat(waywarden): add manifest deployment planning"`.

## Task 4: Read-only inventory, adapter seams, locks, publisher, memory fake, and deterministic output

**File scope**

New files:

- `cmd/waywarden/inventory.go`
- `cmd/waywarden/inventory_test.go`
- `internal/distribution/inventory/inventory.go`
- `internal/distribution/inventory/inventory_test.go`
- `internal/distribution/inventory/state_snapshot.go`
- `internal/distribution/inventory/state_snapshot_test.go`
- `internal/distribution/filesystem/adapter.go`
- `internal/distribution/filesystem/lock.go`
- `internal/distribution/filesystem/publish.go`
- `internal/distribution/filesystem/memory.go`
- `internal/distribution/filesystem/memory_test.go`
- `internal/distribution/runtimes/roots.go`
- `internal/distribution/runtimes/roots_test.go`

Existing files to modify:

- `cmd/waywarden/root.go`
- `internal/distribution/contracts/inventory.go`
- `internal/distribution/contracts/output.go`

**Contract slice**

- Introduce `filesystem.Adapter` as an interface that compiles with memory-backed behavior for inventory, planning evidence, locks, read-only publication, backup snapshot tests, and state tests. Its exact Task 4 interface is:

```go
type Adapter interface {
    Platform() string
    Environment(context.Context) (PlatformEnv, error)
    ObserveNoFollow(context.Context, contracts.AbsolutePath) (Observation, error)
    SnapshotTree(context.Context, contracts.AbsolutePath) (TreeSnapshot, error)
    HashFileByHandle(context.Context, contracts.AbsolutePath) (contracts.SHA256Hex, error)
    LockShared(context.Context, contracts.AbsolutePath, string) (LockHandle, error)
    LockExclusive(context.Context, contracts.AbsolutePath, string) (LockHandle, error)
    AppendFileSync(context.Context, contracts.AbsolutePath, []byte) error
    WriteFileNoReplaceSync(context.Context, contracts.AbsolutePath, []byte) error
    ReadFile(context.Context, contracts.AbsolutePath) ([]byte, error)
    PublishNoReplace(context.Context, contracts.AbsolutePath, []byte, ForbiddenRoots) error
    OwnerPrivateLockRoot(PlatformEnv) (contracts.AbsolutePath, error)
}

```

  In `package inventory`, expose:

```go
type Service interface {
    Inventory(context.Context, Options) (contracts.ArtifactResult, error)
}
```

  Task 8 extends this same interface with mutation methods and updates every existing consumer in the same commit.

- Adapter includes platform/env discovery, no-follow observation, tree snapshot, hash-by-handle seam, shared/exclusive locks, append/write/read file sync seams, same-parent no-replace publication, and owner-private lock root resolution.
- Introduce `filesystem.ArtifactPublisher.PublishNoReplace(ctx, destination, canonical, forbiddenRoots)` and `filesystem.NewMemoryAdapter()` with lock key recording and no real home access.
- Inventory may acquire only a shared selected-ledger lock to snapshot existing state. It never acquires slot locks and never allocates operation, installation, backup, journal, receipt, verification, timestamp, nonce, process, or temporary-path IDs in persisted bytes.
- Default `--out` is `-`. With `--out -`, canonical inventory is stdout and human summary is stderr. `inventory --out - --output json` exits `2`.
- Explicit `--out` destinations must be absolute and outside repository sources, runtime roots, selected state root, and coordination lock root; publication is same-parent create-new staging, fsync, no-replace publish, parent sync.
- Repeated identical evidence produces byte-identical inventory.

**Steps**

- [ ] Red: add command tests for stdout artifact mode, file output with JSON command result, invalid JSON/stdout combination, relative manifest rejection, and existing output destination.
- [ ] Red: add inventory package tests with fake observer and memory adapter proving shared ledger lock only, stable sorted arrays, no generated IDs, and byte-identical output.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./cmd/waywarden ./internal/distribution/inventory ./internal/distribution/filesystem ./internal/distribution/runtimes -count=1`.
- [ ] Minimal: implement inventory service, Cobra command wiring, platform default state root resolution through adapter env, shared ledger snapshot, canonical artifact build, forbidden root checks, and confined no-replace artifact publication.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./cmd/waywarden ./internal/distribution/inventory -run 'Inventory|Out|Deterministic|Ledger' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./cmd/waywarden ./internal/distribution/inventory ./internal/distribution/filesystem ./internal/distribution/runtimes ./internal/distribution/contracts -count=1`.
- [ ] Commit: `git add cmd/waywarden internal/distribution/inventory internal/distribution/filesystem internal/distribution/runtimes internal/distribution/contracts && git commit -m "feat(waywarden): add read-only inventory"`.

## Task 5: Pure planning from inventory artifacts and digest-bound approval

**File scope**

New files:

- `cmd/waywarden/plan.go`
- `cmd/waywarden/plan_test.go`
- `internal/distribution/planning/planner.go`
- `internal/distribution/planning/planner_test.go`
- `internal/distribution/planning/testdata/install_inventory.json`
- `internal/distribution/planning/testdata/uninstall_inventory.json`
- `internal/distribution/planning/testdata/restore_inventory.json`

Existing files to modify:

- `cmd/waywarden/root.go`
- `internal/distribution/contracts/plan.go`
- `internal/distribution/contracts/inventory.go`
- `internal/distribution/contracts/output.go`
- `internal/distribution/planning/deployment.go`
- `internal/distribution/planning/blocker.go`

**Contract slice**

- Consume only Task 2 `contracts` for inventory, selector, deployment, runtime binding, blocker, precondition, backup requirement, verification requirement, rollback, and output envelope types.
- Export the exact pure planning API and CLI service:

```go
func DecodeInventoryArtifact(raw []byte) (InventoryArtifact, error)
func BuildPlan(ctx context.Context, artifact InventoryArtifact, opts Options) (Result, error)
func CanonicalPlanBytes(result Result) ([]byte, error)

type Service interface {
    Plan(context.Context, Options) (contracts.ArtifactResult, error)
}
```

- `BuildPlan` is pure over the inventory artifact and explicit flags. It does not open runtime roots, state roots, manifests, ledgers, clocks, randomness, environment variables, or filesystem paths.
- `PlanEnvelope.Payload.Inventory` embeds the complete `contracts.Inventory`; `payload.inventory_digest` equals the canonical inventory byte digest; top-level `approval_digest` equals SHA-256 over canonical payload bytes.
- Install plans contain ten physical deployments, fifteen runtime bindings, no event/storage IDs, backup requirements, verification requirements, blockers, preconditions, rollback strategy, and lineage transition.
- `cmd/waywarden plan` requires `--inventory`, validates intent and selector union, validates `--out`, calls the pure planner, and publishes through the Task 4 artifact publisher.

**Steps**

- [ ] Red: add planner tests for deterministic install output, approval digest binding, embedded inventory digest, no generated IDs, and selector cardinality.
- [ ] Red: add canonical compact inventory fixtures for install, uninstall, and restore planning with physical-slot dedupe evidence.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/planning ./cmd/waywarden -count=1`.
- [ ] Minimal: implement strict inventory artifact decoding, selector validation, deterministic deployment aggregation, blocker construction, payload digest calculation, canonical envelope emission, and plan command wiring.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/planning ./cmd/waywarden -run 'Plan|Selector|Digest|Deterministic' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/contracts ./internal/distribution/planning ./cmd/waywarden -count=1` and `GOTOOLCHAIN=go1.26.0 go test ./... -count=1`.
- [ ] Commit: `git add cmd/waywarden/plan.go cmd/waywarden/plan_test.go internal/distribution/planning internal/distribution/contracts && git commit -m "feat(waywarden): add pure distribution planning"`.

## Task 6: State roots, lock ordering, aggregate ledger, journals, receipts, store, IDs, and recovery

**File scope**

New files:

- `internal/distribution/state/roots.go`
- `internal/distribution/state/locks.go`
- `internal/distribution/state/ids.go`
- `internal/distribution/state/store.go`
- `internal/distribution/state/ledger.go`
- `internal/distribution/state/journal.go`
- `internal/distribution/state/receipt.go`
- `internal/distribution/state/recovery.go`
- `internal/distribution/state/state_test.go`
- `internal/distribution/state/failure_injection_test.go`

Existing files to modify:

- `internal/distribution/contracts/ownership.go`
- `internal/distribution/contracts/receipt.go`
- `internal/distribution/contracts/types.go`
- `internal/distribution/filesystem/lock.go`
- `internal/distribution/filesystem/memory.go`

**Contract slice**

- `ResolveRoots(env, override)` returns selected state root plus canonical owner-private platform lock root. `--state-root` relocates state artifacts only and never selects the coordination lock root.
- `AcquireMutationLocks(ctx, fs, roots, slots)` acquires global mutation lock, sorted governed-slot locks, then exclusive selected-ledger lock.
- `LockSet.Release()` releases in exact inverse order: ledger first, slots in reverse acquisition order, then global.
- The ledger lock physical namespace prevents concurrent writers to the same selected state root alias by using canonical physical identity of the selected state root in the ledger lock key, while the lock root remains owner-private and independent of the selected state root.
- Verification state writes acquire global then ledger only. Inventory snapshots acquire only a shared selected-ledger lock. Planning acquires no lock.
- Define one `state.Store` interface with these exact methods and no alternate engine-local state APIs:

```go
type Store interface {
    ResolveRoots(context.Context, contracts.AbsolutePath) (Roots, error)
    AcquireMutationLocks(context.Context, Roots, []contracts.GovernedSlotIdentity) (LockSet, error)
    AcquireVerificationLocks(context.Context, Roots) (LockSet, error)
    AcquireInventoryLedgerSnapshot(context.Context, Roots) (filesystem.LockHandle, error)
    GenerateInstallIDs(io.Reader) (contracts.OperationID, contracts.InstallationID, contracts.BackupSetID, error)
    GenerateOperationID(io.Reader) (contracts.OperationID, error)
    OpenLedger(context.Context, Roots) (Ledger, error)
    OpenJournal(context.Context, Roots, contracts.OperationID, contracts.CommandName) (Journal, error)
    PublishRunArtifact(context.Context, Roots, contracts.OperationID, string, []byte) (contracts.ArtifactRef, error)
    PublishReceipt(context.Context, Roots, contracts.OperationID, contracts.Receipt) (contracts.ArtifactRef, error)
    ClassifyRecovery(context.Context, Roots) (contracts.RecoveryStatus, error)
}
```

- Ledger records are newline-framed canonical NDJSON. Record hash excludes trailing newline and excludes `record_hash`; previous hash binds the chain; readers accept only complete newline-terminated records.
- Journal DAG: ledger references ready journal prefix; receipt draft references ledger and ready prefix; terminal journal references receipt digest; ledger schema has no `receipt_ref`.

**Steps**

- [ ] Red: add tests for platform roots, lock-root independence, alias-safe ledger lock keys, acquisition order, release order, and ID generation after locks.
- [ ] Red: add ledger tests for canonical NDJSON append, hash chaining, truncated-tail rejection, hash mismatch, and no `receipt_ref`; add recovery tests after every journal, cleanup, ledger, ready, receipt-draft, terminal, receipt-publication, and run-directory-sync boundary, including interrupted journals, terminal receipt crashes, corrupt ledgers, and `recovery_required`.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/state ./internal/distribution/filesystem ./internal/distribution/contracts -count=1`.
- [ ] Minimal: implement roots, lock acquisition/release, ID factory, ledger scan/append, journal append, run artifact publication, receipt draft/publication, and recovery classification.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/state -run 'Root|Lock|Ledger|Journal|Receipt|Recovery|ID' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/state ./internal/distribution/contracts ./internal/distribution/filesystem -count=1` and `GOTOOLCHAIN=go1.26.0 go test ./... -count=1`.
- [ ] Commit: `git add internal/distribution/state internal/distribution/contracts internal/distribution/filesystem && git commit -m "feat(waywarden): add transactional state core"`.

## Task 7: Backup snapshots, typed-missing entries, metadata masks, tree digests, and restore staging semantics

**File scope**

New files:

- `internal/distribution/backup/backup.go`
- `internal/distribution/backup/metadata.go`
- `internal/distribution/backup/tree_digest.go`
- `internal/distribution/backup/staging.go`
- `internal/distribution/backup/backup_test.go`
- `internal/distribution/backup/testdata/tree/alpha.txt`

Existing files to modify:

- `internal/distribution/contracts/backup.go`
- `internal/distribution/contracts/types.go`
- `internal/distribution/filesystem/adapter.go`
- `internal/distribution/filesystem/memory.go`

**Contract slice**

- Backup consumes `contracts.BackupManifest`, `contracts.BackupEntry`, `contracts.MetadataPolicy`, and `contracts.ArtifactRef`; it does not define duplicate backup models.
- `Snapshotter.CreateBackupSet` records exactly one entry per physical deployment and writes `waywarden.backup-manifest/v1` canonical bytes through Task 4 publication/write seams.
- A missing governed slot becomes `BackupTypedMissing`, has no payload path, no content digest, and verifies by proving absence.
- Supported preimages are regular files, ordinary symlinks, and directory trees containing only ordinary directories, regular files, and ordinary symlinks.
- Metadata policy tests cover UTF-8 names; non-UTF8 blockers; POSIX file modes; directory mask exactly `01777` with sticky as the only bit outside `0777`; closed inode and `st_flags` masks; current owner/group/SID; ACL, xattr, resource fork, hardlink, sparse, mount, device, FIFO, socket, alternate-stream, and unsupported-reparse blockers; Windows inherited unprotected DACL and closed attributes; exact LastWriteTime 100ns preservation; excluded timestamp fields; and backup tree-digest content.
- `TreeDigest` commits to sorted relative UTF-8 paths, object kind, content digest, directory hierarchy, symlink lexical target, supported timestamp preservation, and every preserved metadata value.
- Backup code may implement `StageBackupEntry` and `VerifyStagedBackupEntry`; it must not move staged backup payloads into governed slots and must not record restore publication. Restore publication belongs to the restore engine.

**Steps**

- [ ] Red: add tests for typed-missing entries, unsupported metadata rejection, stable tree digest ordering, and no governed-slot restore publication from backup package.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/backup ./internal/distribution/filesystem ./internal/distribution/contracts -count=1`.
- [ ] Minimal: implement snapshot creation for missing, regular file, symlink, and directory tree observations; write backup manifests; verify each backup entry; implement staging-only restore payload construction.
- [ ] Minimal: implement closed Linux, macOS, and Windows metadata policies plus canonical tree digest.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/backup -run 'Backup|TypedMissing|Metadata|TreeDigest|Staging' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/backup ./internal/distribution/filesystem ./internal/distribution/contracts -count=1` and `GOTOOLCHAIN=go1.26.0 go test ./... -count=1`.
- [ ] Commit: `git add internal/distribution/backup internal/distribution/contracts internal/distribution/filesystem && git commit -m "feat(waywarden): add verified backup snapshots"`.

## Task 8: Native filesystem adapters, build tags, no-replace moves, exact cleanup, and TOCTOU defenses

**File scope**

New files:

- `internal/distribution/filesystem/adapter_linux.go`
- `internal/distribution/filesystem/adapter_darwin.go`
- `internal/distribution/filesystem/adapter_windows.go`
- `internal/distribution/filesystem/inspect.go`
- `internal/distribution/filesystem/move.go`
- `internal/distribution/filesystem/quarantine.go`
- `internal/distribution/filesystem/cleanup.go`
- `internal/distribution/filesystem/sync.go`
- `internal/distribution/filesystem/native_test.go`
- `internal/distribution/filesystem/adapter_unix_test.go`
- `internal/distribution/filesystem/adapter_windows_test.go`

Existing files to modify:

- `go.mod`
- `go.sum`
- `internal/distribution/filesystem/adapter.go`
- `internal/distribution/filesystem/lock.go`
- `internal/distribution/filesystem/publish.go`
- `internal/distribution/filesystem/memory.go`

**Contract slice**

- Modify the Task 4 adapter API to its native shape and update all current consumers in this task. Required methods: `Platform`, `ObserveNoFollow`, `OpenTreeNoFollow`, `SnapshotTree`, `HashFileByHandle`, `CreateManagedLinkStaging`, `MoveNoReplaceSync`, `MoveToQuarantine`, `SyncParent`, `CleanupExact`, `RestoreBackupEntryToStaging`, `LockExclusive`, `LockShared`, `AppendFileSync`, `WriteFileNoReplaceSync`, and `ReadFile`.
- Common slice: implement handle/descriptor-bound observation, same-parent staging/quarantine naming, exact identity revalidation, lock adapter compatibility, parent sync calls, and memory fake parity. Common code must not call `RemoveAll`, shell deletion, or recursive blind deletion.
- Linux slice: use `renameat2(..., RENAME_NOREPLACE)` and classify missing primitive as unsupported exit `3`.
- Darwin slice: use `renameatx_np(..., RENAME_EXCL)` and classify missing primitive as unsupported exit `3`.
- Windows slice: use handle-bound observation and `MoveFileEx` without replace semantics or a proven handle-bound no-replace equivalent; unsupported object kinds block with exit `3`.
- Cleanup reopens and revalidates every file, symlink/reparse point, empty directory, and nonempty tree entry before unlinking, sorted by stable descriptor traversal, syncing parent boundaries.
- Native tests run in temporary homes only and preserve platform primitives.

**Steps**

- [ ] Red common: add tests for API completeness, no-follow observation, exact cleanup identity mismatch, same-parent staging/quarantine, and forbidden recursive cleanup API scanning.
- [ ] Minimal common: update `filesystem.Adapter`, memory fake, observation structs, cleanup planner, locks, sync helpers, and current consumers to compile with the native-shaped interface.
- [ ] Pass common: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/filesystem ./internal/distribution/backup ./internal/distribution/state ./internal/distribution/inventory -run 'Adapter|Cleanup|Staging|Lock|Publish' -count=1`.
- [ ] Red Linux: add `-tags=native` tests for Linux no-replace overwrite protection, parent sync, symlink race, and unsupported primitive classification.
- [ ] Minimal Linux: implement Linux build-tag adapter with `golang.org/x/sys v0.47.0` and `renameat2` no-replace behavior.
- [ ] Pass Linux on Linux: `GOTOOLCHAIN=go1.26.0 go test -tags=native ./internal/distribution/filesystem -run 'Linux|Native|MoveNoReplace|Cleanup' -count=1`.
- [ ] Red Darwin: add `-tags=native` tests for Darwin no-replace overwrite protection, parent sync, symlink race, and unsupported primitive classification.
- [ ] Minimal Darwin: implement Darwin build-tag adapter with `renameatx_np` exclusive rename behavior.
- [ ] Pass Darwin on macOS: `GOTOOLCHAIN=go1.26.0 go test -tags=native ./internal/distribution/filesystem -run 'Darwin|Native|MoveNoReplace|Cleanup' -count=1`.
- [ ] Red Windows: add `-tags=native` tests for Windows no-replace behavior, reparse point rejection, parent sync, and unsupported object kind classification.
- [ ] Minimal Windows: implement Windows build-tag adapter with handle-bound observation and no-replace move semantics.
- [ ] Pass Windows on Windows: `GOTOOLCHAIN=go1.26.0 go test -tags=native ./internal/distribution/filesystem -run 'Windows|Native|MoveNoReplace|Cleanup' -count=1`.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/filesystem ./internal/distribution/contracts -count=1` and `GOTOOLCHAIN=go1.26.0 go test -tags=native ./internal/distribution/filesystem -count=1` on supported OS jobs.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./... -count=1` plus `if grep -R "RemoveAll\|rm -rf" internal/distribution/filesystem; then echo forbidden_recursive_cleanup_api_detected >&2; exit 1; fi`.
- [ ] Commit: `git add go.mod go.sum internal/distribution/filesystem && git commit -m "feat(waywarden): add safe platform filesystem adapters"`.

## Task 9: Apply aggregate engine, backup-before-mutation, rollback, and receipt DAG

**File scope**

New files:

- `internal/distribution/apply/engine.go`
- `internal/distribution/apply/types.go`
- `internal/distribution/apply/rollback.go`
- `internal/distribution/apply/journal_receipt.go`
- `internal/distribution/apply/backup.go`
- `internal/distribution/apply/engine_test.go`
- `internal/distribution/apply/failure_injection_test.go`

Existing files to modify:

- `internal/distribution/contracts/backup.go`
- `internal/distribution/contracts/ownership.go`
- `internal/distribution/contracts/receipt.go`
- `internal/distribution/filesystem/adapter.go`
- `internal/distribution/state/store.go`

**Contract slice**

- Use Task 8 `filesystem.Adapter` and Task 6 `state.Store`; do not introduce alternate `PlatformFS`, `Codec`, `AggregateLedger`, or package-local ledger APIs.
- `apply.Engine` dependencies are `FS filesystem.Adapter`, `State state.Store`, `Snapshotter backup.Snapshotter`, `IDFactory state.IDFactory`, `Clock contracts.Clock`, and `FailureInjector`. Export `type Service interface { Apply(context.Context, Request) (contracts.MutationResult, error) }`; `Engine` implements it.
- `Apply(ctx, request)` strict-parses canonical plan, validates envelope digest, validates embedded inventory digest, requires install intent, compares `--approve-digest`, then acquires locks.
- After locks, generate `operation_id`, `installation_id`, and `backup_set_id`, create run directory, persist embedded inventory canonical bytes and exact input plan envelope bytes, then open journal.
- Create and verify every backup entry before the first governed-slot move. Iterate physical deployments, not runtime bindings.
- Install mutation stages managed links, moves no-replace, reobserves postimage, syncs parent, appends exactly one aggregate `applied_unverified` ledger event with non-null `backup_set_ref` and null `verification_ref`.
- Complete cleanup, ready journal boundary, receipt draft, terminal `committed`, no-replace receipt publication, and run-directory sync. Receipt DAG order is ledger, ready journal prefix, receipt draft, terminal journal, receipt publication. Successful apply exits `0` with mutation status `verification_required`, never `installed_verified`.
- Rollback runs reverse journaled mutation steps before terminal commit; rollback after terminal commit is forbidden.

**Steps**

- [ ] Red: add tests for noncanonical plan before locks, approval mismatch before IDs, ID timing after locks, embedded inventory and exact plan artifact copies, backup before mutation, shared Pi/OpenCode single filesystem mutation, rollback branches, compensating aggregate events, boundary exit mapping, single aggregate ledger event, `verification_required`, acyclic receipt DAG, and receipt publication pending.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/apply -count=1`.
- [ ] Minimal: implement plan validation, lock acquisition, ID timing, run artifacts, backup set creation and verification, physical deployment install protocol, rollback, ledger append, receipt protocol, and phase-aware failure mapping.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/apply -run 'Apply|Backup|Rollback|Receipt|Ledger|Approval' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/apply ./internal/distribution/backup ./internal/distribution/filesystem ./internal/distribution/state ./internal/distribution/contracts -count=1` and `GOTOOLCHAIN=go1.26.0 go test ./... -count=1`.
- [ ] Commit: `git add internal/distribution/apply internal/distribution/contracts internal/distribution/filesystem internal/distribution/state && git commit -m "feat(waywarden): implement aggregate apply transaction"`.

## Task 10: Separate uninstall and restore engines with stable identity and inverse rollback

**File scope**

New files:

- `internal/distribution/uninstall/engine.go`
- `internal/distribution/uninstall/types.go`
- `internal/distribution/uninstall/rollback.go`
- `internal/distribution/uninstall/engine_test.go`
- `internal/distribution/uninstall/failure_injection_test.go`
- `internal/distribution/restore/engine.go`
- `internal/distribution/restore/types.go`
- `internal/distribution/restore/rollback.go`
- `internal/distribution/restore/engine_test.go`
- `internal/distribution/restore/failure_injection_test.go`
- `internal/distribution/uninstall/identity_test.go`

Existing files to modify:

- `internal/distribution/contracts/ownership.go`
- `internal/distribution/contracts/backup.go`
- `internal/distribution/filesystem/adapter.go`
- `internal/distribution/state/store.go`

**Contract slice**

- Use Task 8 `filesystem.Adapter` and Task 6 `state.Store`; do not introduce alternate filesystem, codec, or ledger APIs.
- Uninstall and restore are separate engines and services. Export `uninstall.Service.Uninstall(context.Context, Request) (contracts.MutationResult, error)` and `restore.Service.Restore(context.Context, Request) (contracts.MutationResult, error)`. They may share failure classification helpers from apply, but they must not merge behavior.
- Uninstall requires canonical uninstall plan intent, exactly one installation selector, healthy Waywarden ledger state `applied_unverified` or `installed_verified`, exact current `governed_slot_identity`, and exact current `managed_object_identity`.
- Textual names, textual paths, content match, source digest, resolved source identity, frontmatter, and operator memory are never uninstall authority.
- Uninstall moves installed managed object to same-parent quarantine no-replace, verifies moved object by managed object identity only, appends one aggregate `removed_unverified` event with null `backup_set_ref` and null `verification_ref`, and completes the same receipt protocol.
- Restore requires canonical restore plan intent, exactly one backup-set selector, complete verified backup set for the same lineage, aggregate state `removed_verified`, and every governed slot absent.
- `typed_missing` restore entries perform no filesystem action, create no staging object, and verify absence only.
- Restore stages each backup object through backup staging semantics, verifies backup digest and metadata matrix, moves no-replace into absent governed slot, reobserves, syncs parent, appends one aggregate `restored_unverified` event, and completes receipt protocol.
- Rollback persists `rolled_back` or a compensating aggregate event when safe; failed or unprovable compensation records `recovery_required`. The complete lifecycle regression is outside this engine slice; this task covers package engines and focused integration only.

**Steps**

- [ ] Red: add uninstall tests for intent/selector mismatch, lost or corrupted state, exact identity authority, source drift diagnostic behavior, post-quarantine identity comparison, aggregate ledger event, and inverse rollback.
- [ ] Red: add restore tests for intent/selector mismatch, subset rejection, verified backup lineage requirements, absent slots, `typed_missing` absence-only behavior, staged restore for file/symlink/tree, rollback, and failure injection.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/uninstall ./internal/distribution/restore -count=1`.
- [ ] Minimal: implement uninstall engine, restore engine, shared phase-aware error mapping, stable identity checks, backup staging consumption, journal/ledger/receipt wiring, and rollback branches.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/uninstall ./internal/distribution/restore -run 'Uninstall|Restore|Identity|TypedMissing|Rollback|FailureInjection' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/uninstall ./internal/distribution/restore ./internal/distribution/backup ./internal/distribution/filesystem ./internal/distribution/state ./internal/distribution/contracts -count=1` and `GOTOOLCHAIN=go1.26.0 go test ./... -count=1`.
- [ ] Commit: `git add internal/distribution/uninstall internal/distribution/restore internal/distribution/contracts internal/distribution/filesystem internal/distribution/state && git commit -m "feat(waywarden): separate uninstall and restore transactions"`.

## Task 11: Pi and OpenCode runtime adapters, registry, runner, and shared binding verification

**File scope**

New files:

- `internal/distribution/runtimes/adapter.go`
- `internal/distribution/runtimes/registry.go`
- `internal/distribution/runtimes/runner.go`
- `internal/distribution/runtimes/pi.go`
- `internal/distribution/runtimes/pi_test.go`
- `internal/distribution/runtimes/opencode.go`
- `internal/distribution/runtimes/opencode_test.go`
- `internal/distribution/runtimes/testdata/pi/commands.jsonl`
- `internal/distribution/runtimes/testdata/opencode/debug-skill.json`
- `internal/distribution/runtimes/shared_binding_test.go`

Existing files to modify:

- `internal/distribution/contracts/verification.go`
- `internal/distribution/contracts/types.go`
- `internal/distribution/filesystem/adapter.go`
- `internal/distribution/runtimes/roots.go`

**Contract slice**

- Introduce `runtimes.RuntimeAdapter`, `Runner`, `Registry`, `DiscoveryRequest`, `VerificationRequest`, `Command`, and `CompletedCommand`.
- Provide `NewRegistry`, `NewPiAdapter`, and `NewOpenCodeAdapter` only. Claude adapter files, tests, and types are not part of this task.
- Registry rejects duplicate adapter names and verifies ordered bindings independently.
- Pi supports exact version `0.84.3`, command `pi --mode rpc --no-session --offline`, one JSONL stdin request `{"id":"skills","type":"get_commands"}`, exactly one correlated response, lexical `sourceInfo.path` check before resolved identity check, and exit `6` for malformed, duplicate, missing, or second correlated responses.
- Missing Pi executable during requested verification is verification evidence failure exit `6`; unsupported Pi version or unsupported response contract is exit `3`.
- OpenCode verification invokes `opencode debug skill` with inline `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1`, file-backed capture outside runtime roots, no shell/profile/config writes, and evidence failure exit `6` for missing executable, timeout, nonzero exit, nonempty stderr, unreadable capture, invalid JSON, duplicate governed names, missing names, and wrong winners.
- Shared Pi/OpenCode runtime bindings on one physical deployment must both pass independently.

**Steps**

- [ ] Red: add registry duplicate/sorting test and shared Pi/OpenCode binding verification test.
- [ ] Red: add Pi tests for exact version/RPC invocation, unsupported version/shape, malformed duplicate/missing responses, lexical source check, and missing executable during requested verify.
- [ ] Red: add OpenCode tests for inline ADR 0017 env, file-backed capture, no config writes, and failure modes.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/runtimes ./internal/distribution/verify -count=1`.
- [ ] Minimal: implement runtime adapter interface, registry, runner abstraction, Pi adapter, OpenCode adapter, fake executable harnesses, temporary-home helpers, and verification binding aggregation for Pi/OpenCode.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/runtimes ./internal/distribution/verify -run 'Registry|Pi|OpenCode|Shared' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/runtimes ./internal/distribution/verify ./internal/distribution/contracts ./internal/distribution/filesystem -count=1` and `GOTOOLCHAIN=go1.26.0 go test ./... -count=1`.
- [ ] Commit: `git add internal/distribution/runtimes internal/distribution/verify internal/distribution/contracts internal/distribution/filesystem && git commit -m "feat(waywarden): verify pi and opencode bindings"`.

## Task 12: Claude adapter, operator observation, and verification engine authority

**File scope**

New files:

- `internal/distribution/runtimes/claude.go`
- `internal/distribution/runtimes/claude_test.go`
- `internal/distribution/verify/engine.go`
- `internal/distribution/verify/engine_test.go`
- `internal/distribution/verify/claude_test.go`
- `internal/distribution/verify/verification_dag_test.go`

Existing files to modify:

- `internal/distribution/contracts/operator_observation.go`
- `internal/distribution/contracts/verification.go`
- `internal/distribution/contracts/ownership.go`
- `internal/distribution/contracts/receipt.go`
- `internal/distribution/contracts/types.go`
- `internal/distribution/contracts/schemas/operator-observation.schema.json`
- `internal/distribution/contracts/schemas/verification.schema.json`
- `internal/distribution/filesystem/adapter.go`
- `internal/distribution/runtimes/adapter.go`
- `internal/distribution/runtimes/registry.go`
- `internal/distribution/state/store.go`

**Contract slice**

- Reuse Task 11 `RuntimeAdapter`, `Runner`, and `Registry`; do not create `verify/pi.go`, `verify/opencode.go`, or duplicate runtime adapters.
- Add Claude through `NewClaudeAdapter(fs filesystem.Adapter, clock contracts.Clock)` and bounded challenge handling.
- Operator observations use `waywarden.operator-observation/v1`, no free text, `observer:"human"`, `launch_mode:"normal"`, exact challenge, plan digest, installation ID, transition enum, expected binding set, expiry, and typed observation union with `visible` or `not_visible`.
- For install verification, every syntactically valid Claude observation is audit evidence, but lineage advances only when every expected governed binding is `visible` and no extra binding exists.
- For removed verification, every governed binding must be `not_visible`; visible, missing, extra, invalid outcome, wrong transition, expired challenge, invalid schema, and wrong binding fail as evidence exit `6` unless the adapter contract version is unsupported exit `3`.
- Verify engine is read-only for runtime roots. It acquires verification locks from Task 6, generates operation and verification IDs only after locks, persists canonical `waywarden.verification/v1` evidence before ledger transition, and appends verified aggregate ledger events only when all deployment and runtime binding evidence passes.
- Repeated verification is idempotent: existing verified aggregate state produces exit `0` without a second lineage transition; a new audit artifact may be written only when state is healthy.
- Verification artifacts are non-authoritative audit evidence unless the later ledger transition is durably appended with non-null `verification_ref`. Successful restore verification transitions to `restored_verified` and explicitly returns restored objects to user ownership.
- Export the exact engine surface used by Task 13:

```go
type Engine interface {
    Verify(context.Context, Request) (contracts.VerificationResult, error)
}
```

  `Request` contains the validated `contracts.VerifySelector`, selected state root, absolute/default manifest path, optional operator-observation path, and timeout; selector cardinality is validated before any state/runtime access.

**Steps**

- [ ] Red: add Claude observation schema tests for free-text rejection, wrong challenge, wrong transition, wrong installation, expiry, unsupported contract version, install visibility, and removed non-visibility.
- [ ] Red: add verify engine tests for verification artifact before ledger transition, evidence failure exit `6` preserving failed artifact without ledger append, state write exit `5`, idempotent repeated verification, and every deployment/runtime binding requirement.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/verify ./internal/distribution/runtimes -count=1`.
- [ ] Minimal: implement Claude adapter, challenge persistence/validation, operator observation schema parsing, verification engine, immutable verification artifact publication, verified ledger transition, receipt protocol, and idempotency checks.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/verify ./internal/distribution/runtimes -run 'Claude|Observation|Verify|VerificationDAG|Idempotent' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/verify ./internal/distribution/runtimes ./internal/distribution/contracts ./internal/distribution/state ./internal/distribution/filesystem -count=1` and `GOTOOLCHAIN=go1.26.0 go test ./... -count=1`.
- [ ] Commit: `git add internal/distribution/runtimes internal/distribution/verify internal/distribution/contracts internal/distribution/state internal/distribution/filesystem && git commit -m "feat(waywarden): verify runtime attestations before ledger transitions"`.

## Task 13: Six-command CLI wiring, public output, exit map, and temporary-home lifecycle regression

**File scope**

New files:

- `cmd/waywarden/apply.go`
- `cmd/waywarden/verify.go`
- `cmd/waywarden/uninstall.go`
- `cmd/waywarden/restore.go`
- `cmd/waywarden/output_test.go`
- `cmd/waywarden/exit_test.go`
- `tests/test_waywarden_lifecycle.py`
- `tests/test_waywarden_no_real_home.py`
- `tests/fixtures/waywarden/checkout/distribution/manifest.json`
- `tests/fixtures/waywarden/checkout/skills/adr/SKILL.md`
- `tests/fixtures/waywarden/checkout/skills/decision-calibrator/SKILL.md`
- `tests/fixtures/waywarden/checkout/skills/model-optimizer/SKILL.md`
- `tests/fixtures/waywarden/checkout/skills/remove-gentle-context/SKILL.md`
- `tests/fixtures/waywarden/checkout/skills/systemic-issue-triage/SKILL.md`

Existing files to modify:

- `cmd/waywarden/main.go`
- `cmd/waywarden/root.go`
- `cmd/waywarden/inventory.go`
- `cmd/waywarden/plan.go`
- `internal/distribution/contracts/command_result.go`
- `internal/distribution/contracts/error.go`
- `internal/distribution/contracts/exit.go`
- `internal/distribution/contracts/output.go`
- `internal/distribution/contracts/schemas/command-result.schema.json`
- `internal/distribution/contracts/schemas/error.schema.json`

**Contract slice**

- Root command exposes exactly six primary subcommands plus `--version`; it does not expose a `version` subcommand.
- `cmd/waywarden.Dependencies` uses the exact services introduced earlier: `inventory.Service`, `planning.Service`, `apply.Service`, `verify.Engine`, `uninstall.Service`, `restore.Service`, stdout/stderr writers, and exit function. No command-level adapter may rename or widen those method signatures.
- Public output uses `contracts.CommandResult` discriminated union and `contracts.PublicError`; command-local result/error structs are forbidden.
- Flag validation happens before service calls: missing `--inventory`, multiple verify selectors, mutator intent mismatch, `inventory --out - --output json`, `plan --out - --output json`, and non-absolute `--manifest` exit `2`.
- Output modes: artifact stdout for `--out -` with human stderr; file output human mode leaves stdout empty; file output JSON mode emits one `waywarden.command-result/v1`; errors emit one `waywarden.error/v1` when no artifact/blocker result owns stdout.
- Exit map covers success `0`, invalid input `2`, unsupported capability `3`, safe precondition `4`, state or I/O failure `5`, and verification evidence failure `6`.
- Complete temporary lifecycle sequence is exact: `inventory -> plan install -> apply -> verify installation -> inventory -> plan uninstall -> uninstall -> verify installation -> inventory -> plan restore -> restore -> verify backup`.
- Lifecycle tests build `./cmd/waywarden`, use temporary `HOME`, `XDG_STATE_HOME`, `LOCALAPPDATA`, runtime roots, state roots, lock roots, fake Pi/OpenCode executables, and generated Claude operator observation files.

**Steps**

- [ ] Red: add tests for exactly six primary commands, flag validation, command-result union, stdout/stderr modes, exit mapping, and absence of `version` subcommand.
- [ ] Red: add Python lifecycle regression and no-real-home mutation regression using temporary homes and fixture checkout.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./cmd/waywarden ./internal/distribution/contracts -count=1` and the Python lifecycle command after building the test binary.
- [ ] Minimal: wire all six command handlers to exact services/engines, centralize output routing, implement public exit mapping, redact private paths, add fixtures, fake runtime executables, and temporary-home enforcement.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./cmd/waywarden ./internal/distribution/contracts -run 'Root|Flag|CommandResult|Stdout|Exit|Version' -count=1`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./cmd/waywarden ./internal/distribution/contracts -count=1`; `mkdir -p build && GOTOOLCHAIN=go1.26.0 go build -o build/waywarden-test ./cmd/waywarden`; `WAYWARDEN_BIN="$PWD/build/waywarden-test" WAYWARDEN_FIXTURE="$PWD/tests/fixtures/waywarden/checkout" python -m unittest tests.test_waywarden_lifecycle -v`; `python -m unittest tests.test_waywarden_no_real_home -v`; `GOTOOLCHAIN=go1.26.0 go test ./... -count=1`.
- [ ] Commit: `git add cmd/waywarden internal/distribution/contracts tests && git commit -m "feat(waywarden): wire cli output and lifecycle regression"`.

## Task 14: CI, release, documentation sync, and PR governance

**File scope**

New files:

- `.github/workflows/waywarden-ci.yml`
- `.github/workflows/waywarden-release.yml`
- `.github/pull_request_template.md`
- `.goreleaser.yaml`
- `docs/waywarden.md`
- `docs/waywarden-release.md`
- `docs/waywarden-cli.md`
- `docs/waywarden-acceptance.md`
- `internal/distribution/docs/help_sync_test.go`
- `internal/distribution/docs/release_contract_test.go`
- `tests/test_waywarden_docs.py`

Existing files to modify:

- `go.mod`
- `go.sum`

**Contract slice**

- CI uses Crossbeam light baseline only: `pablontiv/crossbeam/.github/workflows/go-ci.yml@9feddefac77e2bd8dde05f5e493031f965f791c5`, profile `light`, Go `1.26.0`, coverage threshold `85`, nearby comment `v2 reviewed 2026-08-28`.
- Project-owned quality jobs use inspected action pins and every action SHA is labeled as an inspected pin with a note requiring review before future updates.
- Inspected pins to preserve: `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`, `actions/setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e`, `actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9`, `github/codeql-action/init@db488ddef3bf6cb639b32c2e9a7c0a7ea8271d28`, `github/codeql-action/analyze@db488ddef3bf6cb639b32c2e9a7c0a7ea8271d28`, `gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e`, `goreleaser/goreleaser-action@f06c13b6b1a9625abc9e6e439d9c05a8f2190e94`, and `actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8`.
- CI runs `go test ./... -race`, `go vet ./...`, `golangci-lint v2.13.1`, `govulncheck@v1.1.4`, CodeQL, gitleaks, `pkcov check --floors .coverage-floors.toml --module github.com/pablontiv/skills` at `85`, native adapter tests on supported OS jobs, Python regressions, and Rootline ADR validation with a per-file strict loop: `for f in docs/adr/*.md; do rootline validate "$f" --strict; done`.
- Do not use `rootline validate --all` unless the accepted CLI syntax and behavior have been verified in the repository.
- GoReleaser v2 config produces exactly six binary-only archives and `checksums.txt`; no bundled manifest, no bundled skills, no Homebrew formula, no GPG signing, no auto-update.
- Required archive names are `waywarden_${VERSION}_linux_amd64.tar.gz`, `waywarden_${VERSION}_linux_arm64.tar.gz`, `waywarden_${VERSION}_darwin_amd64.tar.gz`, `waywarden_${VERSION}_darwin_arm64.tar.gz`, `waywarden_${VERSION}_windows_amd64.zip`, and `waywarden_${VERSION}_windows_arm64.zip`.
- Release workflow pins GoReleaser v2.18.0, sets `SOURCE_DATE_EPOCH`, requires checksum gate before provenance, and makes provenance mandatory for every archive and `checksums.txt` without `continue-on-error`.
- Docs synchronize CLI help, examples, flags, schemas, exits, status names, state graph, ten-deployment/fifteen-binding cardinality, nullable artifact DAG refs, terminal receipt protocol, verification DAG, output confinement, lifecycle sequence, runtime verification constraints, six release assets, acceptance mapping, and PR checklist governance evidence. The phase-aware error table has exactly one documented row and one test assertion per failure-injection boundary.

**Steps**

- [ ] Red: add documentation/release contract tests for Crossbeam light pin, project-owned quality jobs, per-file Rootline strict loop, six binary archives, release provenance, asset checksum script, native smoke matrix, help/docs/schema sync, and PR template evidence.
- [ ] Fail: run `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/docs -count=1`.
- [ ] Minimal: add CI workflow, release workflow, GoReleaser v2 config, docs, PR template, release asset verification, native smoke jobs, and action pin comments requiring review before future updates.
- [ ] Targeted test: `GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/docs -run 'WaywardenCI|Rootline|GoReleaser|Release|NativeSmoke|HelpDocs|PullRequest' -count=1` and `python -m unittest tests.test_waywarden_docs -v`.
- [ ] Full relevant test: `GOTOOLCHAIN=go1.26.0 go test ./... -race -coverprofile=coverage.out`; `GOTOOLCHAIN=go1.26.0 go vet ./...`; `golangci-lint run ./...`; `govulncheck ./...`; `for f in docs/adr/*.md; do rootline validate "$f" --strict; done`; `python -m unittest discover -s tests -p 'test_waywarden_*.py' -v`; `python -m unittest discover -s skills/systemic-issue-triage/tests -t skills/systemic-issue-triage -p 'test_*.py' -v`; `python -m unittest discover -s skills/model-optimizer/tests -t skills/model-optimizer -p 'test_*.py' -v`; `python -m unittest discover -s skills/remove-gentle-context/tests -t skills/remove-gentle-context -p 'test_*.py' -v`.
- [ ] Commit: `git add .github .goreleaser.yaml docs internal/distribution/docs tests go.mod go.sum && git commit -m "ci(waywarden): pin release governance and documentation checks"`.

## Acceptance criteria coverage

| Acceptance criterion | Covered by |
| --- | --- |
| 1 | Completed governance precondition; Task 14 preserves PR evidence |
| 2 | 11, 12, 14 |
| 3 | 14 |
| 4 | 1 |
| 5 | 3 |
| 6 | 4, 5, 13 |
| 7 | 5, 9, 10 |
| 8 | 2, 5, 9, 10 |
| 9 | 5, 12, 13 |
| 10 | 9, 10 |
| 11 | 3, 5, 9 |
| 12 | 9 |
| 13 | 11, 12 |
| 14 | 10 |
| 15 | 7, 10, 12 |
| 16 | 13 |
| 17 | 6, 7, 9, 10, 12 |
| 18 | 8, 14 |
| 19 | 7, 8 |
| 20 | 11, 12 |
| 21 | 12 |
| 22 | 11 |
| 23 | 13, 14 |
| 24 | 1, 8, 14 |
| 25 | Completed governance precondition; Task 14 repeats the gate |
| 26 | 2, 3, 6, 9, 12, 13, 14 |
| 27 | 14 |
| 28 | 14 |
| 29 | 14 |
| 30 | 13, 14 plus independent final review |
| 31 | 14 |

## Plan self-review checklist

- [ ] Every acceptance criterion 1–31 maps to a completed governance precondition or one or more implementation tasks above.
- [ ] Each created file has one first owner task; later tasks list it only under existing files to modify.
- [ ] Every cross-package interface is introduced before first use; `contracts`, `filesystem.Adapter`, `state.Store`, runtime adapters, and command services have no alternate definitions.
- [ ] Every mutating path validates canonical plan/inventory/digest/intent before locks, generates IDs only after locks, backs up before mutation, and has exact rollback/recovery tests.
- [ ] No plan step bundles skills, migrates Python helpers, copies skills as fallback, resumes implicitly, performs partial aggregate operations, or mutates a real home in tests.
- [ ] Linux, macOS, and Windows native jobs cover their own filesystem primitives; cross-architecture inspection is never reported as native execution.
- [ ] Release tests assert exactly six binary-only archives plus checksums and mandatory provenance.
- [ ] `git diff --check`, Rootline strict validation, Go/Python regressions, and forbidden-marker scans pass before requesting code review.
