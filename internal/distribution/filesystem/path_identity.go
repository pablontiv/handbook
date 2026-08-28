package filesystem

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type PathIdentity string

func CanonicalIdentity(path string) (string, error) {
	if !filepath.IsAbs(path) {
		return "", fmt.Errorf("path identity requires an absolute path: %s", path)
	}
	clean := filepath.Clean(path)
	resolved, err := filepath.EvalSymlinks(clean)
	if err != nil {
		return "", err
	}
	info, err := os.Lstat(resolved)
	if err != nil {
		return "", err
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return "", fmt.Errorf("path identity remains ambiguous after symlink resolution: %s", path)
	}
	return platformPathIdentity(resolved)
}

func LexicalIdentity(path string) (string, error) {
	if !filepath.IsAbs(path) {
		return "", fmt.Errorf("path identity requires an absolute path: %s", path)
	}
	return platformPathIdentity(filepath.Clean(path))
}

func ContainedCanonicalIdentity(root, candidate string) (string, error) {
	rootIdentity, err := CanonicalIdentity(root)
	if err != nil {
		return "", fmt.Errorf("source root identity: %w", err)
	}
	candidateLexical, err := LexicalIdentity(candidate)
	if err != nil {
		return "", err
	}
	if !sameOrDescendant(rootIdentity, candidateLexical) {
		return "", fmt.Errorf("path %s is outside source root %s", candidateLexical, rootIdentity)
	}
	candidateIdentity, err := CanonicalIdentity(candidate)
	if err != nil {
		return "", err
	}
	if !sameOrDescendant(rootIdentity, candidateIdentity) {
		return "", fmt.Errorf("path %s is outside source root %s", candidateIdentity, rootIdentity)
	}
	return candidateIdentity, nil
}

func sameOrDescendant(root, candidate string) bool {
	root = filepath.Clean(root)
	candidate = filepath.Clean(candidate)
	if root == candidate {
		return true
	}
	rel, err := filepath.Rel(root, candidate)
	if err != nil {
		return false
	}
	return rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) && rel != "."
}
