package contracts

// AbsolutePath marks a path that callers have already selected as absolute for
// a filesystem adapter boundary. It intentionally remains a string alias so the
// existing path identity authority stays in internal/distribution/filesystem.
type AbsolutePath string

// Output formats accepted by the public CLI.
const (
	OutputHuman = "human"
	OutputJSON  = "json"
)
