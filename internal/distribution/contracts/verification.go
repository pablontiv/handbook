package contracts

import "fmt"

type Verification struct {
	Schema         SchemaID                `json:"schema"`
	VerificationID string                  `json:"verification_id"`
	OperationID    OperationID             `json:"operation_id"`
	Selector       Selector                `json:"selector"`
	Assertions     []VerificationAssertion `json:"assertions"`
	Status         string                  `json:"status"`
	OperatorRef    *ArtifactRef            `json:"operator_ref"`
}

type VerificationAssertion struct {
	DeploymentID string `json:"deployment_id"`
	Code         string `json:"code"`
	Status       string `json:"status"`
	Evidence     string `json:"evidence"`
}

func ValidateVerification(verification Verification) error {
	if verification.Schema != SchemaVerification {
		return fmt.Errorf("invalid verification schema")
	}
	if err := ValidateVerificationID(verification.VerificationID); err != nil {
		return err
	}
	if err := ValidateOperationID(verification.OperationID); err != nil {
		return err
	}
	if err := ValidateIntentSelector(IntentVerify, &verification.Selector); err != nil {
		return fmt.Errorf("selector: %w", err)
	}
	switch verification.Status {
	case "verified", "failed", "operator_required":
	default:
		return fmt.Errorf("verification status %q is unsupported", verification.Status)
	}
	seen := map[string]bool{}
	for _, assertion := range verification.Assertions {
		if err := ValidateDeploymentID(assertion.DeploymentID); err != nil {
			return err
		}
		if assertion.Code == "" || assertion.Evidence == "" {
			return fmt.Errorf("verification assertion requires code and evidence")
		}
		switch assertion.Status {
		case "verified", "failed", "operator_required", "human_attested":
		default:
			return fmt.Errorf("verification assertion status %q is unsupported", assertion.Status)
		}
		key := assertion.DeploymentID + "\x00" + assertion.Code
		if seen[key] {
			return fmt.Errorf("duplicate verification assertion")
		}
		seen[key] = true
	}
	if verification.OperatorRef != nil {
		if err := ValidateArtifactRef(*verification.OperatorRef); err != nil {
			return fmt.Errorf("operator_ref: %w", err)
		}
	}
	return nil
}
