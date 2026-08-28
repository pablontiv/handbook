package inventory_test

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/inventory"
)

func TestInventoryServiceAcquiresOnlySharedLedgerLock(t *testing.T) {
	fixture := writeInventoryServiceFixture(t, []contracts.ManifestSkill{{SkillID: "b", SourcePath: "skills/b", EntryFiles: []string{"SKILL.md"}}})
	adapter := filesystem.NewMemoryAdapter()
	adapter.SetEnvironment(filesystem.PlatformEnv{Home: fixture.home, XDGStateHome: filepath.Join(fixture.home, ".local", "state"), LocalAppData: filepath.Join(fixture.home, "AppData", "Local")})
	adapter.SetTreeSnapshot(fixture.sourceIdentities["b"], filesystem.TreeSnapshot{Root: contracts.AbsolutePath(fixture.sourceIdentities["b"]), Entries: []filesystem.TreeEntry{{Path: "SKILL.md", SHA256: contracts.SHA256([]byte("# b\n"))}}})
	var artifact []byte

	_, err := inventory.NewService(adapter).Inventory(context.Background(), inventory.Options{
		CWD:           fixture.repo,
		ManifestPath:  fixture.manifestPath,
		StateRoot:     contracts.AbsolutePath(fixture.stateRoot),
		ArtifactLabel: "stdout",
		ArtifactSink: func(data []byte) error {
			artifact = append([]byte(nil), data...)
			return nil
		},
	})
	if err != nil {
		t.Fatalf("Inventory() error = %v", err)
	}
	if len(artifact) == 0 {
		t.Fatalf("artifact sink was not called")
	}
	if got := adapter.SharedLockKeys(); len(got) != 1 || !strings.Contains(got[0], "ledger") {
		t.Fatalf("shared locks = %v, want one selected ledger lock", got)
	}
	if got := adapter.ExclusiveLockKeys(); len(got) != 0 {
		t.Fatalf("exclusive locks = %v, want none", got)
	}
	if got := adapter.WriteLog(); len(got) != 0 {
		t.Fatalf("writes = %v, want inventory to be read-only", got)
	}
}

func TestInventoryServiceProducesSortedStableArrays(t *testing.T) {
	fixture := writeInventoryServiceFixture(t, []contracts.ManifestSkill{
		{SkillID: "zeta", SourcePath: "skills/zeta", EntryFiles: []string{"SKILL.md"}},
		{SkillID: "alpha", SourcePath: "skills/alpha", EntryFiles: []string{"SKILL.md"}},
	})
	adapter := filesystem.NewMemoryAdapter()
	adapter.SetEnvironment(filesystem.PlatformEnv{Home: fixture.home, XDGStateHome: filepath.Join(fixture.home, ".local", "state"), LocalAppData: filepath.Join(fixture.home, "AppData", "Local")})
	for id, identity := range fixture.sourceIdentities {
		adapter.SetTreeSnapshot(identity, filesystem.TreeSnapshot{Root: contracts.AbsolutePath(identity), Entries: []filesystem.TreeEntry{{Path: "SKILL.md", SHA256: contracts.SHA256([]byte("# " + id + "\n"))}}})
	}
	var artifact []byte

	_, err := inventory.NewService(adapter).Inventory(context.Background(), inventory.Options{
		CWD:          fixture.repo,
		ManifestPath: fixture.manifestPath,
		StateRoot:    contracts.AbsolutePath(fixture.stateRoot),
		ArtifactSink: func(data []byte) error { artifact = append([]byte(nil), data...); return nil },
	})
	if err != nil {
		t.Fatalf("Inventory() error = %v", err)
	}
	var got contracts.Inventory
	if err := contracts.StrictParseCanonical(artifact, &got); err != nil {
		t.Fatalf("artifact is not canonical inventory: %v\n%s", err, artifact)
	}
	if len(got.Sources) != 2 || got.Sources[0].SkillID != "alpha" || got.Sources[1].SkillID != "zeta" {
		t.Fatalf("sources not sorted by skill_id: %#v", got.Sources)
	}
	if len(got.Deployments) != 2 || got.Deployments[0].SkillID != "alpha" || got.Deployments[1].SkillID != "zeta" {
		t.Fatalf("deployments not stable/sorted: %#v", got.Deployments)
	}
}

func TestInventoryServiceDoesNotGenerateEventIdentifiers(t *testing.T) {
	fixture := writeInventoryServiceFixture(t, []contracts.ManifestSkill{{SkillID: "alpha", SourcePath: "skills/alpha", EntryFiles: []string{"SKILL.md"}}})
	adapter := filesystem.NewMemoryAdapter()
	adapter.SetEnvironment(filesystem.PlatformEnv{Home: fixture.home, XDGStateHome: filepath.Join(fixture.home, ".local", "state"), LocalAppData: filepath.Join(fixture.home, "AppData", "Local")})
	adapter.SetTreeSnapshot(fixture.sourceIdentities["alpha"], filesystem.TreeSnapshot{Root: contracts.AbsolutePath(fixture.sourceIdentities["alpha"]), Entries: []filesystem.TreeEntry{{Path: "SKILL.md", SHA256: contracts.SHA256([]byte("# alpha\n"))}}})
	var artifact []byte

	_, err := inventory.NewService(adapter).Inventory(context.Background(), inventory.Options{CWD: fixture.repo, ManifestPath: fixture.manifestPath, StateRoot: contracts.AbsolutePath(fixture.stateRoot), ArtifactSink: func(data []byte) error { artifact = append([]byte(nil), data...); return nil }})
	if err != nil {
		t.Fatalf("Inventory() error = %v", err)
	}
	for _, forbidden := range []string{"operation_id", "backup_set_id", "installation_id", "timestamp", "nonce"} {
		if bytes.Contains(artifact, []byte(forbidden)) {
			t.Fatalf("inventory artifact contains generated/event field %q: %s", forbidden, artifact)
		}
	}
}

func TestInventoryServiceRepeatedEvidenceIsByteIdentical(t *testing.T) {
	fixture := writeInventoryServiceFixture(t, []contracts.ManifestSkill{{SkillID: "alpha", SourcePath: "skills/alpha", EntryFiles: []string{"SKILL.md"}}})
	adapter := filesystem.NewMemoryAdapter()
	adapter.SetEnvironment(filesystem.PlatformEnv{Home: fixture.home, XDGStateHome: filepath.Join(fixture.home, ".local", "state"), LocalAppData: filepath.Join(fixture.home, "AppData", "Local")})
	adapter.SetTreeSnapshot(fixture.sourceIdentities["alpha"], filesystem.TreeSnapshot{Root: contracts.AbsolutePath(fixture.sourceIdentities["alpha"]), Entries: []filesystem.TreeEntry{{Path: "SKILL.md", SHA256: contracts.SHA256([]byte("# alpha\n"))}}})

	first := runInventoryForBytes(t, adapter, fixture)
	second := runInventoryForBytes(t, adapter, fixture)
	if !bytes.Equal(first, second) {
		t.Fatalf("inventory bytes changed:\nfirst:  %s\nsecond: %s", first, second)
	}
}

func runInventoryForBytes(t *testing.T, adapter *filesystem.MemoryAdapter, fixture inventoryServiceFixture) []byte {
	t.Helper()
	var artifact []byte
	_, err := inventory.NewService(adapter).Inventory(context.Background(), inventory.Options{CWD: fixture.repo, ManifestPath: fixture.manifestPath, StateRoot: contracts.AbsolutePath(fixture.stateRoot), ArtifactSink: func(data []byte) error { artifact = append([]byte(nil), data...); return nil }})
	if err != nil {
		t.Fatalf("Inventory() error = %v", err)
	}
	return artifact
}

type inventoryServiceFixture struct {
	repo             string
	home             string
	manifestPath     string
	stateRoot        string
	sourceIdentities map[string]string
}

func writeInventoryServiceFixture(t *testing.T, skills []contracts.ManifestSkill) inventoryServiceFixture {
	t.Helper()
	repo := t.TempDir()
	home := t.TempDir()
	sourceIdentities := map[string]string{}
	for _, skill := range skills {
		skillDir := filepath.Join(repo, filepath.FromSlash(skill.SourcePath))
		if err := os.MkdirAll(skillDir, 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(skillDir, "SKILL.md"), []byte("# "+skill.SkillID+"\n"), 0o644); err != nil {
			t.Fatal(err)
		}
		identity, err := filesystem.CanonicalIdentity(skillDir)
		if err != nil {
			t.Fatal(err)
		}
		sourceIdentities[skill.SkillID] = identity
	}
	manifest := contracts.Manifest{
		Schema:       contracts.SchemaManifest,
		Repository:   contracts.RepositoryIdentity{ID: "waywarden-skills", SourceRoot: "."},
		Skills:       skills,
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
	return inventoryServiceFixture{repo: repo, home: home, manifestPath: manifestPath, stateRoot: filepath.Join(t.TempDir(), "state"), sourceIdentities: sourceIdentities}
}
