package contracts

type Manifest struct {
	Schema       SchemaID           `json:"schema"`
	Repository   RepositoryIdentity `json:"repository"`
	Skills       []ManifestSkill    `json:"skills"`
	RuntimeRoots []RuntimeRoot      `json:"runtime_roots"`
	Adapters     []AdapterBinding   `json:"adapters"`
}

type RepositoryIdentity struct {
	ID         string `json:"id"`
	SourceRoot string `json:"source_root"`
}

type ManifestSkill struct {
	SkillID    string   `json:"skill_id"`
	SourcePath string   `json:"source_path"`
	EntryFiles []string `json:"entry_files"`
}

type RuntimeRoot struct {
	Runtime      string `json:"runtime"`
	Root         string `json:"root"`
	LinkStrategy string `json:"link_strategy"`
}

type AdapterBinding struct {
	Runtime string   `json:"runtime"`
	Schemas []string `json:"schemas"`
}
