package contracts

import "fmt"

const (
	v1DeploymentCount     = 10
	v1RuntimeBindingCount = 15
)

var v1AggregateDeploymentIDs = []string{
	"9fd207a11f20bafd1e31ebdfc93990ef1cf34322d6755cc978fc1c2ef51fa51a",
	"033bc31c463554957d74f5542e94699bae46543c55fe0c03d9271692cbdb3ea0",
	"e2b60949eb1ebdbfb413779f38cf0f5d31d64161f4d007d2c7c95339707975dd",
	"3c224075ad1073aaea61a80fd94870d7f222c909a3675c9875f2832fc1430887",
	"3f39e318ae3a7ba0b7e9007a2d3b6d1e08db94d26dd9316caa97d722aad8d7a0",
	"95c128e372c7c7f9ba440d243e92c4967e94a0dd9cf1345dd9bb231d7b1c1e45",
	"a2df3d5ad3956e32f181d4174bc48b3b16307fdeec9d2a8e7bc1659d90cf903c",
	"30bac04c94e106656687c95ebbe92dc96d3f123a58de948b866f6ab682d120ec",
	"972555ce8622fe3f7956e3fb0e20a1e06b8b85a4260ac36c7d94e5f84c4bc160",
	"fc8ab2bfd2e120d0208e4c70df3e2c380e47d6740df5cf39c27d35cb5087a7d0",
}

var v1AggregateRuntimeBindings = []RuntimeBinding{
	{DeploymentID: "95c128e372c7c7f9ba440d243e92c4967e94a0dd9cf1345dd9bb231d7b1c1e45", Runtime: "claude", Root: ".claude/skills", Name: "adr", Target: "skills/adr"},
	{DeploymentID: "a2df3d5ad3956e32f181d4174bc48b3b16307fdeec9d2a8e7bc1659d90cf903c", Runtime: "claude", Root: ".claude/skills", Name: "decision-calibrator", Target: "skills/decision-calibrator"},
	{DeploymentID: "30bac04c94e106656687c95ebbe92dc96d3f123a58de948b866f6ab682d120ec", Runtime: "claude", Root: ".claude/skills", Name: "model-optimizer", Target: "skills/model-optimizer"},
	{DeploymentID: "972555ce8622fe3f7956e3fb0e20a1e06b8b85a4260ac36c7d94e5f84c4bc160", Runtime: "claude", Root: ".claude/skills", Name: "remove-gentle-context", Target: "skills/remove-gentle-context"},
	{DeploymentID: "fc8ab2bfd2e120d0208e4c70df3e2c380e47d6740df5cf39c27d35cb5087a7d0", Runtime: "claude", Root: ".claude/skills", Name: "systemic-issue-triage", Target: "skills/systemic-issue-triage"},
	{DeploymentID: "9fd207a11f20bafd1e31ebdfc93990ef1cf34322d6755cc978fc1c2ef51fa51a", Runtime: "opencode", Root: ".agents/skills", Name: "adr", Target: "skills/adr"},
	{DeploymentID: "033bc31c463554957d74f5542e94699bae46543c55fe0c03d9271692cbdb3ea0", Runtime: "opencode", Root: ".agents/skills", Name: "decision-calibrator", Target: "skills/decision-calibrator"},
	{DeploymentID: "e2b60949eb1ebdbfb413779f38cf0f5d31d64161f4d007d2c7c95339707975dd", Runtime: "opencode", Root: ".agents/skills", Name: "model-optimizer", Target: "skills/model-optimizer"},
	{DeploymentID: "3c224075ad1073aaea61a80fd94870d7f222c909a3675c9875f2832fc1430887", Runtime: "opencode", Root: ".agents/skills", Name: "remove-gentle-context", Target: "skills/remove-gentle-context"},
	{DeploymentID: "3f39e318ae3a7ba0b7e9007a2d3b6d1e08db94d26dd9316caa97d722aad8d7a0", Runtime: "opencode", Root: ".agents/skills", Name: "systemic-issue-triage", Target: "skills/systemic-issue-triage"},
	{DeploymentID: "9fd207a11f20bafd1e31ebdfc93990ef1cf34322d6755cc978fc1c2ef51fa51a", Runtime: "pi", Root: ".agents/skills", Name: "adr", Target: "skills/adr"},
	{DeploymentID: "033bc31c463554957d74f5542e94699bae46543c55fe0c03d9271692cbdb3ea0", Runtime: "pi", Root: ".agents/skills", Name: "decision-calibrator", Target: "skills/decision-calibrator"},
	{DeploymentID: "e2b60949eb1ebdbfb413779f38cf0f5d31d64161f4d007d2c7c95339707975dd", Runtime: "pi", Root: ".agents/skills", Name: "model-optimizer", Target: "skills/model-optimizer"},
	{DeploymentID: "3c224075ad1073aaea61a80fd94870d7f222c909a3675c9875f2832fc1430887", Runtime: "pi", Root: ".agents/skills", Name: "remove-gentle-context", Target: "skills/remove-gentle-context"},
	{DeploymentID: "3f39e318ae3a7ba0b7e9007a2d3b6d1e08db94d26dd9316caa97d722aad8d7a0", Runtime: "pi", Root: ".agents/skills", Name: "systemic-issue-triage", Target: "skills/systemic-issue-triage"},
}

// V1AggregateDeploymentIDs returns the exact ordered physical deployment IDs
// governed by the v1 bundled Waywarden manifest.
func V1AggregateDeploymentIDs() []string {
	return append([]string(nil), v1AggregateDeploymentIDs...)
}

// V1AggregateRuntimeBindings returns the exact ordered runtime bindings governed
// by the v1 bundled Waywarden manifest.
func V1AggregateRuntimeBindings() []RuntimeBinding {
	return append([]RuntimeBinding(nil), v1AggregateRuntimeBindings...)
}

func expectedV1BindingSummariesByDeployment() map[string][]RuntimeBinding {
	out := map[string][]RuntimeBinding{}
	for _, binding := range v1AggregateRuntimeBindings {
		out[binding.DeploymentID] = append(out[binding.DeploymentID], binding)
	}
	return out
}

func validateExactDeploymentIDArray(ids []string) error {
	if len(ids) != v1DeploymentCount {
		return fmt.Errorf("aggregate deployment count = %d, want %d", len(ids), v1DeploymentCount)
	}
	for i, want := range v1AggregateDeploymentIDs {
		if ids[i] != want {
			return fmt.Errorf("aggregate deployment_ids[%d] = %q, want %q", i, ids[i], want)
		}
	}
	return nil
}
