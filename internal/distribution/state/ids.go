package state

import (
	"crypto/rand"
	"encoding/hex"
	"io"

	"waywarden/internal/distribution/contracts"
)

const randomIDBytes = 32

func GenerateInstallIDs(reader io.Reader) (contracts.OperationID, contracts.InstallationID, contracts.BackupSetID, error) {
	op, err := GenerateOperationID(reader)
	if err != nil {
		return "", "", "", err
	}
	installation, err := generateOpaqueID(reader)
	if err != nil {
		return "", "", "", err
	}
	backup, err := generateOpaqueID(reader)
	if err != nil {
		return "", "", "", err
	}
	return op, contracts.InstallationID(installation), contracts.BackupSetID(backup), nil
}

func (s *store) GenerateInstallIDs(reader io.Reader) (contracts.OperationID, contracts.InstallationID, contracts.BackupSetID, error) {
	return GenerateInstallIDs(reader)
}

func GenerateOperationID(reader io.Reader) (contracts.OperationID, error) {
	id, err := generateOpaqueID(reader)
	return contracts.OperationID(id), err
}

func (s *store) GenerateOperationID(reader io.Reader) (contracts.OperationID, error) {
	return GenerateOperationID(reader)
}

func generateOpaqueID(reader io.Reader) (string, error) {
	if reader == nil {
		reader = rand.Reader
	}
	buf := make([]byte, randomIDBytes)
	if _, err := io.ReadFull(reader, buf); err != nil {
		return "", err
	}
	return hex.EncodeToString(buf), nil
}
