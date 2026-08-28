package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"waywarden/internal/distribution/contracts"
)

func TestPlanOutStdoutWritesCanonicalPlanAndHumanSummaryToStderr(t *testing.T) {
	fixture := writePlanCommandFixture(t, "install_inventory.json")
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"plan", "--inventory", fixture.inventoryPath, "--intent", "install", "--state-root", fixture.stateRoot, "--out", "-"}, &stdout, &stderr)

	if exitCode != 0 {
		t.Fatalf("exit code = %d, want 0; stderr=%s stdout=%s", exitCode, stderr.String(), stdout.String())
	}
	if stderr.Len() == 0 || !strings.Contains(stderr.String(), "plan") {
		t.Fatalf("stderr summary = %q, want plan summary", stderr.String())
	}
	envelope, err := contracts.ParseCanonicalPlanEnvelope(stdout.Bytes())
	if err != nil {
		t.Fatalf("stdout is not canonical plan: %v\n%s", err, stdout.String())
	}
	if envelope.Payload.Intent != contracts.IntentInstall || envelope.Payload.Selector != nil {
		t.Fatalf("plan payload = %#v, want install with nil selector", envelope.Payload)
	}
}

func TestPlanOutFileWithJSONWritesCommandResultToStdout(t *testing.T) {
	fixture := writePlanCommandFixture(t, "install_inventory.json")
	outPath := filepath.Join(fixture.artifactRoot, "plan.json")
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"plan", "--inventory", fixture.inventoryPath, "--intent", "install", "--state-root", fixture.stateRoot, "--out", outPath, "--output", "json"}, &stdout, &stderr)

	if exitCode != 0 {
		t.Fatalf("exit code = %d, want 0; stderr=%s stdout=%s", exitCode, stderr.String(), stdout.String())
	}
	var result contracts.CommandResult
	if err := contracts.StrictParseCanonical(stdout.Bytes(), &result); err != nil {
		t.Fatalf("stdout is not canonical command result: %v\n%s", err, stdout.String())
	}
	if result.Kind != contracts.ResultArtifact || result.Command != "plan" || result.Status != contracts.ResultStatusSuccess {
		t.Fatalf("command result = %#v, want successful plan artifact", result)
	}
	if result.Artifact == nil || result.Artifact.Schema != contracts.SchemaPlan {
		t.Fatalf("artifact result = %#v, want plan artifact", result.Artifact)
	}
	data, err := os.ReadFile(outPath)
	if err != nil {
		t.Fatalf("read plan artifact: %v", err)
	}
	if got := contracts.SHA256(data); got != result.Artifact.SHA256 {
		t.Fatalf("artifact sha = %s, command result sha = %s", got, result.Artifact.SHA256)
	}
	assertRealHomeWaywardenArtifactsNotCreated(t, fixture)
}

func TestPlanRejectsJSONOutputWhenArtifactUsesStdout(t *testing.T) {
	fixture := writePlanCommandFixture(t, "install_inventory.json")
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"plan", "--inventory", fixture.inventoryPath, "--intent", "install", "--state-root", fixture.stateRoot, "--out", "-", "--output", "json"}, &stdout, &stderr)

	if exitCode != 2 {
		t.Fatalf("exit code = %d, want 2", exitCode)
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q, want empty", stdout.String())
	}
}

func TestPlanStateRootForbidsFileDestinationUnderExplicitStateRoot(t *testing.T) {
	fixture := writePlanCommandFixture(t, "install_inventory.json")
	outPath := filepath.Join(fixture.stateRoot, "plan.json")
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"plan", "--inventory", fixture.inventoryPath, "--intent", "install", "--state-root", fixture.stateRoot, "--out", outPath}, &stdout, &stderr)

	if exitCode != contracts.ExitPreconditionFailed {
		t.Fatalf("exit code = %d, want 4; stderr=%s stdout=%s", exitCode, stderr.String(), stdout.String())
	}
	assertRealHomeWaywardenArtifactsNotCreated(t, fixture)
}

func TestPlanSelectorMismatchExitsTwoAndMissingRestoreBackupExitsFour(t *testing.T) {
	fixture := writePlanCommandFixture(t, "restore_inventory.json")
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"plan", "--inventory", fixture.inventoryPath, "--intent", "restore", "--installation", "installation-observed-001", "--state-root", fixture.stateRoot, "--out", "-"}, &stdout, &stderr)
	if exitCode != contracts.ExitInvalidInput {
		t.Fatalf("selector mismatch exit code = %d, want 2", exitCode)
	}
	if stdout.Len() != 0 {
		t.Fatalf("selector mismatch stdout = %q, want empty", stdout.String())
	}

	stdout.Reset()
	stderr.Reset()
	exitCode = Execute([]string{"plan", "--inventory", fixture.inventoryPath, "--intent", "restore", "--backup", "missing", "--state-root", fixture.stateRoot, "--out", "-"}, &stdout, &stderr)
	if exitCode != contracts.ExitPreconditionFailed {
		t.Fatalf("missing backup exit code = %d, want 4; stderr=%s stdout=%s", exitCode, stderr.String(), stdout.String())
	}
	if _, err := contracts.ParseCanonicalPlanEnvelope(stdout.Bytes()); err != nil {
		t.Fatalf("missing backup should emit blocker plan artifact: %v\n%s", err, stdout.String())
	}
}

type planCommandFixture struct {
	inventoryPath string
	stateRoot     string
	artifactRoot  string
	realHomeProbe []homeProbe
}

type homeProbe struct {
	path   string
	exists bool
}

func writePlanCommandFixture(t *testing.T, fixture string) planCommandFixture {
	t.Helper()
	testRoot := realTempDir(t)
	home := filepath.Join(testRoot, "home")
	xdgStateHome := filepath.Join(testRoot, "xdg-state")
	localAppData := filepath.Join(testRoot, "local-app-data")
	stateRoot := filepath.Join(testRoot, "state")
	artifactRoot := filepath.Join(testRoot, "artifacts")
	sourceRoot := filepath.Join(testRoot, "source-root")
	runtimeRoot := filepath.Join(testRoot, "runtime-root")
	for _, dir := range []string{home, xdgStateHome, localAppData, stateRoot, artifactRoot, sourceRoot, runtimeRoot} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
	}

	realHome := os.Getenv("HOME")
	fixtureData := planCommandInventoryWithRoots(t, fixture, sourceRoot, runtimeRoot)
	path := filepath.Join(testRoot, fixture)
	if err := os.WriteFile(path, fixtureData, 0o600); err != nil {
		t.Fatal(err)
	}

	t.Setenv("HOME", home)
	t.Setenv("XDG_STATE_HOME", xdgStateHome)
	t.Setenv("LOCALAPPDATA", localAppData)
	return planCommandFixture{inventoryPath: path, stateRoot: stateRoot, artifactRoot: artifactRoot, realHomeProbe: captureRealHomeWaywardenProbes(realHome)}
}

func planCommandInventoryWithRoots(t *testing.T, fixture, sourceRoot, runtimeRoot string) []byte {
	t.Helper()
	data := mustReadFile(t, filepath.Join("..", "..", "internal", "distribution", "planning", "testdata", fixture))
	inventory, err := contracts.ParseCanonicalInventory(data)
	if err != nil {
		t.Fatalf("ParseCanonicalInventory(%s) error = %v", fixture, err)
	}
	sourceBySkill := map[string]string{}
	for i := range inventory.Sources {
		sourceIdentity := filepath.Join(sourceRoot, inventory.Sources[i].SkillID)
		inventory.Sources[i].SourceIdentity = sourceIdentity
		sourceBySkill[inventory.Sources[i].SkillID] = sourceIdentity
	}
	for i := range inventory.Deployments {
		if sourceIdentity, ok := sourceBySkill[inventory.Deployments[i].SkillID]; ok {
			inventory.Deployments[i].SourceIdentity = sourceIdentity
		}
		for j := range inventory.Deployments[i].RuntimeBindings {
			inventory.Deployments[i].RuntimeBindings[j].Root = runtimeRoot
		}
	}
	for i := range inventory.RuntimeBindings {
		inventory.RuntimeBindings[i].Root = runtimeRoot
	}
	canonical, err := contracts.CanonicalBytes(inventory)
	if err != nil {
		t.Fatalf("CanonicalBytes(%s) error = %v", fixture, err)
	}
	if err := contracts.ValidateSchema(contracts.SchemaInventory, canonical); err != nil {
		t.Fatalf("ValidateSchema(%s) error = %v", fixture, err)
	}
	return canonical
}

func captureRealHomeWaywardenProbes(realHome string) []homeProbe {
	if realHome == "" {
		return nil
	}
	candidates := []string{
		filepath.Join(realHome, ".local", "state", "waywarden"),
		filepath.Join(realHome, "Library", "Application Support", "waywarden"),
		filepath.Join(realHome, "AppData", "Local", "waywarden"),
	}
	probes := make([]homeProbe, 0, len(candidates))
	for _, path := range candidates {
		_, err := os.Lstat(path)
		probes = append(probes, homeProbe{path: path, exists: err == nil})
	}
	return probes
}

func assertRealHomeWaywardenArtifactsNotCreated(t *testing.T, fixture planCommandFixture) {
	t.Helper()
	for _, probe := range fixture.realHomeProbe {
		if probe.exists {
			continue
		}
		if _, err := os.Lstat(probe.path); err == nil {
			t.Fatalf("real HOME was touched: %s was created", probe.path)
		} else if !os.IsNotExist(err) {
			t.Fatalf("inspect real HOME probe %s: %v", probe.path, err)
		}
	}
}
