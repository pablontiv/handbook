package state

import (
	"context"
	"fmt"
	"path/filepath"
	"runtime"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

type Roots struct {
	StateRoot contracts.AbsolutePath
	LockRoot  contracts.AbsolutePath
}

func (r Roots) LedgerPath() contracts.AbsolutePath {
	return contracts.AbsolutePath(filepath.Join(string(r.StateRoot), "ownership", "installations.ndjson"))
}

func ResolveRoots(env filesystem.PlatformEnv, override contracts.AbsolutePath) (Roots, error) {
	return resolveRoots(runtime.GOOS, env, override, ownerPrivateLockRoot)
}

func (s *store) ResolveRoots(ctx context.Context, override contracts.AbsolutePath) (Roots, error) {
	env, err := s.fs.Environment(ctx)
	if err != nil {
		return Roots{}, err
	}
	return resolveRoots(s.fs.Platform(), env, override, s.fs.OwnerPrivateLockRoot)
}

func resolveRoots(platform string, env filesystem.PlatformEnv, override contracts.AbsolutePath, lockRoot func(filesystem.PlatformEnv) (contracts.AbsolutePath, error)) (Roots, error) {
	selected, err := defaultStateRoot(platform, env)
	if err != nil {
		return Roots{}, err
	}
	if override != "" {
		if !filepath.IsAbs(string(override)) {
			return Roots{}, fmt.Errorf("state root override must be absolute")
		}
		selected = contracts.AbsolutePath(filepath.Clean(string(override)))
	}
	lock, err := lockRoot(env)
	if err != nil {
		return Roots{}, err
	}
	if !filepath.IsAbs(string(selected)) {
		return Roots{}, fmt.Errorf("state root must be absolute")
	}
	if !filepath.IsAbs(string(lock)) {
		return Roots{}, fmt.Errorf("lock root must be absolute")
	}
	return Roots{StateRoot: contracts.AbsolutePath(filepath.Clean(string(selected))), LockRoot: contracts.AbsolutePath(filepath.Clean(string(lock)))}, nil
}

func defaultStateRoot(platform string, env filesystem.PlatformEnv) (contracts.AbsolutePath, error) {
	switch platform {
	case "windows":
		if env.LocalAppData == "" {
			return "", fmt.Errorf("LOCALAPPDATA is required for state root")
		}
		return contracts.AbsolutePath(filepath.Join(env.LocalAppData, "waywarden", "state")), nil
	case "darwin":
		if env.Home == "" {
			return "", fmt.Errorf("HOME is required for state root")
		}
		return contracts.AbsolutePath(filepath.Join(env.Home, "Library", "Application Support", "waywarden", "state")), nil
	default:
		base := env.XDGStateHome
		if base == "" {
			if env.Home == "" {
				return "", fmt.Errorf("HOME or XDG_STATE_HOME is required for state root")
			}
			base = filepath.Join(env.Home, ".local", "state")
		}
		return contracts.AbsolutePath(filepath.Join(base, "waywarden")), nil
	}
}

func ownerPrivateLockRoot(env filesystem.PlatformEnv) (contracts.AbsolutePath, error) {
	return filesystem.NewLocalAdapter().OwnerPrivateLockRoot(env)
}
