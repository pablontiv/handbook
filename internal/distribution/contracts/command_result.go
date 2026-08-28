package contracts

type ResultKind string

type ResultStatus string

const (
	ResultArtifact     ResultKind = "artifact"
	ResultMutation     ResultKind = "mutation"
	ResultVerification ResultKind = "verification"

	ResultStatusSuccess              ResultStatus = "success"
	ResultStatusBlocked              ResultStatus = "blocked"
	ResultStatusVerificationRequired ResultStatus = "verification_required"
	ResultStatusVerified             ResultStatus = "verified"
	ResultStatusFailed               ResultStatus = "failed"
	ResultStatusOperatorRequired     ResultStatus = "operator_required"
)

type CommandResult struct {
	Schema             SchemaID           `json:"schema"`
	Kind               ResultKind         `json:"kind"`
	Command            string             `json:"command"`
	Status             ResultStatus       `json:"status"`
	Artifact           *ArtifactResult    `json:"artifact,omitempty"`
	OperationID        string             `json:"operation_id,omitempty"`
	InstallationID     string             `json:"installation_id,omitempty"`
	BackupSetID        string             `json:"backup_set_id,omitempty"`
	AggregateEvent     string             `json:"aggregate_event,omitempty"`
	ReceiptRef         *ArtifactRef       `json:"receipt_ref,omitempty"`
	ReceiptDigest      SHA256Hex          `json:"receipt_digest,omitempty"`
	Selector           *RedactedSelector  `json:"selector,omitempty"`
	VerificationRef    *ArtifactRef       `json:"verification_ref,omitempty"`
	VerificationDigest SHA256Hex          `json:"verification_digest,omitempty"`
	Error              *NestedPublicError `json:"error,omitempty"`
}

type ArtifactResult struct {
	Schema SchemaID  `json:"schema"`
	SHA256 SHA256Hex `json:"sha256"`
	Bytes  string    `json:"bytes"`
	Label  string    `json:"label"`
}

type RedactedSelector struct {
	Kind  SelectorKind `json:"kind"`
	Label string       `json:"label"`
}

type NestedPublicError struct {
	Code     string        `json:"code"`
	Message  string        `json:"message"`
	Exit     int           `json:"exit"`
	Evidence []EvidenceRef `json:"evidence"`
}
