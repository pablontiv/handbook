package contracts

import "fmt"

type PlanIntent string

const (
	IntentInstall   PlanIntent = "install"
	IntentUninstall PlanIntent = "uninstall"
	IntentRestore   PlanIntent = "restore"
	IntentVerify    PlanIntent = "verify"
)

type SelectorKind string

const (
	SelectorInstallation SelectorKind = "installation"
	SelectorBackupSet    SelectorKind = "backup_set"
	SelectorReceipt      SelectorKind = "receipt"
)

type PlanEnvelope struct {
	Schema         SchemaID    `json:"schema"`
	ApprovalDigest SHA256Hex   `json:"approval_digest"`
	Payload        PlanPayload `json:"payload"`
}

type PlanPayload struct {
	Inventory                Inventory                 `json:"inventory"`
	InventoryDigest          SHA256Hex                 `json:"inventory_digest"`
	Intent                   PlanIntent                `json:"intent"`
	Selector                 *Selector                 `json:"selector"`
	Deployments              []Deployment              `json:"deployments"`
	Blockers                 []Blocker                 `json:"blockers"`
	Preconditions            []Precondition            `json:"preconditions"`
	BackupRequirement        BackupRequirement         `json:"backup_requirement"`
	VerificationRequirements []VerificationRequirement `json:"verification_requirements"`
	RollbackStrategy         string                    `json:"rollback_strategy"`
	LineageTransition        LineageTransition         `json:"lineage_transition"`
}

type Selector struct {
	Kind           SelectorKind `json:"kind"`
	InstallationID string       `json:"installation_id,omitempty"`
	BackupSetID    string       `json:"backup_set_id,omitempty"`
	ReceiptID      string       `json:"receipt_id,omitempty"`
}

type Precondition struct {
	DeploymentID string `json:"deployment_id"`
	Code         string `json:"code"`
	Expected     string `json:"expected"`
}

type BackupRequirement struct {
	Required bool   `json:"required"`
	Reason   string `json:"reason"`
}

type VerificationRequirement struct {
	DeploymentID string `json:"deployment_id"`
	Runtime      string `json:"runtime"`
	Required     bool   `json:"required"`
}

type LineageTransition struct {
	From string `json:"from"`
	To   string `json:"to"`
}

func ValidateIntentSelector(intent PlanIntent, selector *Selector) error {
	if intent == IntentInstall {
		if selector != nil {
			return fmt.Errorf("install intent does not accept a selector")
		}
		return nil
	}
	if selector == nil {
		return fmt.Errorf("%s intent requires a selector", intent)
	}
	count := 0
	if selector.InstallationID != "" {
		count++
	}
	if selector.BackupSetID != "" {
		count++
	}
	if selector.ReceiptID != "" {
		count++
	}
	if count != 1 {
		return fmt.Errorf("selector must set exactly one selector value")
	}
	switch intent {
	case IntentUninstall:
		if selector.Kind != SelectorInstallation || selector.InstallationID == "" {
			return fmt.Errorf("uninstall requires exactly one installation_id selector")
		}
	case IntentRestore:
		if selector.Kind != SelectorBackupSet || selector.BackupSetID == "" {
			return fmt.Errorf("restore requires exactly one backup_set_id selector")
		}
	case IntentVerify:
		switch selector.Kind {
		case SelectorReceipt:
			if selector.ReceiptID == "" {
				return fmt.Errorf("verify receipt selector requires receipt_id")
			}
		case SelectorInstallation:
			if selector.InstallationID == "" {
				return fmt.Errorf("verify installation selector requires installation_id")
			}
		case SelectorBackupSet:
			if selector.BackupSetID == "" {
				return fmt.Errorf("verify backup selector requires backup_set_id")
			}
		default:
			return fmt.Errorf("verify selector kind %q is unsupported", selector.Kind)
		}
	default:
		return fmt.Errorf("intent %q is unsupported", intent)
	}
	return nil
}
