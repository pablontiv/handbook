package contracts

// SchemaID is the literal versioned namespace for a Waywarden JSON contract.
type SchemaID string

const (
	SchemaManifest            SchemaID = "waywarden.manifest/v1"
	SchemaInventory           SchemaID = "waywarden.inventory/v1"
	SchemaPlan                SchemaID = "waywarden.plan/v1"
	SchemaBackupManifest      SchemaID = "waywarden.backup-manifest/v1"
	SchemaOwnership           SchemaID = "waywarden.ownership/v1"
	SchemaReceipt             SchemaID = "waywarden.receipt/v1"
	SchemaVerification        SchemaID = "waywarden.verification/v1"
	SchemaOperatorObservation SchemaID = "waywarden.operator-observation/v1"
	SchemaCommandResult       SchemaID = "waywarden.command-result/v1"
	SchemaError               SchemaID = "waywarden.error/v1"
)

// SHA256Hex is a lower-case hexadecimal SHA-256 digest.
type SHA256Hex string

// ArtifactRef references an immutable artifact under a selected state/run root.
type ArtifactRef struct {
	Path   string    `json:"path"`
	SHA256 SHA256Hex `json:"sha256"`
	Bytes  string    `json:"bytes"`
}

// EvidenceRef is a public, redacted reference suitable for stdout/stderr JSON.
type EvidenceRef struct {
	Label  string `json:"label"`
	Ref    string `json:"ref,omitempty"`
	Digest string `json:"digest,omitempty"`
}
