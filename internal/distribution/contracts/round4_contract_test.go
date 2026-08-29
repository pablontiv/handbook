package contracts_test

import (
	"fmt"
	"testing"

	"waywarden/internal/distribution/contracts"
)

func TestRound4PureAggregateValidatorsAreEnvironmentAgnostic(t *testing.T) {
	artifact := contracts.ArtifactRef{Path: "runs/" + round4OpID("contract") + "/artifact.json", SHA256: contracts.SHA256([]byte("artifact")), Bytes: "8"}
	record := round4OwnershipRecord(round4OpID("contract"), round4DeploymentIDs("home-a"), artifact)
	if err := contracts.ValidateOwnershipRecord(record); err != nil {
		t.Fatalf("ValidateOwnershipRecord rejected dynamic aggregate IDs: %v", err)
	}

	receipt := round4Receipt(record, artifact)
	if err := contracts.ValidateReceipt(receipt); err != nil {
		t.Fatalf("ValidateReceipt rejected dynamic aggregate IDs: %v", err)
	}

	duplicate := record
	duplicate.DeploymentIDs = append([]string(nil), record.DeploymentIDs...)
	duplicate.DeploymentIDs[3] = duplicate.DeploymentIDs[2]
	if err := contracts.ValidateOwnershipRecord(duplicate); err == nil {
		t.Fatalf("ValidateOwnershipRecord accepted duplicate deployment IDs")
	}

	missingBinding := receipt
	missingBinding.DeploymentResults = append([]contracts.OperationDeploymentResult(nil), receipt.DeploymentResults...)
	missingBinding.DeploymentResults[0].RuntimeBindingSummaries = missingBinding.DeploymentResults[0].RuntimeBindingSummaries[:0]
	if err := contracts.ValidateReceipt(missingBinding); err == nil {
		t.Fatalf("ValidateReceipt accepted aggregate with fewer than 15 total runtime bindings")
	}
}

func round4OpID(seed string) string { return string(contracts.SHA256([]byte("round4-op-" + seed))) }

func round4DeploymentIDs(home string) []string {
	ids := make([]string, 10)
	for i := range ids {
		ids[i] = string(contracts.SHA256([]byte(fmt.Sprintf("%s\x00slot-%02d\x00source-%02d", home, i, i))))
	}
	return ids
}

func round4OwnershipRecord(op string, ids []string, artifact contracts.ArtifactRef) contracts.OwnershipRecord {
	deployments := make([]contracts.OwnershipDeploymentRecord, 0, len(ids))
	for i, id := range ids {
		before := contracts.DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/" + id, GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "missing"}
		after := contracts.DeploymentObservation{ObservedType: "symlink", Path: "/runtime/" + id, GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "object-" + id}
		bindings := []contracts.RuntimeBindingSummary{{Runtime: "pi", BindingIdentity: fmt.Sprintf("pi:skill-%02d", i), Status: "verification_required", EvidenceRef: &artifact}}
		if i < 5 {
			bindings = append(bindings, contracts.RuntimeBindingSummary{Runtime: "opencode", BindingIdentity: fmt.Sprintf("opencode:skill-%02d", i), Status: "verification_required", EvidenceRef: &artifact})
		}
		deployments = append(deployments, contracts.OwnershipDeploymentRecord{DeploymentID: id, BeforeObservation: before, AfterObservation: after, RuntimeBindingSummaries: bindings, OriginalPreimage: before, InstalledPostimage: &after, BackupEntryRef: &artifact, CleanupEvidenceRef: &artifact, RollbackAuthorityRefs: []contracts.ArtifactRef{artifact}, Result: "verification_required"})
	}
	approval := artifact.SHA256
	_ = approval
	return contracts.OwnershipRecord{Schema: contracts.SchemaOwnership, RecordID: "record-" + op, OperationID: contracts.OperationID(op), InstallationID: "install", PreviousHash: nil, PlanRef: artifact, InventoryRef: artifact, JournalRef: contracts.JournalRef{OperationID: op, Path: "runs/" + op + "/journal.ndjson", SHA256: artifact.SHA256}, BackupSetRef: &contracts.BackupSetRef{BackupSetID: string(contracts.SHA256([]byte("backup"))), SHA256: artifact.SHA256}, DeploymentIDs: append([]string(nil), ids...), Deployments: deployments, AggregateEvent: "applied_unverified", OperationResult: "verification_required"}
}

func round4Receipt(record contracts.OwnershipRecord, artifact contracts.ArtifactRef) contracts.Receipt {
	approval := artifact.SHA256
	results := make([]contracts.OperationDeploymentResult, 0, len(record.Deployments))
	for _, deployment := range record.Deployments {
		before := deployment.BeforeObservation
		after := deployment.AfterObservation
		results = append(results, contracts.OperationDeploymentResult{DeploymentID: deployment.DeploymentID, Result: deployment.Result, BeforeObservation: &before, AfterObservation: &after, RuntimeBindingSummaries: deployment.RuntimeBindingSummaries, BackupEntryRef: deployment.BackupEntryRef, CleanupEvidenceRef: deployment.CleanupEvidenceRef, RollbackAuthorityRefs: deployment.RollbackAuthorityRefs})
	}
	return contracts.Receipt{Schema: contracts.SchemaReceipt, ReceiptID: "receipt-" + string(record.OperationID), OperationID: string(record.OperationID), Command: "apply", ApprovalDigest: &approval, LedgerRecordHash: artifact.SHA256, ReadyJournalRef: record.JournalRef, PlanRef: &artifact, InventoryRef: &artifact, BackupSetRef: record.BackupSetRef, Preconditions: []contracts.Precondition{}, DeploymentResults: results, RollbackResults: []contracts.OperationDeploymentResult{}, CleanupEvidenceRef: &artifact, RequiredVerificationStatus: "verification_required", OperationResult: "verification_required"}
}
