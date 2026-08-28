package contracts

type Inventory struct {
	Schema          SchemaID             `json:"schema"`
	ManifestDigest  SHA256Hex            `json:"manifest_digest"`
	Sources         []SourceObservation  `json:"sources"`
	Deployments     []PhysicalDeployment `json:"deployments"`
	RuntimeBindings []RuntimeBinding     `json:"runtime_bindings"`
	Ownership       []OwnershipSnapshot  `json:"ownership"`
	Backups         []BackupSetSnapshot  `json:"backups"`
	Blockers        []Blocker            `json:"blockers"`
}

type SourceObservation struct {
	SkillID string    `json:"skill_id"`
	Path    string    `json:"path"`
	SHA256  SHA256Hex `json:"sha256"`
}

type PhysicalDeployment struct {
	DeploymentID string `json:"deployment_id"`
	SkillID      string `json:"skill_id"`
	SourcePath   string `json:"source_path"`
	GovernedPath string `json:"governed_path"`
	Runtime      string `json:"runtime"`
}

type RuntimeBinding struct {
	DeploymentID string `json:"deployment_id"`
	Runtime      string `json:"runtime"`
	Root         string `json:"root"`
	Name         string `json:"name"`
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
