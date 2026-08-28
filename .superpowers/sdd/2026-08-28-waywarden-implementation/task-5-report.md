# Task 5 report: pure planning from inventory artifacts

## Recovery context

This was a recovery implementation after a prior implementer timeout. I preserved the existing uncommitted RED tests, fixtures, and contract change (`BackupSetSnapshot.Verified`) and did not reset, delete, or recreate the worktree.

Initial worktree status:

```text
## pablontiv/issue-10-go-distributor-design
 M internal/distribution/contracts/inventory.go
?? cmd/waywarden/plan_helpers_test.go
?? cmd/waywarden/plan_test.go
?? internal/distribution/planning/planner_test.go
?? internal/distribution/planning/test_helpers_test.go
?? internal/distribution/planning/testdata/
```

## Preserved RED evidence

Command run before implementation:

```sh
GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/planning ./cmd/waywarden -count=1
```

Observed failure excerpt:

```text
# waywarden/internal/distribution/planning_test [waywarden/internal/distribution/planning.test]
internal/distribution/planning/planner_test.go:16:28: undefined: planning.DecodeInventoryArtifact
internal/distribution/planning/planner_test.go:21:25: undefined: planning.BuildPlan
internal/distribution/planning/planner_test.go:21:76: undefined: planning.Options
internal/distribution/planning/planner_test.go:29:30: undefined: planning.CanonicalPlanBytes
internal/distribution/planning/planner_test.go:143:82: undefined: planning.Result
internal/distribution/planning/planner_test.go:153:56: undefined: planning.InventoryArtifact
FAIL	waywarden/internal/distribution/planning [build failed]
--- FAIL: TestPlanOutStdoutWritesCanonicalPlanAndHumanSummaryToStderr
    plan_test.go:20: exit code = 2, want 0; stderr= stdout=
--- FAIL: TestPlanOutFileWithJSONWritesCommandResultToStdout
    plan_test.go:42: exit code = 2, want 0; stderr= stdout=
--- FAIL: TestPlanSelectorMismatchExitsTwoAndMissingRestoreBackupExitsFour
    plan_test.go:93: missing backup exit code = 2, want 4; stderr= stdout=
FAIL
```

## Implementation summary

- Added `internal/distribution/planning/planner.go` with:
  - `DecodeInventoryArtifact(raw []byte) (InventoryArtifact, error)`
  - `BuildPlan(ctx context.Context, artifact InventoryArtifact, opts Options) (Result, error)`
  - `CanonicalPlanBytes(result Result) ([]byte, error)`
  - `Service` and `NewService(adapter filesystem.Adapter)` for CLI-side inventory read/artifact publishing.
- Added `cmd/waywarden/plan.go` and wired `plan` in `cmd/waywarden/root.go`.
- Preserved strict canonical inventory input via `contracts.ParseCanonicalInventory` and `contracts.ValidateSchema`.
- Embedded the full decoded inventory in the plan payload.
- Bound `payload.inventory_digest` to the exact decoded canonical inventory bytes when the artifact is unchanged.
- Bound top-level `approval_digest` to `contracts.PayloadDigest(payload)`.
- Preserved deterministic deployment and runtime binding order.
- Rejected install selectors and selector cardinality/intent mismatches with exit 2.
- Accepted one observed installation for uninstall.
- Accepted one observed verified backup for restore.
- Returned blocker plan results for safe precondition failures such as a missing restore backup, allowing the CLI to publish an artifact and exit 4.
- Applied capability blocker precedence: `runtime_contract_missing` or severity `error` blockers classify as exit 3.
- Kept plan output free of Task 6+ operation/storage identifiers.
- Synchronized inventory and embedded plan schema backup snapshots with `verified`.

## Purity proof

`BuildPlan` starts at `internal/distribution/planning/planner.go:70` and constructs a plan only from:

- `InventoryArtifact.Inventory`
- `Options.Intent`
- `Options.Selector`
- deterministic contract helpers (`CanonicalBytes`, `PayloadDigest`, `SHA256`)
- deterministic in-memory sorting and cloning

Forbidden ambient dependencies check:

```sh
grep -nE 'os\.|Getenv|time\.|rand\.|Lock|manifest|ledger|ReadFile|PublishNoReplace' internal/distribution/planning/planner.go cmd/waywarden/plan.go
```

Output:

```text
internal/distribution/planning/planner.go:139:	raw, err := s.adapter.ReadFile(ctx, opts.InventoryPath)
internal/distribution/planning/planner.go:156:		if err := s.adapter.PublishNoReplace(ctx, opts.Destination, canonical, filesystem.ForbiddenRoots{}); err != nil {
```

Interpretation: the only filesystem operations are in the CLI service adapter path (`service.Plan`), not in `BuildPlan`. There are no planner uses of environment variables, clocks, randomness, manifests, ledgers, or locks.

## Validation

Initial RED:

```sh
GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/planning ./cmd/waywarden -count=1
# failed as expected before implementation
```

Post-implementation targeted RED-to-GREEN:

```sh
GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/planning ./cmd/waywarden -count=1
```

Output:

```text
ok  	waywarden/internal/distribution/planning	0.426s
ok  	waywarden/cmd/waywarden	0.691s
```

Brief targeted command:

```sh
GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/planning ./cmd/waywarden -run 'Plan|Selector|Digest|Deterministic' -count=1
```

Output:

```text
ok  	waywarden/internal/distribution/planning	0.284s
ok  	waywarden/cmd/waywarden	0.492s
```

Relevant suite:

```sh
GOTOOLCHAIN=go1.26.0 go test ./internal/distribution/contracts ./internal/distribution/planning ./cmd/waywarden -count=1
```

Output:

```text
ok  	waywarden/internal/distribution/contracts	0.280s
ok  	waywarden/internal/distribution/planning	0.723s
ok  	waywarden/cmd/waywarden	0.546s
```

Full suite:

```sh
GOTOOLCHAIN=go1.26.0 go test ./... -count=1
```

Output:

```text
ok  	waywarden/cmd/waywarden	0.330s
ok  	waywarden/internal/distribution/cli	0.678s
ok  	waywarden/internal/distribution/contracts	0.437s
ok  	waywarden/internal/distribution/filesystem	1.119s
ok  	waywarden/internal/distribution/inventory	0.893s
ok  	waywarden/internal/distribution/manifest	1.364s
ok  	waywarden/internal/distribution/planning	1.821s
ok  	waywarden/internal/distribution/runtimes	1.586s
```

## Notes and concerns

- The planner service uses the existing Task 4 no-replace artifact publisher via `filesystem.Adapter.PublishNoReplace` for file output and a sink for stdout output.
- `BuildPlan` remains pure; the service and CLI are the side-effect boundary.
- The plan schema already models `selector` permissively as object/null; no selector schema tightening was needed for this task because Go contract validation is authoritative for intent/cardinality.
