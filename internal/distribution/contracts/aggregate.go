package contracts

import "fmt"

const (
	v1DeploymentCount     = 10
	v1RuntimeBindingCount = 15
)

func validateDeploymentIDArray(ids []string) error {
	if len(ids) != v1DeploymentCount {
		return fmt.Errorf("aggregate deployment count = %d, want %d", len(ids), v1DeploymentCount)
	}
	seen := map[string]bool{}
	for i, id := range ids {
		if !sha256Pattern.MatchString(id) {
			return fmt.Errorf("aggregate deployment_ids[%d] must be lower-case hex SHA-256", i)
		}
		if seen[id] {
			return fmt.Errorf("duplicate deployment_id")
		}
		seen[id] = true
	}
	return nil
}

func validateAggregateBindingSummaries(deployments []OwnershipDeploymentRecord) error {
	seen := map[string]bool{}
	count := 0
	for _, deployment := range deployments {
		if len(deployment.RuntimeBindingSummaries) == 0 {
			return fmt.Errorf("deployment %s has no runtime binding summaries", deployment.DeploymentID)
		}
		for _, binding := range deployment.RuntimeBindingSummaries {
			key := deployment.DeploymentID + "\x00" + binding.Runtime + "\x00" + binding.BindingIdentity
			if seen[key] {
				return fmt.Errorf("duplicate aggregate runtime binding")
			}
			seen[key] = true
			count++
		}
	}
	if count != v1RuntimeBindingCount {
		return fmt.Errorf("aggregate runtime binding count = %d, want %d", count, v1RuntimeBindingCount)
	}
	return nil
}

func validateReceiptAggregateBindingSummaries(results []OperationDeploymentResult) error {
	seen := map[string]bool{}
	count := 0
	for _, result := range results {
		if len(result.RuntimeBindingSummaries) == 0 {
			return fmt.Errorf("deployment result %s has no runtime binding summaries", result.DeploymentID)
		}
		for _, binding := range result.RuntimeBindingSummaries {
			key := result.DeploymentID + "\x00" + binding.Runtime + "\x00" + binding.BindingIdentity
			if seen[key] {
				return fmt.Errorf("duplicate aggregate runtime binding")
			}
			seen[key] = true
			count++
		}
	}
	if count != v1RuntimeBindingCount {
		return fmt.Errorf("receipt runtime binding count = %d, want %d", count, v1RuntimeBindingCount)
	}
	return nil
}
