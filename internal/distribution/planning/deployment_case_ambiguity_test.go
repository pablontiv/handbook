package planning

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"waywarden/internal/distribution/contracts"
)

func TestBuildDeploymentsBlocksInjectedWindowsCaseAmbiguousGovernedSlots(t *testing.T) {
	sourceRoot := writeSingleSkillSource(t, "adr")
	home := t.TempDir()
	manifest := contracts.Manifest{
		Schema:     contracts.SchemaManifest,
		Repository: contracts.RepositoryIdentity{ID: "waywarden-skills", SourceRoot: "."},
		Skills: []contracts.ManifestSkill{
			{SkillID: "adr", SourcePath: filepath.ToSlash(filepath.Join("skills", "adr")), EntryFiles: []string{"SKILL.md"}},
		},
		RuntimeRoots: []contracts.RuntimeRoot{
			{Runtime: "upper", Root: filepath.ToSlash(filepath.Join(".Agents", "skills")), LinkStrategy: "direct_symlink"},
			{Runtime: "lower", Root: filepath.ToSlash(filepath.Join(".agents", "skills")), LinkStrategy: "direct_symlink"},
		},
	}
	identities := defaultDeploymentIdentityResolver
	identities.slotCollisionKey = asciiCaseInsensitiveCollisionKeyForTest

	first, err := buildDeployments(manifest, sourceRoot, home, identities)
	if err != nil {
		t.Fatalf("BuildDeployments first: %v", err)
	}
	second, err := buildDeployments(manifest, sourceRoot, home, identities)
	if err != nil {
		t.Fatalf("BuildDeployments second: %v", err)
	}
	if !reflect.DeepEqual(first, second) {
		t.Fatalf("case ambiguity result is not deterministic:\nfirst=%#v\nsecond=%#v", first, second)
	}
	if len(first.Deployments) != 0 {
		t.Fatalf("deployments = %#v, want none for ambiguous governed slots", first.Deployments)
	}
	if len(first.RuntimeBindings) != 0 {
		t.Fatalf("runtime bindings = %#v, want none for ambiguous governed slots", first.RuntimeBindings)
	}
	if len(first.Blockers) != 1 {
		t.Fatalf("blockers = %#v, want exactly one", first.Blockers)
	}
	blocker := first.Blockers[0]
	if blocker.Code != contracts.BlockerSlotCaseAmbiguity {
		t.Fatalf("blocker code = %q, want %q", blocker.Code, contracts.BlockerSlotCaseAmbiguity)
	}
	if !strings.Contains(blocker.Message, filepath.Join(".Agents", "skills", "adr")) || !strings.Contains(blocker.Message, filepath.Join(".agents", "skills", "adr")) {
		t.Fatalf("blocker message does not include both exact identities: %q", blocker.Message)
	}
}

func writeSingleSkillSource(t *testing.T, skillID string) string {
	t.Helper()
	root := t.TempDir()
	dir := filepath.Join(root, "skills", skillID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte("# "+skillID+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	return root
}

func asciiCaseInsensitiveCollisionKeyForTest(identity string) (string, bool) {
	out := []byte(identity)
	for i, c := range out {
		if c >= 'A' && c <= 'Z' {
			out[i] = c + ('a' - 'A')
		}
	}
	return string(out), true
}
