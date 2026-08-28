package contracts

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
)

func SHA256(data []byte) SHA256Hex {
	sum := sha256.Sum256(data)
	return SHA256Hex(hex.EncodeToString(sum[:]))
}

func PayloadDigest(payload PlanPayload) (SHA256Hex, error) {
	data, err := CanonicalBytes(payload)
	if err != nil {
		return "", err
	}
	return SHA256(data), nil
}

func ParseCanonicalInventory(data []byte) (Inventory, error) {
	var inventory Inventory
	if err := StrictParseCanonical(data, &inventory); err != nil {
		return Inventory{}, err
	}
	if inventory.Schema != SchemaInventory {
		return Inventory{}, fmt.Errorf("inventory schema = %q, want %q", inventory.Schema, SchemaInventory)
	}
	return inventory, nil
}

func ParseCanonicalPlanEnvelope(data []byte) (PlanEnvelope, error) {
	var envelope PlanEnvelope
	if err := StrictParseCanonical(data, &envelope); err != nil {
		return PlanEnvelope{}, err
	}
	if envelope.Schema != SchemaPlan {
		return PlanEnvelope{}, fmt.Errorf("plan schema = %q, want %q", envelope.Schema, SchemaPlan)
	}
	return envelope, nil
}

func VerifyPlanEnvelope(data []byte, approved SHA256Hex) (PlanEnvelope, error) {
	envelope, err := ParseCanonicalPlanEnvelope(data)
	if err != nil {
		return PlanEnvelope{}, err
	}
	inventoryBytes, err := CanonicalBytes(envelope.Payload.Inventory)
	if err != nil {
		return PlanEnvelope{}, err
	}
	if SHA256(inventoryBytes) != envelope.Payload.InventoryDigest {
		return PlanEnvelope{}, fmt.Errorf("embedded inventory digest mismatch")
	}
	payloadDigest, err := PayloadDigest(envelope.Payload)
	if err != nil {
		return PlanEnvelope{}, err
	}
	if payloadDigest != envelope.ApprovalDigest {
		return PlanEnvelope{}, fmt.Errorf("approval_digest does not match canonical payload digest")
	}
	if payloadDigest != approved {
		return PlanEnvelope{}, fmt.Errorf("approved digest does not match canonical payload digest")
	}
	canonicalEnvelope, err := CanonicalBytes(envelope)
	if err != nil {
		return PlanEnvelope{}, err
	}
	if string(canonicalEnvelope) != string(data) {
		return PlanEnvelope{}, fmt.Errorf("plan envelope is not canonical")
	}
	return envelope, nil
}
