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

func AcquireMutationLocks(ctx context.Context, fs filesystem.Adapter, roots Roots, slots []contracts.GovernedSlotIdentity) (LockSet, error) {
	var handles []filesystem.LockHandle
	acquire := func(path contracts.AbsolutePath, reason string) error {
		handle, err := fs.LockExclusive(ctx, path, reason)
		if err != nil {
			return err
		}
		handles = append(handles, handle)
		return nil
	}
	cleanup := func(err error) (LockSet, error) {
		_ = releaseHandlesReverse(handles)
		return nil, err
	}
	if err := acquire(globalMutationLockPath(roots), "waywarden global mutation"); err != nil {
		return cleanup(err)
	}
	for _, path := range governedSlotLockPaths(roots, slots) {
		if err := acquire(path, "waywarden governed slot mutation"); err != nil {
			return cleanup(err)
		}
	}
	if err := acquire(ledgerLockPath(roots), "waywarden selected ledger mutation"); err != nil {
		return cleanup(err)
	}
	return &heldLockSet{handles: handles}, nil
}

func (s *store) AcquireMutationLocks(ctx context.Context, roots Roots, slots []contracts.GovernedSlotIdentity) (LockSet, error) {
	return AcquireMutationLocks(ctx, s.fs, roots, slots)
}

func AcquireVerificationLocks(ctx context.Context, fs filesystem.Adapter, roots Roots) (LockSet, error) {
	var handles []filesystem.LockHandle
	cleanup := func(err error) (LockSet, error) {
		_ = releaseHandlesReverse(handles)
		return nil, err
	}
	global, err := fs.LockExclusive(ctx, globalMutationLockPath(roots), "waywarden verification state write")
	if err != nil {
		return cleanup(err)
	}
	handles = append(handles, global)
	ledger, err := fs.LockExclusive(ctx, ledgerLockPath(roots), "waywarden selected ledger verification write")
	if err != nil {
		return cleanup(err)
	}
	handles = append(handles, ledger)
	return &heldLockSet{handles: handles}, nil
}

func (s *store) AcquireVerificationLocks(ctx context.Context, roots Roots) (LockSet, error) {
	return AcquireVerificationLocks(ctx, s.fs, roots)
}

func AcquireInventoryLedgerSnapshot(ctx context.Context, fs filesystem.Adapter, roots Roots) (filesystem.LockHandle, error) {
	return fs.LockShared(ctx, ledgerLockPath(roots), "waywarden inventory selected ledger snapshot")
}

func (s *store) AcquireInventoryLedgerSnapshot(ctx context.Context, roots Roots) (filesystem.LockHandle, error) {
	return AcquireInventoryLedgerSnapshot(ctx, s.fs, roots)
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

func ledgerLockPath(roots Roots) contracts.AbsolutePath {
	identity := canonicalSelectedStateRootIdentity(roots.StateRoot)
	key := contracts.SHA256([]byte(identity))
	return contracts.AbsolutePath(filepath.Join(string(roots.LockRoot), "ledgers", string(key)+".lock"))
}

func canonicalSelectedStateRootIdentity(root contracts.AbsolutePath) string {
	clean := filepath.Clean(string(root))
	if clean == "." || !filepath.IsAbs(clean) {
		return clean
	}
	resolved, err := filepath.EvalSymlinks(clean)
	if err == nil {
		return filepath.Clean(resolved)
	}
	return clean
}

func validateRoots(roots Roots) error {
	if roots.StateRoot == "" || roots.LockRoot == "" {
		return fmt.Errorf("state and lock roots are required")
	}
	if !filepath.IsAbs(string(roots.StateRoot)) || !filepath.IsAbs(string(roots.LockRoot)) {
		return fmt.Errorf("state and lock roots must be absolute")
	}
	return nil
}
