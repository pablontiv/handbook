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
	inventoryPath := writePlanCommandInventory(t, "install_inventory.json")
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"plan", "--inventory", inventoryPath, "--intent", "install", "--out", "-"}, &stdout, &stderr)

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
	inventoryPath := writePlanCommandInventory(t, "install_inventory.json")
	outPath := filepath.Join(realTempDir(t), "plan.json")
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"plan", "--inventory", inventoryPath, "--intent", "install", "--out", outPath, "--output", "json"}, &stdout, &stderr)

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
}

func TestPlanRejectsJSONOutputWhenArtifactUsesStdout(t *testing.T) {
	inventoryPath := writePlanCommandInventory(t, "install_inventory.json")
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"plan", "--inventory", inventoryPath, "--intent", "install", "--out", "-", "--output", "json"}, &stdout, &stderr)

	if exitCode != 2 {
		t.Fatalf("exit code = %d, want 2", exitCode)
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q, want empty", stdout.String())
	}
}

func TestPlanSelectorMismatchExitsTwoAndMissingRestoreBackupExitsFour(t *testing.T) {
	inventoryPath := writePlanCommandInventory(t, "restore_inventory.json")
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"plan", "--inventory", inventoryPath, "--intent", "restore", "--installation", "installation-observed-001", "--out", "-"}, &stdout, &stderr)
	if exitCode != contracts.ExitInvalidInput {
		t.Fatalf("selector mismatch exit code = %d, want 2", exitCode)
	}
	if stdout.Len() != 0 {
		t.Fatalf("selector mismatch stdout = %q, want empty", stdout.String())
	}

	stdout.Reset()
	stderr.Reset()
	exitCode = Execute([]string{"plan", "--inventory", inventoryPath, "--intent", "restore", "--backup", "missing", "--out", "-"}, &stdout, &stderr)
	if exitCode != contracts.ExitPreconditionFailed {
		t.Fatalf("missing backup exit code = %d, want 4; stderr=%s stdout=%s", exitCode, stderr.String(), stdout.String())
	}
	if _, err := contracts.ParseCanonicalPlanEnvelope(stdout.Bytes()); err != nil {
		t.Fatalf("missing backup should emit blocker plan artifact: %v\n%s", err, stdout.String())
	}
}

func writePlanCommandInventory(t *testing.T, fixture string) string {
	t.Helper()
	data := mustReadFile(t, filepath.Join("..", "..", "internal", "distribution", "planning", "testdata", fixture))
	path := filepath.Join(realTempDir(t), fixture)
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}
