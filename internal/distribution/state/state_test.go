package state_test

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/state"
)

func TestResolveRootsDefaultAndOverrideLockRootIndependence(t *testing.T) {
	ctx := context.Background()
	home := t.TempDir()
	xdg := filepath.Join(t.TempDir(), "xdg-state")
	local := filepath.Join(t.TempDir(), "local-app-data")
	adapter := filesystem.NewMemoryAdapter()
	adapter.SetPlatform("linux")
	adapter.SetEnvironment(filesystem.PlatformEnv{Home: home, XDGStateHome: xdg, LocalAppData: local})
	store := state.NewStore(adapter)

	roots, err := store.ResolveRoots(ctx, "")
	if err != nil {
		t.Fatalf("ResolveRoots(default) error = %v", err)
	}
	wantState := filepath.Join(xdg, "waywarden")
	wantLock := filepath.Join(xdg, "waywarden", "locks")
	if roots.StateRoot != contracts.AbsolutePath(wantState) || roots.LockRoot != contracts.AbsolutePath(wantLock) {
		t.Fatalf("roots = %#v, want state=%s lock=%s", roots, wantState, wantLock)
	}

	override := contracts.AbsolutePath(filepath.Join(t.TempDir(), "selected-state"))
	overridden, err := store.ResolveRoots(ctx, override)
	if err != nil {
		t.Fatalf("ResolveRoots(override) error = %v", err)
	}
	if overridden.StateRoot != override {
		t.Fatalf("override state root = %s, want %s", overridden.StateRoot, override)
	}
	if overridden.LockRoot != roots.LockRoot {
		t.Fatalf("override changed lock root: %s vs %s", overridden.LockRoot, roots.LockRoot)
	}
	if _, err := store.ResolveRoots(ctx, contracts.AbsolutePath("relative-state")); err == nil {
		t.Fatalf("ResolveRoots accepted relative override")
	}
}

func TestMutationLocksAcquireAndReleaseInNormativeOrder(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	slots := []contracts.GovernedSlotIdentity{"slot-z", "slot-a"}

	locks, err := store.AcquireMutationLocks(ctx, roots, slots)
	if err != nil {
		t.Fatalf("AcquireMutationLocks() error = %v", err)
	}
	ledgerKey := filepath.Join(string(roots.LockRoot), "ledgers", string(contracts.SHA256([]byte(filepath.Clean(string(roots.StateRoot)))))+".lock")
	slotAKey := string(contracts.SHA256([]byte("slot-a")))
	slotZKey := string(contracts.SHA256([]byte("slot-z")))
	wantAcquire := []string{
		filepath.Join(string(roots.LockRoot), "global-mutation.lock"),
		filepath.Join(string(roots.LockRoot), "slots", slotZKey+".lock"),
		filepath.Join(string(roots.LockRoot), "slots", slotAKey+".lock"),
		ledgerKey,
	}
	if got := adapter.ExclusiveLockKeys(); !equalStrings(got, wantAcquire) {
		t.Fatalf("exclusive lock acquire order = %v, want %v", got, wantAcquire)
	}
	if err := locks.Release(); err != nil {
		t.Fatalf("Release() error = %v", err)
	}
	wantRelease := []string{ledgerKey, wantAcquire[2], wantAcquire[1], wantAcquire[0]}
	if got := adapter.ReleaseLockKeys(); !equalStrings(got, wantRelease) {
		t.Fatalf("lock release order = %v, want inverse %v", got, wantRelease)
	}
}

func TestVerificationAndInventoryAcquireOnlyNormativeLedgerLocks(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)

	verification, err := store.AcquireVerificationLocks(ctx, roots)
	if err != nil {
		t.Fatalf("AcquireVerificationLocks() error = %v", err)
	}
	defer verification.Release()
	if got := adapter.ExclusiveLockKeys(); len(got) != 2 || !strings.HasSuffix(got[0], "global-mutation.lock") || !strings.Contains(got[1], string(filepath.Separator)+"ledgers"+string(filepath.Separator)) {
		t.Fatalf("verification lock order = %v, want global then ledger only", got)
	}

	adapter = filesystem.NewMemoryAdapter()
	store = state.NewStore(adapter)
	if lock, err := store.AcquireInventoryLedgerSnapshot(ctx, roots); err != nil {
		t.Fatalf("AcquireInventoryLedgerSnapshot() error = %v", err)
	} else {
		_ = lock.Close()
	}
	if got := adapter.ExclusiveLockKeys(); len(got) != 0 {
		t.Fatalf("inventory acquired exclusive locks = %v", got)
	}
	if got := adapter.SharedLockKeys(); len(got) != 1 || !strings.Contains(got[0], string(filepath.Separator)+"ledgers"+string(filepath.Separator)) {
		t.Fatalf("inventory shared locks = %v, want one selected ledger", got)
	}
}

func TestLedgerLockKeyCanonicalizesSelectedStateRootAliases(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	base := t.TempDir()
	lockRoot := contracts.AbsolutePath(filepath.Join(t.TempDir(), "locks"))
	rootA := state.Roots{StateRoot: contracts.AbsolutePath(filepath.Join(base, "state")), LockRoot: lockRoot}
	rootB := state.Roots{StateRoot: contracts.AbsolutePath(filepath.Join(base, ".", "state")), LockRoot: lockRoot}

	lockA, err := store.AcquireInventoryLedgerSnapshot(ctx, rootA)
	if err != nil {
		t.Fatalf("AcquireInventoryLedgerSnapshot(A) error = %v", err)
	}
	_ = lockA.Close()
	lockB, err := store.AcquireInventoryLedgerSnapshot(ctx, rootB)
	if err != nil {
		t.Fatalf("AcquireInventoryLedgerSnapshot(B) error = %v", err)
	}
	_ = lockB.Close()
	keys := adapter.SharedLockKeys()
	if len(keys) != 2 || keys[0] != keys[1] {
		t.Fatalf("ledger alias lock keys = %v, want identical canonical physical selected-state-root key", keys)
	}

	adapter = filesystem.NewMemoryAdapter()
	store = state.NewStore(adapter)
	held, err := store.AcquireInventoryLedgerSnapshot(ctx, rootA)
	if err != nil {
		t.Fatalf("AcquireInventoryLedgerSnapshot(held alias) error = %v", err)
	}
	if _, err := store.AcquireVerificationLocks(ctx, rootB); !errors.Is(err, filesystem.ErrLockConflict) {
		t.Fatalf("alias ledger lock conflict error = %v, want ErrLockConflict", err)
	}
	_ = held.Close()
	if locks, err := store.AcquireVerificationLocks(ctx, rootB); err != nil {
		t.Fatalf("AcquireVerificationLocks(after release) error = %v", err)
	} else {
		_ = locks.Release()
	}
}

func TestGenerateIDsAreOpaqueRandomAndAllocatedAfterLocks(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	locks, err := store.AcquireMutationLocks(ctx, roots, []contracts.GovernedSlotIdentity{"slot-a"})
	if err != nil {
		t.Fatalf("AcquireMutationLocks() error = %v", err)
	}
	defer locks.Release()

	reader := &assertLocksHeldReader{t: t, adapter: adapter}
	op, install, backup, err := store.GenerateInstallIDs(reader)
	if err != nil {
		t.Fatalf("GenerateInstallIDs() error = %v", err)
	}
	ids := []string{string(op), string(install), string(backup)}
	hex64 := regexp.MustCompile(`^[0-9a-f]{64}$`)
	seen := map[string]bool{}
	for _, id := range ids {
		if !hex64.MatchString(id) {
			t.Fatalf("id %q is not opaque 256-bit lowercase hex", id)
		}
		if strings.Contains(id, "/") || strings.Contains(id, "state") || strings.Contains(id, "2026") {
			t.Fatalf("id %q appears to leak path or timestamp material", id)
		}
		if seen[id] {
			t.Fatalf("IDs are not unique: %v", ids)
		}
		seen[id] = true
	}
	if reader.reads != 3 {
		t.Fatalf("reader reads = %d, want one per install id", reader.reads)
	}

	opOnly, err := store.GenerateOperationID(reader)
	if err != nil {
		t.Fatalf("GenerateOperationID() error = %v", err)
	}
	if !hex64.MatchString(string(opOnly)) {
		t.Fatalf("operation id %q is not lowercase hex", opOnly)
	}
}

func TestLedgerAppendCanonicalHashChainRejectsPartialAndMismatch(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	ledger, err := store.OpenLedger(ctx, roots)
	if err != nil {
		t.Fatalf("OpenLedger() error = %v", err)
	}

	firstRecord := ownershipRecord("install-1", opID("op-1"), "applied_unverified")
	firstRecord.JournalRef = appendStartedJournalForTest(ctx, t, store, roots, firstRecord.OperationID)
	publishAuthorityArtifactsForStateTest(ctx, t, adapter, store, roots, &firstRecord)
	firstHash, err := ledger.Append(ctx, firstRecord)
	if err != nil {
		t.Fatalf("Append(first) error = %v", err)
	}
	secondRecord := ownershipRecord("install-1", opID("op-2"), "restored_unverified")
	secondRecord.JournalRef = appendStartedJournalForTest(ctx, t, store, roots, secondRecord.OperationID)
	publishAuthorityArtifactsForStateTest(ctx, t, adapter, store, roots, &secondRecord)
	secondHash, err := ledger.Append(ctx, secondRecord)
	if err != nil {
		t.Fatalf("Append(second) error = %v", err)
	}
	if firstHash == secondHash {
		t.Fatalf("ledger hashes did not advance")
	}
	data, err := adapter.ReadFile(ctx, roots.LedgerPath())
	if err != nil {
		t.Fatalf("Read ledger error = %v", err)
	}
	if !bytes.HasSuffix(data, []byte("\n")) {
		t.Fatalf("ledger is not newline framed: %q", data)
	}
	if bytes.Contains(data, []byte("receipt_ref")) {
		t.Fatalf("ledger contains forbidden receipt_ref: %s", data)
	}
	lines := bytes.Split(bytes.TrimSuffix(data, []byte("\n")), []byte("\n"))
	if len(lines) != 2 {
		t.Fatalf("ledger lines = %d, want 2", len(lines))
	}
	var first, second contracts.OwnershipRecord
	if err := contracts.StrictParseCanonical(lines[0], &first); err != nil {
		t.Fatalf("first ledger line is not canonical: %v", err)
	}
	if err := contracts.StrictParseCanonical(lines[1], &second); err != nil {
		t.Fatalf("second ledger line is not canonical: %v", err)
	}
	if first.Sequence != 1 || second.Sequence != 2 {
		t.Fatalf("sequences = %d, %d; want 1, 2", first.Sequence, second.Sequence)
	}
	if second.PreviousHash == nil || *second.PreviousHash != first.RecordHash {
		t.Fatalf("second previous hash = %v, want %s", second.PreviousHash, first.RecordHash)
	}
	if got, err := computeLedgerRecordHashForTest(first); err != nil || got != first.RecordHash {
		t.Fatalf("first record hash verification = %s, %v; want %s", got, err, first.RecordHash)
	}

	adapter.PutFile(roots.LedgerPath(), bytes.TrimSuffix(data, []byte("\n")))
	if _, err := store.OpenLedger(ctx, roots); err == nil {
		t.Fatalf("OpenLedger accepted truncated tail")
	}

	bad := first
	bad.RecordHash = contracts.SHA256([]byte("wrong"))
	badLine, err := contracts.CanonicalBytes(bad)
	if err != nil {
		t.Fatal(err)
	}
	adapter.PutFile(roots.LedgerPath(), append(badLine, '\n'))
	if _, err := store.OpenLedger(ctx, roots); err == nil {
		t.Fatalf("OpenLedger accepted record_hash mismatch")
	}
}

func TestJournalTransitionsRefsAndTerminality(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	op := contracts.OperationID(opID("op-journal"))

	journal, err := store.OpenJournal(ctx, roots, op, contracts.CommandName("apply"))
	if err != nil {
		t.Fatalf("OpenJournal() error = %v", err)
	}
	started, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "started"})
	if err != nil {
		t.Fatalf("Append(started) error = %v", err)
	}
	ready, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "ready_to_commit", Result: "ready"})
	if err != nil {
		t.Fatalf("Append(ready) error = %v", err)
	}
	committed, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "committed", Result: "verification_required", ReceiptSHA256: contracts.SHA256([]byte("receipt")), FinalReceiptPath: "receipt.json"})
	if err != nil {
		t.Fatalf("Append(committed) error = %v", err)
	}
	if started.Path != "runs/"+string(op)+"/journal.ndjson" || ready.Path != started.Path || committed.OperationID != string(op) {
		t.Fatalf("journal refs = %#v %#v %#v", started, ready, committed)
	}
	if started.SHA256 == ready.SHA256 || ready.SHA256 == committed.SHA256 {
		t.Fatalf("journal prefix hashes did not advance")
	}
	if _, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "late"}); err == nil {
		t.Fatalf("journal accepted append after terminal committed")
	}

	badOp := contracts.OperationID(opID("op-bad"))
	badJournal, err := store.OpenJournal(ctx, roots, badOp, contracts.CommandName("apply"))
	if err != nil {
		t.Fatalf("OpenJournal(bad) error = %v", err)
	}
	if _, err := badJournal.Append(ctx, contracts.JournalEntry{OperationID: string(badOp), Boundary: "committed", Result: "bad", ReceiptSHA256: contracts.SHA256([]byte("receipt")), FinalReceiptPath: "receipt.json"}); err == nil {
		t.Fatalf("journal accepted committed before ready_to_commit")
	}
}

func TestRunArtifactAndReceiptPublication(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	op := contracts.OperationID(opID("op-artifacts"))

	ref, err := store.PublishRunArtifact(ctx, roots, op, "example.json", []byte("{\"schema\":\"example\"}"))
	if err != nil {
		t.Fatalf("PublishRunArtifact() error = %v", err)
	}
	if ref.Path != "runs/"+string(op)+"/example.json" || ref.SHA256 != contracts.SHA256([]byte("{\"schema\":\"example\"}")) || ref.Bytes != strconv.Itoa(len("{\"schema\":\"example\"}")) {
		t.Fatalf("artifact ref = %#v", ref)
	}
	if _, err := store.PublishRunArtifact(ctx, roots, op, "../escape", []byte("x")); err == nil {
		t.Fatalf("PublishRunArtifact accepted escaping name")
	}

	receipt := prepareReceiptProtocol(ctx, t, adapter, store, roots, op)
	receiptRef, err := store.PublishReceipt(ctx, roots, op, receipt)
	if err != nil {
		t.Fatalf("PublishReceipt() error = %v", err)
	}
	if receiptRef.Path != "runs/"+string(op)+"/receipt.json" {
		t.Fatalf("receipt ref path = %s", receiptRef.Path)
	}
	if _, err := store.PublishReceipt(ctx, roots, op, receipt); !errors.Is(err, filesystem.ErrDestinationExists) {
		t.Fatalf("second PublishReceipt error = %v, want ErrDestinationExists", err)
	}
}

func TestClassifyRecoveryFromLedgerAndJournalState(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)

	status, err := store.ClassifyRecovery(ctx, roots)
	if err != nil {
		t.Fatalf("ClassifyRecovery(clean) error = %v", err)
	}
	if status.Status != contracts.RecoveryClean {
		t.Fatalf("clean status = %#v", status)
	}

	startedOp := contracts.OperationID(opID("op-started"))
	journal, err := store.OpenJournal(ctx, roots, startedOp, contracts.CommandName("apply"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(startedOp), Boundary: "started", Result: "started"}); err != nil {
		t.Fatal(err)
	}
	status, err = store.ClassifyRecovery(ctx, roots)
	if err != nil {
		t.Fatalf("ClassifyRecovery(started) error = %v", err)
	}
	if status.Status != contracts.RecoveryRequired || status.Code != "interrupted_journal" {
		t.Fatalf("started status = %#v, want interrupted_journal recovery_required", status)
	}

	adapter = filesystem.NewMemoryAdapter()
	store = state.NewStore(adapter)
	roots = tempRoots(t)
	adapter.PutFile(roots.LedgerPath(), []byte("{\"schema\":\"waywarden.ownership/v1\"}"))
	status, err = store.ClassifyRecovery(ctx, roots)
	if err != nil {
		t.Fatalf("ClassifyRecovery(corrupt) error = %v", err)
	}
	if status.Status != contracts.RecoveryRequired || status.Code != "corrupt_ledger" {
		t.Fatalf("corrupt ledger status = %#v", status)
	}
}

type assertLocksHeldReader struct {
	t       *testing.T
	adapter *filesystem.MemoryAdapter
	counter byte
	reads   int
}

func (r *assertLocksHeldReader) Read(p []byte) (int, error) {
	r.reads++
	if len(r.adapter.ExclusiveLockKeys()) < 3 {
		r.t.Fatalf("ID reader was consumed before normative mutation locks were acquired; locks=%v", r.adapter.ExclusiveLockKeys())
	}
	for i := range p {
		r.counter++
		p[i] = r.counter
	}
	return len(p), nil
}

func tempRoots(t *testing.T) state.Roots {
	t.Helper()
	base := t.TempDir()
	return state.Roots{
		StateRoot: contracts.AbsolutePath(filepath.Join(base, "state")),
		LockRoot:  contracts.AbsolutePath(filepath.Join(base, "locks")),
	}
}

func ownershipRecord(installationID, operationID, event string) contracts.OwnershipRecord {
	sha := contracts.SHA256([]byte("artifact"))
	artifact := contracts.ArtifactRef{Path: "runs/" + operationID + "/plan.json", SHA256: sha, Bytes: "2"}
	journal := contracts.JournalRef{OperationID: operationID, Path: "runs/" + operationID + "/journal.ndjson", SHA256: sha}
	deployments := ownershipDeploymentsForStateTest(artifact, sha)
	record := contracts.OwnershipRecord{
		Schema:                 contracts.SchemaOwnership,
		RecordID:               "record-" + operationID,
		OperationID:            contracts.OperationID(operationID),
		InstallationID:         contracts.InstallationID(installationID),
		DeploymentIDs:          stateAggregateDeploymentIDsForTest(),
		Deployments:            deployments,
		PreviousHash:           nil,
		PlanRef:                artifact,
		InventoryRef:           artifact,
		JournalRef:             journal,
		BackupSetRef:           &contracts.BackupSetRef{BackupSetID: "backup-" + installationID, SHA256: sha},
		VerificationRef:        nil,
		AggregateEvent:         event,
		OperationResult:        "verification_required",
		FailureCode:            nil,
		CompensatingPriorState: nil,
	}
	switch event {
	case "removed_unverified":
		record.BackupSetRef = nil
	case "installed_verified", "removed_verified", "restored_verified":
		record.OperationResult = "verified"
		record.VerificationRef = &artifact
		for i := range record.Deployments {
			record.Deployments[i].Result = "verified"
			for j := range record.Deployments[i].RuntimeBindingSummaries {
				record.Deployments[i].RuntimeBindingSummaries[j].Status = "verified"
			}
		}
		if event != "restored_verified" {
			record.BackupSetRef = nil
		}
	case "install_rolled_back", "uninstall_rolled_back", "restore_rolled_back":
		failure := "state_or_io_failure_preterminal"
		record.OperationResult = "rolled_back"
		record.FailureCode = &failure
		record.CompensatingPriorState = &contracts.CompensatingPriorState{AggregateEvent: "applied_unverified", DeploymentIDs: stateAggregateDeploymentIDsForTest(), LedgerRecordHash: sha}
		for i := range record.Deployments {
			record.Deployments[i].Result = "rolled_back"
		}
	}
	return record
}

func appendStartedJournalForTest(ctx context.Context, t *testing.T, store state.Store, roots state.Roots, op contracts.OperationID) contracts.JournalRef {
	t.Helper()
	journal, err := store.OpenJournal(ctx, roots, op, contracts.CommandName("apply"))
	if err != nil {
		t.Fatal(err)
	}
	ref, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "started"})
	if err != nil {
		t.Fatal(err)
	}
	return ref
}

func prepareReceiptProtocol(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots, op contracts.OperationID) contracts.Receipt {
	t.Helper()
	journal, err := store.OpenJournal(ctx, roots, op, contracts.CommandName("apply"))
	if err != nil {
		t.Fatal(err)
	}
	ledgerRef, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "started"})
	if err != nil {
		t.Fatal(err)
	}
	ledger, err := store.OpenLedger(ctx, roots)
	if err != nil {
		t.Fatal(err)
	}
	record := ownershipRecord("install", string(op), "applied_unverified")
	record.JournalRef = ledgerRef
	publishAuthorityArtifactsForStateTest(ctx, t, adapter, store, roots, &record)
	ledgerHash, err := ledger.Append(ctx, record)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "step", Step: "cleanup", State: "cleanup_completed", Result: "cleanup_completed"}); err != nil {
		t.Fatal(err)
	}
	ready, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "ready_to_commit", Result: "ready"})
	if err != nil {
		t.Fatal(err)
	}
	return receiptFromRecordForStateTest(record, ledgerHash, ready)
}

func receiptFromRecordForStateTest(record contracts.OwnershipRecord, ledgerHash contracts.SHA256Hex, ready contracts.JournalRef) contracts.Receipt {
	approval := record.PlanRef.SHA256
	results := make([]contracts.OperationDeploymentResult, 0, len(record.Deployments))
	for _, deployment := range record.Deployments {
		before := deployment.BeforeObservation
		after := deployment.AfterObservation
		results = append(results, contracts.OperationDeploymentResult{DeploymentID: deployment.DeploymentID, Result: deployment.Result, BeforeObservation: &before, AfterObservation: &after, RuntimeBindingSummaries: deployment.RuntimeBindingSummaries, BackupEntryRef: deployment.BackupEntryRef, VerificationRef: deployment.VerificationRef, CleanupEvidenceRef: deployment.CleanupEvidenceRef, RollbackAuthorityRefs: deployment.RollbackAuthorityRefs})
	}
	return contracts.Receipt{Schema: contracts.SchemaReceipt, ReceiptID: "receipt-" + string(record.OperationID), OperationID: string(record.OperationID), Command: "apply", ApprovalDigest: &approval, LedgerRecordHash: ledgerHash, ReadyJournalRef: ready, PlanRef: &record.PlanRef, InventoryRef: &record.InventoryRef, BackupSetRef: record.BackupSetRef, VerificationRef: record.VerificationRef, Preconditions: []contracts.Precondition{}, DeploymentResults: results, RollbackResults: []contracts.OperationDeploymentResult{}, CleanupEvidenceRef: results[0].CleanupEvidenceRef, RequiredVerificationStatus: "verification_required", OperationResult: record.OperationResult}
}

func publishAuthorityArtifactsForStateTest(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots, record *contracts.OwnershipRecord) {
	t.Helper()
	ids := append([]string(nil), record.DeploymentIDs...)
	deployments := make([]contracts.Deployment, 0, len(ids))
	bindingsByID := map[string][]contracts.RuntimeBinding{}
	for _, binding := range stateAggregateRuntimeBindingsForTest() {
		bindingsByID[binding.DeploymentID] = append(bindingsByID[binding.DeploymentID], binding)
	}
	for i, id := range ids {
		deployments = append(deployments, contracts.Deployment{DeploymentID: id, SkillID: "skill-" + string(rune('a'+i)), SourcePath: "/repo/skills/" + id, SourceIdentity: "source-" + id, GovernedPath: "/runtime/" + id, GovernedSlotIdentity: "slot-" + id, LinkStrategy: "symlink", RuntimeBindings: bindingsByID[id]})
	}
	inventory := contracts.Inventory{Schema: contracts.SchemaInventory, ManifestDigest: contracts.SHA256([]byte("manifest")), Sources: []contracts.SourceObservation{}, Deployments: deployments, RuntimeBindings: flattenStateRuntimeBindings(deployments), Ownership: []contracts.OwnershipSnapshot{}, Backups: []contracts.BackupSetSnapshot{}, Blockers: []contracts.Blocker{}}
	inventoryBytes, err := contracts.CanonicalBytes(inventory)
	if err != nil {
		t.Fatal(err)
	}
	inventoryRef, err := store.PublishRunArtifact(ctx, roots, record.OperationID, "inventory.json", inventoryBytes)
	if err != nil && !errors.Is(err, filesystem.ErrDestinationExists) {
		t.Fatal(err)
	}
	if errors.Is(err, filesystem.ErrDestinationExists) {
		inventoryRef = contracts.ArtifactRef{Path: "runs/" + string(record.OperationID) + "/inventory.json", SHA256: contracts.SHA256(inventoryBytes), Bytes: fmt.Sprintf("%d", len(inventoryBytes))}
	}
	payload := contracts.PlanPayload{Inventory: inventory, InventoryDigest: contracts.SHA256(inventoryBytes), Intent: contracts.IntentInstall, Selector: nil, Deployments: deployments, Blockers: []contracts.Blocker{}, Preconditions: []contracts.Precondition{}, BackupRequirement: contracts.BackupRequirement{Required: true, Reason: "install requires backup set"}, VerificationRequirements: []contracts.VerificationRequirement{}, RollbackStrategy: "rollback_on_preterminal_failure", LineageTransition: contracts.LineageTransition{From: "absent", To: "applied_unverified"}}
	approval, err := contracts.PayloadDigest(payload)
	if err != nil {
		t.Fatal(err)
	}
	planBytes, err := contracts.CanonicalBytes(contracts.PlanEnvelope{Schema: contracts.SchemaPlan, ApprovalDigest: approval, Payload: payload})
	if err != nil {
		t.Fatal(err)
	}
	planRef, err := store.PublishRunArtifact(ctx, roots, record.OperationID, "plan.json", planBytes)
	if err != nil && !errors.Is(err, filesystem.ErrDestinationExists) {
		t.Fatal(err)
	}
	if errors.Is(err, filesystem.ErrDestinationExists) {
		planRef = contracts.ArtifactRef{Path: "runs/" + string(record.OperationID) + "/plan.json", SHA256: contracts.SHA256(planBytes), Bytes: fmt.Sprintf("%d", len(planBytes))}
	}
	record.PlanRef = planRef
	record.InventoryRef = inventoryRef
	if record.BackupSetRef != nil {
		manifest := contracts.BackupManifest{Schema: contracts.SchemaBackupManifest, BackupSetID: record.BackupSetRef.BackupSetID, InstallationID: string(record.InstallationID), Operation: "apply", Entries: []contracts.BackupEntry{}, Verified: true}
		manifestBytes, err := contracts.CanonicalBytes(manifest)
		if err != nil {
			t.Fatal(err)
		}
		adapter.PutFile(contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "backups", record.BackupSetRef.BackupSetID, "manifest.json")), manifestBytes)
		record.BackupSetRef.SHA256 = contracts.SHA256(manifestBytes)
	}
}

func flattenStateRuntimeBindings(deployments []contracts.Deployment) []contracts.RuntimeBinding {
	var out []contracts.RuntimeBinding
	for _, deployment := range deployments {
		out = append(out, deployment.RuntimeBindings...)
	}
	return out
}

func receiptForTest(op contracts.OperationID) contracts.Receipt {
	sha := contracts.SHA256([]byte("artifact"))
	journal := contracts.JournalRef{OperationID: string(op), Path: "runs/" + string(op) + "/journal.ndjson", SHA256: sha}
	artifact := contracts.ArtifactRef{Path: "runs/" + string(op) + "/plan.json", SHA256: sha, Bytes: "2"}
	approval := sha
	return contracts.Receipt{
		Schema:                     contracts.SchemaReceipt,
		ReceiptID:                  "receipt-" + string(op),
		OperationID:                string(op),
		Command:                    "apply",
		ApprovalDigest:             &approval,
		LedgerRecordHash:           sha,
		ReadyJournalRef:            journal,
		PlanRef:                    &artifact,
		InventoryRef:               &artifact,
		BackupSetRef:               &contracts.BackupSetRef{BackupSetID: "backup-install", SHA256: sha},
		VerificationRef:            nil,
		Preconditions:              []contracts.Precondition{},
		DeploymentResults:          operationDeploymentResultsForStateTest(artifact, sha),
		RollbackResults:            []contracts.OperationDeploymentResult{},
		CleanupEvidenceRef:         &artifact,
		RequiredVerificationStatus: "verification_required",
		OperationResult:            "verification_required",
	}
}

func ownershipDeploymentsForStateTest(artifact contracts.ArtifactRef, sha contracts.SHA256Hex) []contracts.OwnershipDeploymentRecord {
	bindings := map[string][]contracts.RuntimeBinding{}
	for _, binding := range stateAggregateRuntimeBindingsForTest() {
		bindings[binding.DeploymentID] = append(bindings[binding.DeploymentID], binding)
	}
	ids := stateAggregateDeploymentIDsForTest()
	out := make([]contracts.OwnershipDeploymentRecord, 0, len(ids))
	for _, id := range ids {
		before := contracts.DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/" + id, GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "missing", AttributesFingerprint: "attrs-before"}
		after := contracts.DeploymentObservation{ObservedType: "symlink", Path: "/runtime/" + id, GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "object-" + id, ManagedLinkIdentity: "link-" + id, LexicalLinkTarget: "/repo/skill", SourceContentDigest: string(sha), AttributesFingerprint: "attrs-after"}
		summaries := make([]contracts.RuntimeBindingSummary, 0, len(bindings[id]))
		for _, binding := range bindings[id] {
			summaries = append(summaries, contracts.RuntimeBindingSummary{Runtime: binding.Runtime, BindingIdentity: binding.Runtime + ":" + binding.Name, Status: "verification_required", EvidenceRef: &artifact})
		}
		out = append(out, contracts.OwnershipDeploymentRecord{DeploymentID: id, BeforeObservation: before, AfterObservation: after, RuntimeBindingSummaries: summaries, OriginalPreimage: before, InstalledPostimage: &after, BackupEntryRef: &artifact, VerificationRef: nil, CleanupEvidenceRef: &artifact, RollbackAuthorityRefs: []contracts.ArtifactRef{artifact}, Result: "verification_required"})
	}
	return out
}

func stateAggregateDeploymentIDsForTest() []string {
	ids := make([]string, 10)
	for i := range ids {
		ids[i] = string(contracts.SHA256([]byte("state-test-deployment-" + string(rune('a'+i)))))
	}
	return ids
}

func stateAggregateRuntimeBindingsForTest() []contracts.RuntimeBinding {
	ids := stateAggregateDeploymentIDsForTest()
	out := make([]contracts.RuntimeBinding, 0, 15)
	for i, id := range ids {
		name := "skill-" + string(rune('a'+i))
		out = append(out, contracts.RuntimeBinding{DeploymentID: id, Runtime: "pi", Root: ".agents/skills", Name: name, Target: "skills/" + name})
		if i < 5 {
			out = append(out, contracts.RuntimeBinding{DeploymentID: id, Runtime: "opencode", Root: ".agents/skills", Name: name, Target: "skills/" + name})
		}
	}
	return out
}

func operationDeploymentResultsForStateTest(artifact contracts.ArtifactRef, sha contracts.SHA256Hex) []contracts.OperationDeploymentResult {
	deployments := ownershipDeploymentsForStateTest(artifact, sha)
	out := make([]contracts.OperationDeploymentResult, 0, len(deployments))
	for _, deployment := range deployments {
		before := deployment.BeforeObservation
		after := deployment.AfterObservation
		out = append(out, contracts.OperationDeploymentResult{DeploymentID: deployment.DeploymentID, Result: deployment.Result, BeforeObservation: &before, AfterObservation: &after, RuntimeBindingSummaries: deployment.RuntimeBindingSummaries, BackupEntryRef: deployment.BackupEntryRef, CleanupEvidenceRef: deployment.CleanupEvidenceRef, RollbackAuthorityRefs: deployment.RollbackAuthorityRefs})
	}
	return out
}

func computeLedgerRecordHashForTest(record contracts.OwnershipRecord) (contracts.SHA256Hex, error) {
	record.RecordHash = ""
	data, err := contracts.CanonicalBytes(record)
	if err != nil {
		return "", err
	}
	var object map[string]any
	if err := contracts.StrictParseCanonical(data, &object); err != nil {
		return "", err
	}
	delete(object, "record_hash")
	preimage, err := contracts.CanonicalBytes(object)
	if err != nil {
		return "", err
	}
	return contracts.SHA256(preimage), nil
}

func opID(seed string) string {
	return string(contracts.SHA256([]byte(seed)))
}

func equalStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

var _ state.Store = state.NewStore(filesystem.NewMemoryAdapter())
var _ io.Reader = (*assertLocksHeldReader)(nil)

func ExampleStore_ResolveRoots() {
	adapter := filesystem.NewMemoryAdapter()
	adapter.SetEnvironment(filesystem.PlatformEnv{Home: "/tmp/home", XDGStateHome: "/tmp/state", LocalAppData: "C:/tmp/local"})
	roots, _ := state.NewStore(adapter).ResolveRoots(context.Background(), "")
	fmt.Println(strings.HasSuffix(string(roots.LockRoot), filepath.Join("waywarden", "locks")))
	// Output: true
}
