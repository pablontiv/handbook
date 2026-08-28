package contracts_test

import (
	"testing"

	"waywarden/internal/distribution/contracts"
)

func TestOwnershipRecordRequiresAggregateOwnedEvidenceFields(t *testing.T) {
	op := string(contracts.SHA256([]byte("round2-op")))
	sha := contracts.SHA256([]byte("artifact"))
	artifact := contracts.ArtifactRef{Path: "runs/" + op + "/artifact.json", SHA256: sha, Bytes: "8"}
	journal := contracts.JournalRef{OperationID: op, Path: "runs/" + op + "/journal.ndjson", SHA256: sha}
	obsBefore := contracts.DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/skill", GovernedSlotIdentity: "slot-a", ManagedObjectIdentity: "missing", ManagedLinkIdentity: "", LexicalLinkTarget: "", SourceContentDigest: "", AttributesFingerprint: "attrs-before"}
	obsAfter := contracts.DeploymentObservation{ObservedType: "symlink", Path: "/runtime/skill", GovernedSlotIdentity: "slot-a", ManagedObjectIdentity: "object-a", ManagedLinkIdentity: "link-a", LexicalLinkTarget: "/repo/skills/skill", SourceContentDigest: string(sha), AttributesFingerprint: "attrs-after"}
	deployment := contracts.OwnershipDeploymentRecord{
		DeploymentID:            "deployment-a",
		BeforeObservation:       obsBefore,
		AfterObservation:        obsAfter,
		RuntimeBindingSummaries: []contracts.RuntimeBindingSummary{{Runtime: "pi", BindingIdentity: "pi:/runtime/skill", Status: "verification_required", EvidenceRef: &artifact}, {Runtime: "opencode", BindingIdentity: "opencode:/runtime/skill", Status: "verification_required", EvidenceRef: &artifact}},
		OriginalPreimage:        obsBefore,
		InstalledPostimage:      &obsAfter,
		BackupEntryRef:          &artifact,
		VerificationRef:         nil,
		CleanupEvidenceRef:      &artifact,
		RollbackAuthorityRefs:   []contracts.ArtifactRef{artifact},
		Result:                  "verification_required",
	}
	record := contracts.OwnershipRecord{
		Schema:                 contracts.SchemaOwnership,
		RecordID:               "record-round2",
		OperationID:            contracts.OperationID(op),
		InstallationID:         "installation-round2",
		PreviousHash:           nil,
		PlanRef:                artifact,
		InventoryRef:           artifact,
		JournalRef:             journal,
		BackupSetRef:           &contracts.BackupSetRef{BackupSetID: "backup-round2", SHA256: sha},
		VerificationRef:        nil,
		DeploymentIDs:          []string{"deployment-a"},
		Deployments:            []contracts.OwnershipDeploymentRecord{deployment},
		AggregateEvent:         "applied_unverified",
		OperationResult:        "verification_required",
		FailureCode:            nil,
		CompensatingPriorState: nil,
	}
	canonical, err := contracts.CanonicalBytes(record)
	if err != nil {
		t.Fatal(err)
	}
	if err := contracts.ValidateSchema(contracts.SchemaOwnership, canonical); err != nil {
		t.Fatalf("valid aggregate ownership evidence rejected: %v", err)
	}

	missingDeployment := record
	missingDeployment.Deployments = nil
	mustRejectOwnership(t, missingDeployment, "missing deployment records")

	mismatchedCardinality := record
	mismatchedCardinality.DeploymentIDs = []string{"deployment-a", "deployment-b"}
	mustRejectOwnership(t, mismatchedCardinality, "incomplete aggregate cardinality")

	duplicateDeployment := record
	duplicateDeployment.Deployments = append(duplicateDeployment.Deployments, deployment)
	mustRejectOwnership(t, duplicateDeployment, "duplicate deployment identity")

	duplicateBinding := record
	duplicateBinding.Deployments = []contracts.OwnershipDeploymentRecord{deployment}
	duplicateBinding.Deployments[0].RuntimeBindingSummaries = append(duplicateBinding.Deployments[0].RuntimeBindingSummaries, deployment.RuntimeBindingSummaries[0])
	mustRejectOwnership(t, duplicateBinding, "duplicate runtime binding identity")

	contradictoryVerify := record
	contradictoryVerify.AggregateEvent = "installed_verified"
	contradictoryVerify.OperationResult = "verification_required"
	contradictoryVerify.VerificationRef = nil
	mustRejectOwnership(t, contradictoryVerify, "verified event without verification ref/result")

	compensatingWithoutPrior := record
	compensatingWithoutPrior.AggregateEvent = "install_rolled_back"
	compensatingWithoutPrior.OperationResult = "rolled_back"
	compensatingWithoutPrior.FailureCode = ptr("state_or_io_failure_preterminal")
	compensatingWithoutPrior.CompensatingPriorState = nil
	mustRejectOwnership(t, compensatingWithoutPrior, "compensation without prior state")
}

func TestReceiptRecordsReadyAuthorityAndDeploymentRollbackEvidence(t *testing.T) {
	op := string(contracts.SHA256([]byte("round2-receipt-op")))
	sha := contracts.SHA256([]byte("artifact"))
	artifact := contracts.ArtifactRef{Path: "runs/" + op + "/artifact.json", SHA256: sha, Bytes: "8"}
	ready := contracts.JournalRef{OperationID: op, Path: "runs/" + op + "/journal.ndjson", SHA256: sha}
	deploymentResult := contracts.OperationDeploymentResult{DeploymentID: "deployment-a", Result: "verification_required", BeforeObservation: &contracts.DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/skill", GovernedSlotIdentity: "slot-a", ManagedObjectIdentity: "missing"}, AfterObservation: &contracts.DeploymentObservation{ObservedType: "symlink", Path: "/runtime/skill", GovernedSlotIdentity: "slot-a", ManagedObjectIdentity: "object-a", ManagedLinkIdentity: "link-a"}, RuntimeBindingSummaries: []contracts.RuntimeBindingSummary{{Runtime: "pi", BindingIdentity: "pi:/runtime/skill", Status: "verification_required", EvidenceRef: &artifact}}, BackupEntryRef: &artifact, CleanupEvidenceRef: &artifact}
	approval := sha
	receipt := contracts.Receipt{Schema: contracts.SchemaReceipt, ReceiptID: "receipt-round2", OperationID: op, Command: "apply", ApprovalDigest: &approval, LedgerRecordHash: sha, ReadyJournalRef: ready, PlanRef: &artifact, InventoryRef: &artifact, BackupSetRef: &contracts.BackupSetRef{BackupSetID: "backup-round2", SHA256: sha}, VerificationRef: nil, Preconditions: []contracts.Precondition{}, DeploymentResults: []contracts.OperationDeploymentResult{deploymentResult}, RollbackResults: []contracts.OperationDeploymentResult{}, CleanupEvidenceRef: &artifact, RequiredVerificationStatus: "verification_required", OperationResult: "verification_required"}
	canonical, err := contracts.CanonicalBytes(receipt)
	if err != nil {
		t.Fatal(err)
	}
	if err := contracts.ValidateSchema(contracts.SchemaReceipt, canonical); err != nil {
		t.Fatalf("valid receipt evidence rejected: %v", err)
	}

	missingResults := receipt
	missingResults.DeploymentResults = nil
	mustRejectReceipt(t, missingResults, "missing deployment results")

	verifyWithApproval := receipt
	verifyWithApproval.Command = "verify"
	verifyWithApproval.ApprovalDigest = &approval
	verifyWithApproval.BackupSetRef = nil
	verifyWithApproval.VerificationRef = &artifact
	verifyWithApproval.RequiredVerificationStatus = "verified"
	verifyWithApproval.OperationResult = "verified"
	mustRejectReceipt(t, verifyWithApproval, "verification receipt with non-null approval digest")

	rollbackClaimMissingEvidence := receipt
	rollbackClaimMissingEvidence.OperationResult = "rolled_back"
	rollbackClaimMissingEvidence.RollbackResults = nil
	mustRejectReceipt(t, rollbackClaimMissingEvidence, "rolled_back receipt missing rollback evidence")
}

func TestJournalEntriesUseTypedSequenceAndTerminalReceiptDestination(t *testing.T) {
	op := string(contracts.SHA256([]byte("round2-journal-op")))
	sha := contracts.SHA256([]byte("artifact"))
	artifact := contracts.ArtifactRef{Path: "runs/" + op + "/artifact.json", SHA256: sha, Bytes: "8"}
	started := contracts.JournalEntry{OperationID: op, Command: "apply", Intent: "install", StateRoot: "/state", Sequence: 1, Step: "start", Boundary: "started", Result: "started", State: "started", DeploymentRefs: []string{"deployment-a"}, GovernedSlotRefs: []string{"slot-a"}, BackupSetRef: nil, VerificationRef: nil, RollbackAuthorityRefs: []contracts.ArtifactRef{artifact}, SyncBoundary: "journal_append", Terminal: false}
	if err := contracts.ValidateJournalEntry(started, op); err != nil {
		t.Fatalf("valid started journal entry rejected: %v", err)
	}
	committed := started
	committed.Sequence = 3
	committed.Step = "terminal_commit"
	committed.Boundary = "committed"
	committed.State = "committed"
	committed.Result = "verification_required"
	committed.ReceiptSHA256 = sha
	committed.FinalReceiptPath = "receipt.json"
	committed.Terminal = true
	committed.SyncBoundary = "terminal_journal_append"
	if err := contracts.ValidateJournalEntry(committed, op); err != nil {
		t.Fatalf("valid committed journal entry rejected: %v", err)
	}
	bad := committed
	bad.FinalReceiptPath = "../receipt.json"
	if err := contracts.ValidateJournalEntry(bad, op); err == nil {
		t.Fatalf("committed journal accepted escaped final receipt destination")
	}
	bad = started
	bad.Sequence = 0
	if err := contracts.ValidateJournalEntry(bad, op); err == nil {
		t.Fatalf("journal accepted missing typed sequence")
	}
}

func mustRejectOwnership(t *testing.T, record contracts.OwnershipRecord, reason string) {
	t.Helper()
	canonical, err := contracts.CanonicalBytes(record)
	if err != nil {
		t.Fatal(err)
	}
	if err := contracts.ValidateSchema(contracts.SchemaOwnership, canonical); err == nil {
		t.Fatalf("ValidateSchema accepted %s", reason)
	}
}

func mustRejectReceipt(t *testing.T, receipt contracts.Receipt, reason string) {
	t.Helper()
	canonical, err := contracts.CanonicalBytes(receipt)
	if err != nil {
		t.Fatal(err)
	}
	if err := contracts.ValidateSchema(contracts.SchemaReceipt, canonical); err == nil {
		t.Fatalf("ValidateSchema accepted %s", reason)
	}
}

func ptr(value string) *string { return &value }
