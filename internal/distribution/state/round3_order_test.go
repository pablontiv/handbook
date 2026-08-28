package state_test

import (
	"context"
	"path/filepath"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/state"
)

func TestRound3PublishReceiptUsesDistinctPrefixesAndNormativeDurabilityOrder(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	op := contracts.OperationID(opID("round3-order"))

	journal, err := store.OpenJournal(ctx, roots, op, contracts.CommandName("apply"))
	if err != nil {
		t.Fatal(err)
	}
	ledgerPrefix, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "started", Step: "operation_started", SyncBoundary: "journal_append"})
	if err != nil {
		t.Fatalf("Append(started) error = %v", err)
	}

	ledger, err := store.OpenLedger(ctx, roots)
	if err != nil {
		t.Fatal(err)
	}
	record := ownershipRecord("install", string(op), "applied_unverified")
	record.JournalRef = ledgerPrefix
	ledgerHash, err := ledger.Append(ctx, record)
	if err != nil {
		t.Fatalf("Append(ledger) error = %v", err)
	}

	if _, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "step", Step: "cleanup", State: "cleanup_completed", Result: "cleanup_completed", SyncBoundary: "cleanup_journal_append"}); err != nil {
		t.Fatalf("Append(cleanup step) error = %v", err)
	}
	ready, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "ready_to_commit", Result: "ready", Step: "ready", SyncBoundary: "ready_journal_append"})
	if err != nil {
		t.Fatalf("Append(ready) error = %v", err)
	}
	if ready.SHA256 == ledgerPrefix.SHA256 {
		t.Fatalf("ready_journal_ref must bind a later prefix than ledger journal_ref")
	}

	receipt := receiptForTest(op)
	receipt.ReadyJournalRef = ready
	receipt.LedgerRecordHash = ledgerHash
	ref, err := store.PublishReceipt(ctx, roots, op, receipt)
	if err != nil {
		t.Fatalf("PublishReceipt() error = %v", err)
	}
	if ref.Path != "runs/"+string(op)+"/receipt.json" {
		t.Fatalf("receipt ref path = %s", ref.Path)
	}

	reopened, err := store.OpenJournal(ctx, roots, op, contracts.CommandName("apply"))
	if err != nil {
		t.Fatal(err)
	}
	terminal := reopened.Entries()[len(reopened.Entries())-1]
	if terminal.FinalReceiptPath != "receipt.json" {
		t.Fatalf("terminal destination final_receipt_path=%q, want receipt.json", terminal.FinalReceiptPath)
	}

	stateRoot := string(roots.StateRoot)
	journalPath := filepath.Join(stateRoot, "runs", string(op), "journal.ndjson")
	ledgerPath := filepath.Join(stateRoot, "ownership", "installations.ndjson")
	draftPath := filepath.Join(stateRoot, "runs", string(op), "receipt.json.draft")
	finalPath := filepath.Join(stateRoot, "runs", string(op), "receipt.json")
	runDir := filepath.Join(stateRoot, "runs", string(op))
	assertWriteLogOrder(t, adapter.WriteLog(), []string{
		"append:" + journalPath,
		"append:" + ledgerPath,
		"append:" + journalPath, // cleanup step after ledger
		"append:" + journalPath, // ready after cleanup
		"write-no-replace:" + draftPath,
		"append:" + journalPath, // terminal committed after draft durability
		"write-no-replace:" + finalPath,
		"sync-dir:" + runDir,
	})
}

func assertWriteLogOrder(t *testing.T, got []string, wantOrdered []string) {
	t.Helper()
	pos := 0
	for _, entry := range got {
		if pos < len(wantOrdered) && entry == wantOrdered[pos] {
			pos++
		}
	}
	if pos != len(wantOrdered) {
		t.Fatalf("write log did not contain ordered durability protocol\n got: %v\nwant ordered subsequence: %v", got, wantOrdered)
	}
}
