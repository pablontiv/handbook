package inventory

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io/fs"
	"path/filepath"
	"sort"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

type stateSnapshot struct {
	Ownership []contracts.OwnershipSnapshot
	Backups   []contracts.BackupSetSnapshot
}

func snapshotState(ctx context.Context, adapter filesystem.Adapter, stateRoot, lockRoot contracts.AbsolutePath) (stateSnapshot, error) {
	lock, err := adapter.LockShared(ctx, ledgerLockPath(lockRoot, stateRoot), "inventory selected ledger snapshot")
	if err != nil {
		return stateSnapshot{}, err
	}
	defer lock.Close()

	data, err := adapter.ReadFile(ctx, ledgerPath(stateRoot))
	if errors.Is(err, fs.ErrNotExist) {
		return stateSnapshot{Ownership: []contracts.OwnershipSnapshot{}, Backups: []contracts.BackupSetSnapshot{}}, nil
	}
	if err != nil {
		return stateSnapshot{}, err
	}
	if len(data) == 0 {
		return stateSnapshot{Ownership: []contracts.OwnershipSnapshot{}, Backups: []contracts.BackupSetSnapshot{}}, nil
	}
	if !bytes.HasSuffix(data, []byte("\n")) {
		return stateSnapshot{}, fmt.Errorf("ownership ledger has a partial tail")
	}
	lines := bytes.Split(bytes.TrimSuffix(data, []byte("\n")), []byte("\n"))
	ownership := make([]contracts.OwnershipSnapshot, 0, len(lines))
	backups := []contracts.BackupSetSnapshot{}
	for _, line := range lines {
		if len(line) == 0 {
			continue
		}
		var record contracts.OwnershipRecord
		if err := contracts.StrictParseCanonical(line, &record); err != nil {
			return stateSnapshot{}, err
		}
		if record.Schema != contracts.SchemaOwnership {
			return stateSnapshot{}, fmt.Errorf("ownership record schema = %q", record.Schema)
		}
		ownership = append(ownership, contracts.OwnershipSnapshot{InstallationID: record.InstallationID, AggregateEvent: record.AggregateEvent})
		if record.BackupSetRef != nil {
			backups = append(backups, contracts.BackupSetSnapshot{BackupSetID: record.BackupSetRef.BackupSetID, InstallationID: record.InstallationID})
		}
	}
	sort.Slice(ownership, func(i, j int) bool {
		if ownership[i].InstallationID != ownership[j].InstallationID {
			return ownership[i].InstallationID < ownership[j].InstallationID
		}
		return ownership[i].AggregateEvent < ownership[j].AggregateEvent
	})
	sort.Slice(backups, func(i, j int) bool {
		if backups[i].BackupSetID != backups[j].BackupSetID {
			return backups[i].BackupSetID < backups[j].BackupSetID
		}
		return backups[i].InstallationID < backups[j].InstallationID
	})
	return stateSnapshot{Ownership: ownership, Backups: backups}, nil
}

func ledgerPath(stateRoot contracts.AbsolutePath) contracts.AbsolutePath {
	return contracts.AbsolutePath(filepath.Join(string(stateRoot), "ownership", "installations.ndjson"))
}

func ledgerLockPath(lockRoot, stateRoot contracts.AbsolutePath) contracts.AbsolutePath {
	return contracts.AbsolutePath(filepath.Join(string(lockRoot), "ledger-"+string(contracts.SHA256([]byte(filepath.Clean(string(stateRoot)))))+".lock"))
}
