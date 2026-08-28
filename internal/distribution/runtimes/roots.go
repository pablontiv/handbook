package runtimes

import (
	"fmt"
	"path/filepath"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

func DefaultStateRoot(platform string, env filesystem.PlatformEnv) (contracts.AbsolutePath, error) {
	switch platform {
	case "windows":
		if env.LocalAppData == "" {
			return "", fmt.Errorf("LOCALAPPDATA is required for default state root")
		}
		return contracts.AbsolutePath(filepath.Join(env.LocalAppData, "waywarden", "state")), nil
	case "darwin":
		if env.Home == "" {
			return "", fmt.Errorf("HOME is required for default state root")
		}
		return contracts.AbsolutePath(filepath.Join(env.Home, "Library", "Application Support", "waywarden", "state")), nil
	case "linux":
		fallthrough
	default:
		base := env.XDGStateHome
		if base == "" {
			if env.Home == "" {
				return "", fmt.Errorf("HOME or XDG_STATE_HOME is required for default state root")
			}
			base = filepath.Join(env.Home, ".local", "state")
		}
		return contracts.AbsolutePath(filepath.Join(base, "waywarden")), nil
	}
}
