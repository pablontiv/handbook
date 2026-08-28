package planning

import (
	"fmt"
	"path/filepath"
	"sort"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

type DeploymentSet struct {
	Deployments     []contracts.Deployment
	RuntimeBindings []contracts.RuntimeBinding
	Blockers        []contracts.Blocker
}

func BuildDeployments(manifest contracts.Manifest, sourceRoot, home string) (DeploymentSet, error) {
	if !filepath.IsAbs(sourceRoot) {
		return DeploymentSet{}, fmt.Errorf("source root must be absolute")
	}
	if !filepath.IsAbs(home) {
		return DeploymentSet{}, fmt.Errorf("home must be absolute")
	}
	sourceRootIdentity, err := filesystem.CanonicalIdentity(sourceRoot)
	if err != nil {
		return DeploymentSet{}, err
	}
	skills := append([]contracts.ManifestSkill(nil), manifest.Skills...)
	runtimeRoots := append([]contracts.RuntimeRoot(nil), manifest.RuntimeRoots...)
	sort.Slice(skills, func(i, j int) bool { return skills[i].SkillID < skills[j].SkillID })
	sort.Slice(runtimeRoots, func(i, j int) bool {
		if runtimeRoots[i].Root != runtimeRoots[j].Root {
			return runtimeRoots[i].Root < runtimeRoots[j].Root
		}
		return runtimeRoots[i].Runtime < runtimeRoots[j].Runtime
	})

	bySlot := map[string]*contracts.Deployment{}
	var blockers []contracts.Blocker
	for _, skill := range skills {
		sourcePath := filepath.Join(sourceRootIdentity, filepath.FromSlash(skill.SourcePath))
		sourceIdentity, err := filesystem.ContainedCanonicalIdentity(sourceRootIdentity, sourcePath)
		if err != nil {
			return DeploymentSet{}, err
		}
		for _, runtimeRoot := range runtimeRoots {
			rootPath := filepath.Join(home, filepath.FromSlash(runtimeRoot.Root))
			governedPath := filepath.Join(rootPath, skill.SkillID)
			slotIdentity, err := filesystem.LexicalIdentity(governedPath)
			if err != nil {
				return DeploymentSet{}, err
			}
			deploymentID := deploymentID(slotIdentity, sourceIdentity)
			binding := contracts.RuntimeBinding{DeploymentID: deploymentID, Runtime: runtimeRoot.Runtime, Root: rootPath, Name: skill.SkillID, Target: filepath.Join(governedPath, "SKILL.md")}
			if existing := bySlot[slotIdentity]; existing != nil {
				if existing.SourceIdentity != sourceIdentity {
					blockers = append(blockers, slotSourceConflict(slotIdentity, existing.SourceIdentity, sourceIdentity))
					continue
				}
				if existing.LinkStrategy != runtimeRoot.LinkStrategy {
					blockers = append(blockers, slotStrategyConflict(slotIdentity, existing.LinkStrategy, runtimeRoot.LinkStrategy))
					continue
				}
				mergeBinding(existing, binding)
				continue
			}
			deployment := contracts.Deployment{
				DeploymentID:         deploymentID,
				SkillID:              skill.SkillID,
				SourcePath:           filepath.ToSlash(skill.SourcePath),
				SourceIdentity:       sourceIdentity,
				GovernedPath:         governedPath,
				GovernedSlotIdentity: slotIdentity,
				LinkStrategy:         runtimeRoot.LinkStrategy,
				RuntimeBindings:      []contracts.RuntimeBinding{binding},
			}
			bySlot[slotIdentity] = &deployment
		}
	}

	deployments := make([]contracts.Deployment, 0, len(bySlot))
	for _, deployment := range bySlot {
		sortBindings(deployment.RuntimeBindings)
		deployments = append(deployments, *deployment)
	}
	sort.Slice(deployments, func(i, j int) bool {
		if deployments[i].GovernedSlotIdentity != deployments[j].GovernedSlotIdentity {
			return deployments[i].GovernedSlotIdentity < deployments[j].GovernedSlotIdentity
		}
		return deployments[i].SourceIdentity < deployments[j].SourceIdentity
	})
	sort.Slice(blockers, func(i, j int) bool {
		if blockers[i].Code != blockers[j].Code {
			return blockers[i].Code < blockers[j].Code
		}
		return blockers[i].Message < blockers[j].Message
	})
	bindings := flattenBindings(deployments)
	return DeploymentSet{Deployments: deployments, RuntimeBindings: bindings, Blockers: blockers}, nil
}

func deploymentID(slotIdentity, sourceIdentity string) string {
	return string(contracts.SHA256([]byte(slotIdentity + "\x00" + sourceIdentity)))
}

func mergeBinding(deployment *contracts.Deployment, binding contracts.RuntimeBinding) {
	for _, existing := range deployment.RuntimeBindings {
		if existing.Runtime == binding.Runtime {
			return
		}
	}
	deployment.RuntimeBindings = append(deployment.RuntimeBindings, binding)
}

func sortBindings(bindings []contracts.RuntimeBinding) {
	sort.Slice(bindings, func(i, j int) bool {
		if bindings[i].Runtime != bindings[j].Runtime {
			return bindings[i].Runtime < bindings[j].Runtime
		}
		return bindings[i].Name < bindings[j].Name
	})
}

func flattenBindings(deployments []contracts.Deployment) []contracts.RuntimeBinding {
	var bindings []contracts.RuntimeBinding
	for _, deployment := range deployments {
		bindings = append(bindings, deployment.RuntimeBindings...)
	}
	sortBindings(bindings)
	return bindings
}
