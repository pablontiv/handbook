package contracts_test

import (
	"testing"

	"waywarden/internal/distribution/contracts"
)

func TestReceiptSchemaIsAcyclicAndRejectsTerminalJournalRef(t *testing.T) {
	for _, artifact := range contracts.MinimalCanonicalArtifactsForTest() {
		if artifact.Schema != contracts.SchemaReceipt {
			continue
		}
		var raw map[string]any
		if err := contracts.StrictParseCanonical(artifact.Data, &raw); err != nil {
			t.Fatal(err)
		}
		if _, exists := raw["terminal_journal_ref"]; exists {
			t.Fatalf("minimal receipt still contains terminal_journal_ref: %s", artifact.Data)
		}
		raw["terminal_journal_ref"] = map[string]any{"operation_id": "op", "path": "runs/op/journal.ndjson", "sha256": string(contracts.SHA256([]byte("x")))}
		bad, err := contracts.CanonicalBytes(raw)
		if err != nil {
			t.Fatal(err)
		}
		if err := contracts.ValidateSchema(contracts.SchemaReceipt, bad); err == nil {
			t.Fatalf("ValidateSchema accepted receipt terminal_journal_ref cycle")
		}
	}
}

func TestOwnershipAndReceiptSemanticValidatorsRejectInvalidNullability(t *testing.T) {
	sha := contracts.SHA256([]byte("artifact"))
	artifact := contracts.ArtifactRef{Path: "runs/op/artifact.json", SHA256: sha, Bytes: "2"}
	journal := contracts.JournalRef{OperationID: "op", Path: "runs/op/journal.ndjson", SHA256: sha}
	ownership := contracts.OwnershipRecord{
		Schema:          contracts.SchemaOwnership,
		RecordID:        "record",
		OperationID:     "op",
		InstallationID:  "install",
		PreviousHash:    nil,
		PlanRef:         artifact,
		InventoryRef:    artifact,
		JournalRef:      journal,
		BackupSetRef:    nil,
		VerificationRef: nil,
		DeploymentIDs:   []string{"deployment"},
		Entries:         []contracts.JournalEntry{},
		AggregateEvent:  "applied_unverified",
		OperationResult: "verification_required",
	}
	bytes, err := contracts.CanonicalBytes(ownership)
	if err != nil {
		t.Fatal(err)
	}
	if err := contracts.ValidateSchema(contracts.SchemaOwnership, bytes); err == nil {
		t.Fatalf("ValidateSchema accepted install ownership without backup_set_ref")
	}

	receipt := contracts.Receipt{
		Schema:           contracts.SchemaReceipt,
		ReceiptID:        "receipt",
		OperationID:      "op",
		Command:          "apply",
		ApprovalDigest:   &sha,
		LedgerRecordHash: sha,
		ReadyJournalRef:  journal,
		PlanRef:          &artifact,
		InventoryRef:     &artifact,
		BackupSetRef:     nil,
		VerificationRef:  &artifact,
		Preconditions:    []contracts.Precondition{},
		Results:          []contracts.JournalEntry{},
		OperationResult:  "verification_required",
	}
	bytes, err = contracts.CanonicalBytes(receipt)
	if err != nil {
		t.Fatal(err)
	}
	if err := contracts.ValidateSchema(contracts.SchemaReceipt, bytes); err == nil {
		t.Fatalf("ValidateSchema accepted mutator receipt with verification_ref and no backup_set_ref")
	}
}
