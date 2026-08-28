package filesystem_test

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

func TestMemoryAdapterExposesActiveLocksAndInjectsIdempotentReleaseFailures(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	lockPath := contracts.AbsolutePath(filepath.Join(t.TempDir(), "locks", "global.lock"))
	closeErr := errors.New("release failed")
	adapter.SetLockCloseError(lockPath, closeErr)

	handle, err := adapter.LockExclusive(ctx, lockPath, "test")
	if err != nil {
		t.Fatalf("LockExclusive() error = %v", err)
	}
	if active := adapter.ActiveLocks(); active[string(lockPath)].Exclusive != 1 {
		t.Fatalf("active locks before close = %#v", active)
	}
	if err := handle.Close(); !errors.Is(err, closeErr) {
		t.Fatalf("Close() error = %v, want injected close error", err)
	}
	if active := adapter.ActiveLocks(); len(active) != 0 {
		t.Fatalf("lock was not safely released after close error: %#v", active)
	}
	if err := handle.Close(); err != nil {
		t.Fatalf("second Close() should be idempotent, got %v", err)
	}
}

func TestMemoryAdapterCanReturnWrittenButErrorOutcomeAtDurabilityBoundaries(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	path := contracts.AbsolutePath(filepath.Join(t.TempDir(), "state", "runs", strings.Repeat("a", 64), "journal.ndjson"))
	ambiguous := errors.New("written but error")
	adapter.SetWriteFailure("append", path, filesystem.FailAfterWrite, ambiguous)

	if err := adapter.AppendFileSync(ctx, path, []byte("evidence\n")); !errors.Is(err, ambiguous) {
		t.Fatalf("AppendFileSync() error = %v, want ambiguous written-but-error", err)
	}
	data, err := adapter.ReadFile(ctx, path)
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	if string(data) != "evidence\n" {
		t.Fatalf("ambiguous after-write failure did not preserve bytes: %q", data)
	}

	beforePath := contracts.AbsolutePath(filepath.Join(t.TempDir(), "state", "runs", strings.Repeat("b", 64), "receipt.json.draft"))
	adapter.SetWriteFailure("write-no-replace", beforePath, filesystem.FailBeforeWrite, ambiguous)
	if err := adapter.WriteFileNoReplaceSync(ctx, beforePath, []byte("draft")); !errors.Is(err, ambiguous) {
		t.Fatalf("WriteFileNoReplaceSync() error = %v, want injected before-write error", err)
	}
	if _, err := adapter.ReadFile(ctx, beforePath); err == nil {
		t.Fatalf("before-write failure created a file")
	}

	syncPath := contracts.AbsolutePath(filepath.Join(t.TempDir(), "state", "runs", strings.Repeat("c", 64)))
	adapter.SetWriteFailure("sync-dir", syncPath, filesystem.FailBeforeWrite, ambiguous)
	if err := adapter.SyncDirectory(ctx, syncPath); !errors.Is(err, ambiguous) {
		t.Fatalf("SyncDirectory() error = %v, want injected sync error", err)
	}
}
