package planning

import (
	"fmt"

	"waywarden/internal/distribution/contracts"
)

const (
	BlockerSlotSourceConflict   = "slot_source_identity_conflict"
	BlockerSlotStrategyConflict = "slot_strategy_conflict"
)

func newBlocker(code, message string) contracts.Blocker {
	return contracts.Blocker{Code: code, Severity: "safe_precondition", Message: message}
}

func slotSourceConflict(slot, existing, candidate string) contracts.Blocker {
	return newBlocker(BlockerSlotSourceConflict, fmt.Sprintf("governed slot %s maps to multiple canonical source identities: %s and %s", slot, existing, candidate))
}

func slotStrategyConflict(slot, existing, candidate string) contracts.Blocker {
	return newBlocker(BlockerSlotStrategyConflict, fmt.Sprintf("governed slot %s maps to incompatible link strategies: %s and %s", slot, existing, candidate))
}
