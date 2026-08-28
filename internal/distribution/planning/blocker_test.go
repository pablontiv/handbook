package planning_test

import (
	"os"
	"path/filepath"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/planning"
)

func TestDeploymentPlanningBlocksSameSlotDifferentSourceIdentity(t *testing.T) {
	sourceRoot := writeSourceTree(t)
	writeExtraSkillSource(t, sourceRoot, "adr-shadow")
	manifest := testManifest()
	manifest.Skills = append(manifest.Skills, contracts.ManifestSkill{SkillID: "adr", SourcePath: filepath.ToSlash(filepath.Join("skills", "adr-shadow")), EntryFiles: []string{"SKILL.md"}})

	set, err := planning.BuildDeployments(manifest, sourceRoot, t.TempDir())
	if err != nil {
		t.Fatalf("BuildDeployments: %v", err)
	}
	if !hasBlockerCode(set.Blockers, planning.BlockerSlotSourceConflict) {
		t.Fatalf("blockers = %#v, want %s", set.Blockers, planning.BlockerSlotSourceConflict)
	}
}

func TestDeploymentPlanningBlocksSameSlotIncompatibleStrategy(t *testing.T) {
	sourceRoot := writeSourceTree(t)
	manifest := testManifest()
	manifest.RuntimeRoots = append(manifest.RuntimeRoots, contracts.RuntimeRoot{Runtime: "pi-audit", Root: filepath.ToSlash(filepath.Join(".agents", "skills")), LinkStrategy: "copy"})
	manifest.Adapters = append(manifest.Adapters, contracts.AdapterBinding{Runtime: "pi-audit", Schemas: []string{"pi.get_commands/v0.84.3"}})

	set, err := planning.BuildDeployments(manifest, sourceRoot, t.TempDir())
	if err != nil {
		t.Fatalf("BuildDeployments: %v", err)
	}
	if !hasBlockerCode(set.Blockers, planning.BlockerSlotStrategyConflict) {
		t.Fatalf("blockers = %#v, want %s", set.Blockers, planning.BlockerSlotStrategyConflict)
	}
}

func hasBlockerCode(blockers []contracts.Blocker, code string) bool {
	for _, blocker := range blockers {
		if blocker.Code == code {
			return true
		}
	}
	return false
}

func writeExtraSkillSource(t *testing.T, root, skill string) {
	t.Helper()
	dir := filepath.Join(root, "skills", skill)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte("# "+skill+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}
