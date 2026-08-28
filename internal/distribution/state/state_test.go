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

	firstHash, err := ledger.Append(ctx, ownershipRecord("install-1", "op-1", "applied_unverified"))
	if err != nil {
		t.Fatalf("Append(first) error = %v", err)
	}
	secondHash, err := ledger.Append(ctx, ownershipRecord("install-1", "op-2", "installed_verified"))
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
	if got, err := state.ComputeLedgerRecordHash(first); err != nil || got != first.RecordHash {
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
	op := contracts.OperationID("op-journal")

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
	committed, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "committed", Result: "verification_required"})
	if err != nil {
		t.Fatalf("Append(committed) error = %v", err)
	}
	if started.Path != "runs/op-journal/journal.ndjson" || ready.Path != started.Path || committed.OperationID != string(op) {
		t.Fatalf("journal refs = %#v %#v %#v", started, ready, committed)
	}
	if started.SHA256 == ready.SHA256 || ready.SHA256 == committed.SHA256 {
		t.Fatalf("journal prefix hashes did not advance")
	}
	if _, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "late"}); err == nil {
		t.Fatalf("journal accepted append after terminal committed")
	}

	badJournal, err := store.OpenJournal(ctx, roots, contracts.OperationID("op-bad"), contracts.CommandName("apply"))
	if err != nil {
		t.Fatalf("OpenJournal(bad) error = %v", err)
	}
	if _, err := badJournal.Append(ctx, contracts.JournalEntry{OperationID: "op-bad", Boundary: "committed", Result: "bad"}); err == nil {
		t.Fatalf("journal accepted committed before ready_to_commit")
	}
}

func TestRunArtifactAndReceiptPublication(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	op := contracts.OperationID("op-artifacts")

	ref, err := store.PublishRunArtifact(ctx, roots, op, "plan.json", []byte("{\"schema\":\"example\"}"))
	if err != nil {
		t.Fatalf("PublishRunArtifact() error = %v", err)
	}
	if ref.Path != "runs/op-artifacts/plan.json" || ref.SHA256 != contracts.SHA256([]byte("{\"schema\":\"example\"}")) || ref.Bytes != strconv.Itoa(len("{\"schema\":\"example\"}")) {
		t.Fatalf("artifact ref = %#v", ref)
	}
	if _, err := store.PublishRunArtifact(ctx, roots, op, "../escape", []byte("x")); err == nil {
		t.Fatalf("PublishRunArtifact accepted escaping name")
	}

	receipt := receiptForTest(op)
	receiptRef, err := store.PublishReceipt(ctx, roots, op, receipt)
	if err != nil {
		t.Fatalf("PublishReceipt() error = %v", err)
	}
	if receiptRef.Path != "runs/op-artifacts/receipt.json" {
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

	journal, err := store.OpenJournal(ctx, roots, contracts.OperationID("op-started"), contracts.CommandName("apply"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := journal.Append(ctx, contracts.JournalEntry{OperationID: "op-started", Boundary: "started", Result: "started"}); err != nil {
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
	artifact := contracts.ArtifactRef{Path: "runs/" + operationID + "/artifact.json", SHA256: sha, Bytes: "2"}
	journal := contracts.JournalRef{OperationID: operationID, Path: "runs/" + operationID + "/journal.ndjson", SHA256: sha}
	return contracts.OwnershipRecord{
		Schema:          contracts.SchemaOwnership,
		RecordID:        "record-" + operationID,
		OperationID:     contracts.OperationID(operationID),
		InstallationID:  contracts.InstallationID(installationID),
		DeploymentIDs:   []string{"deployment-a", "deployment-b"},
		PreviousHash:    nil,
		PlanRef:         artifact,
		InventoryRef:    artifact,
		JournalRef:      journal,
		BackupSetRef:    &contracts.BackupSetRef{BackupSetID: "backup-" + installationID, SHA256: sha},
		VerificationRef: nil,
		Entries:         []contracts.JournalEntry{},
		AggregateEvent:  event,
		OperationResult: "verification_required",
	}
}

func receiptForTest(op contracts.OperationID) contracts.Receipt {
	sha := contracts.SHA256([]byte("artifact"))
	journal := contracts.JournalRef{OperationID: string(op), Path: "runs/" + string(op) + "/journal.ndjson", SHA256: sha}
	artifact := contracts.ArtifactRef{Path: "runs/" + string(op) + "/plan.json", SHA256: sha, Bytes: "2"}
	approval := sha
	return contracts.Receipt{
		Schema:             contracts.SchemaReceipt,
		ReceiptID:          "receipt-" + string(op),
		OperationID:        string(op),
		Command:            "apply",
		ApprovalDigest:     &approval,
		LedgerRecordHash:   sha,
		ReadyJournalRef:    journal,
		TerminalJournalRef: &journal,
		PlanRef:            &artifact,
		InventoryRef:       &artifact,
		BackupSetRef:       &contracts.BackupSetRef{BackupSetID: "backup", SHA256: sha},
		VerificationRef:    nil,
		Preconditions:      []contracts.Precondition{},
		Results:            []contracts.JournalEntry{},
		OperationResult:    "verification_required",
	}
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

func ExampleResolveRoots() {
	env := filesystem.PlatformEnv{Home: "/tmp/home", XDGStateHome: "/tmp/state", LocalAppData: "C:/tmp/local"}
	roots, _ := state.ResolveRoots(env, "")
	fmt.Println(strings.HasSuffix(string(roots.LockRoot), filepath.Join("waywarden", "locks")))
	// Output: true
}
