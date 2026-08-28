package filesystem_test

import (
	"context"
	"errors"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

func TestMemoryAdapterRecordsLockKeysAndNeverTouchesRealHome(t *testing.T) {
	adapter := filesystem.NewMemoryAdapter()
	adapter.SetEnvironment(filesystem.PlatformEnv{Home: "/mem/home", XDGStateHome: "/mem/state", LocalAppData: "C:/mem/local"})

	shared, err := adapter.LockShared(context.Background(), contracts.AbsolutePath("/locks/ledger-a.lock"), "snapshot")
	if err != nil {
		t.Fatalf("LockShared() error = %v", err)
	}
	exclusive, err := adapter.LockExclusive(context.Background(), contracts.AbsolutePath("/locks/global.lock"), "mutation")
	if err != nil {
		t.Fatalf("LockExclusive() error = %v", err)
	}
	_ = shared.Close()
	_ = exclusive.Close()

	if got := adapter.SharedLockKeys(); len(got) != 1 || got[0] != "/locks/ledger-a.lock" {
		t.Fatalf("shared lock keys = %v", got)
	}
	if got := adapter.ExclusiveLockKeys(); len(got) != 1 || got[0] != "/locks/global.lock" {
		t.Fatalf("exclusive lock keys = %v", got)
	}
	env, err := adapter.Environment(context.Background())
	if err != nil {
		t.Fatalf("Environment() error = %v", err)
	}
	if env.Home != "/mem/home" || env.XDGStateHome != "/mem/state" {
		t.Fatalf("environment = %#v, want memory values", env)
	}
}

func TestMemoryAdapterPublishNoReplaceIsConfinedAndNoReplace(t *testing.T) {
	adapter := filesystem.NewMemoryAdapter()
	ctx := context.Background()
	forbidden := filesystem.ForbiddenRoots{RepositorySourceRoot: contracts.AbsolutePath("/repo"), RuntimeRoots: []contracts.AbsolutePath{contracts.AbsolutePath("/runtime")}, StateRoot: contracts.AbsolutePath("/state"), LockRoot: contracts.AbsolutePath("/locks")}

	if err := adapter.PublishNoReplace(ctx, contracts.AbsolutePath("/out/inventory.json"), []byte("{}"), forbidden); err != nil {
		t.Fatalf("PublishNoReplace() fresh destination error = %v", err)
	}
	data, err := adapter.ReadFile(ctx, contracts.AbsolutePath("/out/inventory.json"))
	if err != nil || string(data) != "{}" {
		t.Fatalf("published data = %q, err=%v", data, err)
	}
	if err := adapter.PublishNoReplace(ctx, contracts.AbsolutePath("/out/inventory.json"), []byte("replace"), forbidden); !errors.Is(err, filesystem.ErrDestinationExists) {
		t.Fatalf("existing destination error = %v, want ErrDestinationExists", err)
	}
	data, _ = adapter.ReadFile(ctx, contracts.AbsolutePath("/out/inventory.json"))
	if string(data) != "{}" {
		t.Fatalf("destination was replaced: %q", data)
	}
	if err := adapter.PublishNoReplace(ctx, contracts.AbsolutePath("/repo/inventory.json"), []byte("{}"), forbidden); !errors.Is(err, filesystem.ErrForbiddenDestination) {
		t.Fatalf("forbidden root error = %v, want ErrForbiddenDestination", err)
	}
}
