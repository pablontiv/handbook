package state

import (
	"context"
	"fmt"
	"path/filepath"
	"strconv"
	"strings"

	"waywarden/internal/distribution/contracts"
)

func (s *store) PublishRunArtifact(ctx context.Context, roots Roots, op contracts.OperationID, name string, data []byte) (contracts.ArtifactRef, error) {
	return publishRunArtifact(ctx, s, roots, op, name, data)
}

func (s *store) PublishReceipt(ctx context.Context, roots Roots, op contracts.OperationID, receipt contracts.Receipt) (contracts.ArtifactRef, error) {
	canonical, err := contracts.CanonicalBytes(receipt)
	if err != nil {
		return contracts.ArtifactRef{}, err
	}
	return publishRunArtifact(ctx, s, roots, op, "receipt.json", canonical)
}

func publishRunArtifact(ctx context.Context, s *store, roots Roots, op contracts.OperationID, name string, data []byte) (contracts.ArtifactRef, error) {
	if err := validateRoots(roots); err != nil {
		return contracts.ArtifactRef{}, err
	}
	cleanName := filepath.Clean(filepath.FromSlash(name))
	if name == "" || filepath.IsAbs(name) || cleanName == "." || cleanName == ".." || strings.HasPrefix(cleanName, ".."+string(filepath.Separator)) {
		return contracts.ArtifactRef{}, fmt.Errorf("run artifact name must be relative and confined")
	}
	rel := filepath.ToSlash(filepath.Join("runs", string(op), cleanName))
	abs := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), filepath.FromSlash(rel)))
	if err := s.fs.WriteFileNoReplaceSync(ctx, abs, data); err != nil {
		return contracts.ArtifactRef{}, err
	}
	return contracts.ArtifactRef{Path: rel, SHA256: contracts.SHA256(data), Bytes: strconv.Itoa(len(data))}, nil
}
