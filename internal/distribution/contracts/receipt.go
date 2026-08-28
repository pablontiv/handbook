package contracts

import "fmt"

type Receipt struct {
	Schema           SchemaID       `json:"schema"`
	ReceiptID        string         `json:"receipt_id"`
	OperationID      string         `json:"operation_id"`
	Command          string         `json:"command"`
	ApprovalDigest   *SHA256Hex     `json:"approval_digest"`
	LedgerRecordHash SHA256Hex      `json:"ledger_record_hash"`
	ReadyJournalRef  JournalRef     `json:"ready_journal_ref"`
	PlanRef          *ArtifactRef   `json:"plan_ref"`
	InventoryRef     *ArtifactRef   `json:"inventory_ref"`
	BackupSetRef     *BackupSetRef  `json:"backup_set_ref"`
	VerificationRef  *ArtifactRef   `json:"verification_ref"`
	Preconditions    []Precondition `json:"preconditions"`
	Results          []JournalEntry `json:"results"`
	OperationResult  string         `json:"operation_result"`
}

func ValidateReceipt(receipt Receipt) error {
	if receipt.Schema != SchemaReceipt {
		return fmt.Errorf("invalid receipt schema")
	}
	if receipt.ReceiptID == "" || receipt.OperationID == "" || receipt.Command == "" {
		return fmt.Errorf("receipt requires receipt_id, operation_id, and command")
	}
	if err := ValidateOperationID(receipt.OperationID); err != nil {
		return err
	}
	if !sha256Pattern.MatchString(string(receipt.LedgerRecordHash)) {
		return fmt.Errorf("ledger_record_hash must be lower-case hex SHA-256")
	}
	if err := ValidateJournalRef(receipt.ReadyJournalRef, receipt.OperationID); err != nil {
		return fmt.Errorf("ready_journal_ref: %w", err)
	}
	if receipt.PlanRef != nil {
		if err := ValidateArtifactRef(*receipt.PlanRef); err != nil {
			return fmt.Errorf("plan_ref: %w", err)
		}
	}
	if receipt.InventoryRef != nil {
		if err := ValidateArtifactRef(*receipt.InventoryRef); err != nil {
			return fmt.Errorf("inventory_ref: %w", err)
		}
	}
	if receipt.BackupSetRef != nil {
		if receipt.BackupSetRef.BackupSetID == "" || !sha256Pattern.MatchString(string(receipt.BackupSetRef.SHA256)) {
			return fmt.Errorf("backup_set_ref is invalid")
		}
	}
	if receipt.VerificationRef != nil {
		if err := ValidateArtifactRef(*receipt.VerificationRef); err != nil {
			return fmt.Errorf("verification_ref: %w", err)
		}
	}
	if receipt.OperationResult == "" {
		return fmt.Errorf("receipt requires operation_result")
	}
	switch receipt.Command {
	case "apply", "restore":
		if receipt.ApprovalDigest == nil || receipt.PlanRef == nil || receipt.InventoryRef == nil || receipt.BackupSetRef == nil {
			return fmt.Errorf("%s receipt requires approval, plan, inventory, and backup refs", receipt.Command)
		}
		if receipt.VerificationRef != nil {
			return fmt.Errorf("mutator receipt must not carry verification_ref")
		}
	case "uninstall":
		if receipt.ApprovalDigest == nil || receipt.PlanRef == nil || receipt.InventoryRef == nil {
			return fmt.Errorf("uninstall receipt requires approval, plan, and inventory refs")
		}
		if receipt.VerificationRef != nil {
			return fmt.Errorf("mutator receipt must not carry verification_ref")
		}
	case "verify":
		if receipt.VerificationRef == nil {
			return fmt.Errorf("verify receipt requires verification_ref")
		}
	default:
		return fmt.Errorf("unknown receipt command %q", receipt.Command)
	}
	if receipt.ApprovalDigest != nil && !sha256Pattern.MatchString(string(*receipt.ApprovalDigest)) {
		return fmt.Errorf("approval_digest must be lower-case hex SHA-256 or null")
	}
	return nil
}
