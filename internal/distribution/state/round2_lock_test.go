package state_test

import (
	"context"
	"errors"
	"path/filepath"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/state"
)

func TestPartialMutationLockAcquisitionReleasesHeldLocksAndJoinsReleaseErrors(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	slot := contracts.GovernedSlotIdentity("slot-round2")
	slotPath := contracts.AbsolutePath(filepath.Join(string(roots.LockRoot), "slots", string(contracts.SHA256([]byte(slot)))+".lock"))
	conflicting, err := adapter.LockExclusive(ctx, slotPath, "conflict")
	if err != nil {
		t.Fatal(err)
	}
	defer conflicting.Close()
	globalPath := contracts.AbsolutePath(filepath.Join(string(roots.LockRoot), "global-mutation.lock"))
	releaseErr := errors.New("global release failed")
	adapter.SetLockCloseError(globalPath, releaseErr)

	locks, err := store.AcquireMutationLocks(ctx, roots, []contracts.GovernedSlotIdentity{slot})
	if locks != nil {
		t.Fatalf("AcquireMutationLocks returned locks after partial failure")
	}
	if !errors.Is(err, filesystem.ErrLockConflict) || !errors.Is(err, releaseErr) {
		t.Fatalf("AcquireMutationLocks error = %v, want primary lock conflict joined with release failure", err)
	}
	active := adapter.ActiveLocks()
	if len(active) != 1 || active[string(slotPath)].Exclusive != 1 {
		t.Fatalf("partial cleanup leaked locks beyond caller-held conflict: %#v", active)
	}
}

func TestOperationIDGenerationWhileLocksActiveIsCallerOrderingOnly(t *testing.T) {
	ctx := context.Background()
	adapter := filesystem.NewMemoryAdapter()
	store := state.NewStore(adapter)
	roots := tempRoots(t)
	locks, err := store.AcquireMutationLocks(ctx, roots, []contracts.GovernedSlotIdentity{"slot-a"})
	if err != nil {
		t.Fatal(err)
	}
	if len(adapter.ActiveLocks()) == 0 {
		t.Fatalf("expected active locks before ID generation")
	}
	reader := &assertLocksHeldReader{t: t, adapter: adapter}
	if _, err := store.GenerateOperationID(reader); err != nil {
		t.Fatalf("GenerateOperationID() error = %v", err)
	}
	if err := locks.Release(); err != nil {
		t.Fatalf("Release() error = %v", err)
	}
}
