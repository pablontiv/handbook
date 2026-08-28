package state

import (
	"bytes"
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
	if err := validateRoots(ctx, s.fs, roots); err != nil {
		return contracts.ArtifactRef{}, err
	}
	if err := contracts.ValidateOperationID(op); err != nil {
		return contracts.ArtifactRef{}, err
	}
	if receipt.OperationID != string(op) {
		return contracts.ArtifactRef{}, fmt.Errorf("receipt operation_id mismatch")
	}
	if err := verifyReadyJournalRef(ctx, s, roots, op, receipt.ReadyJournalRef); err != nil {
		return contracts.ArtifactRef{}, err
	}
	records, err := readLedger(ctx, s.fs, roots)
	if err != nil {
		return contracts.ArtifactRef{}, err
	}
	if len(records) == 0 || records[len(records)-1].RecordHash != receipt.LedgerRecordHash {
		return contracts.ArtifactRef{}, fmt.Errorf("receipt ledger_record_hash does not match latest durable ledger record")
	}
	if err := contracts.ValidateReceipt(receipt); err != nil {
		return contracts.ArtifactRef{}, err
	}
	draft, err := contracts.CanonicalBytes(receipt)
	if err != nil {
		return contracts.ArtifactRef{}, err
	}
	draftPath := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op), "receipt.json.draft"))
	if err := s.fs.EnsureDirSync(ctx, contracts.AbsolutePath(filepath.Dir(string(draftPath)))); err != nil {
		return contracts.ArtifactRef{}, err
	}
	if err := s.fs.WriteFileNoReplaceSync(ctx, draftPath, draft); err != nil {
		return contracts.ArtifactRef{}, err
	}
	receiptDigest := contracts.SHA256(draft)
	journal, err := s.OpenJournal(ctx, roots, op, contracts.CommandName(receipt.Command))
	if err != nil {
		return contracts.ArtifactRef{}, err
	}
	if _, err := journal.Append(ctx, contracts.JournalEntry{OperationID: string(op), Boundary: "committed", Result: receipt.OperationResult, ReceiptSHA256: receiptDigest, FinalArtifactPath: "receipt.json"}); err != nil {
		return contracts.ArtifactRef{}, err
	}
	preservedDraft, err := s.fs.ReadFile(ctx, draftPath)
	if err != nil {
		return contracts.ArtifactRef{}, err
	}
	if !bytes.Equal(preservedDraft, draft) {
		return contracts.ArtifactRef{}, fmt.Errorf("receipt draft bytes changed before publication")
	}
	ref, err := publishRunArtifact(ctx, s, roots, op, "receipt.json", preservedDraft)
	if err != nil {
		return contracts.ArtifactRef{}, err
	}
	if err := s.fs.SyncDirectory(ctx, contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs", string(op)))); err != nil {
		return contracts.ArtifactRef{}, err
	}
	return ref, nil
}

func publishRunArtifact(ctx context.Context, s *store, roots Roots, op contracts.OperationID, name string, data []byte) (contracts.ArtifactRef, error) {
	if err := validateRoots(ctx, s.fs, roots); err != nil {
		return contracts.ArtifactRef{}, err
	}
	if err := contracts.ValidateOperationID(op); err != nil {
		return contracts.ArtifactRef{}, err
	}
	if err := validateRunArtifactName(name); err != nil {
		return contracts.ArtifactRef{}, err
	}
	rel := filepath.ToSlash(filepath.Join("runs", string(op), filepath.FromSlash(name)))
	abs := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), filepath.FromSlash(rel)))
	if !isUnderRoot(string(roots.StateRoot), string(abs)) {
		return contracts.ArtifactRef{}, fmt.Errorf("run artifact escaped state root")
	}
	if err := s.fs.EnsureDirSync(ctx, contracts.AbsolutePath(filepath.Dir(string(abs)))); err != nil {
		return contracts.ArtifactRef{}, err
	}
	if err := s.fs.WriteFileNoReplaceSync(ctx, abs, data); err != nil {
		return contracts.ArtifactRef{}, err
	}
	if err := s.fs.SyncDirectory(ctx, contracts.AbsolutePath(filepath.Dir(string(abs)))); err != nil {
		return contracts.ArtifactRef{}, err
	}
	return contracts.ArtifactRef{Path: rel, SHA256: contracts.SHA256(data), Bytes: strconv.Itoa(len(data))}, nil
}

func validateRunArtifactName(name string) error {
	if name == "" || name == "." || name == ".." || strings.ContainsAny(name, `\\:`) || strings.HasPrefix(name, "/") || strings.HasPrefix(name, "../") || strings.Contains(name, "/../") {
		return fmt.Errorf("run artifact name must be relative and confined")
	}
	if filepath.ToSlash(filepath.Clean(filepath.FromSlash(name))) != name {
		return fmt.Errorf("run artifact name must be canonical slash-relative")
	}
	return nil
}

func isUnderRoot(root, target string) bool {
	root = filepath.Clean(root)
	target = filepath.Clean(target)
	if target == root {
		return true
	}
	rel, err := filepath.Rel(root, target)
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) && !filepath.IsAbs(rel)
}

func verifyReadyJournalRef(ctx context.Context, s *store, roots Roots, op contracts.OperationID, ref contracts.JournalRef) error {
	if err := contracts.ValidateJournalRef(ref, op); err != nil {
		return err
	}
	abs := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), filepath.FromSlash(ref.Path)))
	data, err := s.fs.ReadFile(ctx, abs)
	if err != nil {
		return err
	}
	prefix, err := durablePrefixThroughBoundary(data, "ready_to_commit")
	if err != nil {
		return err
	}
	if contracts.SHA256(prefix) != ref.SHA256 {
		return fmt.Errorf("ready_journal_ref hash mismatch")
	}
	return nil
}

func durablePrefixThroughBoundary(data []byte, boundary string) ([]byte, error) {
	if !bytes.HasSuffix(data, []byte("\n")) {
		return nil, fmt.Errorf("journal has a partial tail")
	}
	lines := bytes.Split(bytes.TrimSuffix(data, []byte("\n")), []byte("\n"))
	var prefix []byte
	for _, line := range lines {
		var entry contracts.JournalEntry
		if err := contracts.StrictParseCanonical(line, &entry); err != nil {
			return nil, err
		}
		prefix = append(prefix, line...)
		prefix = append(prefix, '\n')
		if entry.Boundary == boundary {
			return prefix, nil
		}
		if entry.Boundary == "committed" {
			break
		}
	}
	return nil, fmt.Errorf("journal prefix %q not found", boundary)
}
