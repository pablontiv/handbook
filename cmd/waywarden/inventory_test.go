package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"waywarden/internal/distribution/contracts"
)

func TestInventoryOutStdoutWritesArtifactAndHumanSummaryToStderr(t *testing.T) {
	fixture := writeInventoryCommandFixture(t)
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"inventory", "--manifest", fixture.manifestPath, "--state-root", fixture.stateRoot, "--out", "-"}, &stdout, &stderr)

	if exitCode != 0 {
		t.Fatalf("exit code = %d, want 0; stderr=%s stdout=%s", exitCode, stderr.String(), stdout.String())
	}
	if stderr.Len() == 0 || !strings.Contains(stderr.String(), "inventory") {
		t.Fatalf("stderr summary = %q, want inventory summary", stderr.String())
	}
	var artifact contracts.Inventory
	if err := contracts.StrictParseCanonical(stdout.Bytes(), &artifact); err != nil {
		t.Fatalf("stdout is not canonical inventory: %v\n%s", err, stdout.String())
	}
	if artifact.Schema != contracts.SchemaInventory {
		t.Fatalf("schema = %q, want %q", artifact.Schema, contracts.SchemaInventory)
	}
	if len(artifact.Sources) != 1 {
		t.Fatalf("sources = %#v, want one source", artifact.Sources)
	}
}

func TestInventoryOutFileWithJSONWritesCommandResultToStdout(t *testing.T) {
	fixture := writeInventoryCommandFixture(t)
	outPath := filepath.Join(realTempDir(t), "inventory.json")
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"inventory", "--manifest", fixture.manifestPath, "--state-root", fixture.stateRoot, "--out", outPath, "--output", "json"}, &stdout, &stderr)

	if exitCode != 0 {
		t.Fatalf("exit code = %d, want 0; stderr=%s stdout=%s", exitCode, stderr.String(), stdout.String())
	}
	if stderr.Len() == 0 || !strings.Contains(stderr.String(), "inventory") {
		t.Fatalf("stderr summary = %q, want inventory summary", stderr.String())
	}
	var result contracts.CommandResult
	if err := contracts.StrictParseCanonical(stdout.Bytes(), &result); err != nil {
		t.Fatalf("stdout is not canonical command result: %v\n%s", err, stdout.String())
	}
	if result.Kind != contracts.ResultArtifact || result.Command != "inventory" || result.Status != contracts.ResultStatusSuccess {
		t.Fatalf("command result = %#v, want successful inventory artifact", result)
	}
	if result.Artifact == nil || result.Artifact.Schema != contracts.SchemaInventory {
		t.Fatalf("artifact result = %#v, want inventory artifact", result.Artifact)
	}
	data, err := os.ReadFile(outPath)
	if err != nil {
		t.Fatalf("read out artifact: %v", err)
	}
	if got := contracts.SHA256(data); got != result.Artifact.SHA256 {
		t.Fatalf("artifact sha = %s, command result sha = %s", got, result.Artifact.SHA256)
	}
}

func TestInventoryRejectsJSONOutputWhenArtifactUsesStdout(t *testing.T) {
	fixture := writeInventoryCommandFixture(t)
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"inventory", "--manifest", fixture.manifestPath, "--state-root", fixture.stateRoot, "--out", "-", "--output", "json"}, &stdout, &stderr)

	if exitCode != 2 {
		t.Fatalf("exit code = %d, want 2", exitCode)
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q, want empty", stdout.String())
	}
}

func TestInventoryRejectsRelativeManifestOverride(t *testing.T) {
	fixture := writeInventoryCommandFixture(t)
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"inventory", "--manifest", filepath.Join("distribution", "manifest.json"), "--state-root", fixture.stateRoot, "--out", "-"}, &stdout, &stderr)

	if exitCode != 2 {
		t.Fatalf("exit code = %d, want 2", exitCode)
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q, want empty", stdout.String())
	}
}

func TestInventoryExistingOutputDestinationExitsFourAndDoesNotReplace(t *testing.T) {
	fixture := writeInventoryCommandFixture(t)
	outPath := filepath.Join(realTempDir(t), "inventory.json")
	original := []byte("do-not-replace")
	if err := os.WriteFile(outPath, original, 0o600); err != nil {
		t.Fatal(err)
	}
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"inventory", "--manifest", fixture.manifestPath, "--state-root", fixture.stateRoot, "--out", outPath}, &stdout, &stderr)

	if exitCode != 4 {
		t.Fatalf("exit code = %d, want 4; stderr=%s stdout=%s", exitCode, stderr.String(), stdout.String())
	}
	got, err := os.ReadFile(outPath)
	if err != nil {
		t.Fatalf("read output destination: %v", err)
	}
	if !bytes.Equal(got, original) {
		t.Fatalf("output destination was replaced: got %q want %q", got, original)
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q, want empty", stdout.String())
	}
}

type inventoryCommandFixture struct {
	manifestPath string
	stateRoot    string
}

func realTempDir(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	resolved, err := filepath.EvalSymlinks(dir)
	if err != nil {
		t.Fatal(err)
	}
	return resolved
}

func writeInventoryCommandFixture(t *testing.T) inventoryCommandFixture {
	t.Helper()
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("XDG_STATE_HOME", filepath.Join(home, ".local", "state"))
	t.Setenv("LOCALAPPDATA", filepath.Join(home, "AppData", "Local"))

	repo := t.TempDir()
	skillDir := filepath.Join(repo, "skills", "adr")
	if err := os.MkdirAll(skillDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(skillDir, "SKILL.md"), []byte("# adr\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	manifest := contracts.Manifest{
		Schema:       contracts.SchemaManifest,
		Repository:   contracts.RepositoryIdentity{ID: "waywarden-skills", SourceRoot: "."},
		Skills:       []contracts.ManifestSkill{{SkillID: "adr", SourcePath: "skills/adr", EntryFiles: []string{"SKILL.md"}}},
		RuntimeRoots: []contracts.RuntimeRoot{{Runtime: "pi", Root: filepath.ToSlash(filepath.Join(".agents", "skills")), LinkStrategy: "direct_symlink"}},
		Adapters:     []contracts.AdapterBinding{{Runtime: "pi", Schemas: []string{"pi.get_commands/v0.84.3"}}},
	}
	manifestBytes, err := contracts.CanonicalBytes(manifest)
	if err != nil {
		t.Fatal(err)
	}
	manifestDir := filepath.Join(repo, "distribution")
	if err := os.MkdirAll(manifestDir, 0o755); err != nil {
		t.Fatal(err)
	}
	manifestPath := filepath.Join(manifestDir, "manifest.json")
	if err := os.WriteFile(manifestPath, manifestBytes, 0o644); err != nil {
		t.Fatal(err)
	}
	stateRoot := filepath.Join(t.TempDir(), "state")
	return inventoryCommandFixture{manifestPath: manifestPath, stateRoot: stateRoot}
}
