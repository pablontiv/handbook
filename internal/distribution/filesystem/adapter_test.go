package filesystem_test

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

func TestLocalAdapterLocksAreUnsupportedAndCreateNoArtifacts(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewLocalAdapter()

	for _, tc := range []struct {
		name string
		lock func(contracts.AbsolutePath) (filesystem.LockHandle, error)
	}{
		{
			name: "shared",
			lock: func(path contracts.AbsolutePath) (filesystem.LockHandle, error) {
				return adapter.LockShared(ctx, path, "snapshot")
			},
		},
		{
			name: "exclusive",
			lock: func(path contracts.AbsolutePath) (filesystem.LockHandle, error) {
				return adapter.LockExclusive(ctx, path, "mutation")
			},
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			lockPath := filepath.Join(t.TempDir(), "locks", tc.name+".lock")

			handle, err := tc.lock(contracts.AbsolutePath(lockPath))
			if !errors.Is(err, filesystem.ErrUnsupportedCapability) {
				t.Fatalf("lock error = %v, want ErrUnsupportedCapability", err)
			}
			if handle != nil {
				_ = handle.Close()
				t.Fatalf("lock handle = %#v, want nil", handle)
			}
			if _, err := os.Stat(lockPath); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("lock file stat error = %v, want not exist", err)
			}
			if _, err := os.Stat(filepath.Dir(lockPath)); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("lock directory stat error = %v, want not exist", err)
			}
		})
	}
}
