package planning_test

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"reflect"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
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

	nonCapabilityErrorSeverity := decodeModifiedFixture(t, "restore_inventory.json", func(inventory *contracts.Inventory) {
		inventory.Blockers = append(inventory.Blockers, contracts.Blocker{Code: "operator_review_required", Severity: "error", Message: "safe blocker requiring operator review"})
	})
	_, err = planning.BuildPlan(context.Background(), nonCapabilityErrorSeverity, planning.Options{Intent: contracts.IntentRestore, Selector: &contracts.Selector{Kind: contracts.SelectorBackupSet, BackupSetID: "missing"}})
	if !isPlanningExit(err, contracts.ExitPreconditionFailed) {
		t.Fatalf("non-capability error-severity blocker error = %v, want safe precondition exit 4", err)
	}

	withCapability := decodeModifiedFixture(t, "restore_inventory.json", func(inventory *contracts.Inventory) {
		inventory.Blockers = append(inventory.Blockers, contracts.Blocker{Code: "runtime_contract_missing", Severity: "warning", Message: "capability unavailable"})
	})
	_, err = planning.BuildPlan(context.Background(), withCapability, planning.Options{Intent: contracts.IntentRestore, Selector: &contracts.Selector{Kind: contracts.SelectorBackupSet, BackupSetID: "missing"}})
	if !isPlanningExit(err, contracts.ExitUnsupported) {
		t.Fatalf("capability+safe blocker error = %v, want capability exit 3", err)
	}
}

func TestInventoryArtifactIsOpaqueAndPlanDigestUsesExactAcceptedBytes(t *testing.T) {
	if _, ok := reflect.TypeOf(planning.InventoryArtifact{}).FieldByName("Inventory"); ok {
		t.Fatalf("InventoryArtifact exposes mutable Inventory field; want opaque decoded artifact")
	}

	raw := canonicalModifiedInventory(t, "install_inventory.json", func(inventory *contracts.Inventory) {
		inventory.Blockers = append(inventory.Blockers, contracts.Blocker{Code: "operator_review_required", Severity: "warning", Message: "digest evidence"})
	})
	artifact, err := planning.DecodeInventoryArtifact(raw)
	if err != nil {
		t.Fatalf("DecodeInventoryArtifact() error = %v", err)
	}
	result, err := planning.BuildPlan(context.Background(), artifact, planning.Options{Intent: contracts.IntentInstall})
	if err != nil {
		t.Fatalf("BuildPlan() error = %v", err)
	}
	if result.Envelope.Payload.InventoryDigest != contracts.SHA256(raw) {
		t.Fatalf("inventory_digest = %s, want exact accepted raw digest %s", result.Envelope.Payload.InventoryDigest, contracts.SHA256(raw))
	}
}

func TestPlanFileOutputDerivesForbiddenRootsFromInventoryStateAndLocks(t *testing.T) {
	tmp := t.TempDir()
	home := filepath.Join(tmp, "home")
	xdgState := filepath.Join(tmp, "xdg-state")
	stateRoot := filepath.Join(tmp, "state-root")
	lockRoot := filepath.Join(xdgState, "waywarden", "locks")
	sourceA := filepath.Join(tmp, "source-a")
	sourceB := filepath.Join(tmp, "source-b")
	runtimeRoot := filepath.Join(tmp, "runtime-root")
	raw := inventoryWithPublicationRoots(t, sourceA, sourceB, runtimeRoot)

	cases := []struct {
		name        string
		destination string
		wantExit    int
	}{
		{name: "allowed artifact root", destination: filepath.Join(tmp, "artifacts", "plan.json"), wantExit: 0},
		{name: "first source identity", destination: filepath.Join(sourceA, "plan.json"), wantExit: contracts.ExitPreconditionFailed},
		{name: "second source identity", destination: filepath.Join(sourceB, "nested", "plan.json"), wantExit: contracts.ExitPreconditionFailed},
		{name: "runtime binding root", destination: filepath.Join(runtimeRoot, "plan.json"), wantExit: contracts.ExitPreconditionFailed},
		{name: "selected state root", destination: filepath.Join(stateRoot, "plan.json"), wantExit: contracts.ExitPreconditionFailed},
		{name: "coordination lock root", destination: filepath.Join(lockRoot, "plan.json"), wantExit: contracts.ExitPreconditionFailed},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			adapter := filesystem.NewMemoryAdapter()
			adapter.SetEnvironment(filesystem.PlatformEnv{Home: home, XDGStateHome: xdgState, LocalAppData: filepath.Join(tmp, "local-app-data")})
			inventoryPath := contracts.AbsolutePath(filepath.Join(tmp, "inventory.json"))
			adapter.PutFile(inventoryPath, raw)

			_, err := planning.NewService(adapter).Plan(context.Background(), planning.Options{Intent: contracts.IntentInstall, InventoryPath: inventoryPath, Destination: contracts.AbsolutePath(tc.destination), StateRoot: contracts.AbsolutePath(stateRoot)})
			if tc.wantExit == 0 {
				if err != nil {
					t.Fatalf("Plan() error = %v, want success", err)
				}
				return
			}
			if !isPlanningExit(err, tc.wantExit) {
				t.Fatalf("Plan() error = %v, want exit %d", err, tc.wantExit)
			}
		})
	}
}

func TestPlanFileOutputUnionsCanonicalInventoryRootEvidenceAcrossViews(t *testing.T) {
	tmp := t.TempDir()
	home := filepath.Join(tmp, "home")
	xdgState := filepath.Join(tmp, "xdg-state")
	stateRoot := filepath.Join(tmp, "state-root")
	topLevelSource := filepath.Join(tmp, "top-level-source")
	deploymentOnlySource := filepath.Join(tmp, "deployment-only-source")
	topLevelRuntime := filepath.Join(tmp, "top-level-runtime")
	deploymentOnlyRuntime := filepath.Join(tmp, "deployment-only-runtime")

	cases := []struct {
		name        string
		raw         []byte
		destination string
	}{
		{
			name:        "source root present only in deployments",
			destination: filepath.Join(deploymentOnlySource, "nested", "plan.json"),
			raw: canonicalModifiedInventory(t, "install_inventory.json", func(inventory *contracts.Inventory) {
				for i := range inventory.Sources {
					inventory.Sources[i].SourceIdentity = topLevelSource
				}
				for i := range inventory.Deployments {
					inventory.Deployments[i].SourceIdentity = topLevelSource
				}
				inventory.Deployments[0].SourceIdentity = deploymentOnlySource
				for i := range inventory.RuntimeBindings {
					inventory.RuntimeBindings[i].Root = topLevelRuntime
				}
				for i := range inventory.Deployments {
					for j := range inventory.Deployments[i].RuntimeBindings {
						inventory.Deployments[i].RuntimeBindings[j].Root = topLevelRuntime
					}
				}
			}),
		},
		{
			name:        "runtime root present only in deployments",
			destination: filepath.Join(deploymentOnlyRuntime, "plan.json"),
			raw: canonicalModifiedInventory(t, "install_inventory.json", func(inventory *contracts.Inventory) {
				for i := range inventory.Sources {
					inventory.Sources[i].SourceIdentity = topLevelSource
				}
				for i := range inventory.Deployments {
					inventory.Deployments[i].SourceIdentity = topLevelSource
				}
				for i := range inventory.RuntimeBindings {
					inventory.RuntimeBindings[i].Root = topLevelRuntime
				}
				for i := range inventory.Deployments {
					for j := range inventory.Deployments[i].RuntimeBindings {
						inventory.Deployments[i].RuntimeBindings[j].Root = topLevelRuntime
					}
				}
				inventory.Deployments[0].RuntimeBindings[0].Root = deploymentOnlyRuntime
			}),
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			adapter := filesystem.NewMemoryAdapter()
			adapter.SetEnvironment(filesystem.PlatformEnv{Home: home, XDGStateHome: xdgState, LocalAppData: filepath.Join(tmp, "local-app-data")})
			inventoryPath := contracts.AbsolutePath(filepath.Join(tmp, tc.name, "inventory.json"))
			adapter.PutFile(inventoryPath, tc.raw)

			_, err := planning.NewService(adapter).Plan(context.Background(), planning.Options{Intent: contracts.IntentInstall, InventoryPath: inventoryPath, Destination: contracts.AbsolutePath(tc.destination), StateRoot: contracts.AbsolutePath(stateRoot)})
			if !isPlanningExit(err, contracts.ExitPreconditionFailed) {
				t.Fatalf("Plan() error = %v, want destination rejected with exit 4", err)
			}
		})
	}
}

func TestPlanFileOutputFailsClosedWhenTotalPublicationRootEvidenceIsEmpty(t *testing.T) {
	tmp := t.TempDir()
	home := filepath.Join(tmp, "home")
	xdgState := filepath.Join(tmp, "xdg-state")
	stateRoot := filepath.Join(tmp, "state-root")
	validSource := filepath.Join(tmp, "source")
	validRuntime := filepath.Join(tmp, "runtime")

	cases := []struct {
		name string
		raw  []byte
	}{
		{
			name: "source roots empty in both views",
			raw: canonicalModifiedInventory(t, "install_inventory.json", func(inventory *contracts.Inventory) {
				inventory.Sources = []contracts.SourceObservation{}
				for i := range inventory.Deployments {
					inventory.Deployments[i].SourceIdentity = ""
					for j := range inventory.Deployments[i].RuntimeBindings {
						inventory.Deployments[i].RuntimeBindings[j].Root = validRuntime
					}
				}
				for i := range inventory.RuntimeBindings {
					inventory.RuntimeBindings[i].Root = validRuntime
				}
			}),
		},
		{
			name: "runtime roots empty in both views",
			raw: canonicalModifiedInventory(t, "install_inventory.json", func(inventory *contracts.Inventory) {
				for i := range inventory.Sources {
					inventory.Sources[i].SourceIdentity = validSource
				}
				for i := range inventory.Deployments {
					inventory.Deployments[i].SourceIdentity = validSource
					inventory.Deployments[i].RuntimeBindings = []contracts.RuntimeBinding{}
				}
				inventory.RuntimeBindings = []contracts.RuntimeBinding{}
			}),
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			adapter := failIfPublishAdapter{MemoryAdapter: filesystem.NewMemoryAdapter()}
			adapter.SetEnvironment(filesystem.PlatformEnv{Home: home, XDGStateHome: xdgState, LocalAppData: filepath.Join(tmp, "local-app-data")})
			inventoryPath := contracts.AbsolutePath(filepath.Join(tmp, tc.name, "inventory.json"))
			adapter.PutFile(inventoryPath, tc.raw)

			_, err := planning.NewService(&adapter).Plan(context.Background(), planning.Options{Intent: contracts.IntentInstall, InventoryPath: inventoryPath, Destination: contracts.AbsolutePath(filepath.Join(tmp, tc.name, "out", "plan.json")), StateRoot: contracts.AbsolutePath(stateRoot)})
			if !isPlanningExit(err, contracts.ExitUnsupported) {
				t.Fatalf("Plan() error = %v, want fail-closed exit 3", err)
			}
			if adapter.publishCalled {
				t.Fatalf("PublishNoReplace was called despite missing total root evidence")
			}
		})
	}
}

func TestPlanFileOutputFailsClosedWhenPublicationRootProofIsMissing(t *testing.T) {
	tmp := t.TempDir()
	home := filepath.Join(tmp, "home")
	xdgState := filepath.Join(tmp, "xdg-state")
	stateRoot := filepath.Join(tmp, "state-root")
	validSource := filepath.Join(tmp, "source")
	validRuntime := filepath.Join(tmp, "runtime")

	cases := []struct {
		name      string
		raw       []byte
		stateRoot contracts.AbsolutePath
		env       filesystem.PlatformEnv
	}{
		{name: "missing source identity", raw: canonicalModifiedInventory(t, "install_inventory.json", func(inventory *contracts.Inventory) { inventory.Sources[0].SourceIdentity = "" }), stateRoot: contracts.AbsolutePath(stateRoot), env: filesystem.PlatformEnv{Home: home, XDGStateHome: xdgState}},
		{name: "relative deployment source identity", raw: canonicalModifiedInventory(t, "install_inventory.json", func(inventory *contracts.Inventory) {
			for i := range inventory.Sources {
				inventory.Sources[i].SourceIdentity = validSource
			}
			for i := range inventory.Deployments {
				inventory.Deployments[i].SourceIdentity = validSource
			}
			inventory.Deployments[0].SourceIdentity = "relative/source"
		}), stateRoot: contracts.AbsolutePath(stateRoot), env: filesystem.PlatformEnv{Home: home, XDGStateHome: xdgState}},
		{name: "relative runtime root", raw: canonicalModifiedInventory(t, "install_inventory.json", func(inventory *contracts.Inventory) { inventory.RuntimeBindings[0].Root = "relative/runtime" }), stateRoot: contracts.AbsolutePath(stateRoot), env: filesystem.PlatformEnv{Home: home, XDGStateHome: xdgState}},
		{name: "missing deployment runtime root", raw: canonicalModifiedInventory(t, "install_inventory.json", func(inventory *contracts.Inventory) {
			for i := range inventory.RuntimeBindings {
				inventory.RuntimeBindings[i].Root = validRuntime
			}
			for i := range inventory.Deployments {
				for j := range inventory.Deployments[i].RuntimeBindings {
					inventory.Deployments[i].RuntimeBindings[j].Root = validRuntime
				}
			}
			inventory.Deployments[0].RuntimeBindings[0].Root = ""
		}), stateRoot: contracts.AbsolutePath(stateRoot), env: filesystem.PlatformEnv{Home: home, XDGStateHome: xdgState}},
		{name: "missing default state root environment", raw: inventoryWithPublicationRoots(t, validSource, validSource, validRuntime), env: filesystem.PlatformEnv{}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			adapter := filesystem.NewMemoryAdapter()
			adapter.SetEnvironment(tc.env)
			inventoryPath := contracts.AbsolutePath(filepath.Join(tmp, tc.name, "inventory.json"))
			adapter.PutFile(inventoryPath, tc.raw)

			_, err := planning.NewService(adapter).Plan(context.Background(), planning.Options{Intent: contracts.IntentInstall, InventoryPath: inventoryPath, Destination: contracts.AbsolutePath(filepath.Join(tmp, tc.name, "out", "plan.json")), StateRoot: tc.stateRoot})
			if !isPlanningExit(err, contracts.ExitUnsupported) {
				t.Fatalf("Plan() error = %v, want fail-closed exit 3", err)
			}
		})
	}
}

func TestPlanStdoutDoesNotReadEnvironmentForPublicationRoots(t *testing.T) {
	tmp := t.TempDir()
	raw := inventoryWithPublicationRoots(t, filepath.Join(tmp, "source-a"), filepath.Join(tmp, "source-b"), filepath.Join(tmp, "runtime"))
	adapter := noEnvironmentAdapter{MemoryAdapter: filesystem.NewMemoryAdapter()}
	inventoryPath := contracts.AbsolutePath(filepath.Join(tmp, "inventory.json"))
	adapter.PutFile(inventoryPath, raw)
	var artifact []byte

	_, err := planning.NewService(adapter).Plan(context.Background(), planning.Options{Intent: contracts.IntentInstall, InventoryPath: inventoryPath, ArtifactSink: func(data []byte) error {
		artifact = append([]byte(nil), data...)
		return nil
	}})
	if err != nil {
		t.Fatalf("Plan() error = %v, want stdout publication without environment reads", err)
	}
	if _, err := contracts.ParseCanonicalPlanEnvelope(artifact); err != nil {
		t.Fatalf("artifact sink did not receive canonical plan: %v", err)
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

func decodeModifiedFixture(t *testing.T, name string, mutate func(*contracts.Inventory)) planning.InventoryArtifact {
	t.Helper()
	artifact, err := planning.DecodeInventoryArtifact(canonicalModifiedInventory(t, name, mutate))
	if err != nil {
		t.Fatalf("DecodeInventoryArtifact(%s modified) error = %v", name, err)
	}
	return artifact
}

func canonicalModifiedInventory(t *testing.T, name string, mutate func(*contracts.Inventory)) []byte {
	t.Helper()
	inventory, err := contracts.ParseCanonicalInventory(readPlannerFixture(t, name))
	if err != nil {
		t.Fatalf("ParseCanonicalInventory(%s) error = %v", name, err)
	}
	mutate(&inventory)
	canonical, err := contracts.CanonicalBytes(inventory)
	if err != nil {
		t.Fatalf("CanonicalBytes(%s modified) error = %v", name, err)
	}
	if err := contracts.ValidateSchema(contracts.SchemaInventory, canonical); err != nil {
		t.Fatalf("ValidateSchema(%s modified) error = %v", name, err)
	}
	return canonical
}

func inventoryWithPublicationRoots(t *testing.T, sourceA, sourceB, runtimeRoot string) []byte {
	t.Helper()
	return canonicalModifiedInventory(t, "install_inventory.json", func(inventory *contracts.Inventory) {
		sourceBySkill := map[string]string{}
		for i := range inventory.Sources {
			sourceIdentity := filepath.Clean(sourceA)
			if i == 1 {
				sourceIdentity = filepath.Clean(sourceB)
			} else if i > 1 {
				sourceIdentity = filepath.Join(sourceA, fmt.Sprintf("source-%d", i))
			}
			inventory.Sources[i].SourceIdentity = sourceIdentity
			sourceBySkill[inventory.Sources[i].SkillID] = sourceIdentity
		}
		for i := range inventory.Deployments {
			if sourceIdentity, ok := sourceBySkill[inventory.Deployments[i].SkillID]; ok {
				inventory.Deployments[i].SourceIdentity = sourceIdentity
			}
			for j := range inventory.Deployments[i].RuntimeBindings {
				inventory.Deployments[i].RuntimeBindings[j].Root = filepath.Clean(runtimeRoot)
			}
		}
		for i := range inventory.RuntimeBindings {
			inventory.RuntimeBindings[i].Root = filepath.Clean(runtimeRoot)
		}
	})
}

func readPlannerFixture(t *testing.T, name string) []byte {
	t.Helper()
	return mustReadFile(t, "testdata/"+name)
}

type noEnvironmentAdapter struct {
	*filesystem.MemoryAdapter
}

func (a noEnvironmentAdapter) Environment(context.Context) (filesystem.PlatformEnv, error) {
	return filesystem.PlatformEnv{}, errors.New("environment should not be read for stdout artifact output")
}

type failIfPublishAdapter struct {
	*filesystem.MemoryAdapter
	publishCalled bool
}

func (a *failIfPublishAdapter) PublishNoReplace(ctx context.Context, destination contracts.AbsolutePath, canonical []byte, forbiddenRoots filesystem.ForbiddenRoots) error {
	a.publishCalled = true
	return a.MemoryAdapter.PublishNoReplace(ctx, destination, canonical, forbiddenRoots)
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
