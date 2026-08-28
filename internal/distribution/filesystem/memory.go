package filesystem

import (
	"context"
	"fmt"
	"io/fs"
	"path/filepath"
	"sort"
	"sync"

	"waywarden/internal/distribution/contracts"
)

type MemoryAdapter struct {
	mu        sync.Mutex
	platform  string
	env       PlatformEnv
	files     map[string][]byte
	trees     map[string]TreeSnapshot
	locks     map[string]memoryLockState
	shared    []string
	exclusive []string
	released  []string
	writeLog  []string
}

type memoryLockState struct {
	shared    int
	exclusive int
}

func NewMemoryAdapter() *MemoryAdapter {
	return &MemoryAdapter{
		platform: "linux",
		env:      PlatformEnv{Home: "/memory/home", XDGStateHome: "/memory/state", LocalAppData: "C:/memory/local"},
		files:    map[string][]byte{},
		trees:    map[string]TreeSnapshot{},
		locks:    map[string]memoryLockState{},
	}
}

func (m *MemoryAdapter) SetPlatform(platform string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.platform = platform
}

func (m *MemoryAdapter) SetEnvironment(env PlatformEnv) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.env = env
}

func (m *MemoryAdapter) SetTreeSnapshot(root string, snapshot TreeSnapshot) {
	m.mu.Lock()
	defer m.mu.Unlock()
	clone := snapshot
	clone.Entries = append([]TreeEntry(nil), snapshot.Entries...)
	sort.Slice(clone.Entries, func(i, j int) bool { return clone.Entries[i].Path < clone.Entries[j].Path })
	m.trees[cleanMemoryPath(root)] = clone
}

func (m *MemoryAdapter) PutFile(path contracts.AbsolutePath, data []byte) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.files[cleanMemoryPath(string(path))] = append([]byte(nil), data...)
}

func (m *MemoryAdapter) SharedLockKeys() []string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]string(nil), m.shared...)
}

func (m *MemoryAdapter) ExclusiveLockKeys() []string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]string(nil), m.exclusive...)
}

func (m *MemoryAdapter) ReleaseLockKeys() []string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]string(nil), m.released...)
}

func (m *MemoryAdapter) WriteLog() []string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]string(nil), m.writeLog...)
}

func (m *MemoryAdapter) FilePaths() []contracts.AbsolutePath {
	m.mu.Lock()
	defer m.mu.Unlock()
	paths := make([]string, 0, len(m.files))
	for path := range m.files {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	out := make([]contracts.AbsolutePath, 0, len(paths))
	for _, path := range paths {
		out = append(out, contracts.AbsolutePath(path))
	}
	return out
}

func (m *MemoryAdapter) Platform() string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.platform
}

func (m *MemoryAdapter) Environment(context.Context) (PlatformEnv, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.env, nil
}

func (m *MemoryAdapter) ObserveNoFollow(_ context.Context, path contracts.AbsolutePath) (Observation, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	clean := cleanMemoryPath(string(path))
	_, fileExists := m.files[clean]
	_, treeExists := m.trees[clean]
	return Observation{Path: contracts.AbsolutePath(clean), Exists: fileExists || treeExists, Kind: memoryKind(fileExists, treeExists), Identity: clean}, nil
}

func (m *MemoryAdapter) SnapshotTree(_ context.Context, root contracts.AbsolutePath) (TreeSnapshot, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	clean := cleanMemoryPath(string(root))
	snapshot, ok := m.trees[clean]
	if !ok {
		return TreeSnapshot{}, fmt.Errorf("snapshot tree %s: %w", clean, fs.ErrNotExist)
	}
	clone := snapshot
	clone.Entries = append([]TreeEntry(nil), snapshot.Entries...)
	sort.Slice(clone.Entries, func(i, j int) bool { return clone.Entries[i].Path < clone.Entries[j].Path })
	return clone, nil
}

func (m *MemoryAdapter) HashFileByHandle(_ context.Context, path contracts.AbsolutePath) (contracts.SHA256Hex, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	data, ok := m.files[cleanMemoryPath(string(path))]
	if !ok {
		return "", fs.ErrNotExist
	}
	return contracts.SHA256(data), nil
}

func (m *MemoryAdapter) LockShared(_ context.Context, path contracts.AbsolutePath, _ string) (LockHandle, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	clean := cleanMemoryPath(string(path))
	state := m.locks[clean]
	if state.exclusive > 0 {
		return nil, ErrLockConflict
	}
	state.shared++
	m.locks[clean] = state
	m.shared = append(m.shared, clean)
	return &memoryLockHandle{onClose: func() error {
		m.mu.Lock()
		defer m.mu.Unlock()
		state := m.locks[clean]
		if state.shared > 0 {
			state.shared--
		}
		if state.shared == 0 && state.exclusive == 0 {
			delete(m.locks, clean)
		} else {
			m.locks[clean] = state
		}
		m.released = append(m.released, clean)
		return nil
	}}, nil
}

func (m *MemoryAdapter) LockExclusive(_ context.Context, path contracts.AbsolutePath, _ string) (LockHandle, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	clean := cleanMemoryPath(string(path))
	state := m.locks[clean]
	if state.shared > 0 || state.exclusive > 0 {
		return nil, ErrLockConflict
	}
	state.exclusive++
	m.locks[clean] = state
	m.exclusive = append(m.exclusive, clean)
	return &memoryLockHandle{onClose: func() error {
		m.mu.Lock()
		defer m.mu.Unlock()
		state := m.locks[clean]
		if state.exclusive > 0 {
			state.exclusive--
		}
		if state.shared == 0 && state.exclusive == 0 {
			delete(m.locks, clean)
		} else {
			m.locks[clean] = state
		}
		m.released = append(m.released, clean)
		return nil
	}}, nil
}

func (m *MemoryAdapter) AppendFileSync(_ context.Context, path contracts.AbsolutePath, data []byte) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	clean := cleanMemoryPath(string(path))
	m.files[clean] = append(m.files[clean], data...)
	m.writeLog = append(m.writeLog, "append:"+clean)
	return nil
}

func (m *MemoryAdapter) WriteFileNoReplaceSync(_ context.Context, path contracts.AbsolutePath, data []byte) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	clean := cleanMemoryPath(string(path))
	if _, exists := m.files[clean]; exists {
		return ErrDestinationExists
	}
	m.files[clean] = append([]byte(nil), data...)
	m.writeLog = append(m.writeLog, "write-no-replace:"+clean)
	return nil
}

func (m *MemoryAdapter) ReadFile(_ context.Context, path contracts.AbsolutePath) ([]byte, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	data, ok := m.files[cleanMemoryPath(string(path))]
	if !ok {
		return nil, fs.ErrNotExist
	}
	return append([]byte(nil), data...), nil
}

func (m *MemoryAdapter) PublishNoReplace(_ context.Context, destination contracts.AbsolutePath, canonical []byte, forbiddenRoots ForbiddenRoots) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	clean := cleanMemoryPath(string(destination))
	if err := validatePublishDestination(clean, forbiddenRoots); err != nil {
		return err
	}
	if _, exists := m.files[clean]; exists {
		return ErrDestinationExists
	}
	m.files[clean] = append([]byte(nil), canonical...)
	return nil
}

func (m *MemoryAdapter) OwnerPrivateLockRoot(env PlatformEnv) (contracts.AbsolutePath, error) {
	m.mu.Lock()
	platform := m.platform
	m.mu.Unlock()
	switch platform {
	case "windows":
		if env.LocalAppData == "" {
			return "", fmt.Errorf("LOCALAPPDATA is required for lock root")
		}
		return contracts.AbsolutePath(filepath.Join(env.LocalAppData, "waywarden", "locks")), nil
	case "darwin":
		if env.Home == "" {
			return "", fmt.Errorf("HOME is required for lock root")
		}
		return contracts.AbsolutePath(filepath.Join(env.Home, "Library", "Application Support", "waywarden", "locks")), nil
	default:
		base := env.XDGStateHome
		if base == "" {
			if env.Home == "" {
				return "", fmt.Errorf("HOME or XDG_STATE_HOME is required for lock root")
			}
			base = filepath.Join(env.Home, ".local", "state")
		}
		return contracts.AbsolutePath(filepath.Join(base, "waywarden", "locks")), nil
	}
}

func cleanMemoryPath(path string) string {
	if path == "" {
		return ""
	}
	return filepath.Clean(path)
}

func memoryKind(fileExists, treeExists bool) string {
	switch {
	case treeExists:
		return "directory"
	case fileExists:
		return "file"
	default:
		return ""
	}
}
