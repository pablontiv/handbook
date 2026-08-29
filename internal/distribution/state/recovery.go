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
		if errors.Is(err, errUnknownRunEvidence) {
			return recoveryRequired("unknown_run_evidence", "runs"), nil
		}
		return contracts.RecoveryStatus{}, err
	}
	if code, ref := validateLedgerJournalCorrelation(roots, records, journals); code != "" {
		return recoveryRequired(code, ref), nil
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
	if code, ref := validateClosedRunLayout(ctx, s.fs, roots, records, journals); code != "" {
		return recoveryRequired(code, ref), nil
	}
	if code, ref := validateClosedStateLayout(ctx, s.fs, roots, records); code != "" {
		return recoveryRequired(code, ref), nil
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

func validateLedgerJournalCorrelation(roots Roots, records []contracts.OwnershipRecord, journals []contracts.AbsolutePath) (string, string) {
	journalOps := map[string]bool{}
	for _, journal := range journals {
		rel := relativeStateRef(roots, journal)
		parts := strings.Split(rel, "/")
		if len(parts) == 3 && parts[0] == "runs" && parts[2] == "journal.ndjson" {
			journalOps[parts[1]] = true
		}
	}
	seenRecordHashes := map[contracts.SHA256Hex]bool{}
	seenJournalRefs := map[string]bool{}
	for _, record := range records {
		if seenRecordHashes[record.RecordHash] {
			return "duplicate_ledger_record_hash", relativeStateRef(roots, roots.LedgerPath())
		}
		seenRecordHashes[record.RecordHash] = true
		if !journalOps[string(record.OperationID)] {
			return "unmatched_ledger_record", relativeStateRef(roots, roots.LedgerPath())
		}
		key := record.JournalRef.OperationID + "\x00" + record.JournalRef.Path + "\x00" + string(record.JournalRef.SHA256)
		if seenJournalRefs[key] {
			return "duplicate_ledger_journal_ref", relativeStateRef(roots, roots.LedgerPath())
		}
		seenJournalRefs[key] = true
	}
	return "", ""
}

func validateClosedRunLayout(ctx context.Context, adapter filesystem.Adapter, roots Roots, records []contracts.OwnershipRecord, journals []contracts.AbsolutePath) (string, string) {
	runs := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), "runs"))
	entries, err := adapter.ListNoFollow(ctx, runs)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return "", ""
		}
		return "run_layout_read_failed", "runs"
	}
	allowed := map[string]bool{}
	for _, journal := range journals {
		allowed[relativeStateRef(roots, journal)] = true
	}
	for _, record := range records {
		op := string(record.OperationID)
		allowed[filepath.ToSlash(filepath.Join("runs", op, "journal.ndjson"))] = true
		allowed[record.PlanRef.Path] = true
		allowed[record.InventoryRef.Path] = true
		if record.VerificationRef != nil {
			allowed[record.VerificationRef.Path] = true
		}
		allowed[filepath.ToSlash(filepath.Join("runs", op, "receipt.json"))] = true
		allowed[filepath.ToSlash(filepath.Join("runs", op, "receipt.json.draft"))] = true
	}
	for _, entry := range entries {
		if entry.Kind != "directory" || contracts.ValidateOperationID(contracts.OperationID(entry.Name)) != nil {
			return "unknown_run_evidence", "runs"
		}
		runEntries, err := adapter.ListNoFollow(ctx, entry.Path)
		if err != nil {
			return "run_layout_read_failed", relativeStateRef(roots, entry.Path)
		}
		if len(runEntries) == 0 {
			return "empty_run_evidence", relativeStateRef(roots, entry.Path)
		}
		for _, runEntry := range runEntries {
			rel := relativeStateRef(roots, runEntry.Path)
			switch runEntry.Kind {
			case "file":
				if !allowed[rel] {
					return "unreferenced_run_artifact", rel
				}
			case "directory":
				if runEntry.Name != "verification" {
					return "unknown_run_evidence", rel
				}
				if code, ref := validateVerificationLayout(ctx, adapter, roots, runEntry.Path, allowed); code != "" {
					return code, ref
				}
			default:
				return "unknown_run_evidence", rel
			}
		}
	}
	return "", ""
}

func validateClosedStateLayout(ctx context.Context, adapter filesystem.Adapter, roots Roots, records []contracts.OwnershipRecord) (string, string) {
	entries, err := adapter.ListNoFollow(ctx, roots.StateRoot)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return "", ""
		}
		return "state_layout_read_failed", "."
	}
	for _, entry := range entries {
		if entry.Kind != "directory" {
			return "unknown_state_evidence", relativeStateRef(roots, entry.Path)
		}
		switch entry.Name {
		case "runs":
		case "backups":
			if code, ref := validateBackupTreeLayout(ctx, adapter, roots, entry.Path, records); code != "" {
				return code, ref
			}
		case "ownership":
			if code, ref := validateOwnershipLayout(ctx, adapter, roots, entry.Path); code != "" {
				return code, ref
			}
		default:
			return "unknown_state_evidence", relativeStateRef(roots, entry.Path)
		}
	}
	return "", ""
}

func validateOwnershipLayout(ctx context.Context, adapter filesystem.Adapter, roots Roots, dir contracts.AbsolutePath) (string, string) {
	entries, err := adapter.ListNoFollow(ctx, dir)
	if err != nil {
		return "state_layout_read_failed", relativeStateRef(roots, dir)
	}
	for _, entry := range entries {
		if entry.Kind != "file" || entry.Name != "installations.ndjson" {
			return "unknown_ownership_evidence", relativeStateRef(roots, entry.Path)
		}
	}
	return "", ""
}

func validateBackupTreeLayout(ctx context.Context, adapter filesystem.Adapter, roots Roots, dir contracts.AbsolutePath, records []contracts.OwnershipRecord) (string, string) {
	allowedBackupSets := map[string]bool{}
	allowedFiles := map[string]bool{}
	for _, record := range records {
		if record.BackupSetRef != nil {
			allowedBackupSets[record.BackupSetRef.BackupSetID] = true
			allowedFiles[filepath.ToSlash(filepath.Join("backups", record.BackupSetRef.BackupSetID, "manifest.json"))] = true
		}
		for _, deployment := range record.Deployments {
			if deployment.BackupEntryRef != nil && strings.HasPrefix(deployment.BackupEntryRef.Path, "backups/") {
				allowedFiles[deployment.BackupEntryRef.Path] = true
			}
		}
	}
	sets, err := adapter.ListNoFollow(ctx, dir)
	if err != nil {
		return "state_layout_read_failed", relativeStateRef(roots, dir)
	}
	for _, set := range sets {
		if set.Kind != "directory" || contracts.ValidateBackupSetID(set.Name) != nil || !allowedBackupSets[set.Name] {
			return "unreferenced_backup_evidence", relativeStateRef(roots, set.Path)
		}
		children, err := adapter.ListNoFollow(ctx, set.Path)
		if err != nil {
			return "state_layout_read_failed", relativeStateRef(roots, set.Path)
		}
		for _, child := range children {
			rel := relativeStateRef(roots, child.Path)
			if child.Kind == "file" {
				if !allowedFiles[rel] {
					return "unreferenced_backup_evidence", rel
				}
				continue
			}
			if child.Kind != "directory" || contracts.ValidateDeploymentID(child.Name) != nil {
				return "unknown_backup_evidence", rel
			}
			if code, ref := validateReferencedBackupDeploymentLayout(ctx, adapter, roots, child.Path, allowedFiles); code != "" {
				return code, ref
			}
		}
	}
	return "", ""
}

func validateReferencedBackupDeploymentLayout(ctx context.Context, adapter filesystem.Adapter, roots Roots, dir contracts.AbsolutePath, allowedFiles map[string]bool) (string, string) {
	entries, err := adapter.ListNoFollow(ctx, dir)
	if err != nil {
		return "state_layout_read_failed", relativeStateRef(roots, dir)
	}
	for _, entry := range entries {
		rel := relativeStateRef(roots, entry.Path)
		if entry.Kind == "file" {
			if !allowedFiles[rel] {
				return "unreferenced_backup_evidence", rel
			}
			continue
		}
		if entry.Kind == "directory" && entry.Name == "payload" {
			continue
		}
		return "unknown_backup_evidence", rel
	}
	return "", ""
}

func validateVerificationLayout(ctx context.Context, adapter filesystem.Adapter, roots Roots, dir contracts.AbsolutePath, allowed map[string]bool) (string, string) {
	entries, err := adapter.ListNoFollow(ctx, dir)
	if err != nil {
		return "run_layout_read_failed", relativeStateRef(roots, dir)
	}
	for _, entry := range entries {
		rel := relativeStateRef(roots, entry.Path)
		if entry.Kind != "file" || !allowed[rel] {
			return "unreferenced_run_artifact", rel
		}
	}
	return "", ""
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
	if finalReceiptPath != "receipt.json" {
		return "terminal_receipt_path_mismatch"
	}
	runDir := filepath.Dir(string(journalPath))
	receiptPath := contracts.AbsolutePath(filepath.Join(runDir, filepath.FromSlash(finalReceiptPath)))
	receiptBytes, err := adapter.ReadFileNoFollow(ctx, receiptPath)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return "receipt_publish_pending"
		}
		return "receipt_read_failed"
	}
	if contracts.SHA256(receiptBytes) != last.ReceiptSHA256 {
		return "terminal_receipt_digest_mismatch"
	}
	draftPath := contracts.AbsolutePath(filepath.Join(runDir, "receipt.json.draft"))
	if draftBytes, err := adapter.ReadFileNoFollow(ctx, draftPath); err == nil {
		if !bytes.Equal(draftBytes, receiptBytes) || contracts.SHA256(draftBytes) != last.ReceiptSHA256 {
			return "receipt_draft_final_mismatch"
		}
	} else if !errors.Is(err, fs.ErrNotExist) {
		return "receipt_draft_read_failed"
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
	journalBytes, err := adapter.ReadFileNoFollow(ctx, journalPath)
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
	record := findLedgerRecordForReceipt(records, op, receipt.LedgerRecordHash)
	if record == nil {
		return "ledger_record_hash_mismatch"
	}
	s := &store{fs: adapter}
	if err := validateReadyCommitEvidence(ctx, s, roots, op, receipt.ReadyJournalRef, *record); err != nil {
		return "ready_commit_evidence_mismatch"
	}
	if !artifactRefsEqualPtr(&record.PlanRef, receipt.PlanRef) || !artifactRefsEqualPtr(&record.InventoryRef, receipt.InventoryRef) || !backupSetRefsEqual(record.BackupSetRef, receipt.BackupSetRef) || !artifactRefsEqualPtr(record.VerificationRef, receipt.VerificationRef) {
		return "receipt_ledger_ref_mismatch"
	}
	if err := validateReceiptMatchesLedgerAggregate(receipt, *record); err != nil {
		return "receipt_ledger_aggregate_mismatch"
	}
	return ""
}

func findLedgerRecordForReceipt(records []contracts.OwnershipRecord, op contracts.OperationID, hash contracts.SHA256Hex) *contracts.OwnershipRecord {
	for i := range records {
		if records[i].OperationID == string(op) && records[i].RecordHash == hash {
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
	data, err := adapter.ReadFileNoFollow(ctx, path)
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
