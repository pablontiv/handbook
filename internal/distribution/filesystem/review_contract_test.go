package filesystem_test

import (
	"context"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

type requiredStateAdapterSeams interface {
	SafeRoot(context.Context, contracts.AbsolutePath) (filesystem.SafeRoot, error)
	PhysicalIdentity(context.Context, contracts.AbsolutePath) (filesystem.PhysicalIdentity, error)
	ListNoFollow(context.Context, contracts.AbsolutePath) ([]filesystem.DirEntry, error)
	SyncDirectory(context.Context, contracts.AbsolutePath) error
}

func TestMemoryAdapterExposesStateRootRecoverySeams(t *testing.T) {
	var _ requiredStateAdapterSeams = filesystem.NewMemoryAdapter()
}

func TestLocalStateRootRecoverySeamsFailClosedUntilNativeTask(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewLocalAdapter()
	root := contracts.AbsolutePath(t.TempDir())

	if _, err := adapter.SafeRoot(ctx, root); err == nil {
		t.Fatalf("local SafeRoot succeeded before native no-follow/private-root implementation")
	} else if err != filesystem.ErrUnsupportedCapability {
		t.Fatalf("local SafeRoot error = %v, want ErrUnsupportedCapability", err)
	}
	if _, err := adapter.PhysicalIdentity(ctx, root); err == nil {
		t.Fatalf("local PhysicalIdentity succeeded before native physical identity implementation")
	} else if err != filesystem.ErrUnsupportedCapability {
		t.Fatalf("local PhysicalIdentity error = %v, want ErrUnsupportedCapability", err)
	}
	if _, err := adapter.ListNoFollow(ctx, root); err == nil {
		t.Fatalf("local ListNoFollow succeeded before native no-follow enumeration implementation")
	} else if err != filesystem.ErrUnsupportedCapability {
		t.Fatalf("local ListNoFollow error = %v, want ErrUnsupportedCapability", err)
	}
	if err := adapter.SyncDirectory(ctx, root); err == nil {
		t.Fatalf("local SyncDirectory succeeded before native directory sync implementation")
	} else if err != filesystem.ErrUnsupportedCapability {
		t.Fatalf("local SyncDirectory error = %v, want ErrUnsupportedCapability", err)
	}
}
