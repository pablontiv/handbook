package state

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

func (s *store) ClassifyRecovery(ctx context.Context, roots Roots) (contracts.RecoveryStatus, error) {
	if err := validateRoots(roots); err != nil {
		return contracts.RecoveryStatus{}, err
	}
	records, err := readLedger(ctx, s.fs, roots)
	if err != nil {
		return recoveryRequired("corrupt_ledger", roots.LedgerPath()), nil
	}
	for _, record := range records {
		if record.AggregateEvent == contracts.RecoveryRequired || record.OperationResult == contracts.RecoveryRequired {
			return recoveryRequired("ledger_recovery_required", roots.LedgerPath()), nil
		}
	}
	journals, err := journalFiles(ctx, s.fs, roots)
	if err != nil {
		return contracts.RecoveryStatus{}, err
	}
	for _, path := range journals {
		entries, err := readJournalEntries(ctx, s.fs, path)
		if err != nil {
			return recoveryRequired("corrupt_journal", path), nil
		}
		if len(entries) == 0 {
			continue
		}
		last := entries[len(entries)-1].Boundary
		switch last {
		case "rollback_failed":
			return recoveryRequired("rollback_failed", path), nil
		case "committed":
			runDir := filepath.Dir(string(path))
			if _, err := s.fs.ReadFile(ctx, contracts.AbsolutePath(filepath.Join(runDir, "receipt.json"))); err != nil {
				if errors.Is(err, fs.ErrNotExist) {
					return recoveryRequired("receipt_publish_pending", path), nil
				}
				return contracts.RecoveryStatus{}, err
			}
		case "rolled_back":
			continue
		default:
			return recoveryRequired("interrupted_journal", path), nil
		}
	}
	return contracts.RecoveryStatus{Status: contracts.RecoveryClean, Evidence: []contracts.EvidenceRef{}}, nil
}

func recoveryRequired(code string, path contracts.AbsolutePath) contracts.RecoveryStatus {
	return contracts.RecoveryStatus{Status: contracts.RecoveryRequired, Code: code, Evidence: []contracts.EvidenceRef{{Label: code, Ref: string(path)}}}
}

type filePathLister interface {
	FilePaths() []contracts.AbsolutePath
}

func journalFiles(ctx context.Context, adapter filesystem.Adapter, roots Roots) ([]contracts.AbsolutePath, error) {
	prefix := filepath.Join(string(roots.StateRoot), "runs") + string(filepath.Separator)
	var out []contracts.AbsolutePath
	if lister, ok := adapter.(filePathLister); ok {
		for _, path := range lister.FilePaths() {
			clean := filepath.Clean(string(path))
			if strings.HasPrefix(clean, prefix) && filepath.Base(clean) == "journal.ndjson" {
				out = append(out, contracts.AbsolutePath(clean))
			}
		}
		return out, nil
	}
	if _, ok := adapter.(interface{ Platform() string }); ok {
		root := filepath.Join(string(roots.StateRoot), "runs")
		if _, err := os.Stat(root); errors.Is(err, os.ErrNotExist) {
			return nil, nil
		}
		err := filepath.WalkDir(root, func(path string, entry os.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if entry.IsDir() {
				return nil
			}
			if filepath.Base(path) == "journal.ndjson" {
				out = append(out, contracts.AbsolutePath(filepath.Clean(path)))
			}
			return nil
		})
		return out, err
	}
	_ = ctx
	return out, nil
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
		if err := validateJournalTransition(entries, entry.Boundary); err != nil {
			return nil, err
		}
		entries = append(entries, entry)
	}
	return entries, nil
}
