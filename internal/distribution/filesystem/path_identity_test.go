package filesystem_test

import (
	"os"
	"path/filepath"
	"testing"

	"waywarden/internal/distribution/filesystem"
)

func TestCanonicalIdentityIsStableForCleanEquivalentPaths(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "skills", "adr")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}

	first, err := filesystem.CanonicalIdentity(dir)
	if err != nil {
		t.Fatalf("CanonicalIdentity first: %v", err)
	}
	second, err := filesystem.CanonicalIdentity(filepath.Join(root, "skills", ".", "adr"))
	if err != nil {
		t.Fatalf("CanonicalIdentity second: %v", err)
	}
	if first != second {
		t.Fatalf("identity mismatch: %q != %q", first, second)
	}
}

func TestCanonicalIdentityRejectsRelativePath(t *testing.T) {
	_, err := filesystem.CanonicalIdentity(filepath.Join("skills", "adr"))
	if err == nil {
		t.Fatal("CanonicalIdentity accepted relative path")
	}
}

func TestContainedCanonicalIdentityRejectsEscapes(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	if _, err := filesystem.ContainedCanonicalIdentity(root, filepath.Join(outside, "skill")); err == nil {
		t.Fatal("ContainedCanonicalIdentity accepted path outside root")
	}
}
