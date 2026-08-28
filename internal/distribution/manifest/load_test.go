package manifest_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/manifest"
)

func TestManifestLoadDefaultPathIsCheckoutBound(t *testing.T) {
	checkout := writeManifestFixture(t)

	loaded, err := manifest.Load(manifest.LoadOptions{CWD: checkout})
	if err != nil {
		t.Fatalf("Load default manifest: %v", err)
	}

	wantManifest := filepath.Join(checkout, "distribution", "manifest.json")
	if loaded.ManifestPath != wantManifest {
		t.Fatalf("manifest path = %q, want %q", loaded.ManifestPath, wantManifest)
	}
	wantSourceRoot, err := filesystem.CanonicalIdentity(checkout)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.SourceRoot != wantSourceRoot {
		t.Fatalf("source root = %q, want %q", loaded.SourceRoot, wantSourceRoot)
	}
	if got := len(loaded.Manifest.Skills); got != 5 {
		t.Fatalf("skill count = %d, want 5", got)
	}
}

func TestManifestLoadAcceptsAbsoluteOverride(t *testing.T) {
	checkout := writeManifestFixture(t)
	manifestPath := filepath.Join(checkout, "distribution", "manifest.json")

	loaded, err := manifest.Load(manifest.LoadOptions{CWD: t.TempDir(), ManifestPath: manifestPath})
	if err != nil {
		t.Fatalf("Load absolute manifest override: %v", err)
	}
	if loaded.ManifestPath != manifestPath {
		t.Fatalf("manifest path = %q, want %q", loaded.ManifestPath, manifestPath)
	}
	wantSourceRoot, err := filesystem.CanonicalIdentity(checkout)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.SourceRoot != wantSourceRoot {
		t.Fatalf("source root = %q, want %q", loaded.SourceRoot, wantSourceRoot)
	}
}

func TestManifestLoadRejectsRelativeOverride(t *testing.T) {
	_, err := manifest.Load(manifest.LoadOptions{CWD: t.TempDir(), ManifestPath: filepath.Join("distribution", "manifest.json")})
	if err == nil {
		t.Fatal("Load accepted a relative manifest override")
	}
	if !strings.Contains(err.Error(), "absolute") {
		t.Fatalf("error = %q, want absolute-path rejection", err.Error())
	}
}

func TestManifestLoadRejectsSourceEscape(t *testing.T) {
	checkout := t.TempDir()
	if err := os.MkdirAll(filepath.Join(checkout, "distribution"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "distribution", "manifest.json"), []byte(escapedManifestJSON()), 0o644); err != nil {
		t.Fatal(err)
	}

	_, err := manifest.Load(manifest.LoadOptions{CWD: checkout})
	if err == nil {
		t.Fatal("Load accepted a source path escaping the checkout root")
	}
	if !strings.Contains(err.Error(), "outside source root") {
		t.Fatalf("error = %q, want source-root confinement rejection", err.Error())
	}
}

func TestManifestLoadDoesNotSearchUpward(t *testing.T) {
	parent := writeManifestFixture(t)
	child := filepath.Join(parent, "child")
	if err := os.MkdirAll(child, 0o755); err != nil {
		t.Fatal(err)
	}

	_, err := manifest.Load(manifest.LoadOptions{CWD: child})
	if err == nil {
		t.Fatal("Load found parent distribution/manifest.json from child cwd")
	}
	if !strings.Contains(err.Error(), filepath.Join("child", "distribution", "manifest.json")) {
		t.Fatalf("error = %q, want only child default path attempted", err.Error())
	}
}

func TestRepositoryManifestListsOnlyGovernedSkillsAndRoots(t *testing.T) {
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	repoRoot, err := filepath.Abs(filepath.Join(cwd, "..", "..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	loaded, err := manifest.Load(manifest.LoadOptions{CWD: t.TempDir(), ManifestPath: filepath.Join(repoRoot, "distribution", "manifest.json")})
	if err != nil {
		t.Fatalf("Load repository manifest: %v", err)
	}
	wantSkills := map[string]bool{"adr": false, "decision-calibrator": false, "model-optimizer": false, "remove-gentle-context": false, "systemic-issue-triage": false}
	for _, skill := range loaded.Manifest.Skills {
		if _, ok := wantSkills[skill.SkillID]; !ok {
			t.Fatalf("unexpected repository skill %q", skill.SkillID)
		}
		wantSkills[skill.SkillID] = true
	}
	for skill, seen := range wantSkills {
		if !seen {
			t.Fatalf("missing repository skill %q", skill)
		}
	}
	wantRoots := map[string]bool{"opencode|.agents/skills|direct_symlink": false, "pi|.agents/skills|direct_symlink": false, "claude|.claude/skills|direct_symlink": false}
	for _, root := range loaded.Manifest.RuntimeRoots {
		key := root.Runtime + "|" + root.Root + "|" + root.LinkStrategy
		if _, ok := wantRoots[key]; !ok {
			t.Fatalf("unexpected runtime root %q", key)
		}
		wantRoots[key] = true
	}
	for root, seen := range wantRoots {
		if !seen {
			t.Fatalf("missing runtime root %q", root)
		}
	}
}

func writeManifestFixture(t *testing.T) string {
	t.Helper()
	checkout := t.TempDir()
	for _, skill := range []string{"adr", "decision-calibrator", "model-optimizer", "remove-gentle-context", "systemic-issue-triage"} {
		dir := filepath.Join(checkout, "skills", skill)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte("# "+skill+"\n"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.MkdirAll(filepath.Join(checkout, "distribution"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkout, "distribution", "manifest.json"), []byte(validManifestJSON()), 0o644); err != nil {
		t.Fatal(err)
	}
	return checkout
}

func validManifestJSON() string {
	return `{"adapters":[{"runtime":"claude","schemas":["claude.skills/v1"]},{"runtime":"opencode","schemas":["opencode.skills/v1"]},{"runtime":"pi","schemas":["pi.get_commands/v0.84.3"]}],"repository":{"id":"waywarden-skills","source_root":"."},"runtime_roots":[{"link_strategy":"direct_symlink","root":".agents/skills","runtime":"opencode"},{"link_strategy":"direct_symlink","root":".agents/skills","runtime":"pi"},{"link_strategy":"direct_symlink","root":".claude/skills","runtime":"claude"}],"schema":"waywarden.manifest/v1","skills":[{"entry_files":["SKILL.md"],"skill_id":"adr","source_path":"skills/adr"},{"entry_files":["SKILL.md"],"skill_id":"decision-calibrator","source_path":"skills/decision-calibrator"},{"entry_files":["SKILL.md"],"skill_id":"model-optimizer","source_path":"skills/model-optimizer"},{"entry_files":["SKILL.md"],"skill_id":"remove-gentle-context","source_path":"skills/remove-gentle-context"},{"entry_files":["SKILL.md"],"skill_id":"systemic-issue-triage","source_path":"skills/systemic-issue-triage"}]}`
}

func escapedManifestJSON() string {
	return `{"adapters":[{"runtime":"pi","schemas":["pi.get_commands/v0.84.3"]}],"repository":{"id":"waywarden-skills","source_root":"."},"runtime_roots":[{"link_strategy":"direct_symlink","root":".agents/skills","runtime":"pi"}],"schema":"waywarden.manifest/v1","skills":[{"entry_files":["SKILL.md"],"skill_id":"escape","source_path":"../outside"}]}`
}
