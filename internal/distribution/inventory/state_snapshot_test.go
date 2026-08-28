package inventory

import (
	"context"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

func TestSnapshotStateReadsCompleteLedgerRecordsUnderSharedLock(t *testing.T) {
	adapter := filesystem.NewMemoryAdapter()
	stateRoot := contracts.AbsolutePath("/state")
	lockRoot := contracts.AbsolutePath("/locks")
	record := ownershipRecordForSnapshotTest("install-z", "backup-z", "installed_verified")
	line, err := contracts.CanonicalBytes(record)
	if err != nil {
		t.Fatal(err)
	}
	adapter.PutFile(ledgerPath(stateRoot), append(line, '\n'))

	snapshot, err := snapshotState(context.Background(), adapter, stateRoot, lockRoot)
	if err != nil {
		t.Fatalf("snapshotState() error = %v", err)
	}
	if got := adapter.SharedLockKeys(); len(got) != 1 {
		t.Fatalf("shared locks = %v, want one", got)
	}
	if len(snapshot.Ownership) != 1 || snapshot.Ownership[0].InstallationID != "install-z" || snapshot.Ownership[0].AggregateEvent != "installed_verified" {
		t.Fatalf("ownership snapshot = %#v", snapshot.Ownership)
	}
	if len(snapshot.Backups) != 1 || snapshot.Backups[0].BackupSetID != "backup-z" || snapshot.Backups[0].InstallationID != "install-z" {
		t.Fatalf("backup snapshot = %#v", snapshot.Backups)
	}
}

func TestSnapshotStateRejectsTruncatedLedgerTail(t *testing.T) {
	adapter := filesystem.NewMemoryAdapter()
	stateRoot := contracts.AbsolutePath("/state")
	lockRoot := contracts.AbsolutePath("/locks")
	record := ownershipRecordForSnapshotTest("install-z", "backup-z", "installed_verified")
	line, err := contracts.CanonicalBytes(record)
	if err != nil {
		t.Fatal(err)
	}
	adapter.PutFile(ledgerPath(stateRoot), line)

	if _, err := snapshotState(context.Background(), adapter, stateRoot, lockRoot); err == nil {
		t.Fatalf("snapshotState() accepted non-newline-terminated ledger")
	}
}

func ownershipRecordForSnapshotTest(installationID, backupID, event string) contracts.OwnershipRecord {
	sha := contracts.SHA256([]byte("artifact"))
	artifact := contracts.ArtifactRef{Path: "runs/op/artifact.json", SHA256: sha, Bytes: "2"}
	journal := contracts.JournalRef{OperationID: "op", Path: "runs/op/journal.ndjson", SHA256: sha}
	return contracts.OwnershipRecord{
		Schema:          contracts.SchemaOwnership,
		RecordID:        "record",
		InstallationID:  installationID,
		PreviousHash:    nil,
		PlanRef:         artifact,
		InventoryRef:    artifact,
		JournalRef:      journal,
		BackupSetRef:    &contracts.BackupSetRef{BackupSetID: backupID, SHA256: sha},
		VerificationRef: nil,
		Entries:         []contracts.JournalEntry{},
		AggregateEvent:  event,
		OperationResult: "verification_required",
	}
}
