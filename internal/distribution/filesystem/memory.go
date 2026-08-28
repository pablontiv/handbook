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
	shared    []string
	exclusive []string
	writeLog  []string
}

func NewMemoryAdapter() *MemoryAdapter {
	return &MemoryAdapter{
		platform: "linux",
		env:      PlatformEnv{Home: "/memory/home", XDGStateHome: "/memory/state", LocalAppData: "C:/memory/local"},
		files:    map[string][]byte{},
		trees:    map[string]TreeSnapshot{},
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

func (m *MemoryAdapter) WriteLog() []string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]string(nil), m.writeLog...)
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
	m.shared = append(m.shared, cleanMemoryPath(string(path)))
	return &memoryLockHandle{}, nil
}

func (m *MemoryAdapter) LockExclusive(_ context.Context, path contracts.AbsolutePath, _ string) (LockHandle, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.exclusive = append(m.exclusive, cleanMemoryPath(string(path)))
	return &memoryLockHandle{}, nil
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
	base := env.XDGStateHome
	if base == "" {
		if env.Home == "" {
			return "", fmt.Errorf("HOME or XDG_STATE_HOME is required for lock root")
		}
		base = filepath.Join(env.Home, ".local", "state")
	}
	return contracts.AbsolutePath(filepath.Join(base, "waywarden", "locks")), nil
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
