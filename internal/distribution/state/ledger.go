package state

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io/fs"

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
	hash, err := ComputeLedgerRecordHash(record)
	if err != nil {
		return "", err
	}
	record.RecordHash = hash
	line, err := contracts.CanonicalBytes(record)
	if err != nil {
		return "", err
	}
	if bytes.Contains(line, []byte("receipt_ref")) {
		return "", fmt.Errorf("ownership ledger records must not contain receipt_ref")
	}
	appendBytes := append(append([]byte(nil), line...), '\n')
	if err := l.fs.AppendFileSync(ctx, l.roots.LedgerPath(), appendBytes); err != nil {
		return "", err
	}
	l.records = append(records, record)
	return hash, nil
}

func (l *ledger) Records() []contracts.OwnershipRecord {
	return append([]contracts.OwnershipRecord(nil), l.records...)
}

func readLedger(ctx context.Context, adapter filesystem.Adapter, roots Roots) ([]contracts.OwnershipRecord, error) {
	data, err := adapter.ReadFile(ctx, roots.LedgerPath())
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
		if bytes.Contains(line, []byte("receipt_ref")) {
			return nil, fmt.Errorf("ownership ledger record contains forbidden receipt_ref")
		}
		var raw map[string]any
		if err := contracts.StrictParseCanonical(line, &raw); err != nil {
			return nil, err
		}
		if raw["schema"] != string(contracts.SchemaOwnership) {
			return nil, fmt.Errorf("ownership record schema = %v", raw["schema"])
		}
		var record contracts.OwnershipRecord
		if err := contracts.StrictParseCanonical(line, &record); err != nil {
			return nil, err
		}
		if err := contracts.ValidateOwnershipRecord(record); err != nil {
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
		computed, err := ComputeLedgerRecordHash(record)
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
	return records, nil
}

func ComputeLedgerRecordHash(record contracts.OwnershipRecord) (contracts.SHA256Hex, error) {
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
