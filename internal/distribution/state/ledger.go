package state

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io/fs"
	"path/filepath"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

type Ledger interface {
	Append(context.Context, contracts.OwnershipRecord) (contracts.SHA256Hex, error)
	Records() []contracts.OwnershipRecord
}

type ledger struct {
	fs      filesystem.Adapter
	roots   Roots
	records []contracts.OwnershipRecord
}

func (s *store) OpenLedger(ctx context.Context, roots Roots) (Ledger, error) {
	if err := validateRoots(ctx, s.fs, roots); err != nil {
		return nil, err
	}
	records, err := readLedger(ctx, s.fs, roots)
	if err != nil {
		return nil, err
	}
	return &ledger{fs: s.fs, roots: roots, records: records}, nil
}

func (l *ledger) Append(ctx context.Context, record contracts.OwnershipRecord) (contracts.SHA256Hex, error) {
	records, err := readLedger(ctx, l.fs, l.roots)
	if err != nil {
		return "", err
	}
	record.Schema = contracts.SchemaOwnership
	record.Sequence = int64(len(records) + 1)
	if len(records) == 0 {
		record.PreviousHash = nil
	} else {
		prev := records[len(records)-1].RecordHash
		record.PreviousHash = &prev
	}
	record.RecordHash = ""
	if err := contracts.ValidateOwnershipRecord(record); err != nil {
		return "", err
	}
	if err := validateOwnershipRecordContext(ctx, l.fs, l.roots, record); err != nil {
		return "", err
	}
	if err := l.validateCurrentJournalPrefix(ctx, record.JournalRef); err != nil {
		return "", err
	}
	hash, err := computeLedgerRecordHash(record)
	if err != nil {
		return "", err
	}
	record.RecordHash = hash
	line, err := contracts.CanonicalBytes(record)
	if err != nil {
		return "", err
	}
	appendBytes := append(append([]byte(nil), line...), '\n')
	if err := l.fs.EnsureDirSync(ctx, contracts.AbsolutePath(filepath.Dir(string(l.roots.LedgerPath())))); err != nil {
		return "", err
	}
	if err := l.fs.AppendFileSync(ctx, l.roots.LedgerPath(), appendBytes); err != nil {
		return "", err
	}
	if err := l.fs.SyncDirectory(ctx, contracts.AbsolutePath(filepath.Dir(string(l.roots.LedgerPath())))); err != nil {
		return "", err
	}
	l.records = append(records, record)
	return hash, nil
}

func (l *ledger) Records() []contracts.OwnershipRecord {
	return append([]contracts.OwnershipRecord(nil), l.records...)
}

func (l *ledger) validateCurrentJournalPrefix(ctx context.Context, ref contracts.JournalRef) error {
	journalPath := contracts.AbsolutePath(filepath.Join(string(l.roots.StateRoot), filepath.FromSlash(ref.Path)))
	data, err := l.fs.ReadFileNoFollow(ctx, journalPath)
	if err != nil {
		return fmt.Errorf("journal_ref is not durable: %w", err)
	}
	if contracts.SHA256(data) != ref.SHA256 {
		return fmt.Errorf("journal_ref does not match current durable journal prefix before ledger append")
	}
	entries, err := readJournalEntries(ctx, l.fs, journalPath)
	if err != nil {
		return fmt.Errorf("journal_ref prefix invalid: %w", err)
	}
	if len(entries) == 0 {
		return fmt.Errorf("journal_ref cannot bind an empty journal")
	}
	last := entries[len(entries)-1].Boundary
	if last == "ready_to_commit" || isTerminalBoundary(last) {
		return fmt.Errorf("ledger journal_ref must bind a pre-ready nonterminal prefix")
	}
	return nil
}

func readLedger(ctx context.Context, adapter filesystem.Adapter, roots Roots) ([]contracts.OwnershipRecord, error) {
	data, err := adapter.ReadFileNoFollow(ctx, roots.LedgerPath())
	if errors.Is(err, fs.ErrNotExist) {
		return []contracts.OwnershipRecord{}, nil
	}
	if err != nil {
		return nil, err
	}
	if len(data) == 0 {
		return []contracts.OwnershipRecord{}, nil
	}
	if !bytes.HasSuffix(data, []byte("\n")) {
		return nil, fmt.Errorf("ownership ledger has a partial tail")
	}
	lines := bytes.Split(bytes.TrimSuffix(data, []byte("\n")), []byte("\n"))
	records := make([]contracts.OwnershipRecord, 0, len(lines))
	var previous *contracts.SHA256Hex
	for i, line := range lines {
		if len(line) == 0 {
			return nil, fmt.Errorf("ownership ledger contains an empty record")
		}
		var raw map[string]any
		if err := contracts.StrictParseCanonical(line, &raw); err != nil {
			return nil, err
		}
		if raw["schema"] != string(contracts.SchemaOwnership) {
			return nil, fmt.Errorf("ownership record schema = %v", raw["schema"])
		}
		if err := contracts.ValidateSchema(contracts.SchemaOwnership, line); err != nil {
			return nil, err
		}
		var record contracts.OwnershipRecord
		if err := contracts.StrictParseCanonical(line, &record); err != nil {
			return nil, err
		}
		if err := contracts.ValidateOwnershipRecord(record); err != nil {
			return nil, err
		}
		if err := validateOwnershipRecordContext(ctx, adapter, roots, record); err != nil {
			return nil, err
		}
		if err := validateDurableJournalRef(ctx, adapter, roots, record.JournalRef); err != nil {
			return nil, err
		}
		if record.RecordHash == "" {
			return nil, fmt.Errorf("ownership record %d is missing record_hash", i+1)
		}
		if record.Sequence != int64(i+1) {
			return nil, fmt.Errorf("ownership record sequence = %d, want %d", record.Sequence, i+1)
		}
		if previous == nil {
			if record.PreviousHash != nil {
				return nil, fmt.Errorf("first ownership record has previous_hash")
			}
		} else if record.PreviousHash == nil || *record.PreviousHash != *previous {
			return nil, fmt.Errorf("ownership record previous_hash mismatch")
		}
		computed, err := computeLedgerRecordHash(record)
		if err != nil {
			return nil, err
		}
		if computed != record.RecordHash {
			return nil, fmt.Errorf("ownership record hash mismatch")
		}
		current := record.RecordHash
		previous = &current
		records = append(records, record)
	}
	if err := validateLedgerLineage(records); err != nil {
		return nil, err
	}
	return records, nil
}

func validateDurableJournalRef(ctx context.Context, adapter filesystem.Adapter, roots Roots, ref contracts.JournalRef) error {
	journalPath := contracts.AbsolutePath(filepath.Join(string(roots.StateRoot), filepath.FromSlash(ref.Path)))
	if !isUnderRoot(string(roots.StateRoot), string(journalPath)) {
		return fmt.Errorf("journal_ref escapes state root")
	}
	data, err := adapter.ReadFileNoFollow(ctx, journalPath)
	if err != nil {
		return fmt.Errorf("journal_ref is not durable: %w", err)
	}
	prefixes, err := journalPrefixes(data)
	if err != nil {
		return err
	}
	for _, prefix := range prefixes {
		if contracts.SHA256(prefix.bytes) == ref.SHA256 {
			return nil
		}
	}
	return fmt.Errorf("journal_ref does not match any exact durable operation journal prefix")
}

func validateLedgerLineage(records []contracts.OwnershipRecord) error {
	stateByInstallation := map[contracts.InstallationID]string{}
	recordByHash := map[contracts.SHA256Hex]contracts.OwnershipRecord{}
	opFirst := map[contracts.OperationID]contracts.OwnershipRecord{}
	opCount := map[contracts.OperationID]int{}
	for _, record := range records {
		op := record.OperationID
		opCount[op]++
		if opCount[op] > 2 {
			return fmt.Errorf("operation_id %s appears more than twice", op)
		}
		first, seenOp := opFirst[op]
		if !seenOp {
			opFirst[op] = record
		} else if !isCompensatingEvent(record.AggregateEvent) || record.CompensatingPriorState == nil || record.CompensatingPriorState.LedgerRecordHash != first.RecordHash {
			return fmt.Errorf("operation_id %s repeated without exact compatible compensation pointer", op)
		}
		if record.CompensatingPriorState != nil {
			prior, ok := recordByHash[record.CompensatingPriorState.LedgerRecordHash]
			if !ok {
				return fmt.Errorf("compensating prior state does not resolve to earlier ledger record")
			}
			if !equalStringSlices(prior.DeploymentIDs, record.CompensatingPriorState.DeploymentIDs) || prior.AggregateEvent != record.CompensatingPriorState.AggregateEvent {
				return fmt.Errorf("compensating prior state does not match pointed ledger record")
			}
		}
		current := stateByInstallation[record.InstallationID]
		if err := validateLineageTransition(current, record.AggregateEvent); err != nil {
			return err
		}
		stateByInstallation[record.InstallationID] = record.AggregateEvent
		recordByHash[record.RecordHash] = record
	}
	return nil
}

func validateLineageTransition(current, next string) error {
	if current == "" {
		if next == "applied_unverified" || isCompensatingEvent(next) || next == contracts.RecoveryRequired {
			return nil
		}
		return fmt.Errorf("first ownership event %q is illegal", next)
	}
	switch next {
	case "installed_verified":
		if current == "applied_unverified" {
			return nil
		}
	case "removed_unverified":
		if current == "applied_unverified" || current == "installed_verified" {
			return nil
		}
	case "removed_verified":
		if current == "removed_unverified" {
			return nil
		}
	case "restored_unverified":
		if current == "removed_verified" {
			return nil
		}
	case "restored_verified":
		if current == "restored_unverified" {
			return nil
		}
	case "install_rolled_back", "uninstall_rolled_back", "restore_rolled_back", contracts.RecoveryRequired:
		return nil
	}
	return fmt.Errorf("illegal ownership lineage transition %q -> %q", current, next)
}

func isCompensatingEvent(event string) bool {
	return event == "install_rolled_back" || event == "uninstall_rolled_back" || event == "restore_rolled_back" || event == contracts.RecoveryRequired
}

func computeLedgerRecordHash(record contracts.OwnershipRecord) (contracts.SHA256Hex, error) {
	preimage, err := canonicalLedgerRecordPreimage(record)
	if err != nil {
		return "", err
	}
	return contracts.SHA256(preimage), nil
}

func canonicalLedgerRecordPreimage(record contracts.OwnershipRecord) ([]byte, error) {
	record.RecordHash = ""
	data, err := contracts.CanonicalBytes(record)
	if err != nil {
		return nil, err
	}
	var object map[string]any
	if err := contracts.StrictParseCanonical(data, &object); err != nil {
		return nil, err
	}
	delete(object, "record_hash")
	return contracts.CanonicalBytes(object)
}
