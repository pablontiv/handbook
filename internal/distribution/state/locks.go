package state

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"sort"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

type LockSet interface {
	Release() error
}

type heldLockSet struct {
	handles []filesystem.LockHandle
}

func (s *store) AcquireMutationLocks(ctx context.Context, roots Roots, slots []contracts.GovernedSlotIdentity) (LockSet, error) {
	if err := validateRoots(ctx, s.fs, roots); err != nil {
		return nil, err
	}
	var handles []filesystem.LockHandle
	acquire := func(path contracts.AbsolutePath, reason string) error {
		handle, err := s.fs.LockExclusive(ctx, path, reason)
		if err != nil {
			return err
		}
		handles = append(handles, handle)
		return nil
	}
	cleanup := func(primary error) (LockSet, error) {
		return nil, errors.Join(primary, releaseHandlesReverse(handles))
	}
	if err := acquire(globalMutationLockPath(roots), "waywarden global mutation"); err != nil {
		return cleanup(err)
	}
	for _, path := range governedSlotLockPaths(roots, slots) {
		if err := acquire(path, "waywarden governed slot mutation"); err != nil {
			return cleanup(err)
		}
	}
	ledgerPath, err := ledgerLockPath(ctx, s.fs, roots)
	if err != nil {
		return cleanup(err)
	}
	if err := acquire(ledgerPath, "waywarden selected ledger mutation"); err != nil {
		return cleanup(err)
	}
	return &heldLockSet{handles: handles}, nil
}

func (s *store) AcquireVerificationLocks(ctx context.Context, roots Roots) (LockSet, error) {
	if err := validateRoots(ctx, s.fs, roots); err != nil {
		return nil, err
	}
	var handles []filesystem.LockHandle
	cleanup := func(primary error) (LockSet, error) {
		return nil, errors.Join(primary, releaseHandlesReverse(handles))
	}
	global, err := s.fs.LockExclusive(ctx, globalMutationLockPath(roots), "waywarden verification state write")
	if err != nil {
		return cleanup(err)
	}
	handles = append(handles, global)
	ledgerPath, err := ledgerLockPath(ctx, s.fs, roots)
	if err != nil {
		return cleanup(err)
	}
	ledger, err := s.fs.LockExclusive(ctx, ledgerPath, "waywarden selected ledger verification write")
	if err != nil {
		return cleanup(err)
	}
	handles = append(handles, ledger)
	return &heldLockSet{handles: handles}, nil
}

func (s *store) AcquireInventoryLedgerSnapshot(ctx context.Context, roots Roots) (filesystem.LockHandle, error) {
	if err := validateRoots(ctx, s.fs, roots); err != nil {
		return nil, err
	}
	ledgerPath, err := ledgerLockPath(ctx, s.fs, roots)
	if err != nil {
		return nil, err
	}
	return s.fs.LockShared(ctx, ledgerPath, "waywarden inventory selected ledger snapshot")
}

func (l *heldLockSet) Release() error {
	return releaseHandlesReverse(l.handles)
}

func releaseHandlesReverse(handles []filesystem.LockHandle) error {
	var out error
	for i := len(handles) - 1; i >= 0; i-- {
		if handles[i] == nil {
			continue
		}
		if err := handles[i].Close(); err != nil {
			out = errors.Join(out, err)
		}
	}
	return out
}

func globalMutationLockPath(roots Roots) contracts.AbsolutePath {
	return contracts.AbsolutePath(filepath.Join(string(roots.LockRoot), "global-mutation.lock"))
}

func governedSlotLockPaths(roots Roots, slots []contracts.GovernedSlotIdentity) []contracts.AbsolutePath {
	seen := map[string]bool{}
	keys := make([]string, 0, len(slots))
	for _, slot := range slots {
		key := string(contracts.SHA256([]byte(slot)))
		if seen[key] {
			continue
		}
		seen[key] = true
		keys = append(keys, key)
	}
	sort.Strings(keys)
	paths := make([]contracts.AbsolutePath, 0, len(keys))
	for _, key := range keys {
		paths = append(paths, contracts.AbsolutePath(filepath.Join(string(roots.LockRoot), "slots", key+".lock")))
	}
	return paths
}

func ledgerLockPath(ctx context.Context, adapter filesystem.Adapter, roots Roots) (contracts.AbsolutePath, error) {
	identity, err := adapter.PhysicalIdentity(ctx, roots.StateRoot)
	if err != nil {
		return "", err
	}
	key := contracts.SHA256([]byte(identity))
	return contracts.AbsolutePath(filepath.Join(string(roots.LockRoot), "ledgers", string(key)+".lock")), nil
}

func validateRootsBasic(roots Roots) error {
	if roots.StateRoot == "" || roots.LockRoot == "" {
		return fmt.Errorf("state and lock roots are required")
	}
	if !filepath.IsAbs(string(roots.StateRoot)) || !filepath.IsAbs(string(roots.LockRoot)) {
		return fmt.Errorf("state and lock roots must be absolute")
	}
	return nil
}

func validateRoots(ctx context.Context, adapter filesystem.Adapter, roots Roots) error {
	if err := validateRootsBasic(roots); err != nil {
		return err
	}
	stateRoot, err := adapter.SafeRoot(ctx, roots.StateRoot)
	if err != nil {
		return err
	}
	lockRoot, err := adapter.SafeRoot(ctx, roots.LockRoot)
	if err != nil {
		return err
	}
	if stateRoot.Identity == "" || lockRoot.Identity == "" {
		return fmt.Errorf("state and lock roots require physical identity")
	}
	if stateRoot.Identity == lockRoot.Identity {
		return fmt.Errorf("state and lock roots must be physically disjoint")
	}
	return nil
}
