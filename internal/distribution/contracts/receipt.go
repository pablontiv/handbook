package contracts

import "fmt"

type Receipt struct {
	Schema                     SchemaID                    `json:"schema"`
	ReceiptID                  string                      `json:"receipt_id"`
	OperationID                string                      `json:"operation_id"`
	Command                    string                      `json:"command"`
	ApprovalDigest             *SHA256Hex                  `json:"approval_digest"`
	LedgerRecordHash           SHA256Hex                   `json:"ledger_record_hash"`
	ReadyJournalRef            JournalRef                  `json:"ready_journal_ref"`
	PlanRef                    *ArtifactRef                `json:"plan_ref"`
	InventoryRef               *ArtifactRef                `json:"inventory_ref"`
	BackupSetRef               *BackupSetRef               `json:"backup_set_ref"`
	VerificationRef            *ArtifactRef                `json:"verification_ref"`
	Preconditions              []Precondition              `json:"preconditions"`
	DeploymentResults          []OperationDeploymentResult `json:"deployment_results"`
	RollbackResults            []OperationDeploymentResult `json:"rollback_results"`
	CleanupEvidenceRef         *ArtifactRef                `json:"cleanup_evidence_ref"`
	RequiredVerificationStatus string                      `json:"required_verification_status"`
	OperationResult            string                      `json:"operation_result"`
}

type OperationDeploymentResult struct {
	DeploymentID            string                  `json:"deployment_id"`
	Result                  string                  `json:"result"`
	BeforeObservation       *DeploymentObservation  `json:"before_observation"`
	AfterObservation        *DeploymentObservation  `json:"after_observation"`
	RuntimeBindingSummaries []RuntimeBindingSummary `json:"runtime_binding_summaries"`
	BackupEntryRef          *ArtifactRef            `json:"backup_entry_ref"`
	VerificationRef         *ArtifactRef            `json:"verification_ref"`
	CleanupEvidenceRef      *ArtifactRef            `json:"cleanup_evidence_ref"`
	RollbackAuthorityRefs   []ArtifactRef           `json:"rollback_authority_refs"`
}

func ValidateReceipt(receipt Receipt) error {
	if receipt.Schema != SchemaReceipt {
		return fmt.Errorf("invalid receipt schema")
	}
	if receipt.ReceiptID == "" || receipt.OperationID == "" || receipt.Command == "" {
		return fmt.Errorf("receipt requires receipt_id, operation_id, and command")
	}
	if err := ValidateOperationID(receipt.OperationID); err != nil {
		return err
	}
	if !sha256Pattern.MatchString(string(receipt.LedgerRecordHash)) {
		return fmt.Errorf("ledger_record_hash must be lower-case hex SHA-256")
	}
	if err := ValidateJournalRef(receipt.ReadyJournalRef, receipt.OperationID); err != nil {
		return fmt.Errorf("ready_journal_ref: %w", err)
	}
	if receipt.PlanRef != nil {
		if err := ValidateArtifactRef(*receipt.PlanRef); err != nil {
			return fmt.Errorf("plan_ref: %w", err)
		}
	}
	if receipt.InventoryRef != nil {
		if err := ValidateArtifactRef(*receipt.InventoryRef); err != nil {
			return fmt.Errorf("inventory_ref: %w", err)
		}
	}
	if err := validateBackupSetRef(receipt.BackupSetRef); err != nil {
		return err
	}
	if receipt.VerificationRef != nil {
		if err := ValidateArtifactRef(*receipt.VerificationRef); err != nil {
			return fmt.Errorf("verification_ref: %w", err)
		}
	}
	if receipt.OperationResult == "" || receipt.RequiredVerificationStatus == "" {
		return fmt.Errorf("receipt requires operation_result and required_verification_status")
	}
	if len(receipt.DeploymentResults) != v1DeploymentCount {
		return fmt.Errorf("receipt deployment result count = %d, want %d", len(receipt.DeploymentResults), v1DeploymentCount)
	}
	if err := validateReceiptCommandRefs(receipt); err != nil {
		return err
	}
	if receipt.CleanupEvidenceRef == nil && (receipt.OperationResult == "verification_required" || receipt.OperationResult == "rolled_back") {
		return fmt.Errorf("completed command-phase receipt requires cleanup_evidence_ref")
	}
	if receipt.CleanupEvidenceRef != nil {
		if err := ValidateArtifactRef(*receipt.CleanupEvidenceRef); err != nil {
			return fmt.Errorf("cleanup_evidence_ref: %w", err)
		}
	}
	if err := validateReceiptAggregateAuthority(receipt.DeploymentResults); err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, result := range receipt.DeploymentResults {
		if err := validateOperationDeploymentResult(result, receipt); err != nil {
			return err
		}
		if seen[result.DeploymentID] {
			return fmt.Errorf("duplicate deployment result")
		}
		seen[result.DeploymentID] = true
	}
	if receipt.OperationResult == "rolled_back" && len(receipt.RollbackResults) == 0 {
		return fmt.Errorf("rolled_back receipt requires rollback_results")
	}
	for _, result := range receipt.RollbackResults {
		if err := validateOperationDeploymentResult(result, receipt); err != nil {
			return fmt.Errorf("rollback_results: %w", err)
		}
	}
	if receipt.ApprovalDigest != nil && !sha256Pattern.MatchString(string(*receipt.ApprovalDigest)) {
		return fmt.Errorf("approval_digest must be lower-case hex SHA-256 or null")
	}
	return nil
}

func validateReceiptCommandRefs(receipt Receipt) error {
	switch receipt.Command {
	case "apply", "restore":
		if receipt.ApprovalDigest == nil || receipt.PlanRef == nil || receipt.InventoryRef == nil || receipt.BackupSetRef == nil {
			return fmt.Errorf("%s receipt requires approval, plan, inventory, and backup refs", receipt.Command)
		}
		if receipt.VerificationRef != nil {
			return fmt.Errorf("mutator receipt must not carry verification_ref")
		}
		if receipt.OperationResult != "verification_required" && receipt.OperationResult != "rolled_back" && receipt.OperationResult != RecoveryRequired {
			return fmt.Errorf("mutator receipt operation_result is contradictory")
		}
	case "uninstall":
		if receipt.ApprovalDigest == nil || receipt.PlanRef == nil || receipt.InventoryRef == nil {
			return fmt.Errorf("uninstall receipt requires approval, plan, and inventory refs")
		}
		if receipt.BackupSetRef != nil || receipt.VerificationRef != nil {
			return fmt.Errorf("uninstall receipt requires null backup_set_ref and verification_ref")
		}
		if receipt.OperationResult != "verification_required" && receipt.OperationResult != "rolled_back" && receipt.OperationResult != RecoveryRequired {
			return fmt.Errorf("uninstall receipt operation_result is contradictory")
		}
	case "verify":
		if receipt.ApprovalDigest != nil {
			return fmt.Errorf("verify receipt requires null approval_digest")
		}
		if receipt.VerificationRef == nil {
			return fmt.Errorf("verify receipt requires verification_ref")
		}
		if receipt.OperationResult != "verified" && receipt.OperationResult != "failed" && receipt.OperationResult != "operator_required" && receipt.OperationResult != RecoveryRequired {
			return fmt.Errorf("verify receipt operation_result is contradictory")
		}
	default:
		return fmt.Errorf("unknown receipt command %q", receipt.Command)
	}
	return nil
}

func validateReceiptAggregateAuthority(results []OperationDeploymentResult) error {
	if len(results) != v1DeploymentCount {
		return fmt.Errorf("receipt deployment result count = %d, want %d", len(results), v1DeploymentCount)
	}
	expectedIDs := map[string]bool{}
	for _, id := range v1AggregateDeploymentIDs {
		expectedIDs[id] = true
	}
	expectedBindings := expectedV1BindingSummariesByDeployment()
	seenIDs := map[string]bool{}
	bindingCount := 0
	for _, result := range results {
		if !expectedIDs[result.DeploymentID] {
			return fmt.Errorf("unexpected deployment result %s", result.DeploymentID)
		}
		if seenIDs[result.DeploymentID] {
			return fmt.Errorf("duplicate deployment result")
		}
		seenIDs[result.DeploymentID] = true
		want := expectedBindings[result.DeploymentID]
		if len(result.RuntimeBindingSummaries) != len(want) {
			return fmt.Errorf("runtime binding count for deployment %s = %d, want %d", result.DeploymentID, len(result.RuntimeBindingSummaries), len(want))
		}
		for i, binding := range result.RuntimeBindingSummaries {
			wantBinding := want[i]
			wantIdentity := wantBinding.Runtime + ":" + wantBinding.Name
			if binding.Runtime != wantBinding.Runtime || binding.BindingIdentity != wantIdentity {
				return fmt.Errorf("runtime binding summary %s[%d] = %s/%s, want %s/%s", result.DeploymentID, i, binding.Runtime, binding.BindingIdentity, wantBinding.Runtime, wantIdentity)
			}
			bindingCount++
		}
	}
	if len(seenIDs) != v1DeploymentCount {
		return fmt.Errorf("receipt deployment result set is incomplete")
	}
	if bindingCount != v1RuntimeBindingCount {
		return fmt.Errorf("receipt runtime binding count = %d, want %d", bindingCount, v1RuntimeBindingCount)
	}
	return nil
}

func validateOperationDeploymentResult(result OperationDeploymentResult, receipt Receipt) error {
	if result.DeploymentID == "" || result.Result == "" {
		return fmt.Errorf("deployment result requires deployment_id and result")
	}
	if !allowedDeploymentResult(receipt.OperationResult, result.Result) {
		return fmt.Errorf("deployment result %q is not allowed for operation_result %q", result.Result, receipt.OperationResult)
	}
	if result.BeforeObservation == nil || result.AfterObservation == nil {
		return fmt.Errorf("deployment result requires before and after observations")
	}
	if err := validateObservation(*result.BeforeObservation, false); err != nil {
		return fmt.Errorf("before_observation: %w", err)
	}
	if err := validateObservation(*result.AfterObservation, false); err != nil {
		return fmt.Errorf("after_observation: %w", err)
	}
	seenBindings := map[string]bool{}
	for _, binding := range result.RuntimeBindingSummaries {
		if binding.Runtime == "" || binding.BindingIdentity == "" || binding.Status == "" {
			return fmt.Errorf("runtime binding summary requires runtime, binding_identity, and status")
		}
		if !allowedRuntimeBindingStatus(receipt.OperationResult, binding.Status) {
			return fmt.Errorf("runtime binding status %q is not allowed for operation_result %q", binding.Status, receipt.OperationResult)
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
	if receipt.Command == "verify" && len(result.RuntimeBindingSummaries) == 0 {
		return fmt.Errorf("verify receipt requires runtime binding summaries per deployment")
	}
	if receipt.BackupSetRef != nil && result.BackupEntryRef == nil {
		return fmt.Errorf("backup-backed receipt requires backup_entry_ref per deployment")
	}
	if result.BackupEntryRef != nil {
		if err := ValidateArtifactRef(*result.BackupEntryRef); err != nil {
			return fmt.Errorf("backup_entry_ref: %w", err)
		}
	}
	if result.VerificationRef != nil {
		if err := ValidateArtifactRef(*result.VerificationRef); err != nil {
			return fmt.Errorf("deployment verification_ref: %w", err)
		}
	}
	if result.CleanupEvidenceRef != nil {
		if err := ValidateArtifactRef(*result.CleanupEvidenceRef); err != nil {
			return fmt.Errorf("cleanup_evidence_ref: %w", err)
		}
	}
	for _, ref := range result.RollbackAuthorityRefs {
		if err := ValidateArtifactRef(ref); err != nil {
			return fmt.Errorf("rollback_authority_refs: %w", err)
		}
	}
	return nil
}
