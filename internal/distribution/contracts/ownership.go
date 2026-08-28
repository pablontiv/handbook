package contracts

import (
	"fmt"
	"path"
	"strings"
)

type OwnershipRecord struct {
	Schema                 SchemaID                    `json:"schema"`
	RecordID               string                      `json:"record_id"`
	OperationID            OperationID                 `json:"operation_id"`
	InstallationID         InstallationID              `json:"installation_id"`
	Sequence               int64                       `json:"sequence,omitempty"`
	PreviousHash           *SHA256Hex                  `json:"previous_hash"`
	RecordHash             SHA256Hex                   `json:"record_hash,omitempty"`
	PlanRef                ArtifactRef                 `json:"plan_ref"`
	InventoryRef           ArtifactRef                 `json:"inventory_ref"`
	JournalRef             JournalRef                  `json:"journal_ref"`
	BackupSetRef           *BackupSetRef               `json:"backup_set_ref"`
	VerificationRef        *ArtifactRef                `json:"verification_ref"`
	DeploymentIDs          []string                    `json:"deployment_ids"`
	Deployments            []OwnershipDeploymentRecord `json:"deployments"`
	AggregateEvent         string                      `json:"aggregate_event"`
	OperationResult        string                      `json:"operation_result"`
	FailureCode            *string                     `json:"failure_code"`
	CompensatingPriorState *CompensatingPriorState     `json:"compensating_prior_state"`
}

type BackupSetRef struct {
	BackupSetID string    `json:"backup_set_id"`
	SHA256      SHA256Hex `json:"sha256"`
}

type JournalRef struct {
	OperationID string    `json:"operation_id"`
	Path        string    `json:"path"`
	SHA256      SHA256Hex `json:"sha256"`
}

type JournalEntry struct {
	OperationID           string        `json:"operation_id"`
	Command               string        `json:"command,omitempty"`
	Intent                string        `json:"intent,omitempty"`
	StateRoot             string        `json:"state_root,omitempty"`
	Sequence              int64         `json:"sequence,omitempty"`
	Step                  string        `json:"step,omitempty"`
	Boundary              string        `json:"boundary"`
	State                 string        `json:"state,omitempty"`
	Result                string        `json:"result"`
	DeploymentRefs        []string      `json:"deployment_refs,omitempty"`
	GovernedSlotRefs      []string      `json:"governed_slot_refs,omitempty"`
	BackupSetRef          *BackupSetRef `json:"backup_set_ref,omitempty"`
	VerificationRef       *ArtifactRef  `json:"verification_ref,omitempty"`
	RollbackAuthorityRefs []ArtifactRef `json:"rollback_authority_refs,omitempty"`
	ReceiptSHA256         SHA256Hex     `json:"receipt_sha256,omitempty"`
	FinalReceiptPath      string        `json:"final_receipt_path,omitempty"`
	SyncBoundary          string        `json:"sync_boundary,omitempty"`
	Terminal              bool          `json:"terminal,omitempty"`
}

type DeploymentObservation struct {
	ObservedType          string `json:"observed_type"`
	Path                  string `json:"path"`
	GovernedSlotIdentity  string `json:"governed_slot_identity"`
	ManagedObjectIdentity string `json:"managed_object_identity"`
	ManagedLinkIdentity   string `json:"managed_link_identity"`
	LexicalLinkTarget     string `json:"lexical_link_target"`
	SourceContentDigest   string `json:"source_content_digest"`
	AttributesFingerprint string `json:"attributes_fingerprint"`
}

type RuntimeBindingSummary struct {
	Runtime         string       `json:"runtime"`
	BindingIdentity string       `json:"binding_identity"`
	Status          string       `json:"status"`
	EvidenceRef     *ArtifactRef `json:"evidence_ref"`
}

type OwnershipDeploymentRecord struct {
	DeploymentID            string                  `json:"deployment_id"`
	BeforeObservation       DeploymentObservation   `json:"before_observation"`
	AfterObservation        DeploymentObservation   `json:"after_observation"`
	RuntimeBindingSummaries []RuntimeBindingSummary `json:"runtime_binding_summaries"`
	OriginalPreimage        DeploymentObservation   `json:"original_preimage"`
	InstalledPostimage      *DeploymentObservation  `json:"installed_postimage"`
	BackupEntryRef          *ArtifactRef            `json:"backup_entry_ref"`
	VerificationRef         *ArtifactRef            `json:"verification_ref"`
	CleanupEvidenceRef      *ArtifactRef            `json:"cleanup_evidence_ref"`
	RollbackAuthorityRefs   []ArtifactRef           `json:"rollback_authority_refs"`
	Result                  string                  `json:"result"`
}

type CompensatingPriorState struct {
	AggregateEvent   string    `json:"aggregate_event"`
	DeploymentIDs    []string  `json:"deployment_ids"`
	LedgerRecordHash SHA256Hex `json:"ledger_record_hash"`
}

func ValidateOwnershipRecord(record OwnershipRecord) error {
	if record.Schema != SchemaOwnership {
		return fmt.Errorf("invalid ownership schema")
	}
	if record.RecordID == "" || record.OperationID == "" || record.InstallationID == "" {
		return fmt.Errorf("ownership record requires record_id, operation_id, and installation_id")
	}
	if err := ValidateOperationID(record.OperationID); err != nil {
		return err
	}
	if err := ValidateArtifactRef(record.PlanRef); err != nil {
		return fmt.Errorf("plan_ref: %w", err)
	}
	if err := ValidateArtifactRef(record.InventoryRef); err != nil {
		return fmt.Errorf("inventory_ref: %w", err)
	}
	if err := ValidateJournalRef(record.JournalRef, record.OperationID); err != nil {
		return fmt.Errorf("journal_ref: %w", err)
	}
	if err := validateBackupSetRef(record.BackupSetRef); err != nil {
		return err
	}
	if record.VerificationRef != nil {
		if err := ValidateArtifactRef(*record.VerificationRef); err != nil {
			return fmt.Errorf("verification_ref: %w", err)
		}
	}
	if err := validateDeploymentCardinality(record.DeploymentIDs, record.Deployments); err != nil {
		return err
	}
	if err := validateOwnershipRuntimeBindingAuthority(record.Deployments); err != nil {
		return err
	}
	if record.AggregateEvent == "" || record.OperationResult == "" {
		return fmt.Errorf("ownership record requires aggregate_event and operation_result")
	}
	if err := validateOwnershipEventRefs(record); err != nil {
		return err
	}
	return nil
}

func validateBackupSetRef(ref *BackupSetRef) error {
	if ref == nil {
		return nil
	}
	if ref.BackupSetID == "" || !sha256Pattern.MatchString(string(ref.SHA256)) {
		return fmt.Errorf("backup_set_ref is invalid")
	}
	return nil
}

func validateOwnershipEventRefs(record OwnershipRecord) error {
	switch record.AggregateEvent {
	case "applied_unverified", "restored_unverified":
		if record.BackupSetRef == nil {
			return fmt.Errorf("%s requires backup_set_ref", record.AggregateEvent)
		}
		if record.VerificationRef != nil {
			return fmt.Errorf("mutator ownership event must not carry verification_ref")
		}
		if record.FailureCode != nil || record.CompensatingPriorState != nil {
			return fmt.Errorf("normal mutator ownership event requires null failure and compensating refs")
		}
		if record.OperationResult != "verification_required" {
			return fmt.Errorf("normal mutator ownership event result must be verification_required")
		}
	case "removed_unverified":
		if record.BackupSetRef != nil || record.VerificationRef != nil {
			return fmt.Errorf("uninstall mutator event requires null backup_set_ref and verification_ref")
		}
		if record.FailureCode != nil || record.CompensatingPriorState != nil {
			return fmt.Errorf("normal uninstall event requires null failure and compensating refs")
		}
		if record.OperationResult != "verification_required" {
			return fmt.Errorf("normal uninstall event result must be verification_required")
		}
	case "installed_verified", "removed_verified", "restored_verified":
		if record.VerificationRef == nil {
			return fmt.Errorf("verified ownership event requires verification_ref")
		}
		if record.AggregateEvent != "restored_verified" && record.BackupSetRef != nil {
			return fmt.Errorf("installation/removal verification event requires null backup_set_ref")
		}
		if record.FailureCode != nil || record.CompensatingPriorState != nil {
			return fmt.Errorf("verified ownership event requires null failure and compensating refs")
		}
		if record.OperationResult != "verified" {
			return fmt.Errorf("verified ownership event result must be verified")
		}
	case "install_rolled_back", "uninstall_rolled_back", "restore_rolled_back", RecoveryRequired:
		if record.FailureCode == nil || *record.FailureCode == "" {
			return fmt.Errorf("compensating ownership event requires failure_code")
		}
		if record.CompensatingPriorState == nil {
			return fmt.Errorf("compensating ownership event requires compensating_prior_state")
		}
		if !sha256Pattern.MatchString(string(record.CompensatingPriorState.LedgerRecordHash)) {
			return fmt.Errorf("compensating_prior_state ledger_record_hash must be lower-case hex SHA-256")
		}
		if record.OperationResult != "rolled_back" && record.OperationResult != RecoveryRequired {
			return fmt.Errorf("compensating ownership event result must be rolled_back or recovery_required")
		}
	default:
		return fmt.Errorf("unknown aggregate_event %q", record.AggregateEvent)
	}
	for _, deployment := range record.Deployments {
		if err := validateOwnershipDeployment(record, deployment); err != nil {
			return err
		}
	}
	return nil
}

func validateOwnershipDeployment(record OwnershipRecord, deployment OwnershipDeploymentRecord) error {
	if deployment.DeploymentID == "" || deployment.Result == "" {
		return fmt.Errorf("deployment record requires deployment_id and result")
	}
	if !allowedDeploymentResult(record.OperationResult, deployment.Result) {
		return fmt.Errorf("deployment result %q is not allowed for operation_result %q", deployment.Result, record.OperationResult)
	}
	if err := validateObservation(deployment.BeforeObservation, false); err != nil {
		return fmt.Errorf("before_observation: %w", err)
	}
	if err := validateObservation(deployment.AfterObservation, false); err != nil {
		return fmt.Errorf("after_observation: %w", err)
	}
	if err := validateObservation(deployment.OriginalPreimage, false); err != nil {
		return fmt.Errorf("original_preimage: %w", err)
	}
	if deployment.InstalledPostimage == nil && (record.AggregateEvent == "applied_unverified" || record.AggregateEvent == "installed_verified") {
		return fmt.Errorf("installed state requires installed_postimage")
	}
	if deployment.InstalledPostimage != nil {
		if err := validateObservation(*deployment.InstalledPostimage, false); err != nil {
			return fmt.Errorf("installed_postimage: %w", err)
		}
	}
	seenBindings := map[string]bool{}
	for _, binding := range deployment.RuntimeBindingSummaries {
		if binding.Runtime == "" || binding.BindingIdentity == "" || binding.Status == "" {
			return fmt.Errorf("runtime binding summary requires runtime, binding_identity, and status")
		}
		if !allowedRuntimeBindingStatus(record.OperationResult, binding.Status) {
			return fmt.Errorf("runtime binding status %q is not allowed for operation_result %q", binding.Status, record.OperationResult)
		}
		key := binding.Runtime + "\x00" + binding.BindingIdentity
		if seenBindings[key] {
			return fmt.Errorf("duplicate runtime binding identity")
		}
		seenBindings[key] = true
		if binding.EvidenceRef != nil {
			if err := ValidateArtifactRef(*binding.EvidenceRef); err != nil {
				return fmt.Errorf("runtime binding evidence_ref: %w", err)
			}
		}
	}
	if len(deployment.RuntimeBindingSummaries) == 0 && strings.HasSuffix(record.AggregateEvent, "verified") {
		return fmt.Errorf("verified aggregate event requires runtime binding summaries")
	}
	if record.BackupSetRef != nil && deployment.BackupEntryRef == nil {
		return fmt.Errorf("backup-backed aggregate event requires backup_entry_ref per deployment")
	}
	if deployment.BackupEntryRef != nil {
		if err := ValidateArtifactRef(*deployment.BackupEntryRef); err != nil {
			return fmt.Errorf("backup_entry_ref: %w", err)
		}
	}
	if deployment.VerificationRef != nil {
		if err := ValidateArtifactRef(*deployment.VerificationRef); err != nil {
			return fmt.Errorf("deployment verification_ref: %w", err)
		}
	}
	if deployment.CleanupEvidenceRef == nil && (record.OperationResult == "verification_required" || record.OperationResult == "rolled_back") {
		return fmt.Errorf("completed command-phase event requires cleanup_evidence_ref per deployment")
	}
	if deployment.CleanupEvidenceRef != nil {
		if err := ValidateArtifactRef(*deployment.CleanupEvidenceRef); err != nil {
			return fmt.Errorf("cleanup_evidence_ref: %w", err)
		}
	}
	for _, ref := range deployment.RollbackAuthorityRefs {
		if err := ValidateArtifactRef(ref); err != nil {
			return fmt.Errorf("rollback_authority_refs: %w", err)
		}
	}
	if record.OperationResult == "rolled_back" && len(deployment.RollbackAuthorityRefs) == 0 {
		return fmt.Errorf("rolled_back deployment requires rollback authority refs")
	}
	return nil
}

func validateObservation(observation DeploymentObservation, allowZero bool) error {
	if allowZero && observation == (DeploymentObservation{}) {
		return nil
	}
	if observation.ObservedType == "" || observation.Path == "" || observation.GovernedSlotIdentity == "" || observation.ManagedObjectIdentity == "" {
		return fmt.Errorf("observation requires observed_type, path, governed_slot_identity, and managed_object_identity")
	}
	if !allowedObservationType(observation.ObservedType) {
		return fmt.Errorf("unknown observation type %q", observation.ObservedType)
	}
	if observation.SourceContentDigest != "" && !sha256Pattern.MatchString(observation.SourceContentDigest) {
		return fmt.Errorf("source_content_digest must be lower-case hex SHA-256 when present")
	}
	return nil
}

func validateDeploymentCardinality(ids []string, deployments []OwnershipDeploymentRecord) error {
	if err := validateExactDeploymentIDArray(ids); err != nil {
		return err
	}
	if len(deployments) != v1DeploymentCount {
		return fmt.Errorf("ownership deployment record count = %d, want %d", len(deployments), v1DeploymentCount)
	}
	seenIDs := map[string]bool{}
	for _, id := range ids {
		if id == "" {
			return fmt.Errorf("deployment_ids must not contain empty values")
		}
		if seenIDs[id] {
			return fmt.Errorf("duplicate deployment_id")
		}
		seenIDs[id] = true
	}
	seenDeployments := map[string]bool{}
	for _, deployment := range deployments {
		if deployment.DeploymentID == "" {
			return fmt.Errorf("deployment record requires deployment_id")
		}
		if seenDeployments[deployment.DeploymentID] {
			return fmt.Errorf("duplicate deployment identity")
		}
		seenDeployments[deployment.DeploymentID] = true
		if !seenIDs[deployment.DeploymentID] {
			return fmt.Errorf("deployment record not listed in deployment_ids")
		}
	}
	if len(seenIDs) != len(seenDeployments) {
		return fmt.Errorf("incomplete aggregate deployment cardinality")
	}
	return nil
}

func validateOwnershipRuntimeBindingAuthority(deployments []OwnershipDeploymentRecord) error {
	expected := expectedV1BindingSummariesByDeployment()
	count := 0
	seenDeployments := map[string]bool{}
	for _, deployment := range deployments {
		seenDeployments[deployment.DeploymentID] = true
		want := expected[deployment.DeploymentID]
		if len(deployment.RuntimeBindingSummaries) != len(want) {
			return fmt.Errorf("runtime binding count for deployment %s = %d, want %d", deployment.DeploymentID, len(deployment.RuntimeBindingSummaries), len(want))
		}
		for i, binding := range deployment.RuntimeBindingSummaries {
			wantBinding := want[i]
			wantIdentity := wantBinding.Runtime + ":" + wantBinding.Name
			if binding.Runtime != wantBinding.Runtime || binding.BindingIdentity != wantIdentity {
				return fmt.Errorf("runtime binding summary %s[%d] = %s/%s, want %s/%s", deployment.DeploymentID, i, binding.Runtime, binding.BindingIdentity, wantBinding.Runtime, wantIdentity)
			}
			count++
		}
	}
	for _, id := range v1AggregateDeploymentIDs {
		if !seenDeployments[id] {
			return fmt.Errorf("missing deployment %s", id)
		}
	}
	if count != v1RuntimeBindingCount {
		return fmt.Errorf("aggregate runtime binding count = %d, want %d", count, v1RuntimeBindingCount)
	}
	return nil
}

func allowedDeploymentResult(operationResult, result string) bool {
	switch operationResult {
	case "verification_required":
		return result == "verification_required" || result == "cleanup_completed"
	case "verified":
		return result == "verified"
	case "rolled_back":
		return result == "rolled_back"
	case RecoveryRequired:
		return result == RecoveryRequired || result == "rollback_failed"
	case "failed":
		return result == "failed"
	case "operator_required":
		return result == "operator_required"
	default:
		return false
	}
}

func allowedRuntimeBindingStatus(operationResult, status string) bool {
	switch operationResult {
	case "verification_required":
		return status == "verification_required"
	case "verified":
		return status == "verified"
	case "rolled_back":
		return status == "rolled_back" || status == "verification_required"
	case RecoveryRequired:
		return status == RecoveryRequired || status == "failed" || status == "operator_required"
	case "failed":
		return status == "failed"
	case "operator_required":
		return status == "operator_required"
	default:
		return false
	}
}

func allowedObservationType(kind string) bool {
	switch kind {
	case "typed_missing", "regular_file", "file", "ordinary_symlink", "symlink", "empty_directory", "nonempty_directory", "directory":
		return true
	default:
		return false
	}
}

func ValidateJournalRef(ref JournalRef, operationID OperationID) error {
	if ref.OperationID == "" || ref.Path == "" || ref.SHA256 == "" {
		return fmt.Errorf("journal_ref requires operation_id, path, and sha256")
	}
	if ref.OperationID != string(operationID) {
		return fmt.Errorf("journal_ref operation_id mismatch")
	}
	if err := ValidateOperationID(ref.OperationID); err != nil {
		return err
	}
	if ref.Path != "runs/"+ref.OperationID+"/journal.ndjson" {
		return fmt.Errorf("journal_ref path must be the operation journal relative path")
	}
	if !sha256Pattern.MatchString(string(ref.SHA256)) {
		return fmt.Errorf("journal_ref sha256 must be lower-case hex SHA-256")
	}
	return nil
}

func ValidateJournalEntry(entry JournalEntry, operationID OperationID) error {
	if entry.OperationID == "" || entry.Boundary == "" || entry.Result == "" {
		return fmt.Errorf("journal entry requires operation_id, boundary, and result")
	}
	if entry.OperationID != string(operationID) {
		return fmt.Errorf("journal entry operation_id mismatch")
	}
	if err := ValidateOperationID(entry.OperationID); err != nil {
		return err
	}
	if entry.Sequence < 1 {
		return fmt.Errorf("journal entry requires positive sequence")
	}
	if entry.State != "" && entry.Boundary != "step" && entry.State != entry.Boundary {
		return fmt.Errorf("journal state must match boundary")
	}
	if entry.Boundary == "step" && entry.State == "" {
		return fmt.Errorf("step journal entry requires step state")
	}
	if entry.BackupSetRef != nil {
		if err := validateBackupSetRef(entry.BackupSetRef); err != nil {
			return err
		}
	}
	if entry.VerificationRef != nil {
		if err := ValidateArtifactRef(*entry.VerificationRef); err != nil {
			return fmt.Errorf("verification_ref: %w", err)
		}
	}
	for _, ref := range entry.RollbackAuthorityRefs {
		if err := ValidateArtifactRef(ref); err != nil {
			return fmt.Errorf("rollback_authority_refs: %w", err)
		}
	}
	switch entry.Boundary {
	case "started", "step", "ready_to_commit":
		if entry.Terminal || entry.ReceiptSHA256 != "" || entry.FinalReceiptPath != "" {
			return fmt.Errorf("nonterminal journal entry must not carry terminal receipt fields")
		}
		if entry.Boundary == "step" && entry.Step == "" {
			return fmt.Errorf("step journal entry requires step name")
		}
	case "committed":
		if !entry.Terminal {
			return fmt.Errorf("committed journal entry must be terminal")
		}
		if entry.ReceiptSHA256 == "" || !sha256Pattern.MatchString(string(entry.ReceiptSHA256)) {
			return fmt.Errorf("committed journal entry requires receipt digest")
		}
		if err := validateFinalReceiptPath(entry.FinalReceiptPath); err != nil {
			return err
		}
	case "rolled_back", "rollback_failed":
		if !entry.Terminal {
			return fmt.Errorf("rollback terminal journal entry must be terminal")
		}
	default:
		return fmt.Errorf("unknown journal boundary %q", entry.Boundary)
	}
	return nil
}

func validateFinalReceiptPath(value string) error {
	if value == "" {
		return fmt.Errorf("terminal journal entry requires final receipt destination")
	}
	if value != "receipt.json" {
		return fmt.Errorf("final receipt destination must be exactly receipt.json")
	}
	if strings.HasPrefix(value, "/") || strings.ContainsAny(value, `\\:`) || value == "." || value == ".." || strings.HasPrefix(value, "../") || strings.Contains(value, "/../") || path.Clean(value) != value {
		return fmt.Errorf("final receipt destination must be slash-relative and confined")
	}
	return nil
}
