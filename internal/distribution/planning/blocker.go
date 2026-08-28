package planning

import (
	"fmt"
	"sort"

	"waywarden/internal/distribution/contracts"
)

const (
	BlockerSlotSourceConflict   = contracts.BlockerSlotSourceConflict
	BlockerSlotStrategyConflict = contracts.BlockerSlotStrategyConflict
	BlockerSlotCaseAmbiguity    = contracts.BlockerSlotCaseAmbiguity
)

func newBlocker(code, message string) contracts.Blocker {
	return contracts.Blocker{Code: code, Severity: contracts.BlockerSeveritySafePrecondition, Message: message}
}

func slotSourceConflict(slot, existing, candidate string) contracts.Blocker {
	return newBlocker(BlockerSlotSourceConflict, fmt.Sprintf("governed slot %s maps to multiple canonical source identities: %s and %s", slot, existing, candidate))
}

func slotStrategyConflict(slot, existing, candidate string) contracts.Blocker {
	return newBlocker(BlockerSlotStrategyConflict, fmt.Sprintf("governed slot %s maps to incompatible link strategies: %s and %s", slot, existing, candidate))
}

func slotCaseAmbiguity(first, second, comparisonKey string) contracts.Blocker {
	slots := []string{first, second}
	sort.Strings(slots)
	return newBlocker(BlockerSlotCaseAmbiguity, fmt.Sprintf("governed slots are ambiguous under Windows case-insensitive comparison key %s: %s and %s", comparisonKey, slots[0], slots[1]))
}

func slotUnsupportedCaseAmbiguity(slot string) contracts.Blocker {
	return newBlocker(BlockerSlotCaseAmbiguity, fmt.Sprintf("governed slot %s contains unsupported Unicode for Windows case comparison", slot))
}
