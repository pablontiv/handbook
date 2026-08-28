package filesystem_test

import (
	"context"
	"errors"
	"io/fs"
	"path/filepath"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

func TestRound4MemoryCrashCloneExposesOnlyDurableBytesAndDropsProcessMetadata(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	runDir := contracts.AbsolutePath(filepath.Join(t.TempDir(), "state", "runs", string(contracts.SHA256([]byte("round4-crash")))))
	journalPath := contracts.AbsolutePath(filepath.Join(string(runDir), "journal.ndjson"))
	draftPath := contracts.AbsolutePath(filepath.Join(string(runDir), "receipt.json.draft"))
	finalPath := contracts.AbsolutePath(filepath.Join(string(runDir), "receipt.json"))

	if err := adapter.EnsureDirSync(ctx, runDir); err != nil {
		t.Fatal(err)
	}
	if err := adapter.AppendFileSync(ctx, journalPath, []byte("started\n")); err != nil {
		t.Fatal(err)
	}
	if _, err := adapter.CrashClone().ReadFile(ctx, journalPath); !errors.Is(err, fs.ErrNotExist) {
		t.Fatalf("new journal entry survived crash before parent directory sync")
	}
	if err := adapter.SyncDirectory(ctx, runDir); err != nil {
		t.Fatal(err)
	}
	crashed := adapter.CrashClone()
	if got, err := crashed.ReadFile(ctx, journalPath); err != nil || string(got) != "started\n" {
		t.Fatalf("durable journal after parent sync = %q, %v", got, err)
	}

	if err := adapter.AppendFileSync(ctx, journalPath, []byte("step\n")); err != nil {
		t.Fatal(err)
	}
	if got, err := adapter.CrashClone().ReadFile(ctx, journalPath); err != nil || string(got) != "started\nstep\n" {
		t.Fatalf("append to already durable file did not survive file sync: %q, %v", got, err)
	}

	if err := adapter.WriteFileNoReplaceSync(ctx, draftPath, []byte("draft")); err != nil {
		t.Fatal(err)
	}
	if _, err := adapter.CrashClone().ReadFile(ctx, draftPath); err == nil {
		t.Fatalf("new draft file survived crash before run directory sync")
	}
	if err := adapter.SyncDirectory(ctx, runDir); err != nil {
		t.Fatal(err)
	}
	if got, err := adapter.CrashClone().ReadFile(ctx, draftPath); err != nil || string(got) != "draft" {
		t.Fatalf("draft after directory sync = %q, %v", got, err)
	}

	boom := errors.New("reported after sync")
	adapter.SetWriteFailure("sync-dir", runDir, filesystem.FailAfterWrite, boom)
	if err := adapter.WriteFileNoReplaceSync(ctx, finalPath, []byte("final")); err != nil {
		t.Fatal(err)
	}
	if err := adapter.SyncDirectory(ctx, runDir); !errors.Is(err, boom) {
		t.Fatalf("SyncDirectory error = %v, want injected", err)
	}
	crashed = adapter.CrashClone()
	if failures := crashed.AmbiguousDurabilityFailures(); len(failures) != 0 {
		t.Fatalf("crash clone retained process-local ambiguity metadata: %v", failures)
	}
	if got, err := crashed.ReadFile(ctx, finalPath); err != nil || string(got) != "final" {
		t.Fatalf("file whose parent sync completed before reported error must survive restart: %q, %v", got, err)
	}
}
