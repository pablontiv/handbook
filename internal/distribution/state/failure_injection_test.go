package state_test

import (
	"context"
	"path/filepath"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/state"
)

func TestRecoveryClassificationFailureBoundaries(t *testing.T) {
	ctx := context.Background()

	for _, tc := range []struct {
		name       string
		seed       func(context.Context, *testing.T, *filesystem.MemoryAdapter, state.Store, state.Roots)
		wantStatus string
		wantCode   string
	}{
		{
			name: "interrupted after first durable journal boundary",
			seed: func(ctx context.Context, t *testing.T, _ *filesystem.MemoryAdapter, store state.Store, roots state.Roots) {
				appendJournalBoundary(ctx, t, store, roots, opID("op-started"), "started")
			},
			wantStatus: contracts.RecoveryRequired,
			wantCode:   "interrupted_journal",
		},
		{
			name: "normal ledger and cleanup durable but ready boundary nonterminal",
			seed: func(ctx context.Context, t *testing.T, _ *filesystem.MemoryAdapter, store state.Store, roots state.Roots) {
				ledger, err := store.OpenLedger(ctx, roots)
				if err != nil {
					t.Fatal(err)
				}
				op := opID("op-ready")
				if _, err := ledger.Append(ctx, ownershipRecord("install-ready", op, "applied_unverified")); err != nil {
					t.Fatal(err)
				}
				appendJournalBoundary(ctx, t, store, roots, op, "started")
				appendJournalBoundary(ctx, t, store, roots, op, "ready_to_commit")
			},
			wantStatus: contracts.RecoveryRequired,
			wantCode:   "interrupted_journal",
		},
		{
			name: "receipt draft durable before terminal commit",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) {
				op := opID("op-draft")
				appendJournalBoundary(ctx, t, store, roots, op, "started")
				appendJournalBoundary(ctx, t, store, roots, op, "ready_to_commit")
				adapter.PutFile(contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", op, "receipt.json.draft")), []byte("draft"))
			},
			wantStatus: contracts.RecoveryRequired,
			wantCode:   "interrupted_journal",
		},
		{
			name: "terminal committed before receipt publication",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) {
				op := opID("op-pending")
				appendJournalBoundary(ctx, t, store, roots, op, "started")
				appendJournalBoundary(ctx, t, store, roots, op, "ready_to_commit")
				appendJournalBoundary(ctx, t, store, roots, op, "committed")
				adapter.PutFile(contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", op, "receipt.json.draft")), []byte("draft"))
			},
			wantStatus: contracts.RecoveryRequired,
			wantCode:   "receipt_publish_pending",
		},
		{
			name: "receipt publication complete",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) {
				completeReceiptDAG(ctx, t, adapter, store, roots, "op-complete")
			},
			wantStatus: contracts.RecoveryClean,
			wantCode:   "",
		},
		{
			name: "rollback failed terminal boundary",
			seed: func(ctx context.Context, t *testing.T, _ *filesystem.MemoryAdapter, store state.Store, roots state.Roots) {
				op := opID("op-rbf")
				appendJournalBoundary(ctx, t, store, roots, op, "started")
				appendJournalBoundary(ctx, t, store, roots, op, "rollback_failed")
			},
			wantStatus: contracts.RecoveryRequired,
			wantCode:   "rollback_failed",
		},
		{
			name: "ledger recovery required aggregate event",
			seed: func(ctx context.Context, t *testing.T, _ *filesystem.MemoryAdapter, store state.Store, roots state.Roots) {
				ledger, err := store.OpenLedger(ctx, roots)
				if err != nil {
					t.Fatal(err)
				}
				record := ownershipRecord("install-rec", opID("op-rec"), "recovery_required")
				failure := "mutation_unprovable"
				record.FailureCode = &failure
				record.OperationResult = contracts.RecoveryRequired
				record.CompensatingPriorState = &contracts.CompensatingPriorState{AggregateEvent: "applied_unverified", DeploymentIDs: record.DeploymentIDs, LedgerRecordHash: contracts.SHA256([]byte("prior"))}
				if _, err := ledger.Append(ctx, record); err != nil {
					t.Fatal(err)
				}
			},
			wantStatus: contracts.RecoveryRequired,
			wantCode:   "ledger_recovery_required",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			adapter := filesystem.NewMemoryAdapter()
			store := state.NewStore(adapter)
			roots := tempRoots(t)
			tc.seed(ctx, t, adapter, store, roots)

			status, err := store.ClassifyRecovery(ctx, roots)
			if err != nil {
				t.Fatalf("ClassifyRecovery() error = %v", err)
			}
			if status.Status != tc.wantStatus || status.Code != tc.wantCode {
				t.Fatalf("status = %#v, want status=%q code=%q", status, tc.wantStatus, tc.wantCode)
			}
		})
	}
}

func appendJournalBoundary(ctx context.Context, t *testing.T, store state.Store, roots state.Roots, op, boundary string) {
	t.Helper()
	journal, err := store.OpenJournal(ctx, roots, contracts.OperationID(op), contracts.CommandName("apply"))
	if err != nil {
		t.Fatal(err)
	}
	entry := contracts.JournalEntry{OperationID: op, Boundary: boundary, Result: boundary}
	if boundary == "committed" {
		entry.ReceiptSHA256 = contracts.SHA256([]byte("receipt-" + op))
		entry.FinalArtifactPath = "receipt.json"
	}
	if _, err := journal.Append(ctx, entry); err != nil {
		t.Fatalf("Append(%s/%s) error = %v", op, boundary, err)
	}
}
