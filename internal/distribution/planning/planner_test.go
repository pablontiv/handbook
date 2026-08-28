package planning_test

import (
	"bytes"
	"context"
	"errors"
	"reflect"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/planning"
)

func TestBuildPlanInstallIsDeterministicAndDigestBound(t *testing.T) {
	raw := readPlannerFixture(t, "install_inventory.json")
	artifact, err := planning.DecodeInventoryArtifact(raw)
	if err != nil {
		t.Fatalf("DecodeInventoryArtifact() error = %v", err)
	}

	first, err := planning.BuildPlan(context.Background(), artifact, planning.Options{Intent: contracts.IntentInstall})
	if err != nil {
		t.Fatalf("BuildPlan() error = %v", err)
	}
	second, err := planning.BuildPlan(context.Background(), artifact, planning.Options{Intent: contracts.IntentInstall})
	if err != nil {
		t.Fatalf("second BuildPlan() error = %v", err)
	}
	firstBytes, err := planning.CanonicalPlanBytes(first)
	if err != nil {
		t.Fatalf("CanonicalPlanBytes(first) error = %v", err)
	}
	secondBytes, err := planning.CanonicalPlanBytes(second)
	if err != nil {
		t.Fatalf("CanonicalPlanBytes(second) error = %v", err)
	}
	if !bytes.Equal(firstBytes, secondBytes) {
		t.Fatalf("plan bytes changed:\nfirst=%s\nsecond=%s", firstBytes, secondBytes)
	}

	envelope, err := contracts.ParseCanonicalPlanEnvelope(firstBytes)
	if err != nil {
		t.Fatalf("plan is not a canonical envelope: %v\n%s", err, firstBytes)
	}
	if envelope.Payload.InventoryDigest != contracts.SHA256(raw) {
		t.Fatalf("inventory_digest = %s, want digest of exact raw inventory bytes %s", envelope.Payload.InventoryDigest, contracts.SHA256(raw))
	}
	payloadDigest, err := contracts.PayloadDigest(envelope.Payload)
	if err != nil {
		t.Fatalf("PayloadDigest() error = %v", err)
	}
	if envelope.ApprovalDigest != payloadDigest {
		t.Fatalf("approval_digest = %s, want payload digest %s", envelope.ApprovalDigest, payloadDigest)
	}
	if _, err := contracts.VerifyPlanEnvelope(firstBytes, envelope.ApprovalDigest); err != nil {
		t.Fatalf("VerifyPlanEnvelope() error = %v", err)
	}
	if !reflect.DeepEqual(first.Envelope.Payload.Inventory.Deployments[0].RuntimeBindings, envelope.Payload.Inventory.Deployments[0].RuntimeBindings) {
		t.Fatalf("embedded inventory was not preserved completely")
	}
}

func TestBuildPlanInstallContainsTenPhysicalDeploymentsFifteenBindingsAndNoEventIDs(t *testing.T) {
	result := buildFixturePlan(t, "install_inventory.json", planning.Options{Intent: contracts.IntentInstall})
	payload := result.Envelope.Payload
	if got := len(payload.Deployments); got != 10 {
		t.Fatalf("deployment count = %d, want 10", got)
	}
	if got := countPlanRuntimeBindings(payload.Deployments); got != 15 {
		t.Fatalf("runtime binding count = %d, want 15", got)
	}
	shared := deploymentBySkillAndSuffix(t, payload.Deployments, "adr", "/.agents/skills/adr")
	if got := len(shared.RuntimeBindings); got != 2 {
		t.Fatalf("shared physical slot binding count = %d, want 2", got)
	}
	if payload.Selector != nil {
		t.Fatalf("install selector = %#v, want nil", payload.Selector)
	}
	planBytes, err := planning.CanonicalPlanBytes(result)
	if err != nil {
		t.Fatalf("CanonicalPlanBytes() error = %v", err)
	}
	for _, forbidden := range []string{"operation_id", "installation_id", "backup_set_id", "journal", "receipt_id", "verification_id", "nonce", "timestamp"} {
		if bytes.Contains(planBytes, []byte(forbidden)) {
			t.Fatalf("install plan contains forbidden event/storage identifier %q: %s", forbidden, planBytes)
		}
	}
}

func TestBuildPlanValidatesSelectorCardinalityAndObservedSelectors(t *testing.T) {
	install := decodeFixture(t, "install_inventory.json")
	if _, err := planning.BuildPlan(context.Background(), install, planning.Options{Intent: contracts.IntentInstall, Selector: &contracts.Selector{Kind: contracts.SelectorInstallation, InstallationID: "unexpected"}}); !isPlanningExit(err, contracts.ExitInvalidInput) {
		t.Fatalf("install selector error = %v, want exit 2", err)
	}

	uninstall := decodeFixture(t, "uninstall_inventory.json")
	selector := &contracts.Selector{Kind: contracts.SelectorInstallation, InstallationID: "installation-observed-001"}
	result, err := planning.BuildPlan(context.Background(), uninstall, planning.Options{Intent: contracts.IntentUninstall, Selector: selector})
	if err != nil {
		t.Fatalf("uninstall BuildPlan() error = %v", err)
	}
	if result.Envelope.Payload.Selector == nil || result.Envelope.Payload.Selector.InstallationID != "installation-observed-001" {
		t.Fatalf("uninstall selector = %#v, want observed installation", result.Envelope.Payload.Selector)
	}

	_, err = planning.BuildPlan(context.Background(), uninstall, planning.Options{Intent: contracts.IntentUninstall, Selector: &contracts.Selector{Kind: contracts.SelectorInstallation, InstallationID: "installation-observed-001", BackupSetID: "backup-too"}})
	if !isPlanningExit(err, contracts.ExitInvalidInput) {
		t.Fatalf("selector cardinality error = %v, want exit 2", err)
	}
}

func TestBuildPlanRestoreRequiresObservedVerifiedBackupAndClassifiesBlockers(t *testing.T) {
	restore := decodeFixture(t, "restore_inventory.json")
	selector := &contracts.Selector{Kind: contracts.SelectorBackupSet, BackupSetID: "backup-observed-001"}
	result, err := planning.BuildPlan(context.Background(), restore, planning.Options{Intent: contracts.IntentRestore, Selector: selector})
	if err != nil {
		t.Fatalf("restore BuildPlan() error = %v", err)
	}
	if result.Envelope.Payload.Selector == nil || result.Envelope.Payload.Selector.BackupSetID != "backup-observed-001" {
		t.Fatalf("restore selector = %#v, want observed backup", result.Envelope.Payload.Selector)
	}

	_, err = planning.BuildPlan(context.Background(), restore, planning.Options{Intent: contracts.IntentRestore, Selector: &contracts.Selector{Kind: contracts.SelectorBackupSet, BackupSetID: "missing"}})
	if !isPlanningExit(err, contracts.ExitPreconditionFailed) {
		t.Fatalf("missing backup error = %v, want exit 4", err)
	}

	withCapability := restore
	withCapability.Inventory.Blockers = append(withCapability.Inventory.Blockers, contracts.Blocker{Code: "runtime_contract_missing", Severity: "error", Message: "capability unavailable"})
	_, err = planning.BuildPlan(context.Background(), withCapability, planning.Options{Intent: contracts.IntentRestore, Selector: &contracts.Selector{Kind: contracts.SelectorBackupSet, BackupSetID: "missing"}})
	if !isPlanningExit(err, contracts.ExitUnsupported) {
		t.Fatalf("capability+safe blocker error = %v, want capability exit 3", err)
	}
}

func TestDecodeInventoryArtifactRejectsNonCanonicalInventory(t *testing.T) {
	pretty := append([]byte("\n"), readPlannerFixture(t, "install_inventory.json")...)
	if _, err := planning.DecodeInventoryArtifact(pretty); err == nil {
		t.Fatalf("DecodeInventoryArtifact() accepted noncanonical inventory")
	}
}

func buildFixturePlan(t *testing.T, name string, opts planning.Options) planning.Result {
	t.Helper()
	artifact := decodeFixture(t, name)
	result, err := planning.BuildPlan(context.Background(), artifact, opts)
	if err != nil {
		t.Fatalf("BuildPlan(%s) error = %v", name, err)
	}
	return result
}

func decodeFixture(t *testing.T, name string) planning.InventoryArtifact {
	t.Helper()
	artifact, err := planning.DecodeInventoryArtifact(readPlannerFixture(t, name))
	if err != nil {
		t.Fatalf("DecodeInventoryArtifact(%s) error = %v", name, err)
	}
	return artifact
}

func readPlannerFixture(t *testing.T, name string) []byte {
	t.Helper()
	return mustReadFile(t, "testdata/"+name)
}

func countPlanRuntimeBindings(deployments []contracts.Deployment) int {
	count := 0
	for _, deployment := range deployments {
		count += len(deployment.RuntimeBindings)
	}
	return count
}

func isPlanningExit(err error, exit int) bool {
	var planErr planning.Error
	return errors.As(err, &planErr) && planErr.Exit == exit
}
