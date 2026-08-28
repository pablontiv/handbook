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

func TestTask6DurabilityBoundaryFailureInjection(t *testing.T) {
	ctx := context.Background()
	ambiguous := errors.New("ambiguous durability failure")
	for _, tc := range []struct {
		name string
		seed func(context.Context, *testing.T, *filesystem.MemoryAdapter, state.Store, state.Roots) error
	}{
		{
			name: "parent sync for new journal authority after sync error",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) error {
				op := contracts.OperationID(strings.Repeat("1", 64))
				adapter.SetWriteFailure("ensure-dir", contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op))), filesystem.FailAfterWrite, ambiguous)
				journal, err := store.OpenJournal(ctx, roots, op, "apply")
				if err != nil {
					return err
				}
				_, err = journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "started"})
				return err
			},
		},
		{
			name: "journal append written but error",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) error {
				op := contracts.OperationID(strings.Repeat("2", 64))
				journalPath := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op), "journal.ndjson"))
				adapter.SetWriteFailure("append", journalPath, filesystem.FailAfterWrite, ambiguous)
				journal, err := store.OpenJournal(ctx, roots, op, "apply")
				if err != nil {
					return err
				}
				_, err = journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "started"})
				return err
			},
		},
		{
			name: "cleanup evidence publication written but error",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) error {
				op := contracts.OperationID(strings.Repeat("3", 64))
				cleanupPath := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op), "cleanup.json"))
				adapter.SetWriteFailure("write-no-replace", cleanupPath, filesystem.FailAfterWrite, ambiguous)
				_, err := store.PublishRunArtifact(ctx, roots, op, "cleanup.json", []byte(`{"cleanup":"done"}`))
				return err
			},
		},
		{
			name: "ledger append written but error",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) error {
				op := opID("round2-ledger-fail")
				appendJournalBoundary(ctx, t, store, roots, op, "started")
				ledgerPath := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "ownership", "installations.ndjson"))
				adapter.SetWriteFailure("append", ledgerPath, filesystem.FailAfterWrite, ambiguous)
				ledger, err := store.OpenLedger(ctx, roots)
				if err != nil {
					return err
				}
				_, err = ledger.Append(ctx, ownershipRecord("install-ledger", op, "applied_unverified"))
				return err
			},
		},
		{
			name: "ready journal append written but error",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) error {
				op := contracts.OperationID(opID("round2-ready-fail"))
				journal, err := store.OpenJournal(ctx, roots, op, "apply")
				if err != nil {
					return err
				}
				if _, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "started"}); err != nil {
					return err
				}
				journalPath := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op), "journal.ndjson"))
				adapter.SetWriteFailure("append", journalPath, filesystem.FailAfterWrite, ambiguous)
				_, err = journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "ready_to_commit", Result: "ready"})
				return err
			},
		},
		{
			name: "receipt draft written but error",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) error {
				op := contracts.OperationID(opID("round2-draft-fail"))
				receipt := prepareReceiptProtocol(ctx, t, store, roots, op)
				draftPath := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op), "receipt.json.draft"))
				adapter.SetWriteFailure("write-no-replace", draftPath, filesystem.FailAfterWrite, ambiguous)
				_, err := store.PublishReceipt(ctx, roots, op, receipt)
				return err
			},
		},
		{
			name: "terminal append written but error",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) error {
				op := contracts.OperationID(opID("round2-terminal-fail"))
				receipt := prepareReceiptProtocol(ctx, t, store, roots, op)
				journalPath := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op), "journal.ndjson"))
				adapter.SetWriteFailure("append", journalPath, filesystem.FailAfterWrite, ambiguous)
				_, err := store.PublishReceipt(ctx, roots, op, receipt)
				return err
			},
		},
		{
			name: "final no-replace receipt publication written but error",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) error {
				op := contracts.OperationID(opID("round2-final-fail"))
				receipt := prepareReceiptProtocol(ctx, t, store, roots, op)
				finalPath := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op), "receipt.json"))
				adapter.SetWriteFailure("write-no-replace", finalPath, filesystem.FailAfterWrite, ambiguous)
				_, err := store.PublishReceipt(ctx, roots, op, receipt)
				return err
			},
		},
		{
			name: "run directory sync after receipt publication error",
			seed: func(ctx context.Context, t *testing.T, adapter *filesystem.MemoryAdapter, store state.Store, roots state.Roots) error {
				op := contracts.OperationID(opID("round2-run-sync-fail"))
				receipt := prepareReceiptProtocol(ctx, t, store, roots, op)
				runDir := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op)))
				adapter.SetWriteFailure("sync-dir", runDir, filesystem.FailAfterWrite, ambiguous)
				_, err := store.PublishReceipt(ctx, roots, op, receipt)
				return err
			},
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			adapter := filesystem.NewMemoryAdapter()
			store := state.NewStore(adapter)
			roots := tempRoots(t)
			if err := tc.seed(ctx, t, adapter, store, roots); !errors.Is(err, ambiguous) {
				t.Fatalf("seed error = %v, want ambiguous injected failure", err)
			}
			status, err := store.ClassifyRecovery(ctx, roots)
			if err != nil {
				t.Fatalf("ClassifyRecovery() error = %v", err)
			}
			if status.Status != contracts.RecoveryRequired {
				t.Fatalf("status = %#v, want recovery_required after ambiguous boundary", status)
			}
		})
	}
}
