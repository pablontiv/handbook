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
	if ambiguous, ok := s.fs.(interface {
		AmbiguousDurabilityFailures() []contracts.AbsolutePath
	}); ok {
		failures := ambiguous.AmbiguousDurabilityFailures()
		if len(failures) > 0 {
			return recoveryRequired("ambiguous_durability_failure", relativeStateRef(roots, failures[0])), nil
		}
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
		if errors.Is(err, errUnknownRunEvidence) {
			return recoveryRequired("unknown_run_evidence", "runs"), nil
		}
		return contracts.RecoveryStatus{}, err
	}
	for _, path := range journals {
		entries, err := readJournalEntries(ctx, s.fs, path)
		if err != nil {
			return recoveryRequired("corrupt_journal", relativeStateRef(roots, path)), nil
		}
		if len(entries) == 0 {
			return recoveryRequired("empty_journal", relativeStateRef(roots, path)), nil
		}
		last := entries[len(entries)-1]
		switch last.Boundary {
		case "rollback_failed":
			return recoveryRequired("rollback_failed", relativeStateRef(roots, path)), nil
		case "committed":
			if code := validateCommittedRecoveryDAG(ctx, s.fs, roots, path, entries, records); code != "" {
				return recoveryRequired(code, relativeStateRef(roots, path)), nil
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

var errUnknownRunEvidence = errors.New("unknown run evidence")

func journalFiles(ctx context.Context, adapter filesystem.Adapter, roots Roots) ([]contracts.AbsolutePath, error) {
	runs := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs"))
	entries, err := adapter.ListNoFollow(ctx, runs)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return nil, nil
		}
		return nil, err
	}
	journals := []contracts.AbsolutePath{}
	for _, entry := range entries {
		if entry.Kind != "directory" {
			return nil, errUnknownRunEvidence
		}
		if err := contracts.ValidateOperationID(entry.Name); err != nil {
			return nil, errUnknownRunEvidence
		}
		runEntries, err := adapter.ListNoFollow(ctx, entry.Path)
		if err != nil {
			return nil, err
		}
		var journal contracts.AbsolutePath
		for _, runEntry := range runEntries {
			if runEntry.Kind == "file" && runEntry.Name == "journal.ndjson" {
				journal = runEntry.Path
			}
		}
		if journal == "" {
			return nil, errUnknownRunEvidence
		}
		journals = append(journals, journal)
	}
	return journals, nil
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

func validateCommittedRecoveryDAG(ctx context.Context, adapter filesystem.Adapter, roots Roots, journalPath contracts.AbsolutePath, entries []contracts.JournalEntry, records []contracts.OwnershipRecord) string {
	last := entries[len(entries)-1]
	op := contracts.OperationID(last.OperationID)
	if err := contracts.ValidateOperationID(op); err != nil {
		return "journal_operation_invalid"
	}
	expectedJournalRel := filepath.ToSlash(filepath.Join("runs", string(op), "journal.ndjson"))
	if relativeStateRef(roots, journalPath) != expectedJournalRel {
		return "journal_path_mismatch"
	}
	finalReceiptPath := last.FinalReceiptPath
	if finalReceiptPath == "" {
		finalReceiptPath = last.FinalArtifactPath
	}
	if finalReceiptPath != "receipt.json" {
		return "terminal_receipt_path_mismatch"
	}
	runDir := filepath.Dir(string(journalPath))
	receiptPath := contracts.AbsolutePath(filepath.Join(runDir, filepath.FromSlash(finalReceiptPath)))
	receiptBytes, err := adapter.ReadFile(ctx, receiptPath)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return "receipt_publish_pending"
		}
		return "receipt_read_failed"
	}
	if contracts.SHA256(receiptBytes) != last.ReceiptSHA256 {
		return "terminal_receipt_digest_mismatch"
	}
	if err := contracts.ValidateSchema(contracts.SchemaReceipt, receiptBytes); err != nil {
		return "receipt_invalid"
	}
	var receipt contracts.Receipt
	if err := contracts.StrictParseCanonical(receiptBytes, &receipt); err != nil {
		return "receipt_invalid"
	}
	if receipt.OperationID != string(op) {
		return "receipt_operation_mismatch"
	}
	journalBytes, err := adapter.ReadFile(ctx, journalPath)
	if err != nil {
		return "journal_read_failed"
	}
	readyPrefix, err := durablePrefixThroughBoundary(journalBytes, "ready_to_commit")
	if err != nil {
		return "ready_prefix_missing"
	}
	if receipt.ReadyJournalRef.OperationID != string(op) || receipt.ReadyJournalRef.Path != expectedJournalRel || contracts.SHA256(readyPrefix) != receipt.ReadyJournalRef.SHA256 {
		return "ready_journal_ref_mismatch"
	}
	record := findLedgerRecordForReadyRef(records, receipt.ReadyJournalRef)
	if record == nil {
		return "ledger_ready_ref_missing"
	}
	if record.RecordHash != receipt.LedgerRecordHash {
		return "ledger_record_hash_mismatch"
	}
	if !artifactRefsEqualPtr(&record.PlanRef, receipt.PlanRef) || !artifactRefsEqualPtr(&record.InventoryRef, receipt.InventoryRef) || !backupSetRefsEqual(record.BackupSetRef, receipt.BackupSetRef) || !artifactRefsEqualPtr(record.VerificationRef, receipt.VerificationRef) {
		return "receipt_ledger_ref_mismatch"
	}
	return ""
}

func findLedgerRecordForReadyRef(records []contracts.OwnershipRecord, ready contracts.JournalRef) *contracts.OwnershipRecord {
	for i := range records {
		ref := records[i].JournalRef
		if ref.OperationID == ready.OperationID && ref.Path == ready.Path && ref.SHA256 == ready.SHA256 {
			return &records[i]
		}
	}
	return nil
}

func artifactRefsEqualPtr(a, b *contracts.ArtifactRef) bool {
	if a == nil || b == nil {
		return a == nil && b == nil
	}
	return a.Path == b.Path && a.SHA256 == b.SHA256 && a.Bytes == b.Bytes
}

func backupSetRefsEqual(a, b *contracts.BackupSetRef) bool {
	if a == nil || b == nil {
		return a == nil && b == nil
	}
	return a.BackupSetID == b.BackupSetID && a.SHA256 == b.SHA256
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
