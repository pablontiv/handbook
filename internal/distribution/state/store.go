package state

import (
	"context"
	"io"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

type Store interface {
	ResolveRoots(context.Context, contracts.AbsolutePath) (Roots, error)
	AcquireMutationLocks(context.Context, Roots, []contracts.GovernedSlotIdentity) (LockSet, error)
	AcquireVerificationLocks(context.Context, Roots) (LockSet, error)
	AcquireInventoryLedgerSnapshot(context.Context, Roots) (filesystem.LockHandle, error)
	GenerateInstallIDs(io.Reader) (contracts.OperationID, contracts.InstallationID, contracts.BackupSetID, error)
	GenerateOperationID(io.Reader) (contracts.OperationID, error)
	OpenLedger(context.Context, Roots) (Ledger, error)
	OpenJournal(context.Context, Roots, contracts.OperationID, contracts.CommandName) (Journal, error)
	PublishRunArtifact(context.Context, Roots, contracts.OperationID, string, []byte) (contracts.ArtifactRef, error)
	PublishReceipt(context.Context, Roots, contracts.OperationID, contracts.Receipt) (contracts.ArtifactRef, error)
	ClassifyRecovery(context.Context, Roots) (contracts.RecoveryStatus, error)
}

type store struct {
	fs filesystem.Adapter
}

func NewStore(fs filesystem.Adapter) Store {
	return &store{fs: fs}
}
