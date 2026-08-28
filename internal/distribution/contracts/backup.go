package contracts

type BackupManifest struct {
	Schema         SchemaID      `json:"schema"`
	BackupSetID    string        `json:"backup_set_id"`
	InstallationID string        `json:"installation_id"`
	Operation      string        `json:"operation"`
	Entries        []BackupEntry `json:"entries"`
	Verified       bool          `json:"verified"`
}

type BackupEntry struct {
	DeploymentID string      `json:"deployment_id"`
	Kind         string      `json:"kind"`
	Payload      ArtifactRef `json:"payload"`
	Metadata     []string    `json:"metadata"`
}
