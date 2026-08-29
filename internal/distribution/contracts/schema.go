package contracts

import (
	"bytes"
	"embed"
	"fmt"
	"path"
	"regexp"
	"strings"
	"sync"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

//go:embed schemas/*.schema.json
var schemaFS embed.FS

var schemaFiles = map[SchemaID]string{
	SchemaManifest:            "schemas/manifest.schema.json",
	SchemaInventory:           "schemas/inventory.schema.json",
	SchemaPlan:                "schemas/plan.schema.json",
	SchemaBackupManifest:      "schemas/backup-manifest.schema.json",
	SchemaOwnership:           "schemas/ownership.schema.json",
	SchemaReceipt:             "schemas/receipt.schema.json",
	SchemaVerification:        "schemas/verification.schema.json",
	SchemaOperatorObservation: "schemas/operator-observation.schema.json",
	SchemaCommandResult:       "schemas/command-result.schema.json",
	SchemaError:               "schemas/error.schema.json",
}

func AllSchemaIDs() []SchemaID {
	return []SchemaID{SchemaManifest, SchemaInventory, SchemaPlan, SchemaBackupManifest, SchemaOwnership, SchemaReceipt, SchemaVerification, SchemaOperatorObservation, SchemaCommandResult, SchemaError}
}

func LoadSchema(schema SchemaID) ([]byte, error) {
	path, ok := schemaFiles[schema]
	if !ok {
		return nil, fmt.Errorf("unknown schema %q", schema)
	}
	return schemaFS.ReadFile(path)
}

func ValidateSchema(schema SchemaID, canonical []byte) error {
	compiled, err := compiledSchema(schema)
	if err != nil {
		return err
	}
	jsonValue, err := jsonschema.UnmarshalJSON(bytes.NewReader(canonical))
	if err != nil {
		return err
	}
	if err := compiled.Validate(jsonValue); err != nil {
		return fmt.Errorf("%s schema validation failed: %w", schema, err)
	}
	var object map[string]any
	if err := StrictParseCanonical(canonical, &object); err != nil {
		return err
	}
	if object["schema"] != string(schema) {
		return fmt.Errorf("schema const = %v, want %s", object["schema"], schema)
	}
	if err := rejectUnknownTopLevel(schema, object); err != nil {
		return err
	}
	switch schema {
	case SchemaManifest:
		var v Manifest
		return StrictParseCanonical(canonical, &v)
	case SchemaInventory:
		var v Inventory
		return StrictParseCanonical(canonical, &v)
	case SchemaPlan:
		_, err := ParseCanonicalPlanEnvelope(canonical)
		return err
	case SchemaBackupManifest:
		var v BackupManifest
		if err := StrictParseCanonical(canonical, &v); err != nil {
			return err
		}
		return ValidateBackupManifest(v)
	case SchemaOwnership:
		var v OwnershipRecord
		if err := StrictParseCanonical(canonical, &v); err != nil {
			return err
		}
		return ValidateOwnershipRecord(v)
	case SchemaReceipt:
		var v Receipt
		if err := StrictParseCanonical(canonical, &v); err != nil {
			return err
		}
		return ValidateReceipt(v)
	case SchemaVerification:
		var v Verification
		if err := StrictParseCanonical(canonical, &v); err != nil {
			return err
		}
		return ValidateVerification(v)
	case SchemaOperatorObservation:
		var v OperatorObservation
		return StrictParseCanonical(canonical, &v)
	case SchemaCommandResult:
		var v CommandResult
		if err := StrictParseCanonical(canonical, &v); err != nil {
			return err
		}
		return validateCommandResult(v)
	case SchemaError:
		var v PublicError
		if err := StrictParseCanonical(canonical, &v); err != nil {
			return err
		}
		return validatePublicError(v)
	default:
		return fmt.Errorf("unknown schema %q", schema)
	}
}

var (
	compileSchemasOnce sync.Once
	compiledSchemas    map[SchemaID]*jsonschema.Schema
	compiledSchemasErr error
)

func compiledSchema(schema SchemaID) (*jsonschema.Schema, error) {
	compileSchemasOnce.Do(func() {
		compiler := jsonschema.NewCompiler()
		compiler.AssertFormat()
		for _, id := range AllSchemaIDs() {
			data, err := LoadSchema(id)
			if err != nil {
				compiledSchemasErr = err
				return
			}
			doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))
			if err != nil {
				compiledSchemasErr = fmt.Errorf("load %s: %w", id, err)
				return
			}
			if err := compiler.AddResource(string(id), doc); err != nil {
				compiledSchemasErr = fmt.Errorf("register %s: %w", id, err)
				return
			}
		}
		compiledSchemas = make(map[SchemaID]*jsonschema.Schema, len(schemaFiles))
		for _, id := range AllSchemaIDs() {
			compiled, err := compiler.Compile(string(id))
			if err != nil {
				compiledSchemasErr = fmt.Errorf("compile %s: %w", id, err)
				return
			}
			compiledSchemas[id] = compiled
		}
	})
	if compiledSchemasErr != nil {
		return nil, compiledSchemasErr
	}
	compiled, ok := compiledSchemas[schema]
	if !ok {
		return nil, fmt.Errorf("unknown schema %q", schema)
	}
	return compiled, nil
}

var allowedTopLevel = map[SchemaID]map[string]bool{
	SchemaManifest:            keys("schema", "repository", "skills", "runtime_roots", "adapters"),
	SchemaInventory:           keys("schema", "manifest_digest", "sources", "deployments", "runtime_bindings", "ownership", "backups", "blockers"),
	SchemaPlan:                keys("schema", "approval_digest", "payload"),
	SchemaBackupManifest:      keys("schema", "backup_set_id", "installation_id", "operation_id", "operation", "entries", "verified"),
	SchemaOwnership:           keys("schema", "record_id", "operation_id", "installation_id", "sequence", "previous_hash", "record_hash", "plan_ref", "inventory_ref", "journal_ref", "backup_set_ref", "verification_ref", "deployment_ids", "deployments", "aggregate_event", "operation_result", "failure_code", "compensating_prior_state"),
	SchemaReceipt:             keys("schema", "receipt_id", "operation_id", "command", "approval_digest", "ledger_record_hash", "ready_journal_ref", "plan_ref", "inventory_ref", "backup_set_ref", "verification_ref", "preconditions", "deployment_results", "rollback_results", "cleanup_evidence_ref", "required_verification_status", "operation_result"),
	SchemaVerification:        keys("schema", "verification_id", "operation_id", "selector", "assertions", "status", "operator_ref"),
	SchemaOperatorObservation: keys("schema", "observation_id", "runtime", "challenge", "declaration", "freshness"),
	SchemaCommandResult:       keys("schema", "kind", "command", "status", "artifact", "operation_id", "installation_id", "backup_set_id", "aggregate_event", "receipt_ref", "receipt_digest", "selector", "verification_ref", "verification_digest", "error"),
	SchemaError:               keys("schema", "code", "message", "exit", "command", "evidence"),
}

func keys(values ...string) map[string]bool {
	out := make(map[string]bool, len(values))
	for _, value := range values {
		out[value] = true
	}
	return out
}

func rejectUnknownTopLevel(schema SchemaID, object map[string]any) error {
	allowed := allowedTopLevel[schema]
	for key := range object {
		if !allowed[key] {
			return fmt.Errorf("unknown top-level property %q for %s", key, schema)
		}
	}
	return nil
}

var sha256Pattern = regexp.MustCompile(`^[0-9a-f]{64}$`)
var decimalPattern = regexp.MustCompile(`^(0|[1-9][0-9]*)$`)

func ValidateOperationID(id OperationID) error {
	return validateGeneratedOpaqueID("operation_id", string(id))
}

func ValidateInstallationID(id InstallationID) error {
	return validateGeneratedOpaqueID("installation_id", string(id))
}

func ValidateBackupSetID(id BackupSetID) error {
	return validateGeneratedOpaqueID("backup_set_id", string(id))
}

func ValidateDeploymentID(id string) error {
	return validateGeneratedOpaqueID("deployment_id", id)
}

func ValidateVerificationID(id string) error {
	return validateGeneratedOpaqueID("verification_id", id)
}

func validateGeneratedOpaqueID(field, id string) error {
	if !sha256Pattern.MatchString(id) {
		return fmt.Errorf("%s must be generated lower-case SHA-256-shape hex", field)
	}
	return nil
}

func ValidateArtifactRef(ref ArtifactRef) error {
	if ref.Path == "" || strings.HasPrefix(ref.Path, "/") || strings.HasPrefix(ref.Path, "../") || strings.Contains(ref.Path, "/../") || ref.Path == ".." || strings.ContainsAny(ref.Path, `\\:`) || path.Clean(ref.Path) != ref.Path || ref.Path == "." {
		return fmt.Errorf("artifact path must be relative and confined")
	}
	parts := strings.Split(ref.Path, "/")
	if len(parts) >= 2 && parts[0] == "runs" {
		if err := ValidateOperationID(parts[1]); err != nil {
			return err
		}
	}
	if !sha256Pattern.MatchString(string(ref.SHA256)) {
		return fmt.Errorf("artifact sha256 must be lower-case hex SHA-256")
	}
	if !decimalPattern.MatchString(ref.Bytes) {
		return fmt.Errorf("artifact byte length must be a canonical decimal string")
	}
	return nil
}

func validateCommandResult(result CommandResult) error {
	if result.Schema != SchemaCommandResult {
		return fmt.Errorf("invalid command-result schema")
	}
	switch result.Kind {
	case ResultArtifact:
		if result.Artifact == nil {
			return fmt.Errorf("artifact result requires artifact")
		}
		if result.Status != ResultStatusSuccess && result.Status != ResultStatusBlocked {
			return fmt.Errorf("artifact result status is invalid")
		}
		if result.Error != nil && result.Status != ResultStatusBlocked {
			return fmt.Errorf("artifact error is allowed only for blocked status")
		}
	case ResultMutation:
		if result.Status != ResultStatusVerificationRequired {
			return fmt.Errorf("mutation result must be verification_required")
		}
		if result.Artifact != nil || result.VerificationRef != nil || result.Selector != nil {
			return fmt.Errorf("mutation result contains nonapplicable fields")
		}
	case ResultVerification:
		if result.Status != ResultStatusVerified && result.Status != ResultStatusFailed && result.Status != ResultStatusOperatorRequired {
			return fmt.Errorf("verification result status is invalid")
		}
		if result.Error != nil && result.Status == ResultStatusVerified {
			return fmt.Errorf("verification error is forbidden for verified status")
		}
	default:
		return fmt.Errorf("unknown command result kind %q", result.Kind)
	}
	return nil
}

func validatePublicError(publicErr PublicError) error {
	if publicErr.Schema != SchemaError {
		return fmt.Errorf("invalid error schema")
	}
	if publicErr.Code == "" || publicErr.Message == "" || publicErr.Command == "" {
		return fmt.Errorf("public error requires code, message, and command")
	}
	if publicErr.Exit < 2 || publicErr.Exit > 6 {
		return fmt.Errorf("public error exit must be a stable nonzero class")
	}
	return nil
}
