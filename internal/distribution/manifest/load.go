package manifest

import (
	"fmt"
	"os"
	"path/filepath"
	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

type LoadOptions struct {
	CWD          string
	ManifestPath string
}

type LoadedManifest struct {
	Manifest       contracts.Manifest
	ManifestPath   string
	SourceRoot     string
	CanonicalBytes []byte
	Digest         contracts.SHA256Hex
}

func Load(options LoadOptions) (LoadedManifest, error) {
	manifestPath, err := selectManifestPath(options)
	if err != nil {
		return LoadedManifest{}, err
	}
	sourceRoot, err := sourceRootForManifest(manifestPath)
	if err != nil {
		return LoadedManifest{}, err
	}
	data, err := os.ReadFile(manifestPath)
	if err != nil {
		return LoadedManifest{}, err
	}
	if err := contracts.ValidateSchema(contracts.SchemaManifest, data); err != nil {
		return LoadedManifest{}, err
	}
	var manifest contracts.Manifest
	if err := contracts.StrictParseCanonical(data, &manifest); err != nil {
		return LoadedManifest{}, err
	}
	if err := validateManifest(manifest, sourceRoot); err != nil {
		return LoadedManifest{}, err
	}
	return LoadedManifest{Manifest: manifest, ManifestPath: manifestPath, SourceRoot: sourceRoot, CanonicalBytes: append([]byte(nil), data...), Digest: contracts.SHA256(data)}, nil
}

func selectManifestPath(options LoadOptions) (string, error) {
	if options.ManifestPath != "" {
		if !filepath.IsAbs(options.ManifestPath) {
			return "", fmt.Errorf("manifest override must be an absolute path")
		}
		return filepath.Clean(options.ManifestPath), nil
	}
	cwd := options.CWD
	if cwd == "" {
		var err error
		cwd, err = os.Getwd()
		if err != nil {
			return "", err
		}
	}
	if !filepath.IsAbs(cwd) {
		abs, err := filepath.Abs(cwd)
		if err != nil {
			return "", err
		}
		cwd = abs
	}
	return filepath.Join(filepath.Clean(cwd), "distribution", "manifest.json"), nil
}

func sourceRootForManifest(manifestPath string) (string, error) {
	if filepath.Base(manifestPath) != "manifest.json" || filepath.Base(filepath.Dir(manifestPath)) != "distribution" {
		return "", fmt.Errorf("manifest path must be named distribution%cmanifest.json", filepath.Separator)
	}
	root := filepath.Dir(filepath.Dir(manifestPath))
	identity, err := filesystem.CanonicalIdentity(root)
	if err != nil {
		return "", err
	}
	return identity, nil
}

func validateManifest(manifest contracts.Manifest, sourceRoot string) error {
	if manifest.Schema != contracts.SchemaManifest {
		return fmt.Errorf("manifest schema = %q, want %q", manifest.Schema, contracts.SchemaManifest)
	}
	if manifest.Repository.ID == "" {
		return fmt.Errorf("manifest repository id is required")
	}
	if manifest.Repository.SourceRoot != "." {
		return fmt.Errorf("manifest repository source_root must be checkout-bound '.'")
	}
	if len(manifest.Skills) == 0 {
		return fmt.Errorf("manifest must list at least one skill")
	}
	seenSkills := map[string]bool{}
	for _, skill := range manifest.Skills {
		if skill.SkillID == "" {
			return fmt.Errorf("manifest skill_id is required")
		}
		if seenSkills[skill.SkillID] {
			return fmt.Errorf("duplicate manifest skill_id %q", skill.SkillID)
		}
		seenSkills[skill.SkillID] = true
		if err := validateRelativePath("source_path", skill.SourcePath); err != nil {
			return err
		}
		sourcePath := filepath.Join(sourceRoot, filepath.FromSlash(skill.SourcePath))
		sourceIdentity, err := filesystem.ContainedCanonicalIdentity(sourceRoot, sourcePath)
		if err != nil {
			return err
		}
		if !containsString(skill.EntryFiles, "SKILL.md") {
			return fmt.Errorf("skill %s must declare SKILL.md entry file", skill.SkillID)
		}
		for _, entry := range skill.EntryFiles {
			if err := validateRelativePath("entry_files", entry); err != nil {
				return err
			}
			entryPath := filepath.Join(sourceIdentity, filepath.FromSlash(entry))
			if _, err := filesystem.ContainedCanonicalIdentity(sourceIdentity, entryPath); err != nil {
				return err
			}
		}
	}
	for _, root := range manifest.RuntimeRoots {
		if root.Runtime == "" || root.Root == "" || root.LinkStrategy == "" {
			return fmt.Errorf("runtime_roots entries require runtime, root, and link_strategy")
		}
		if root.LinkStrategy != "direct_symlink" {
			return fmt.Errorf("runtime %s uses unsupported link_strategy %q", root.Runtime, root.LinkStrategy)
		}
		if err := validateRelativePath("runtime root", root.Root); err != nil {
			return err
		}
	}
	for _, adapter := range manifest.Adapters {
		if adapter.Runtime == "" || len(adapter.Schemas) == 0 {
			return fmt.Errorf("adapter entries require runtime and schemas")
		}
	}
	return nil
}

func validateRelativePath(label, path string) error {
	if path == "" {
		return fmt.Errorf("%s is required", label)
	}
	if filepath.IsAbs(path) || filepath.IsAbs(filepath.FromSlash(path)) {
		return fmt.Errorf("%s must be relative: %s", label, path)
	}
	clean := filepath.Clean(filepath.FromSlash(path))
	if clean == "." || clean == ".." || clean == string(filepath.Separator) || clean == "" {
		return fmt.Errorf("%s must name a confined relative path: %s", label, path)
	}
	if clean == ".." || len(clean) >= 3 && clean[:3] == ".."+string(filepath.Separator) {
		return fmt.Errorf("%s is outside source root: %s", label, path)
	}
	return nil
}

func containsString(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
