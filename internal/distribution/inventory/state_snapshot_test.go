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
	record := ownershipRecordForSnapshotTest("install-z", "backup-z", "applied_unverified")
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
	if len(snapshot.Ownership) != 1 || snapshot.Ownership[0].InstallationID != "install-z" || snapshot.Ownership[0].AggregateEvent != "applied_unverified" {
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
	record := ownershipRecordForSnapshotTest("install-z", "backup-z", "applied_unverified")
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
	op := string(contracts.SHA256([]byte("snapshot-op")))
	artifact := contracts.ArtifactRef{Path: "runs/" + op + "/artifact.json", SHA256: sha, Bytes: "2"}
	journal := contracts.JournalRef{OperationID: op, Path: "runs/" + op + "/journal.ndjson", SHA256: sha}
	before := contracts.DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/skill", GovernedSlotIdentity: "slot", ManagedObjectIdentity: "missing"}
	after := contracts.DeploymentObservation{ObservedType: "symlink", Path: "/runtime/skill", GovernedSlotIdentity: "slot", ManagedObjectIdentity: "object", ManagedLinkIdentity: "link", SourceContentDigest: string(sha)}
	deployment := contracts.OwnershipDeploymentRecord{DeploymentID: "deployment", BeforeObservation: before, AfterObservation: after, RuntimeBindingSummaries: []contracts.RuntimeBindingSummary{{Runtime: "pi", BindingIdentity: "pi:/runtime/skill", Status: "verification_required", EvidenceRef: &artifact}}, OriginalPreimage: before, InstalledPostimage: &after, BackupEntryRef: &artifact, VerificationRef: nil, CleanupEvidenceRef: &artifact, RollbackAuthorityRefs: []contracts.ArtifactRef{artifact}, Result: "verification_required"}
	record := contracts.OwnershipRecord{
		Schema:                 contracts.SchemaOwnership,
		RecordID:               "record",
		OperationID:            contracts.OperationID(op),
		InstallationID:         contracts.InstallationID(installationID),
		PreviousHash:           nil,
		PlanRef:                artifact,
		InventoryRef:           artifact,
		JournalRef:             journal,
		BackupSetRef:           &contracts.BackupSetRef{BackupSetID: backupID, SHA256: sha},
		VerificationRef:        nil,
		DeploymentIDs:          []string{"deployment"},
		Deployments:            []contracts.OwnershipDeploymentRecord{deployment},
		AggregateEvent:         event,
		OperationResult:        "verification_required",
		FailureCode:            nil,
		CompensatingPriorState: nil,
	}
	if event == "installed_verified" || event == "removed_verified" || event == "restored_verified" {
		deployment.Result = "verified"
		deployment.VerificationRef = &artifact
		record.Deployments = []contracts.OwnershipDeploymentRecord{deployment}
		record.VerificationRef = &artifact
		record.OperationResult = "verified"
		if event != "restored_verified" {
			record.BackupSetRef = nil
		}
	}
	return record
}
