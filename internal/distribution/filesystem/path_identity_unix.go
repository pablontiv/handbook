//go:build !windows

package filesystem

import "path/filepath"

func platformPathIdentity(path string) (string, error) {
	return filepath.Clean(path), nil
}

func platformGovernedSlotCollisionKey(identity string) (string, bool) {
	return identity, true
}
