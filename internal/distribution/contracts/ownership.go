package contracts

import "fmt"

type OwnershipRecord struct {
	Schema          SchemaID       `json:"schema"`
	RecordID        string         `json:"record_id"`
	OperationID     OperationID    `json:"operation_id"`
	InstallationID  InstallationID `json:"installation_id"`
	Sequence        int64          `json:"sequence,omitempty"`
	PreviousHash    *SHA256Hex     `json:"previous_hash"`
	RecordHash      SHA256Hex      `json:"record_hash,omitempty"`
	PlanRef         ArtifactRef    `json:"plan_ref"`
	InventoryRef    ArtifactRef    `json:"inventory_ref"`
	JournalRef      JournalRef     `json:"journal_ref"`
	BackupSetRef    *BackupSetRef  `json:"backup_set_ref"`
	VerificationRef *ArtifactRef   `json:"verification_ref"`
	DeploymentIDs   []string       `json:"deployment_ids"`
	Entries         []JournalEntry `json:"entries"`
	AggregateEvent  string         `json:"aggregate_event"`
	OperationResult string         `json:"operation_result"`
	FailureCode     string         `json:"failure_code,omitempty"`
}

type BackupSetRef struct {
	BackupSetID string    `json:"backup_set_id"`
	SHA256      SHA256Hex `json:"sha256"`
}

type JournalRef struct {
	OperationID string    `json:"operation_id"`
	Path        string    `json:"path"`
	SHA256      SHA256Hex `json:"sha256"`
}

type JournalEntry struct {
	OperationID       string    `json:"operation_id"`
	Boundary          string    `json:"boundary"`
	Result            string    `json:"result"`
	ReceiptSHA256     SHA256Hex `json:"receipt_sha256,omitempty"`
	FinalArtifactPath string    `json:"final_artifact_path,omitempty"`
}

func ValidateOwnershipRecord(record OwnershipRecord) error {
	if record.Schema != SchemaOwnership {
		return fmt.Errorf("invalid ownership schema")
	}
	if record.RecordID == "" || record.OperationID == "" || record.InstallationID == "" {
		return fmt.Errorf("ownership record requires record_id, operation_id, and installation_id")
	}
	if err := ValidateOperationID(record.OperationID); err != nil {
		return err
	}
	if err := ValidateArtifactRef(record.PlanRef); err != nil {
		return fmt.Errorf("plan_ref: %w", err)
	}
	if err := ValidateArtifactRef(record.InventoryRef); err != nil {
		return fmt.Errorf("inventory_ref: %w", err)
	}
	if err := ValidateJournalRef(record.JournalRef, record.OperationID); err != nil {
		return fmt.Errorf("journal_ref: %w", err)
	}
	if record.BackupSetRef != nil {
		if record.BackupSetRef.BackupSetID == "" || !sha256Pattern.MatchString(string(record.BackupSetRef.SHA256)) {
			return fmt.Errorf("backup_set_ref is invalid")
		}
	}
	if record.VerificationRef != nil {
		if err := ValidateArtifactRef(*record.VerificationRef); err != nil {
			return fmt.Errorf("verification_ref: %w", err)
		}
	}
	if len(record.DeploymentIDs) == 0 {
		return fmt.Errorf("ownership record requires deployment_ids")
	}
	if record.AggregateEvent == "" || record.OperationResult == "" {
		return fmt.Errorf("ownership record requires aggregate_event and operation_result")
	}
	switch record.AggregateEvent {
	case "applied_unverified", "restored_unverified", "restored_verified":
		if record.BackupSetRef == nil {
			return fmt.Errorf("%s requires backup_set_ref", record.AggregateEvent)
		}
		if record.VerificationRef != nil && record.AggregateEvent != "restored_verified" {
			return fmt.Errorf("mutator ownership event must not carry verification_ref")
		}
	case "installed_verified", "removed_verified":
		if record.VerificationRef == nil {
			return fmt.Errorf("verified ownership event requires verification_ref")
		}
	case "removed_unverified", "install_rolled_back", "uninstall_rolled_back", "restore_rolled_back", RecoveryRequired:
		if record.AggregateEvent == RecoveryRequired && record.FailureCode == "" {
			return fmt.Errorf("recovery_required ownership event requires failure_code")
		}
	default:
		return fmt.Errorf("unknown aggregate_event %q", record.AggregateEvent)
	}
	return nil
}

func ValidateJournalRef(ref JournalRef, operationID OperationID) error {
	if ref.OperationID == "" || ref.Path == "" || ref.SHA256 == "" {
		return fmt.Errorf("journal_ref requires operation_id, path, and sha256")
	}
	if ref.OperationID != string(operationID) {
		return fmt.Errorf("journal_ref operation_id mismatch")
	}
	if err := ValidateOperationID(ref.OperationID); err != nil {
		return err
	}
	if ref.Path != "runs/"+ref.OperationID+"/journal.ndjson" {
		return fmt.Errorf("journal_ref path must be the operation journal relative path")
	}
	if !sha256Pattern.MatchString(string(ref.SHA256)) {
		return fmt.Errorf("journal_ref sha256 must be lower-case hex SHA-256")
	}
	return nil
}
