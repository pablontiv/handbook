package filesystem

import (
	"errors"
	"sync/atomic"
)

var ErrLockConflict = errors.New("filesystem lock is already held")

type memoryLockHandle struct {
	closed  atomic.Bool
	onClose func() error
}

func (h *memoryLockHandle) Close() error {
	if !h.closed.CompareAndSwap(false, true) {
		return nil
	}
	if h.onClose != nil {
		return h.onClose()
	}
	return nil
}
