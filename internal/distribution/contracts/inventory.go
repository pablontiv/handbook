package contracts

type Inventory struct {
	Schema          SchemaID            `json:"schema"`
	ManifestDigest  SHA256Hex           `json:"manifest_digest"`
	Sources         []SourceObservation `json:"sources"`
	Deployments     []Deployment        `json:"deployments"`
	RuntimeBindings []RuntimeBinding    `json:"runtime_bindings"`
	Ownership       []OwnershipSnapshot `json:"ownership"`
	Backups         []BackupSetSnapshot `json:"backups"`
	Blockers        []Blocker           `json:"blockers"`
}

type SourceObservation struct {
	SkillID        string    `json:"skill_id"`
	Path           string    `json:"path"`
	SourceIdentity string    `json:"source_identity"`
	SHA256         SHA256Hex `json:"sha256"`
}

type Deployment struct {
	DeploymentID         string           `json:"deployment_id"`
	SkillID              string           `json:"skill_id"`
	SourcePath           string           `json:"source_path"`
	SourceIdentity       string           `json:"source_identity"`
	GovernedPath         string           `json:"governed_path"`
	GovernedSlotIdentity string           `json:"governed_slot_identity"`
	LinkStrategy         string           `json:"link_strategy"`
	RuntimeBindings      []RuntimeBinding `json:"runtime_bindings"`
}

// PhysicalDeployment is retained as a compatibility alias for earlier contract tests.
type PhysicalDeployment = Deployment

type RuntimeBinding struct {
	DeploymentID string `json:"deployment_id"`
	Runtime      string `json:"runtime"`
	Root         string `json:"root"`
	Name         string `json:"name"`
	Target       string `json:"target"`
}

type OwnershipSnapshot struct {
	InstallationID string `json:"installation_id"`
	AggregateEvent string `json:"aggregate_event"`
}

type BackupSetSnapshot struct {
	BackupSetID    string `json:"backup_set_id"`
	InstallationID string `json:"installation_id"`
}

type Blocker struct {
	Code     string `json:"code"`
	Severity string `json:"severity"`
	Message  string `json:"message"`
}
