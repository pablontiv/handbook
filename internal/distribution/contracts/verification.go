package contracts

type Verification struct {
	Schema         SchemaID                `json:"schema"`
	VerificationID string                  `json:"verification_id"`
	OperationID    string                  `json:"operation_id"`
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
