package filesystem

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"waywarden/internal/distribution/contracts"
)

var (
	ErrDestinationExists     = errors.New("destination already exists")
	ErrForbiddenDestination  = errors.New("destination is inside a forbidden root")
	ErrUnsupportedCapability = errors.New("filesystem capability is unsupported")
)

type ForbiddenRoots struct {
	RepositorySourceRoot  contracts.AbsolutePath
	RepositorySourceRoots []contracts.AbsolutePath
	RuntimeRoots          []contracts.AbsolutePath
	StateRoot             contracts.AbsolutePath
	LockRoot              contracts.AbsolutePath
}

type ArtifactPublisher struct {
	adapter Adapter
}

func NewArtifactPublisher(adapter Adapter) ArtifactPublisher {
	return ArtifactPublisher{adapter: adapter}
}

func (p ArtifactPublisher) PublishNoReplace(ctx context.Context, destination contracts.AbsolutePath, canonical []byte, forbiddenRoots ForbiddenRoots) error {
	_ = ctx
	if p.adapter == nil {
		return ErrUnsupportedCapability
	}
	if _, ok := p.adapter.(localAdapter); ok {
		return publishLocalNoReplace(destination, canonical, forbiddenRoots)
	}
	return p.adapter.PublishNoReplace(ctx, destination, canonical, forbiddenRoots)
}

func publishLocalNoReplace(destination contracts.AbsolutePath, canonical []byte, forbiddenRoots ForbiddenRoots) error {
	dest := filepath.Clean(string(destination))
	if err := validatePublishDestination(dest, forbiddenRoots); err != nil {
		return err
	}
	if err := rejectSymlinkAncestors(filepath.Dir(dest)); err != nil {
		return err
	}
	if _, err := os.Lstat(dest); err == nil {
		return ErrDestinationExists
	} else if !os.IsNotExist(err) {
		return err
	}

	staging, file, err := createSameParentStaging(filepath.Dir(dest))
	if err != nil {
		return err
	}
	published := false
	defer func() {
		_ = os.Remove(staging)
	}()
	if _, err := file.Write(canonical); err != nil {
		_ = file.Close()
		return err
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	if err := os.Link(staging, dest); err != nil {
		if os.IsExist(err) {
			return ErrDestinationExists
		}
		if strings.Contains(strings.ToLower(err.Error()), "not supported") || strings.Contains(strings.ToLower(err.Error()), "operation not permitted") {
			return ErrUnsupportedCapability
		}
		return err
	}
	published = true
	if err := syncDirectory(filepath.Dir(dest)); err != nil {
		return err
	}
	if !published {
		return ErrUnsupportedCapability
	}
	return nil
}

func validatePublishDestination(dest string, forbiddenRoots ForbiddenRoots) error {
	if !filepath.IsAbs(dest) {
		return fmt.Errorf("artifact destination must be absolute")
	}
	for _, root := range collectForbiddenRoots(forbiddenRoots) {
		if root == "" {
			continue
		}
		if sameOrDescendant(filepath.Clean(root), dest) {
			return ErrForbiddenDestination
		}
	}
	return nil
}

func collectForbiddenRoots(forbiddenRoots ForbiddenRoots) []string {
	roots := []string{string(forbiddenRoots.RepositorySourceRoot)}
	for _, root := range forbiddenRoots.RepositorySourceRoots {
		roots = append(roots, string(root))
	}
	roots = append(roots, string(forbiddenRoots.StateRoot), string(forbiddenRoots.LockRoot))
	for _, root := range forbiddenRoots.RuntimeRoots {
		roots = append(roots, string(root))
	}
	return roots
}

func rejectSymlinkAncestors(path string) error {
	clean := filepath.Clean(path)
	if !filepath.IsAbs(clean) {
		return fmt.Errorf("artifact parent must be absolute")
	}
	volume := filepath.VolumeName(clean)
	start := string(filepath.Separator)
	if volume != "" {
		start = volume + string(filepath.Separator)
	}
	rel, err := filepath.Rel(start, clean)
	if err != nil {
		return err
	}
	current := start
	if rel == "." {
		return nil
	}
	for _, part := range strings.Split(rel, string(filepath.Separator)) {
		if part == "" || part == "." {
			continue
		}
		current = filepath.Join(current, part)
		info, err := os.Lstat(current)
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return ErrForbiddenDestination
		}
	}
	return nil
}

func createSameParentStaging(parent string) (string, *os.File, error) {
	for i := 0; i < 16; i++ {
		var nonce [16]byte
		if _, err := rand.Read(nonce[:]); err != nil {
			return "", nil, err
		}
		path := filepath.Join(parent, ".waywarden-publish-"+hex.EncodeToString(nonce[:])+".tmp")
		file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
		if os.IsExist(err) {
			continue
		}
		return path, file, err
	}
	return "", nil, ErrUnsupportedCapability
}

func syncDirectory(path string) error {
	dir, err := os.Open(path)
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}
