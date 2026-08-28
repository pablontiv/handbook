package runtimes_test

import (
	"path/filepath"
	"testing"

	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/runtimes"
)

func TestDefaultStateRootUsesRedirectedLinuxStateEnvironment(t *testing.T) {
	env := filesystem.PlatformEnv{Home: "/home/tester", XDGStateHome: "/xdg/state"}
	root, err := runtimes.DefaultStateRoot("linux", env)
	if err != nil {
		t.Fatalf("DefaultStateRoot() error = %v", err)
	}
	if string(root) != filepath.Clean("/xdg/state/waywarden") {
		t.Fatalf("state root = %s, want redirected XDG_STATE_HOME", root)
	}
}

func TestDefaultStateRootFallsBackToRedirectedHome(t *testing.T) {
	env := filesystem.PlatformEnv{Home: "/home/tester"}
	root, err := runtimes.DefaultStateRoot("linux", env)
	if err != nil {
		t.Fatalf("DefaultStateRoot() error = %v", err)
	}
	if string(root) != filepath.Clean("/home/tester/.local/state/waywarden") {
		t.Fatalf("state root = %s, want HOME fallback", root)
	}
}

func TestDefaultStateRootRejectsMissingEnvironment(t *testing.T) {
	if _, err := runtimes.DefaultStateRoot("linux", filesystem.PlatformEnv{}); err == nil {
		t.Fatalf("DefaultStateRoot() accepted missing HOME and XDG_STATE_HOME")
	}
}
