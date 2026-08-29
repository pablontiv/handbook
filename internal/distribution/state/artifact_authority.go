package state

import (
	"bytes"
	"context"
	"fmt"
	"path/filepath"
	"strconv"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

type aggregateAuthority struct {
	deploymentIDs []string
	bindings      map[string][]contracts.RuntimeBindingSummary
}

func validateOwnershipRecordContext(ctx context.Context, adapter filesystem.Adapter, roots Roots, record contracts.OwnershipRecord) error {
	if err := validateOperationArtifactLineage(record.OperationID, record.PlanRef, record.InventoryRef, record.VerificationRef); err != nil {
		return err
	}
	authority, err := aggregateAuthorityFromPlanInventory(ctx, adapter, roots, record.PlanRef, record.InventoryRef)
	if err != nil {
		return err
	}
	if err := validateRecordMatchesAuthority(record, authority); err != nil {
		return err
	}
	if record.BackupSetRef != nil {
		if err := validateBackupManifestForRecord(ctx, adapter, roots, record); err != nil {
			return err
		}
	}
	if record.VerificationRef != nil {
		if _, err := readCanonicalArtifactRef(ctx, adapter, roots, *record.VerificationRef, contracts.SchemaVerification); err != nil {
			return fmt.Errorf("verification_ref: %w", err)
		}
	}
	return nil
}

func validateReceiptContext(ctx context.Context, adapter filesystem.Adapter, roots Roots, receipt contracts.Receipt) error {
	if receipt.PlanRef == nil || receipt.InventoryRef == nil {
		return nil
	}
	if err := validateOperationArtifactLineage(contracts.OperationID(receipt.OperationID), *receipt.PlanRef, *receipt.InventoryRef, receipt.VerificationRef); err != nil {
		return err
	}
	authority, err := aggregateAuthorityFromPlanInventory(ctx, adapter, roots, *receipt.PlanRef, *receipt.InventoryRef)
	if err != nil {
		return err
	}
	if err := validateReceiptMatchesAuthority(receipt, authority); err != nil {
		return err
	}
	if receipt.BackupSetRef != nil {
		if err := validateBackupManifestForReceipt(ctx, adapter, roots, receipt); err != nil {
			return err
		}
	}
	if receipt.VerificationRef != nil {
		if _, err := readCanonicalArtifactRef(ctx, adapter, roots, *receipt.VerificationRef, contracts.SchemaVerification); err != nil {
			return fmt.Errorf("verification_ref: %w", err)
		}
	}
	return nil
}

func validateOperationArtifactLineage(op contracts.OperationID, planRef, inventoryRef contracts.ArtifactRef, verificationRef *contracts.ArtifactRef) error {
	if !artifactRefInOperationRun(op, planRef) {
		return fmt.Errorf("plan_ref does not belong to operation run")
	}
	if !artifactRefInOperationRun(op, inventoryRef) {
		return fmt.Errorf("inventory_ref does not belong to operation run")
	}
	if verificationRef != nil && !artifactRefInOperationRun(op, *verificationRef) {
		return fmt.Errorf("verification_ref does not belong to operation run")
	}
	return nil
}

func artifactRefInOperationRun(op contracts.OperationID, ref contracts.ArtifactRef) bool {
	prefix := filepath.ToSlash(filepath.Join("runs", string(op))) + "/"
	return len(ref.Path) > len(prefix) && ref.Path[:len(prefix)] == prefix
}

func aggregateAuthorityFromPlanInventory(ctx context.Context, adapter filesystem.Adapter, roots Roots, planRef, inventoryRef contracts.ArtifactRef) (aggregateAuthority, error) {
	planBytes, err := readCanonicalArtifactRef(ctx, adapter, roots, planRef, contracts.SchemaPlan)
	if err != nil {
		return aggregateAuthority{}, fmt.Errorf("plan_ref: %w", err)
	}
	inventoryBytes, err := readCanonicalArtifactRef(ctx, adapter, roots, inventoryRef, contracts.SchemaInventory)
	if err != nil {
		return aggregateAuthority{}, fmt.Errorf("inventory_ref: %w", err)
	}
	inventory, err := contracts.ParseCanonicalInventory(inventoryBytes)
	if err != nil {
		return aggregateAuthority{}, fmt.Errorf("inventory_ref: %w", err)
	}
	plan, err := contracts.ParseCanonicalPlanEnvelope(planBytes)
	if err != nil {
		return aggregateAuthority{}, fmt.Errorf("plan_ref: %w", err)
	}
	verifiedPlan, err := contracts.VerifyPlanEnvelope(planBytes, plan.ApprovalDigest)
	if err != nil {
		return aggregateAuthority{}, fmt.Errorf("plan_ref: %w", err)
	}
	plan = verifiedPlan
	embeddedInventoryBytes, err := contracts.CanonicalBytes(plan.Payload.Inventory)
	if err != nil {
		return aggregateAuthority{}, fmt.Errorf("embedded inventory canonicalization: %w", err)
	}
	if !bytes.Equal(embeddedInventoryBytes, inventoryBytes) {
		return aggregateAuthority{}, fmt.Errorf("plan embedded inventory bytes do not match inventory_ref bytes")
	}
	if plan.Payload.InventoryDigest != contracts.SHA256(inventoryBytes) {
		return aggregateAuthority{}, fmt.Errorf("plan embedded inventory digest does not match inventory_ref bytes")
	}
	if !sameDeployments(plan.Payload.Deployments, inventory.Deployments) {
		return aggregateAuthority{}, fmt.Errorf("plan deployments do not match inventory deployments")
	}
	if !sameRuntimeBindings(flattenDeploymentBindings(plan.Payload.Deployments), inventory.RuntimeBindings) {
		return aggregateAuthority{}, fmt.Errorf("plan runtime bindings do not match inventory runtime bindings")
	}
	authority, err := authorityFromDeployments(plan.Payload.Deployments)
	if err != nil {
		return aggregateAuthority{}, err
	}
	return authority, nil
}

func readCanonicalArtifactRef(ctx context.Context, adapter filesystem.Adapter, roots Roots, ref contracts.ArtifactRef, schema contracts.SchemaID) ([]byte, error) {
	if err := contracts.ValidateArtifactRef(ref); err != nil {
		return nil, err
	}
	abs := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), filepath.FromSlash(ref.Path)))
	if !isUnderRoot(string(roots.StateRoot), string(abs)) {
		return nil, fmt.Errorf("artifact ref escapes state root")
	}
	data, err := adapter.ReadFileNoFollow(ctx, abs)
	if err != nil {
		return nil, err
	}
	if contracts.SHA256(data) != ref.SHA256 {
		return nil, fmt.Errorf("artifact digest mismatch")
	}
	if strconv.Itoa(len(data)) != ref.Bytes {
		return nil, fmt.Errorf("artifact byte length mismatch")
	}
	if err := contracts.ValidateSchema(schema, data); err != nil {
		return nil, err
	}
	return data, nil
}

func readBackupManifestRef(ctx context.Context, adapter filesystem.Adapter, roots Roots, ref contracts.BackupSetRef) (contracts.BackupManifest, error) {
	if err := contracts.ValidateBackupSetID(ref.BackupSetID); err != nil {
		return contracts.BackupManifest{}, err
	}
	backupRoot := filepath.Join(string(roots.StateRoot), "backups", ref.BackupSetID)
	path := contracts.AbsolutePath(filepath.Join(backupRoot, "manifest.json"))
	if !isUnderRoot(filepath.Join(string(roots.StateRoot), "backups"), string(path)) || !isUnderRoot(backupRoot, string(path)) {
		return contracts.BackupManifest{}, fmt.Errorf("backup manifest path escapes backup set root")
	}
	data, err := adapter.ReadFileNoFollow(ctx, path)
	if err != nil {
		return contracts.BackupManifest{}, fmt.Errorf("backup manifest: %w", err)
	}
	if contracts.SHA256(data) != ref.SHA256 {
		return contracts.BackupManifest{}, fmt.Errorf("backup manifest digest mismatch")
	}
	if err := contracts.ValidateSchema(contracts.SchemaBackupManifest, data); err != nil {
		return contracts.BackupManifest{}, fmt.Errorf("backup manifest: %w", err)
	}
	var manifest contracts.BackupManifest
	if err := contracts.StrictParseCanonical(data, &manifest); err != nil {
		return contracts.BackupManifest{}, err
	}
	return manifest, nil
}

func validateBackupManifestForRecord(ctx context.Context, adapter filesystem.Adapter, roots Roots, record contracts.OwnershipRecord) error {
	manifest, err := readBackupManifestRef(ctx, adapter, roots, *record.BackupSetRef)
	if err != nil {
		return err
	}
	if manifest.BackupSetID != record.BackupSetRef.BackupSetID {
		return fmt.Errorf("backup manifest backup_set_id mismatch")
	}
	if manifest.InstallationID != record.InstallationID {
		return fmt.Errorf("backup manifest installation_id mismatch")
	}
	if manifest.OperationID != record.OperationID {
		return fmt.Errorf("backup manifest operation_id mismatch")
	}
	if !manifest.Verified {
		return fmt.Errorf("backup manifest must be verified")
	}
	if !backupManifestEntriesMatchDeployments(manifest, record.DeploymentIDs) {
		return fmt.Errorf("backup manifest entries do not match ledger deployments")
	}
	return nil
}

func validateBackupManifestForReceipt(ctx context.Context, adapter filesystem.Adapter, roots Roots, receipt contracts.Receipt) error {
	manifest, err := readBackupManifestRef(ctx, adapter, roots, *receipt.BackupSetRef)
	if err != nil {
		return err
	}
	if manifest.BackupSetID != receipt.BackupSetRef.BackupSetID {
		return fmt.Errorf("backup manifest backup_set_id mismatch")
	}
	if manifest.OperationID != contracts.OperationID(receipt.OperationID) {
		return fmt.Errorf("backup manifest operation_id mismatch")
	}
	if !manifest.Verified {
		return fmt.Errorf("backup manifest must be verified")
	}
	if !backupManifestEntriesMatchDeployments(manifest, receiptDeploymentIDs(receipt.DeploymentResults)) {
		return fmt.Errorf("backup manifest entries do not match receipt deployments")
	}
	return nil
}

func backupManifestEntriesMatchDeployments(manifest contracts.BackupManifest, deploymentIDs []string) bool {
	if len(manifest.Entries) != len(deploymentIDs) {
		return false
	}
	want := map[string]bool{}
	for _, id := range deploymentIDs {
		want[id] = true
	}
	seen := map[string]bool{}
	for _, entry := range manifest.Entries {
		if !want[entry.DeploymentID] || seen[entry.DeploymentID] {
			return false
		}
		seen[entry.DeploymentID] = true
	}
	return true
}

func authorityFromDeployments(deployments []contracts.Deployment) (aggregateAuthority, error) {
	if len(deployments) != 10 {
		return aggregateAuthority{}, fmt.Errorf("approved deployment count = %d, want 10", len(deployments))
	}
	ids := make([]string, 0, len(deployments))
	bindings := map[string][]contracts.RuntimeBindingSummary{}
	seenIDs := map[string]bool{}
	seenBindings := map[string]bool{}
	bindingCount := 0
	for _, deployment := range deployments {
		if deployment.DeploymentID == "" {
			return aggregateAuthority{}, fmt.Errorf("approved deployment_id is empty")
		}
		if seenIDs[deployment.DeploymentID] {
			return aggregateAuthority{}, fmt.Errorf("duplicate approved deployment_id")
		}
		seenIDs[deployment.DeploymentID] = true
		ids = append(ids, deployment.DeploymentID)
		if len(deployment.RuntimeBindings) == 0 {
			return aggregateAuthority{}, fmt.Errorf("approved deployment %s has no runtime bindings", deployment.DeploymentID)
		}
		for _, binding := range deployment.RuntimeBindings {
			if binding.DeploymentID != deployment.DeploymentID {
				return aggregateAuthority{}, fmt.Errorf("approved runtime binding deployment mismatch")
			}
			identity := binding.Runtime + ":" + binding.Name
			key := binding.DeploymentID + "\x00" + binding.Runtime + "\x00" + identity
			if seenBindings[key] {
				return aggregateAuthority{}, fmt.Errorf("duplicate approved runtime binding")
			}
			seenBindings[key] = true
			bindings[deployment.DeploymentID] = append(bindings[deployment.DeploymentID], contracts.RuntimeBindingSummary{Runtime: binding.Runtime, BindingIdentity: identity})
			bindingCount++
		}
	}
	if bindingCount != 15 {
		return aggregateAuthority{}, fmt.Errorf("approved runtime binding count = %d, want 15", bindingCount)
	}
	return aggregateAuthority{deploymentIDs: ids, bindings: bindings}, nil
}

func validateRecordMatchesAuthority(record contracts.OwnershipRecord, authority aggregateAuthority) error {
	if !equalStringSlices(record.DeploymentIDs, authority.deploymentIDs) {
		return fmt.Errorf("ledger deployment_ids do not match approved plan/inventory")
	}
	seen := map[string]bool{}
	for _, deployment := range record.Deployments {
		seen[deployment.DeploymentID] = true
		if !bindingSummariesMatchAuthority(deployment.RuntimeBindingSummaries, authority.bindings[deployment.DeploymentID]) {
			return fmt.Errorf("ledger runtime bindings for deployment %s do not match approved plan/inventory", deployment.DeploymentID)
		}
	}
	for _, id := range authority.deploymentIDs {
		if !seen[id] {
			return fmt.Errorf("ledger missing approved deployment %s", id)
		}
	}
	return nil
}

func validateReceiptMatchesAuthority(receipt contracts.Receipt, authority aggregateAuthority) error {
	if !equalStringSlices(receiptDeploymentIDs(receipt.DeploymentResults), authority.deploymentIDs) {
		return fmt.Errorf("receipt deployment_results do not match approved plan/inventory")
	}
	for _, result := range receipt.DeploymentResults {
		if !bindingSummariesMatchAuthority(result.RuntimeBindingSummaries, authority.bindings[result.DeploymentID]) {
			return fmt.Errorf("receipt runtime bindings for deployment %s do not match approved plan/inventory", result.DeploymentID)
		}
	}
	return nil
}

func bindingSummariesMatchAuthority(got, want []contracts.RuntimeBindingSummary) bool {
	if len(got) != len(want) {
		return false
	}
	for i := range got {
		if got[i].Runtime != want[i].Runtime || got[i].BindingIdentity != want[i].BindingIdentity {
			return false
		}
	}
	return true
}

func sameDeployments(a, b []contracts.Deployment) bool {
	ba, err := contracts.CanonicalBytes(a)
	if err != nil {
		return false
	}
	bb, err := contracts.CanonicalBytes(b)
	if err != nil {
		return false
	}
	return bytes.Equal(ba, bb)
}

func sameRuntimeBindings(a, b []contracts.RuntimeBinding) bool {
	ba, err := contracts.CanonicalBytes(a)
	if err != nil {
		return false
	}
	bb, err := contracts.CanonicalBytes(b)
	if err != nil {
		return false
	}
	return bytes.Equal(ba, bb)
}

func flattenDeploymentBindings(deployments []contracts.Deployment) []contracts.RuntimeBinding {
	var out []contracts.RuntimeBinding
	for _, deployment := range deployments {
		out = append(out, deployment.RuntimeBindings...)
	}
	return out
}
