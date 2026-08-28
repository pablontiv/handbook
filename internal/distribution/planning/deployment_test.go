package planning_test

import (
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/planning"
)

func TestDeploymentPlanningDedupesPhysicalSlotsAndKeepsRuntimeBindings(t *testing.T) {
	sourceRoot := writeSourceTree(t)
	home := t.TempDir()

	set, err := planning.BuildDeployments(testManifest(), sourceRoot, home)
	if err != nil {
		t.Fatalf("BuildDeployments: %v", err)
	}
	if len(set.Blockers) != 0 {
		t.Fatalf("blockers = %#v, want none", set.Blockers)
	}
	if got := len(set.Deployments); got != 10 {
		t.Fatalf("deployment count = %d, want 10", got)
	}
	if got := len(set.RuntimeBindings); got != 15 {
		t.Fatalf("runtime binding count = %d, want 15", got)
	}

	shared := deploymentBySkillAndSuffix(t, set.Deployments, "adr", filepath.Join(".agents", "skills", "adr"))
	if len(shared.RuntimeBindings) != 2 {
		t.Fatalf("shared adr binding count = %d, want 2", len(shared.RuntimeBindings))
	}
	if got := bindingRuntimes(shared.RuntimeBindings); got != "opencode,pi" {
		t.Fatalf("shared adr runtimes = %s, want opencode,pi", got)
	}

	claude := deploymentBySkillAndSuffix(t, set.Deployments, "adr", filepath.Join(".claude", "skills", "adr"))
	if len(claude.RuntimeBindings) != 1 || claude.RuntimeBindings[0].Runtime != "claude" {
		t.Fatalf("claude adr bindings = %#v, want exactly claude", claude.RuntimeBindings)
	}

	for _, deployment := range set.Deployments {
		if deployment.DeploymentID == "" {
			t.Fatalf("deployment %#v has empty deployment_id", deployment)
		}
		if hasForbiddenDesiredRoot(deployment.GovernedPath) {
			t.Fatalf("deployment governed path uses forbidden desired root: %s", deployment.GovernedPath)
		}
	}
}

func TestDeploymentPlanningIsDeterministic(t *testing.T) {
	sourceRoot := writeSourceTree(t)
	home := t.TempDir()

	first, err := planning.BuildDeployments(testManifest(), sourceRoot, home)
	if err != nil {
		t.Fatalf("first BuildDeployments: %v", err)
	}
	second, err := planning.BuildDeployments(testManifest(), sourceRoot, home)
	if err != nil {
		t.Fatalf("second BuildDeployments: %v", err)
	}
	if len(first.Deployments) != len(second.Deployments) {
		t.Fatalf("deployment count changed: %d vs %d", len(first.Deployments), len(second.Deployments))
	}
	for i := range first.Deployments {
		if first.Deployments[i].DeploymentID != second.Deployments[i].DeploymentID || first.Deployments[i].GovernedSlotIdentity != second.Deployments[i].GovernedSlotIdentity || first.Deployments[i].SourceIdentity != second.Deployments[i].SourceIdentity {
			t.Fatalf("deployment[%d] not deterministic:\nfirst=%#v\nsecond=%#v", i, first.Deployments[i], second.Deployments[i])
		}
	}
}

func deploymentBySkillAndSuffix(t *testing.T, deployments []contracts.Deployment, skillID, suffix string) contracts.Deployment {
	t.Helper()
	wantSuffix := filepath.ToSlash(suffix)
	for _, deployment := range deployments {
		if deployment.SkillID == skillID && strings.HasSuffix(filepath.ToSlash(deployment.GovernedPath), wantSuffix) {
			return deployment
		}
	}
	t.Fatalf("missing deployment skill=%s suffix=%s in %#v", skillID, suffix, deployments)
	return contracts.Deployment{}
}

func bindingRuntimes(bindings []contracts.RuntimeBinding) string {
	runtimes := make([]string, 0, len(bindings))
	for _, binding := range bindings {
		runtimes = append(runtimes, binding.Runtime)
	}
	sort.Strings(runtimes)
	out := ""
	for i, runtime := range runtimes {
		if i > 0 {
			out += ","
		}
		out += runtime
	}
	return out
}

func hasForbiddenDesiredRoot(path string) bool {
	parts := filepath.ToSlash(path)
	return containsPathSegment(parts, ".pi") || parts == ".config/opencode" || containsPathSegment(parts, ".config/opencode")
}

func containsPathSegment(path, segment string) bool {
	for _, part := range strings.Split(filepath.ToSlash(path), "/") {
		if part == segment {
			return true
		}
	}
	return false
}

func writeSourceTree(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	for _, skill := range skillIDs() {
		dir := filepath.Join(root, "skills", skill)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte("# "+skill+"\n"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return root
}

func testManifest() contracts.Manifest {
	skills := make([]contracts.ManifestSkill, 0, len(skillIDs()))
	for _, skill := range skillIDs() {
		skills = append(skills, contracts.ManifestSkill{SkillID: skill, SourcePath: filepath.ToSlash(filepath.Join("skills", skill)), EntryFiles: []string{"SKILL.md"}})
	}
	return contracts.Manifest{
		Schema:     contracts.SchemaManifest,
		Repository: contracts.RepositoryIdentity{ID: "waywarden-skills", SourceRoot: "."},
		Skills:     skills,
		RuntimeRoots: []contracts.RuntimeRoot{
			{Runtime: "opencode", Root: filepath.ToSlash(filepath.Join(".agents", "skills")), LinkStrategy: "direct_symlink"},
			{Runtime: "pi", Root: filepath.ToSlash(filepath.Join(".agents", "skills")), LinkStrategy: "direct_symlink"},
			{Runtime: "claude", Root: filepath.ToSlash(filepath.Join(".claude", "skills")), LinkStrategy: "direct_symlink"},
		},
		Adapters: []contracts.AdapterBinding{
			{Runtime: "claude", Schemas: []string{"claude.skills/v1"}},
			{Runtime: "opencode", Schemas: []string{"opencode.skills/v1"}},
			{Runtime: "pi", Schemas: []string{"pi.get_commands/v0.84.3"}},
		},
	}
}

func skillIDs() []string {
	return []string{"adr", "decision-calibrator", "model-optimizer", "remove-gentle-context", "systemic-issue-triage"}
}
