package state

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io/fs"
	"path/filepath"
	"strings"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

func (s *store) ClassifyRecovery(ctx context.Context, roots Roots) (contracts.RecoveryStatus, error) {
	if err := validateRoots(ctx, s.fs, roots); err != nil {
		return contracts.RecoveryStatus{}, err
	}
	records, err := readLedger(ctx, s.fs, roots)
	if err != nil {
		return recoveryRequired("corrupt_ledger", relativeStateRef(roots, roots.LedgerPath())), nil
	}
	compensating := map[string]bool{}
	for _, record := range records {
		if record.AggregateEvent == contracts.RecoveryRequired || record.OperationResult == contracts.RecoveryRequired {
			return recoveryRequired("ledger_recovery_required", relativeStateRef(roots, roots.LedgerPath())), nil
		}
		switch record.AggregateEvent {
		case "install_rolled_back", "uninstall_rolled_back", "restore_rolled_back":
			compensating[string(record.OperationID)] = true
		}
	}
	journals, err := journalFiles(ctx, s.fs, roots)
	if err != nil {
		return contracts.RecoveryStatus{}, err
	}
	for _, path := range journals {
		entries, err := readJournalEntries(ctx, s.fs, path)
		if err != nil {
			return recoveryRequired("corrupt_journal", relativeStateRef(roots, path)), nil
		}
		if len(entries) == 0 {
			continue
		}
		last := entries[len(entries)-1]
		switch last.Boundary {
		case "rollback_failed":
			return recoveryRequired("rollback_failed", relativeStateRef(roots, path)), nil
		case "committed":
			runDir := filepath.Dir(string(path))
			if _, err := s.fs.ReadFile(ctx, contracts.AbsolutePath(filepath.Join(runDir, "receipt.json"))); err != nil {
				if errors.Is(err, fs.ErrNotExist) {
					return recoveryRequired("receipt_publish_pending", relativeStateRef(roots, path)), nil
				}
				return contracts.RecoveryStatus{}, err
			}
		case "rolled_back":
			if !compensating[last.OperationID] {
				return recoveryRequired("missing_compensating_ledger", relativeStateRef(roots, path)), nil
			}
		default:
			return recoveryRequired("interrupted_journal", relativeStateRef(roots, path)), nil
		}
	}
	return contracts.RecoveryStatus{Status: contracts.RecoveryClean, Evidence: []contracts.EvidenceRef{}}, nil
}

func recoveryRequired(code, ref string) contracts.RecoveryStatus {
	return contracts.RecoveryStatus{Status: contracts.RecoveryRequired, Code: code, Evidence: []contracts.EvidenceRef{{Label: code, Ref: ref}}}
}

func journalFiles(ctx context.Context, adapter filesystem.Adapter, roots Roots) ([]contracts.AbsolutePath, error) {
	runs := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs"))
	var out []contracts.AbsolutePath
	if err := collectJournalFiles(ctx, adapter, runs, &out); err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return nil, nil
		}
		return nil, err
	}
	return out, nil
}

func collectJournalFiles(ctx context.Context, adapter filesystem.Adapter, dir contracts.AbsolutePath, out *[]contracts.AbsolutePath) error {
	entries, err := adapter.ListNoFollow(ctx, dir)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		switch entry.Kind {
		case "file":
			if entry.Name == "journal.ndjson" {
				*out = append(*out, entry.Path)
			}
		case "directory":
			if err := collectJournalFiles(ctx, adapter, entry.Path, out); err != nil {
				return err
			}
		default:
			return fmt.Errorf("unsupported recovery entry kind %q", entry.Kind)
		}
	}
	return nil
}

func readJournalEntries(ctx context.Context, adapter filesystem.Adapter, path contracts.AbsolutePath) ([]contracts.JournalEntry, error) {
	data, err := adapter.ReadFile(ctx, path)
	if err != nil {
		return nil, err
	}
	if len(data) == 0 {
		return []contracts.JournalEntry{}, nil
	}
	if !bytes.HasSuffix(data, []byte("\n")) {
		return nil, fmt.Errorf("journal has a partial tail")
	}
	lines := bytes.Split(bytes.TrimSuffix(data, []byte("\n")), []byte("\n"))
	entries := make([]contracts.JournalEntry, 0, len(lines))
	for _, line := range lines {
		var entry contracts.JournalEntry
		if err := contracts.StrictParseCanonical(line, &entry); err != nil {
			return nil, err
		}
		if err := validateJournalTransition(entries, entry); err != nil {
			return nil, err
		}
		entries = append(entries, entry)
	}
	return entries, nil
}

func relativeStateRef(roots Roots, path contracts.AbsolutePath) string {
	rel, err := filepath.Rel(string(roots.StateRoot), string(path))
	if err != nil || rel == "." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) || filepath.IsAbs(rel) {
		return filepath.Base(string(path))
	}
	return filepath.ToSlash(rel)
}
