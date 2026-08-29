package filesystem_test

import (
	"context"
	"errors"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

func TestRound5MemoryFailpointTargetsOccurrenceWithinPhase(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	dir := contracts.AbsolutePath("/state/runs/" + string(contracts.SHA256([]byte("occurrence"))))
	boom := errors.New("second sync")
	adapter.SetWriteFailureOccurrence("sync-dir", dir, filesystem.FailBeforeWrite, 2, boom)

	if err := adapter.SyncDirectory(ctx, dir); err != nil {
		t.Fatalf("first sync consumed second-occurrence failpoint: %v", err)
	}
	if err := adapter.SyncDirectory(ctx, dir); !errors.Is(err, boom) {
		t.Fatalf("second sync error = %v, want injected failure", err)
	}
	if err := adapter.SyncDirectory(ctx, dir); err != nil {
		t.Fatalf("one-shot occurrence failpoint was not consumed: %v", err)
	}
}
