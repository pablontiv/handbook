package contracts_test

import (
	"testing"

	"waywarden/internal/distribution/contracts"
)

func TestRound3ValidateSchemaRejectsNestedUnknownFields(t *testing.T) {
	for _, tc := range []struct {
		name   string
		schema contracts.SchemaID
		mutate func(map[string]any)
	}{
		{
			name:   "ownership journal_ref",
			schema: contracts.SchemaOwnership,
			mutate: func(doc map[string]any) { doc["journal_ref"].(map[string]any)["unexpected"] = "loophole" },
		},
		{
			name:   "ownership deployment observation",
			schema: contracts.SchemaOwnership,
			mutate: func(doc map[string]any) {
				doc["deployments"].([]any)[0].(map[string]any)["before_observation"].(map[string]any)["unexpected"] = "loophole"
			},
		},
		{
			name:   "receipt ready_journal_ref",
			schema: contracts.SchemaReceipt,
			mutate: func(doc map[string]any) { doc["ready_journal_ref"].(map[string]any)["unexpected"] = "loophole" },
		},
		{
			name:   "receipt deployment result observation",
			schema: contracts.SchemaReceipt,
			mutate: func(doc map[string]any) {
				doc["deployment_results"].([]any)[0].(map[string]any)["after_observation"].(map[string]any)["unexpected"] = "loophole"
			},
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			doc := canonicalDocForSchema(t, tc.schema)
			tc.mutate(doc)
			data, err := contracts.CanonicalBytes(doc)
			if err != nil {
				t.Fatal(err)
			}
			if err := contracts.ValidateSchema(tc.schema, data); err == nil {
				t.Fatalf("ValidateSchema accepted nested unknown field in %s: %s", tc.schema, data)
			}
		})
	}
}

func TestRound3JournalTerminalDestinationIsExactlyReceiptJSON(t *testing.T) {
	op := string(contracts.SHA256([]byte("round3-journal-terminal")))
	sha := contracts.SHA256([]byte("receipt"))
	valid := contracts.JournalEntry{OperationID: op, Command: "apply", Sequence: 3, Boundary: "committed", State: "committed", Result: "verification_required", ReceiptSHA256: sha, FinalReceiptPath: "receipt.json", Terminal: true}
	if err := contracts.ValidateJournalEntry(valid, op); err != nil {
		t.Fatalf("valid terminal journal entry rejected: %v", err)
	}
	legacyAlias := map[string]any{"operation_id": op, "command": "apply", "sequence": int64(3), "boundary": "committed", "state": "committed", "result": "verification_required", "receipt_sha256": string(sha), "final_artifact_path": "receipt.json", "terminal": true}
	legacyBytes, err := contracts.CanonicalBytes(legacyAlias)
	if err != nil {
		t.Fatal(err)
	}
	var decoded contracts.JournalEntry
	if err := contracts.StrictParseCanonical(legacyBytes, &decoded); err == nil {
		t.Fatalf("journal decoding accepted legacy final_artifact_path alias")
	}
	alternate := valid
	alternate.FinalReceiptPath = "nested/receipt.json"
	if err := contracts.ValidateJournalEntry(alternate, op); err == nil {
		t.Fatalf("terminal journal accepted alternate final receipt destination")
	}
}

func TestRound3AggregateAuthorityRequiresExactV1DeploymentAndBindingSets(t *testing.T) {
	oneDeployment := ownershipRecordFixture(t)
	if err := contracts.ValidateOwnershipRecord(oneDeployment); err == nil {
		t.Fatalf("ownership validator accepted legacy 1-deployment aggregate fixture")
	}

	oneReceipt := receiptFixture(t)
	if err := contracts.ValidateReceipt(oneReceipt); err == nil {
		t.Fatalf("receipt validator accepted legacy 1-deployment aggregate fixture")
	}

	exact := exactAggregateOwnershipFixture(t)
	if err := contracts.ValidateOwnershipRecord(exact); err != nil {
		t.Fatalf("exact aggregate ownership rejected: %v", err)
	}
	duplicate := exact
	duplicate.DeploymentIDs = append([]string(nil), exact.DeploymentIDs...)
	duplicate.DeploymentIDs[1] = duplicate.DeploymentIDs[0]
	if err := contracts.ValidateOwnershipRecord(duplicate); err == nil {
		t.Fatalf("ownership validator accepted duplicate deployment ID in exact aggregate")
	}

	exactReceipt := exactAggregateReceiptFixture(t)
	if err := contracts.ValidateReceipt(exactReceipt); err != nil {
		t.Fatalf("exact aggregate receipt rejected: %v", err)
	}
	missingBinding := exactReceipt
	missingBinding.DeploymentResults = cloneDeploymentResults(exactReceipt.DeploymentResults)
	missingBinding.DeploymentResults[0].RuntimeBindingSummaries = missingBinding.DeploymentResults[0].RuntimeBindingSummaries[:1]
	if err := contracts.ValidateReceipt(missingBinding); err == nil {
		t.Fatalf("receipt validator accepted missing runtime binding from exact aggregate")
	}
}

func canonicalDocForSchema(t *testing.T, schema contracts.SchemaID) map[string]any {
	t.Helper()
	for _, artifact := range contracts.MinimalCanonicalArtifactsForTest() {
		if artifact.Schema != schema {
			continue
		}
		var doc map[string]any
		if err := contracts.StrictParseCanonical(artifact.Data, &doc); err != nil {
			t.Fatal(err)
		}
		return doc
	}
	t.Fatalf("missing minimal artifact for %s", schema)
	return nil
}

func ownershipRecordFixture(t *testing.T) contracts.OwnershipRecord {
	t.Helper()
	op := string(contracts.SHA256([]byte("round3-one-op")))
	sha := contracts.SHA256([]byte("artifact"))
	artifact := contracts.ArtifactRef{Path: "runs/" + op + "/artifact.json", SHA256: sha, Bytes: "8"}
	deployment := contracts.OwnershipDeploymentRecord{
		DeploymentID:            "deployment-a",
		BeforeObservation:       contracts.DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/skill", GovernedSlotIdentity: "slot-a", ManagedObjectIdentity: "missing"},
		AfterObservation:        contracts.DeploymentObservation{ObservedType: "symlink", Path: "/runtime/skill", GovernedSlotIdentity: "slot-a", ManagedObjectIdentity: "object-a"},
		RuntimeBindingSummaries: []contracts.RuntimeBindingSummary{{Runtime: "pi", BindingIdentity: "pi:/runtime/skill", Status: "verification_required", EvidenceRef: &artifact}},
		OriginalPreimage:        contracts.DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/skill", GovernedSlotIdentity: "slot-a", ManagedObjectIdentity: "missing"},
		InstalledPostimage:      &contracts.DeploymentObservation{ObservedType: "symlink", Path: "/runtime/skill", GovernedSlotIdentity: "slot-a", ManagedObjectIdentity: "object-a"},
		BackupEntryRef:          &artifact,
		CleanupEvidenceRef:      &artifact,
		RollbackAuthorityRefs:   []contracts.ArtifactRef{artifact},
		Result:                  "verification_required",
	}
	return contracts.OwnershipRecord{Schema: contracts.SchemaOwnership, RecordID: "record", OperationID: op, InstallationID: "install", PreviousHash: nil, PlanRef: artifact, InventoryRef: artifact, JournalRef: contracts.JournalRef{OperationID: op, Path: "runs/" + op + "/journal.ndjson", SHA256: sha}, BackupSetRef: &contracts.BackupSetRef{BackupSetID: string(contracts.SHA256([]byte("backup"))), SHA256: sha}, DeploymentIDs: []string{"deployment-a"}, Deployments: []contracts.OwnershipDeploymentRecord{deployment}, AggregateEvent: "applied_unverified", OperationResult: "verification_required"}
}

func receiptFixture(t *testing.T) contracts.Receipt {
	t.Helper()
	record := ownershipRecordFixture(t)
	artifact := record.PlanRef
	approval := artifact.SHA256
	before := record.Deployments[0].BeforeObservation
	after := record.Deployments[0].AfterObservation
	return contracts.Receipt{Schema: contracts.SchemaReceipt, ReceiptID: "receipt", OperationID: string(record.OperationID), Command: "apply", ApprovalDigest: &approval, LedgerRecordHash: artifact.SHA256, ReadyJournalRef: record.JournalRef, PlanRef: &artifact, InventoryRef: &artifact, BackupSetRef: record.BackupSetRef, Preconditions: []contracts.Precondition{}, DeploymentResults: []contracts.OperationDeploymentResult{{DeploymentID: "deployment-a", Result: "verification_required", BeforeObservation: &before, AfterObservation: &after, RuntimeBindingSummaries: record.Deployments[0].RuntimeBindingSummaries, BackupEntryRef: &artifact, CleanupEvidenceRef: &artifact}}, RollbackResults: []contracts.OperationDeploymentResult{}, CleanupEvidenceRef: &artifact, RequiredVerificationStatus: "verification_required", OperationResult: "verification_required"}
}

func exactAggregateOwnershipFixture(t *testing.T) contracts.OwnershipRecord {
	t.Helper()
	record := ownershipRecordFixture(t)
	record.DeploymentIDs = round3AggregateDeploymentIDs()
	record.Deployments = exactOwnershipDeployments(record.PlanRef)
	return record
}

func exactAggregateReceiptFixture(t *testing.T) contracts.Receipt {
	t.Helper()
	receipt := receiptFixture(t)
	receipt.DeploymentResults = exactReceiptDeploymentResults(*receipt.PlanRef)
	return receipt
}

func exactOwnershipDeployments(artifact contracts.ArtifactRef) []contracts.OwnershipDeploymentRecord {
	ids := round3AggregateDeploymentIDs()
	bindings := round3AggregateRuntimeBindings()
	out := make([]contracts.OwnershipDeploymentRecord, 0, len(ids))
	for _, id := range ids {
		before := contracts.DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/" + id, GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "missing"}
		after := contracts.DeploymentObservation{ObservedType: "symlink", Path: "/runtime/" + id, GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "object-" + id}
		deployment := contracts.OwnershipDeploymentRecord{DeploymentID: id, BeforeObservation: before, AfterObservation: after, OriginalPreimage: before, InstalledPostimage: &after, BackupEntryRef: &artifact, CleanupEvidenceRef: &artifact, RollbackAuthorityRefs: []contracts.ArtifactRef{artifact}, Result: "verification_required"}
		for _, binding := range bindings {
			if binding.DeploymentID == id {
				deployment.RuntimeBindingSummaries = append(deployment.RuntimeBindingSummaries, contracts.RuntimeBindingSummary{Runtime: binding.Runtime, BindingIdentity: binding.Runtime + ":" + binding.Name, Status: "verification_required", EvidenceRef: &artifact})
			}
		}
		out = append(out, deployment)
	}
	return out
}

func round3AggregateDeploymentIDs() []string {
	ids := make([]string, 10)
	for i := range ids {
		ids[i] = string(contracts.SHA256([]byte("round3-contract-deployment-" + string(rune('a'+i)))))
	}
	return ids
}

func round3AggregateRuntimeBindings() []contracts.RuntimeBinding {
	ids := round3AggregateDeploymentIDs()
	out := make([]contracts.RuntimeBinding, 0, 15)
	for i, id := range ids {
		name := "skill-" + string(rune('a'+i))
		out = append(out, contracts.RuntimeBinding{DeploymentID: id, Runtime: "pi", Root: ".agents/skills", Name: name, Target: "skills/" + name})
		if i < 5 {
			out = append(out, contracts.RuntimeBinding{DeploymentID: id, Runtime: "opencode", Root: ".agents/skills", Name: name, Target: "skills/" + name})
		}
	}
	return out
}

func exactReceiptDeploymentResults(artifact contracts.ArtifactRef) []contracts.OperationDeploymentResult {
	deployments := exactOwnershipDeployments(artifact)
	out := make([]contracts.OperationDeploymentResult, 0, len(deployments))
	for _, deployment := range deployments {
		before := deployment.BeforeObservation
		after := deployment.AfterObservation
		out = append(out, contracts.OperationDeploymentResult{DeploymentID: deployment.DeploymentID, Result: deployment.Result, BeforeObservation: &before, AfterObservation: &after, RuntimeBindingSummaries: deployment.RuntimeBindingSummaries, BackupEntryRef: deployment.BackupEntryRef, CleanupEvidenceRef: deployment.CleanupEvidenceRef, RollbackAuthorityRefs: deployment.RollbackAuthorityRefs})
	}
	return out
}

func cloneDeploymentResults(in []contracts.OperationDeploymentResult) []contracts.OperationDeploymentResult {
	out := append([]contracts.OperationDeploymentResult(nil), in...)
	for i := range out {
		out[i].RuntimeBindingSummaries = append([]contracts.RuntimeBindingSummary(nil), out[i].RuntimeBindingSummaries...)
	}
	return out
}
