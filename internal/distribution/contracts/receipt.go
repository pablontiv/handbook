package contracts

type Receipt struct {
	Schema             SchemaID       `json:"schema"`
	ReceiptID          string         `json:"receipt_id"`
	OperationID        string         `json:"operation_id"`
	Command            string         `json:"command"`
	ApprovalDigest     *SHA256Hex     `json:"approval_digest"`
	LedgerRecordHash   SHA256Hex      `json:"ledger_record_hash"`
	ReadyJournalRef    JournalRef     `json:"ready_journal_ref"`
	TerminalJournalRef *JournalRef    `json:"terminal_journal_ref"`
	PlanRef            *ArtifactRef   `json:"plan_ref"`
	InventoryRef       *ArtifactRef   `json:"inventory_ref"`
	BackupSetRef       *BackupSetRef  `json:"backup_set_ref"`
	VerificationRef    *ArtifactRef   `json:"verification_ref"`
	Preconditions      []Precondition `json:"preconditions"`
	Results            []JournalEntry `json:"results"`
	OperationResult    string         `json:"operation_result"`
}
