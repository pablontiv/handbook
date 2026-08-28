package contracts

type OwnershipRecord struct {
	Schema          SchemaID       `json:"schema"`
	RecordID        string         `json:"record_id"`
	OperationID     OperationID    `json:"operation_id,omitempty"`
	InstallationID  InstallationID `json:"installation_id"`
	Sequence        int64          `json:"sequence,omitempty"`
	PreviousHash    *SHA256Hex     `json:"previous_hash"`
	RecordHash      SHA256Hex      `json:"record_hash,omitempty"`
	PlanRef         ArtifactRef    `json:"plan_ref"`
	InventoryRef    ArtifactRef    `json:"inventory_ref"`
	JournalRef      JournalRef     `json:"journal_ref"`
	BackupSetRef    *BackupSetRef  `json:"backup_set_ref"`
	VerificationRef *ArtifactRef   `json:"verification_ref"`
	DeploymentIDs   []string       `json:"deployment_ids,omitempty"`
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
	OperationID string `json:"operation_id"`
	Boundary    string `json:"boundary"`
	Result      string `json:"result"`
}
