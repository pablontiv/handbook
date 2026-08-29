package state_test

import (
	"context"
	"fmt"
	"path/filepath"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/state"
)

const round4ForbiddenFixtureDeploymentID = "9fd207a11f20bafd1e31ebdfc93990ef1cf34322d6755cc978fc1c2ef51fa51a"

func TestRound4LedgerAppendDerivesAggregateAuthorityFromDurablePlanAndInventory(t *testing.T) {
	ctx := context.Background()
	for _, home := range []string{filepath.Join(t.TempDir(), "home-a"), filepath.Join(t.TempDir(), "home-b")} {
		t.Run(filepath.Base(home), func(t *testing.T) {
			adapter := filesystem.NewMemoryAdapter()
			store := state.NewStore(adapter)
			roots := tempRoots(t)
			op := contracts.OperationID(round4StateOpID(home))
			planRef, inventoryRef, ids, err := publishRound4PlanInventory(ctx, store, roots, op, home)
			if err != nil {
				t.Fatal(err)
			}
			for _, id := range ids {
				if id == round4ForbiddenFixtureDeploymentID {
					t.Fatalf("dynamic temp-home deployment set reused forbidden fixture deployment ID %s", id)
				}
			}

			journal, err := store.OpenJournal(ctx, roots, op, contracts.CommandName("apply"))
			if err != nil {
				t.Fatal(err)
			}
			ledgerRef, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "started", Result: "started"})
			if err != nil {
				t.Fatal(err)
			}
			ledger, err := store.OpenLedger(ctx, roots)
			if err != nil {
				t.Fatal(err)
			}
			record := round4StateOwnershipRecord(string(op), ids, planRef, inventoryRef)
			record.JournalRef = ledgerRef
			publishRound4BackupManifest(t, adapter, roots, &record)
			if _, err := ledger.Append(ctx, record); err != nil {
				t.Fatalf("ledger append rejected dynamic plan/inventory aggregate: %v", err)
			}

			forged := record
			forged.RecordID += "-forged"
			forged.DeploymentIDs = append([]string(nil), record.DeploymentIDs...)
			forged.Deployments = cloneRound4StateDeployments(record.Deployments)
			forged.DeploymentIDs[0] = round4ForbiddenFixtureDeploymentID
			forged.Deployments[0].DeploymentID = round4ForbiddenFixtureDeploymentID
			if _, err := ledger.Append(ctx, forged); err == nil {
				t.Fatalf("ledger append accepted fixture deployment ID not present in approved plan/inventory")
			}
		})
	}
}

func publishRound4PlanInventory(ctx context.Context, store state.Store, roots state.Roots, op contracts.OperationID, home string) (contracts.ArtifactRef, contracts.ArtifactRef, []string, error) {
	ids := round4StateDeploymentIDs(home)
	deployments := round4PlanDeployments(home, ids)
	inventory := contracts.Inventory{Schema: contracts.SchemaInventory, ManifestDigest: contracts.SHA256([]byte("manifest-" + home)), Sources: []contracts.SourceObservation{}, Deployments: deployments, RuntimeBindings: flattenRuntimeBindings(deployments), Ownership: []contracts.OwnershipSnapshot{}, Backups: []contracts.BackupSetSnapshot{}, Blockers: []contracts.Blocker{}}
	inventoryBytes, err := contracts.CanonicalBytes(inventory)
	if err != nil {
		return contracts.ArtifactRef{}, contracts.ArtifactRef{}, nil, err
	}
	inventoryRef, err := store.PublishRunArtifact(ctx, roots, op, "inventory.json", inventoryBytes)
	if err != nil {
		return contracts.ArtifactRef{}, contracts.ArtifactRef{}, nil, err
	}
	payload := contracts.PlanPayload{Inventory: inventory, InventoryDigest: contracts.SHA256(inventoryBytes), Intent: contracts.IntentInstall, Selector: nil, Deployments: deployments, Blockers: []contracts.Blocker{}, Preconditions: []contracts.Precondition{}, BackupRequirement: contracts.BackupRequirement{Required: true, Reason: "install requires backup set"}, VerificationRequirements: []contracts.VerificationRequirement{}, RollbackStrategy: "rollback_on_preterminal_failure", LineageTransition: contracts.LineageTransition{From: "absent", To: "applied_unverified"}}
	approval, err := contracts.PayloadDigest(payload)
	if err != nil {
		return contracts.ArtifactRef{}, contracts.ArtifactRef{}, nil, err
	}
	planBytes, err := contracts.CanonicalBytes(contracts.PlanEnvelope{Schema: contracts.SchemaPlan, ApprovalDigest: approval, Payload: payload})
	if err != nil {
		return contracts.ArtifactRef{}, contracts.ArtifactRef{}, nil, err
	}
	planRef, err := store.PublishRunArtifact(ctx, roots, op, "plan.json", planBytes)
	if err != nil {
		return contracts.ArtifactRef{}, contracts.ArtifactRef{}, nil, err
	}
	return planRef, inventoryRef, ids, nil
}

func round4StateOpID(seed string) string {
	return string(contracts.SHA256([]byte("round4-state-op-" + seed)))
}

func round4StateDeploymentIDs(home string) []string {
	ids := make([]string, 10)
	for i := range ids {
		ids[i] = string(contracts.SHA256([]byte(fmt.Sprintf("%s\x00slot-%02d\x00source-%02d", home, i, i))))
	}
	return ids
}

func round4PlanDeployments(home string, ids []string) []contracts.Deployment {
	out := make([]contracts.Deployment, 0, len(ids))
	for i, id := range ids {
		bindings := []contracts.RuntimeBinding{{DeploymentID: id, Runtime: "pi", Root: filepath.ToSlash(filepath.Join(home, ".agents", "skills")), Name: fmt.Sprintf("skill-%02d", i), Target: fmt.Sprintf("skills/skill-%02d", i)}}
		if i < 5 {
			bindings = append(bindings, contracts.RuntimeBinding{DeploymentID: id, Runtime: "opencode", Root: filepath.ToSlash(filepath.Join(home, ".agents", "skills")), Name: fmt.Sprintf("skill-%02d", i), Target: fmt.Sprintf("skills/skill-%02d", i)})
		}
		out = append(out, contracts.Deployment{DeploymentID: id, SkillID: fmt.Sprintf("skill-%02d", i), SourcePath: fmt.Sprintf("/repo/skills/skill-%02d", i), SourceIdentity: fmt.Sprintf("source-%02d", i), GovernedPath: filepath.ToSlash(filepath.Join(home, ".agents", "skills", fmt.Sprintf("skill-%02d", i))), GovernedSlotIdentity: fmt.Sprintf("slot-%02d@%s", i, home), LinkStrategy: "symlink", RuntimeBindings: bindings})
	}
	return out
}

func flattenRuntimeBindings(deployments []contracts.Deployment) []contracts.RuntimeBinding {
	var out []contracts.RuntimeBinding
	for _, deployment := range deployments {
		out = append(out, deployment.RuntimeBindings...)
	}
	return out
}

func round4StateOwnershipRecord(op string, ids []string, planRef, inventoryRef contracts.ArtifactRef) contracts.OwnershipRecord {
	sha := contracts.SHA256([]byte("artifact"))
	artifact := contracts.ArtifactRef{Path: "runs/" + op + "/cleanup.json", SHA256: sha, Bytes: "8"}
	deployments := make([]contracts.OwnershipDeploymentRecord, 0, len(ids))
	for i, id := range ids {
		before := contracts.DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/" + id, GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "missing"}
		after := contracts.DeploymentObservation{ObservedType: "symlink", Path: "/runtime/" + id, GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "object-" + id}
		bindings := []contracts.RuntimeBindingSummary{{Runtime: "pi", BindingIdentity: fmt.Sprintf("pi:skill-%02d", i), Status: "verification_required", EvidenceRef: &artifact}}
		if i < 5 {
			bindings = append(bindings, contracts.RuntimeBindingSummary{Runtime: "opencode", BindingIdentity: fmt.Sprintf("opencode:skill-%02d", i), Status: "verification_required", EvidenceRef: &artifact})
		}
		deployments = append(deployments, contracts.OwnershipDeploymentRecord{DeploymentID: id, BeforeObservation: before, AfterObservation: after, RuntimeBindingSummaries: bindings, OriginalPreimage: before, InstalledPostimage: &after, BackupEntryRef: &artifact, CleanupEvidenceRef: &artifact, RollbackAuthorityRefs: []contracts.ArtifactRef{artifact}, Result: "verification_required"})
	}
	return contracts.OwnershipRecord{Schema: contracts.SchemaOwnership, RecordID: "record-" + op, OperationID: contracts.OperationID(op), InstallationID: "install", PreviousHash: nil, PlanRef: planRef, InventoryRef: inventoryRef, JournalRef: contracts.JournalRef{OperationID: op, Path: "runs/" + op + "/journal.ndjson", SHA256: sha}, BackupSetRef: &contracts.BackupSetRef{BackupSetID: string(contracts.SHA256([]byte("backup"))), SHA256: sha}, DeploymentIDs: append([]string(nil), ids...), Deployments: deployments, AggregateEvent: "applied_unverified", OperationResult: "verification_required"}
}

func publishRound4BackupManifest(t *testing.T, adapter *filesystem.MemoryAdapter, roots state.Roots, record *contracts.OwnershipRecord) {
	t.Helper()
	if record.BackupSetRef == nil {
		return
	}
	entries := make([]contracts.BackupEntry, 0, len(record.DeploymentIDs))
	for _, id := range record.DeploymentIDs {
		entries = append(entries, contracts.BackupEntry{DeploymentID: id, Kind: "typed_missing", Payload: nil, Metadata: []string{}})
	}
	manifest := contracts.BackupManifest{Schema: contracts.SchemaBackupManifest, BackupSetID: record.BackupSetRef.BackupSetID, InstallationID: string(record.InstallationID), OperationID: record.OperationID, Operation: "apply", Entries: entries, Verified: true}
	manifestBytes, err := contracts.CanonicalBytes(manifest)
	if err != nil {
		t.Fatal(err)
	}
	adapter.PutFile(contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "backups", record.BackupSetRef.BackupSetID, "manifest.json")), manifestBytes)
	record.BackupSetRef.SHA256 = contracts.SHA256(manifestBytes)
}

func cloneRound4StateDeployments(in []contracts.OwnershipDeploymentRecord) []contracts.OwnershipDeploymentRecord {
	out := append([]contracts.OwnershipDeploymentRecord(nil), in...)
	for i := range out {
		out[i].RuntimeBindingSummaries = append([]contracts.RuntimeBindingSummary(nil), out[i].RuntimeBindingSummaries...)
	}
	return out
}
