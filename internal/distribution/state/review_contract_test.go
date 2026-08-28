package state_test

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/state"
)

func TestResolveRootsPlatformMatrixUsesRedirectedTempEnv(t *testing.T) {
	ctx := context.Background()
	for _, tc := range []struct {
		platform string
		want     func(filesystem.PlatformEnv) string
	}{
		{platform: "linux", want: func(env filesystem.PlatformEnv) string { return filepath.Join(env.XDGStateHome, "waywarden") }},
		{platform: "darwin", want: func(env filesystem.PlatformEnv) string {
			return filepath.Join(env.Home, "Library", "Application Support", "waywarden", "state")
		}},
		{platform: "windows", want: func(env filesystem.PlatformEnv) string { return filepath.Join(env.LocalAppData, "waywarden", "state") }},
	} {
		t.Run(tc.platform, func(t *testing.T) {
			env := filesystem.PlatformEnv{Home: filepath.Join(t.TempDir(), "home"), XDGStateHome: filepath.Join(t.TempDir(), "xdg"), LocalAppData: filepath.Join(t.TempDir(), "local")}
			adapter := filesystem.NewMemoryAdapter()
			adapter.SetPlatform(tc.platform)
			adapter.SetEnvironment(env)
			roots, err := state.NewStore(adapter).ResolveRoots(ctx, "")
			if err != nil {
				t.Fatalf("ResolveRoots(%s) error = %v", tc.platform, err)
			}
			if string(roots.StateRoot) != tc.want(env) {
				t.Fatalf("state root = %s, want %s", roots.StateRoot, tc.want(env))
			}
			if roots.LockRoot == "" || roots.LockRoot == roots.StateRoot {
				t.Fatalf("lock root not independent/private: %#v", roots)
			}
		})
	}
}

func TestLocksValidateSafeRootsBeforeAcquisition(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := state.Roots{StateRoot: contracts.AbsolutePath("relative-state"), LockRoot: contracts.AbsolutePath(filepath.Join(t.TempDir(), "locks"))}

	if _, err := store.AcquireMutationLocks(ctx, roots, []contracts.GovernedSlotIdentity{"slot"}); err == nil {
		t.Fatalf("AcquireMutationLocks accepted unsafe roots")
	}
	if got := adapter.ExclusiveLockKeys(); len(got) != 0 {
		t.Fatalf("locks were acquired before root validation: %v", got)
	}
	if _, err := store.AcquireInventoryLedgerSnapshot(ctx, roots); err == nil {
		t.Fatalf("AcquireInventoryLedgerSnapshot accepted unsafe roots")
	}
	if got := adapter.SharedLockKeys(); len(got) != 0 {
		t.Fatalf("shared lock was acquired before root validation: %v", got)
	}
}

func TestLedgerLockUsesAdapterPhysicalIdentityAndFailsOnAmbiguity(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	stateRoot := contracts.AbsolutePath(filepath.Join(t.TempDir(), "state"))
	aliasRoot := contracts.AbsolutePath(filepath.Join(t.TempDir(), "alias-state"))
	lockRoot := contracts.AbsolutePath(filepath.Join(t.TempDir(), "locks"))
	adapter.SetPhysicalIdentity(stateRoot, filesystem.PhysicalIdentity("dev:1/inode:42"))
	adapter.SetPhysicalIdentity(aliasRoot, filesystem.PhysicalIdentity("dev:1/inode:42"))
	store := state.NewStore(adapter)

	first, err := store.AcquireInventoryLedgerSnapshot(ctx, state.Roots{StateRoot: stateRoot, LockRoot: lockRoot})
	if err != nil {
		t.Fatalf("AcquireInventoryLedgerSnapshot(first) error = %v", err)
	}
	defer first.Close()
	if _, err := store.AcquireVerificationLocks(ctx, state.Roots{StateRoot: aliasRoot, LockRoot: lockRoot}); !errors.Is(err, filesystem.ErrLockConflict) {
		t.Fatalf("alias ledger lock error = %v, want ErrLockConflict", err)
	}

	ambiguous := contracts.AbsolutePath(filepath.Join(t.TempDir(), "ambiguous"))
	adapter.SetPhysicalIdentityError(ambiguous, filesystem.ErrUnsupportedCapability)
	if _, err := store.AcquireInventoryLedgerSnapshot(ctx, state.Roots{StateRoot: ambiguous, LockRoot: lockRoot}); !errors.Is(err, filesystem.ErrUnsupportedCapability) {
		t.Fatalf("ambiguous physical identity error = %v, want ErrUnsupportedCapability", err)
	}
}

func TestRunArtifactNameAndOperationIDAreContractValidated(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)

	badOps := []contracts.OperationID{"op-human", "../" + strings.Repeat("a", 64), strings.Repeat("A", 64)}
	for _, op := range badOps {
		if _, err := store.PublishRunArtifact(ctx, roots, op, "plan.json", []byte("{}")); err == nil {
			t.Fatalf("PublishRunArtifact accepted invalid operation_id %q", op)
		}
	}
	validOp := contracts.OperationID(strings.Repeat("a", 64))
	badNames := []string{"", ".", "..", "../escape.json", "nested/../../escape.json", `/absolute.json`, `C:\\absolute.json`, `nested\\escape.json`}
	for _, name := range badNames {
		if _, err := store.PublishRunArtifact(ctx, roots, validOp, name, []byte("{}")); err == nil {
			t.Fatalf("PublishRunArtifact accepted unsafe artifact name %q", name)
		}
	}
}

func TestRecoveryEvidenceUsesRelativeRefsAndAdapterEnumerationOnly(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	journal, err := store.OpenJournal(ctx, roots, contracts.OperationID(strings.Repeat("b", 64)), contracts.CommandName("apply"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := journal.Append(ctx, contracts.JournalEntry{OperationID: strings.Repeat("b", 64), Boundary: "started", Result: "started"}); err != nil {
		t.Fatal(err)
	}
	status, err := store.ClassifyRecovery(ctx, roots)
	if err != nil {
		t.Fatalf("ClassifyRecovery() error = %v", err)
	}
	if status.Status != contracts.RecoveryRequired || len(status.Evidence) == 0 {
		t.Fatalf("status = %#v, want recovery evidence", status)
	}
	for _, evidence := range status.Evidence {
		if filepath.IsAbs(evidence.Ref) || strings.Contains(evidence.Ref, string(roots.StateRoot)) {
			t.Fatalf("recovery evidence exposes absolute/private path: %#v", evidence)
		}
	}

	localStore := state.NewStore(filesystem.NewLocalAdapter())
	if _, err := localStore.ClassifyRecovery(ctx, roots); !errors.Is(err, filesystem.ErrUnsupportedCapability) {
		t.Fatalf("local recovery classification error = %v, want ErrUnsupportedCapability", err)
	}
}

func TestPublishReceiptRequiresReadyLedgerAndPublishesThroughTerminalProtocol(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	op := contracts.OperationID(strings.Repeat("c", 64))
	receipt := receiptForTest(op)

	if _, err := store.PublishReceipt(ctx, roots, op, receipt); err == nil {
		t.Fatalf("PublishReceipt succeeded without ready journal prefix and ledger hash")
	}

	journal, err := store.OpenJournal(ctx, roots, op, contracts.CommandName("apply"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "started"}); err != nil {
		t.Fatal(err)
	}
	ready, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "ready_to_commit", Result: "ready"})
	if err != nil {
		t.Fatal(err)
	}
	ledger, err := store.OpenLedger(ctx, roots)
	if err != nil {
		t.Fatal(err)
	}
	record := ownershipRecord("install", string(op), "applied_unverified")
	record.JournalRef = ready
	ledgerHash, err := ledger.Append(ctx, record)
	if err != nil {
		t.Fatal(err)
	}
	receipt.ReadyJournalRef = ready
	receipt.LedgerRecordHash = ledgerHash
	ref, err := store.PublishReceipt(ctx, roots, op, receipt)
	if err != nil {
		t.Fatalf("PublishReceipt() error = %v", err)
	}
	if ref.Path != "runs/"+string(op)+"/receipt.json" {
		t.Fatalf("receipt ref = %#v", ref)
	}
	reopened, err := store.OpenJournal(ctx, roots, op, contracts.CommandName("apply"))
	if err != nil {
		t.Fatal(err)
	}
	entries := reopened.Entries()
	if entries[len(entries)-1].Boundary != "committed" || entries[len(entries)-1].ReceiptSHA256 == "" || entries[len(entries)-1].FinalArtifactPath != "receipt.json" {
		t.Fatalf("terminal journal entry missing receipt digest/final relative destination: %#v", entries[len(entries)-1])
	}
	if !containsWriteLog(adapter.WriteLog(), "sync-dir:"+filepath.Join(string(roots.StateRoot), "runs", string(op))) {
		t.Fatalf("run directory sync missing from write log: %v", adapter.WriteLog())
	}
}

func containsWriteLog(log []string, want string) bool {
	for _, entry := range log {
		if entry == want {
			return true
		}
	}
	return false
}
