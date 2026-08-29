package contracts

import "fmt"

type BackupManifest struct {
	Schema         SchemaID       `json:"schema"`
	BackupSetID    BackupSetID    `json:"backup_set_id"`
	InstallationID InstallationID `json:"installation_id"`
	OperationID    OperationID    `json:"operation_id"`
	Operation      string         `json:"operation"`
	Entries        []BackupEntry  `json:"entries"`
	Verified       bool           `json:"verified"`
}

type BackupEntry struct {
	DeploymentID string       `json:"deployment_id"`
	Kind         string       `json:"kind"`
	Payload      *ArtifactRef `json:"payload"`
	Metadata     []string     `json:"metadata"`
}

func ValidateBackupManifest(manifest BackupManifest) error {
	if manifest.Schema != SchemaBackupManifest {
		return fmt.Errorf("invalid backup manifest schema")
	}
	if err := ValidateBackupSetID(manifest.BackupSetID); err != nil {
		return err
	}
	if manifest.InstallationID == "" {
		return fmt.Errorf("backup manifest requires installation_id")
	}
	if err := ValidateOperationID(manifest.OperationID); err != nil {
		return err
	}
	switch manifest.Operation {
	case "apply", "restore", "uninstall", "verify":
	default:
		return fmt.Errorf("backup manifest operation %q is unsupported", manifest.Operation)
	}
	seen := map[string]bool{}
	for _, entry := range manifest.Entries {
		if err := ValidateDeploymentID(entry.DeploymentID); err != nil {
			return err
		}
		if seen[entry.DeploymentID] {
			return fmt.Errorf("duplicate backup manifest deployment_id")
		}
		seen[entry.DeploymentID] = true
		switch entry.Kind {
		case "typed_missing":
			if entry.Payload != nil {
				return fmt.Errorf("typed_missing backup entry must not carry payload")
			}
		case "regular_file", "ordinary_symlink", "empty_directory", "nonempty_directory", "directory", "file", "symlink":
			if entry.Payload == nil {
				return fmt.Errorf("backup entry kind %q requires payload", entry.Kind)
			}
			if err := ValidateArtifactRef(*entry.Payload); err != nil {
				return fmt.Errorf("backup entry payload: %w", err)
			}
		default:
			return fmt.Errorf("backup entry kind %q is unsupported", entry.Kind)
		}
	}
	return nil
}
