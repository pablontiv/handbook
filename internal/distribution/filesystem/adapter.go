package filesystem

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"sort"

	"waywarden/internal/distribution/contracts"
)

type Adapter interface {
	Platform() string
	Environment(context.Context) (PlatformEnv, error)
	SafeRoot(context.Context, contracts.AbsolutePath) (SafeRoot, error)
	PhysicalIdentity(context.Context, contracts.AbsolutePath) (PhysicalIdentity, error)
	ListNoFollow(context.Context, contracts.AbsolutePath) ([]DirEntry, error)
	ObserveNoFollow(context.Context, contracts.AbsolutePath) (Observation, error)
	SnapshotTree(context.Context, contracts.AbsolutePath) (TreeSnapshot, error)
	HashFileByHandle(context.Context, contracts.AbsolutePath) (contracts.SHA256Hex, error)
	LockShared(context.Context, contracts.AbsolutePath, string) (LockHandle, error)
	LockExclusive(context.Context, contracts.AbsolutePath, string) (LockHandle, error)
	AppendFileSync(context.Context, contracts.AbsolutePath, []byte) error
	WriteFileNoReplaceSync(context.Context, contracts.AbsolutePath, []byte) error
	ReadFile(context.Context, contracts.AbsolutePath) ([]byte, error)
	SyncDirectory(context.Context, contracts.AbsolutePath) error
	PublishNoReplace(context.Context, contracts.AbsolutePath, []byte, ForbiddenRoots) error
	OwnerPrivateLockRoot(PlatformEnv) (contracts.AbsolutePath, error)
}

type PlatformEnv struct {
	Home         string
	XDGStateHome string
	LocalAppData string
}

type SafeRoot struct {
	Path     contracts.AbsolutePath
	Identity PhysicalIdentity
}

type PhysicalIdentity string

type DirEntry struct {
	Name string
	Kind string
	Path contracts.AbsolutePath
}

type Observation struct {
	Path     contracts.AbsolutePath
	Exists   bool
	Kind     string
	Identity string
	Target   string
}

type TreeSnapshot struct {
	Root    contracts.AbsolutePath `json:"root"`
	Entries []TreeEntry            `json:"entries"`
}

type TreeEntry struct {
	Path   string              `json:"path"`
	SHA256 contracts.SHA256Hex `json:"sha256"`
}

type LockHandle interface {
	Close() error
}

type localAdapter struct{}

func NewLocalAdapter() Adapter { return localAdapter{} }

func (localAdapter) Platform() string { return runtime.GOOS }

func (localAdapter) Environment(context.Context) (PlatformEnv, error) {
	return PlatformEnv{Home: os.Getenv("HOME"), XDGStateHome: os.Getenv("XDG_STATE_HOME"), LocalAppData: os.Getenv("LOCALAPPDATA")}, nil
}

func (localAdapter) SafeRoot(context.Context, contracts.AbsolutePath) (SafeRoot, error) {
	return SafeRoot{}, ErrUnsupportedCapability
}

func (localAdapter) PhysicalIdentity(context.Context, contracts.AbsolutePath) (PhysicalIdentity, error) {
	return "", ErrUnsupportedCapability
}

func (localAdapter) ListNoFollow(context.Context, contracts.AbsolutePath) ([]DirEntry, error) {
	return nil, ErrUnsupportedCapability
}

func (localAdapter) ObserveNoFollow(_ context.Context, path contracts.AbsolutePath) (Observation, error) {
	p := filepath.Clean(string(path))
	info, err := os.Lstat(p)
	if os.IsNotExist(err) {
		return Observation{Path: contracts.AbsolutePath(p), Exists: false}, nil
	}
	if err != nil {
		return Observation{}, err
	}
	obs := Observation{Path: contracts.AbsolutePath(p), Exists: true}
	switch {
	case info.Mode()&os.ModeSymlink != 0:
		obs.Kind = "symlink"
		target, err := os.Readlink(p)
		if err == nil {
			obs.Target = target
		}
	case info.IsDir():
		obs.Kind = "directory"
	default:
		obs.Kind = "file"
	}
	identity, err := LexicalIdentity(p)
	if err == nil {
		obs.Identity = identity
	}
	return obs, nil
}

func (localAdapter) SnapshotTree(_ context.Context, root contracts.AbsolutePath) (TreeSnapshot, error) {
	cleanRoot := filepath.Clean(string(root))
	var entries []TreeEntry
	err := filepath.WalkDir(cleanRoot, func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if path == cleanRoot {
			return nil
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("symlink source entries are unsupported for inventory: %s", path)
		}
		if entry.IsDir() {
			return nil
		}
		rel, err := filepath.Rel(cleanRoot, path)
		if err != nil {
			return err
		}
		digest, err := hashFile(path)
		if err != nil {
			return err
		}
		entries = append(entries, TreeEntry{Path: filepath.ToSlash(rel), SHA256: digest})
		return nil
	})
	if err != nil {
		return TreeSnapshot{}, err
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Path < entries[j].Path })
	return TreeSnapshot{Root: contracts.AbsolutePath(cleanRoot), Entries: entries}, nil
}

func (localAdapter) HashFileByHandle(_ context.Context, path contracts.AbsolutePath) (contracts.SHA256Hex, error) {
	return hashFile(string(path))
}

func (localAdapter) LockShared(context.Context, contracts.AbsolutePath, string) (LockHandle, error) {
	return nil, ErrUnsupportedCapability
}

func (localAdapter) LockExclusive(context.Context, contracts.AbsolutePath, string) (LockHandle, error) {
	return nil, ErrUnsupportedCapability
}

func (localAdapter) AppendFileSync(_ context.Context, path contracts.AbsolutePath, data []byte) error {
	p := filepath.Clean(string(path))
	if err := os.MkdirAll(filepath.Dir(p), 0o700); err != nil {
		return err
	}
	f, err := os.OpenFile(p, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return err
	}
	defer f.Close()
	if _, err := f.Write(data); err != nil {
		return err
	}
	return f.Sync()
}

func (localAdapter) WriteFileNoReplaceSync(_ context.Context, path contracts.AbsolutePath, data []byte) error {
	p := filepath.Clean(string(path))
	if err := os.MkdirAll(filepath.Dir(p), 0o700); err != nil {
		return err
	}
	f, err := os.OpenFile(p, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if os.IsExist(err) {
		return ErrDestinationExists
	}
	if err != nil {
		return err
	}
	defer f.Close()
	if _, err := f.Write(data); err != nil {
		return err
	}
	return f.Sync()
}

func (localAdapter) ReadFile(_ context.Context, path contracts.AbsolutePath) ([]byte, error) {
	return os.ReadFile(filepath.Clean(string(path)))
}

func (localAdapter) SyncDirectory(context.Context, contracts.AbsolutePath) error {
	return ErrUnsupportedCapability
}

func (a localAdapter) PublishNoReplace(ctx context.Context, destination contracts.AbsolutePath, canonical []byte, forbiddenRoots ForbiddenRoots) error {
	return NewArtifactPublisher(a).PublishNoReplace(ctx, destination, canonical, forbiddenRoots)
}

func (localAdapter) OwnerPrivateLockRoot(env PlatformEnv) (contracts.AbsolutePath, error) {
	var base string
	switch runtime.GOOS {
	case "windows":
		base = env.LocalAppData
		if base == "" {
			return "", fmt.Errorf("LOCALAPPDATA is required for lock root")
		}
		return contracts.AbsolutePath(filepath.Join(base, "waywarden", "locks")), nil
	case "darwin":
		if env.Home == "" {
			return "", fmt.Errorf("HOME is required for lock root")
		}
		return contracts.AbsolutePath(filepath.Join(env.Home, "Library", "Application Support", "waywarden", "locks")), nil
	default:
		base = env.XDGStateHome
		if base == "" {
			if env.Home == "" {
				return "", fmt.Errorf("HOME or XDG_STATE_HOME is required for lock root")
			}
			base = filepath.Join(env.Home, ".local", "state")
		}
		return contracts.AbsolutePath(filepath.Join(base, "waywarden", "locks")), nil
	}
}

func hashFile(path string) (contracts.SHA256Hex, error) {
	f, err := os.Open(filepath.Clean(path))
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return contracts.SHA256Hex(hex.EncodeToString(h.Sum(nil))), nil
}

func TreeDigest(snapshot TreeSnapshot) (contracts.SHA256Hex, error) {
	entries := append([]TreeEntry(nil), snapshot.Entries...)
	sort.Slice(entries, func(i, j int) bool { return entries[i].Path < entries[j].Path })
	canonical, err := contracts.CanonicalBytes(struct {
		Entries []TreeEntry `json:"entries"`
	}{Entries: entries})
	if err != nil {
		return "", err
	}
	return contracts.SHA256(canonical), nil
}
