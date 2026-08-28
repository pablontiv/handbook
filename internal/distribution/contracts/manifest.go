package contracts

type Manifest struct {
	Schema       SchemaID         `json:"schema"`
	Skills       []ManifestSkill  `json:"skills"`
	RuntimeRoots []RuntimeRoot    `json:"runtime_roots"`
	Adapters     []AdapterBinding `json:"adapters"`
}

type ManifestSkill struct {
	SkillID    string `json:"skill_id"`
	SourcePath string `json:"source_path"`
}

type RuntimeRoot struct {
	Runtime string `json:"runtime"`
	Root    string `json:"root"`
}

type AdapterBinding struct {
	Runtime string   `json:"runtime"`
	Schemas []string `json:"schemas"`
}
