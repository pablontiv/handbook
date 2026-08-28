package state_test

import (
	"context"
	"path/filepath"
	"strings"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/state"
)

func TestRecoveryValidatesReceiptTerminalDigestAndEdges(t *testing.T) {
	ctx := context.Background()
	for _, tc := range []struct {
		name   string
		tamper func(*testing.T, *filesystem.MemoryAdapter, state.Roots, contracts.OperationID, contracts.Receipt)
	}{
		{
			name: "malformed published receipt canonical document",
			tamper: func(t *testing.T, adapter *filesystem.MemoryAdapter, roots state.Roots, op contracts.OperationID, _ contracts.Receipt) {
				adapter.PutFile(receiptPath(roots, op), []byte("{not-json"))
			},
		},
		{
			name: "terminal digest differs from final published bytes",
			tamper: func(t *testing.T, adapter *filesystem.MemoryAdapter, roots state.Roots, op contracts.OperationID, receipt contracts.Receipt) {
				receipt.ReceiptID = "tampered"
				bytes, err := contracts.CanonicalBytes(receipt)
				if err != nil {
					t.Fatal(err)
				}
				adapter.PutFile(receiptPath(roots, op), bytes)
			},
		},
		{
			name: "receipt ready journal ref hash mismatch",
			tamper: func(t *testing.T, adapter *filesystem.MemoryAdapter, roots state.Roots, op contracts.OperationID, receipt contracts.Receipt) {
				receipt.ReadyJournalRef.SHA256 = contracts.SHA256([]byte("wrong-ready"))
				bytes, err := contracts.CanonicalBytes(receipt)
				if err != nil {
					t.Fatal(err)
				}
				adapter.PutFile(receiptPath(roots, op), bytes)
			},
		},
		{
			name: "receipt operation id mismatch",
			tamper: func(t *testing.T, adapter *filesystem.MemoryAdapter, roots state.Roots, op contracts.OperationID, receipt contracts.Receipt) {
				other := contracts.OperationID(strings.Repeat("d", 64))
				receipt.OperationID = string(other)
				receipt.ReadyJournalRef.OperationID = string(other)
				receipt.ReadyJournalRef.Path = "runs/" + string(other) + "/journal.ndjson"
				if receipt.PlanRef != nil {
					receipt.PlanRef.Path = "runs/" + string(other) + "/plan.json"
				}
				if receipt.InventoryRef != nil {
					receipt.InventoryRef.Path = "runs/" + string(other) + "/inventory.json"
				}
				bytes, err := contracts.CanonicalBytes(receipt)
				if err != nil {
					t.Fatal(err)
				}
				adapter.PutFile(receiptPath(roots, op), bytes)
			},
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			adapter := filesystem.NewMemoryAdapter()
			store := state.NewStore(adapter)
			roots := tempRoots(t)
			op, receipt := completeReceiptDAG(ctx, t, adapter, store, roots, "round2-recovery-"+tc.name)
			tc.tamper(t, adapter, roots, op, receipt)

			status, err := store.ClassifyRecovery(ctx, roots)
			if err != nil {
				t.Fatalf("ClassifyRecovery() error = %v", err)
			}
			if status.Status != contracts.RecoveryRequired {
				t.Fatalf("status = %#v, want recovery_required", status)
			}
		})
	}
}

func TestRecoveryRequiresOperatorForUnknownRunEvidenceWithoutJournal(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	op := contracts.OperationID(strings.Repeat("e", 64))
	adapter.PutFile(contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op), "cleanup.json")), []byte(`{"cleanup":"durable"}`))
	status, err := store.ClassifyRecovery(ctx, roots)
	if err != nil {
		t.Fatalf("ClassifyRecovery() error = %v", err)
	}
	if status.Status != contracts.RecoveryRequired {
		t.Fatalf("status = %#v, want recovery_required for unknown run evidence", status)
	}
}

func TestRecoveryRejectsCrossOperationReceiptSwaps(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	opA, _ := completeReceiptDAG(ctx, t, adapter, store, roots, "swap-a")
	opB, _ := completeReceiptDAG(ctx, t, adapter, store, roots, "swap-b")
	bytesA, err := adapter.ReadFile(ctx, receiptPath(roots, opA))
	if err != nil {
		t.Fatal(err)
	}
	bytesB, err := adapter.ReadFile(ctx, receiptPath(roots, opB))
	if err != nil {
		t.Fatal(err)
	}
	adapter.PutFile(receiptPath(roots, opA), bytesB)
	adapter.PutFile(receiptPath(roots, opB), bytesA)

	status, err := store.ClassifyRecovery(ctx, roots)
	if err != nil {
		t.Fatalf("ClassifyRecovery() error = %v", err)
	}
	if status.Status != contracts.RecoveryRequired {
		t.Fatalf("status = %#v, want recovery_required for cross-operation swapped receipts", status)
	}
}

func completeReceiptDAG(ctx context.Context, t *testing.T, _ *filesystem.MemoryAdapter, store state.Store, roots state.Roots, seed string) (contracts.OperationID, contracts.Receipt) {
	t.Helper()
	op := contracts.OperationID(string(contracts.SHA256([]byte(seed))))
	receipt := prepareReceiptProtocol(ctx, t, store, roots, op)
	if _, err := store.PublishReceipt(ctx, roots, op, receipt); err != nil {
		t.Fatalf("PublishReceipt() error = %v", err)
	}
	status, err := store.ClassifyRecovery(ctx, roots)
	if err != nil {
		t.Fatalf("ClassifyRecovery(clean baseline) error = %v", err)
	}
	if status.Status != contracts.RecoveryClean {
		t.Fatalf("baseline status = %#v, want clean", status)
	}
	return op, receipt
}

func receiptPath(roots state.Roots, op contracts.OperationID) contracts.AbsolutePath {
	return contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op), "receipt.json"))
}
