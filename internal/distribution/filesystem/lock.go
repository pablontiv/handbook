package filesystem

import "sync/atomic"

type memoryLockHandle struct {
	closed atomic.Bool
}

func (h *memoryLockHandle) Close() error {
	h.closed.Store(true)
	return nil
}
