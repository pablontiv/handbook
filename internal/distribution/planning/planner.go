package planning

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"sort"
	"strconv"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/runtimes"
)

type InventoryArtifact struct {
	inventory contracts.Inventory
	raw       []byte
}

func (a InventoryArtifact) Inventory() contracts.Inventory {
	return cloneInventory(a.inventory)
}

type Options struct {
	Intent        contracts.PlanIntent
	Selector      *contracts.Selector
	InventoryPath contracts.AbsolutePath
	ArtifactLabel string
	ArtifactSink  func([]byte) error
	Destination   contracts.AbsolutePath
	StateRoot     contracts.AbsolutePath
}

type Result struct {
	Envelope contracts.PlanEnvelope
}

type Service interface {
	Plan(context.Context, Options) (contracts.ArtifactResult, error)
}

type Error struct {
	Code    string
	Message string
	Exit    int
}

func (e Error) Error() string {
	if e.Message != "" {
		return e.Message
	}
	return e.Code
}

type service struct {
	adapter filesystem.Adapter
}

func NewService(adapter filesystem.Adapter) Service {
	return service{adapter: adapter}
}

func DecodeInventoryArtifact(raw []byte) (InventoryArtifact, error) {
	inventory, err := contracts.ParseCanonicalInventory(raw)
	if err != nil {
		return InventoryArtifact{}, Error{Code: "invalid_inventory", Message: err.Error(), Exit: contracts.ExitInvalidInput}
	}
	if err := contracts.ValidateSchema(contracts.SchemaInventory, raw); err != nil {
		return InventoryArtifact{}, Error{Code: "invalid_inventory", Message: err.Error(), Exit: contracts.ExitInvalidInput}
	}
	return InventoryArtifact{inventory: cloneInventory(inventory), raw: append([]byte(nil), raw...)}, nil
}

func BuildPlan(_ context.Context, artifact InventoryArtifact, opts Options) (Result, error) {
	if len(artifact.raw) == 0 {
		return Result{}, Error{Code: "invalid_inventory", Message: "inventory artifact was not decoded from canonical bytes", Exit: contracts.ExitInvalidInput}
	}
	if err := contracts.ValidateIntentSelector(opts.Intent, opts.Selector); err != nil {
		return Result{}, Error{Code: "invalid_selector", Message: err.Error(), Exit: contracts.ExitInvalidInput}
	}

	inventory := cloneInventory(artifact.inventory)
	deployments := cloneDeployments(inventory.Deployments)
	sortDeployments(deployments)
	blockers := append([]contracts.Blocker(nil), inventory.Blockers...)

	var planningErr error
	switch opts.Intent {
	case contracts.IntentInstall:
		// Install intentionally has no selector; contract validation above enforces it.
	case contracts.IntentUninstall:
		if !hasObservedInstallation(inventory, opts.Selector.InstallationID) {
			blockers = append(blockers, contracts.Blocker{Code: "installation_not_observed", Severity: contracts.BlockerSeveritySafePrecondition, Message: fmt.Sprintf("installation %s is not present in inventory ownership observations", opts.Selector.InstallationID)})
			planningErr = Error{Code: "safe_precondition_failed", Message: "selected installation is not observed", Exit: contracts.ExitPreconditionFailed}
		}
	case contracts.IntentRestore:
		if !hasObservedVerifiedBackup(inventory, opts.Selector.BackupSetID) {
			blockers = append(blockers, contracts.Blocker{Code: "backup_not_observed_verified", Severity: contracts.BlockerSeveritySafePrecondition, Message: fmt.Sprintf("backup set %s is not present as a verified inventory backup", opts.Selector.BackupSetID)})
			planningErr = Error{Code: "safe_precondition_failed", Message: "selected backup is not observed and verified", Exit: contracts.ExitPreconditionFailed}
		}
	default:
		return Result{}, Error{Code: "unsupported_intent", Message: fmt.Sprintf("intent %q is unsupported", opts.Intent), Exit: contracts.ExitUnsupported}
	}

	if capabilityErr := firstCapabilityBlocker(blockers); capabilityErr != nil {
		planningErr = capabilityErr
	}

	sortBlockers(blockers)
	payload := contracts.PlanPayload{
		Inventory:                inventory,
		InventoryDigest:          inventoryDigest(artifact, inventory),
		Intent:                   opts.Intent,
		Selector:                 cloneSelector(opts.Selector),
		Deployments:              deployments,
		Blockers:                 blockers,
		Preconditions:            preconditionsFor(deployments),
		BackupRequirement:        backupRequirementFor(opts.Intent),
		VerificationRequirements: verificationRequirementsFor(deployments),
		RollbackStrategy:         rollbackStrategyFor(opts.Intent),
		LineageTransition:        lineageTransitionFor(opts.Intent),
	}
	approvalDigest, err := contracts.PayloadDigest(payload)
	if err != nil {
		return Result{}, err
	}
	result := Result{Envelope: contracts.PlanEnvelope{Schema: contracts.SchemaPlan, ApprovalDigest: approvalDigest, Payload: payload}}
	return result, planningErr
}

func CanonicalPlanBytes(result Result) ([]byte, error) {
	canonical, err := contracts.CanonicalBytes(result.Envelope)
	if err != nil {
		return nil, err
	}
	if err := contracts.ValidateSchema(contracts.SchemaPlan, canonical); err != nil {
		return nil, err
	}
	return canonical, nil
}

func (s service) Plan(ctx context.Context, opts Options) (contracts.ArtifactResult, error) {
	if opts.InventoryPath == "" {
		return contracts.ArtifactResult{}, Error{Code: "invalid_input", Message: "--inventory is required", Exit: contracts.ExitInvalidInput}
	}
	raw, err := s.adapter.ReadFile(ctx, opts.InventoryPath)
	if err != nil {
		return contracts.ArtifactResult{}, Error{Code: "inventory_read_failed", Message: "cannot read inventory artifact", Exit: contracts.ExitStateOrIOFailure}
	}
	artifact, err := DecodeInventoryArtifact(raw)
	if err != nil {
		return contracts.ArtifactResult{}, err
	}
	plan, planErr := BuildPlan(ctx, artifact, opts)
	canonical, err := CanonicalPlanBytes(plan)
	if err != nil {
		if planErr != nil {
			return contracts.ArtifactResult{}, planErr
		}
		return contracts.ArtifactResult{}, err
	}
	if opts.Destination != "" {
		forbidden, err := publicationForbiddenRoots(ctx, s.adapter, artifact, opts.StateRoot)
		if err != nil {
			return contracts.ArtifactResult{}, err
		}
		if err := s.adapter.PublishNoReplace(ctx, opts.Destination, canonical, forbidden); err != nil {
			return contracts.ArtifactResult{}, publishError(err)
		}
	}
	if opts.ArtifactSink != nil {
		if err := opts.ArtifactSink(canonical); err != nil {
			return contracts.ArtifactResult{}, Error{Code: "read_only_publish_failed", Message: "artifact output failed", Exit: contracts.ExitStateOrIOFailure}
		}
	}
	label := opts.ArtifactLabel
	if label == "" {
		label = "plan artifact"
	}
	result := contracts.ArtifactResult{Schema: contracts.SchemaPlan, SHA256: contracts.SHA256(canonical), Bytes: strconv.Itoa(len(canonical)), Label: label}
	return result, planErr
}

func publicationForbiddenRoots(ctx context.Context, adapter filesystem.Adapter, artifact InventoryArtifact, overrideStateRoot contracts.AbsolutePath) (filesystem.ForbiddenRoots, error) {
	env, err := adapter.Environment(ctx)
	if err != nil {
		return filesystem.ForbiddenRoots{}, Error{Code: "runtime_contract_missing", Message: "cannot read platform environment for artifact publication", Exit: contracts.ExitUnsupported}
	}
	stateRoot, err := selectedPublicationStateRoot(adapter.Platform(), env, overrideStateRoot)
	if err != nil {
		return filesystem.ForbiddenRoots{}, err
	}
	lockRoot, err := adapter.OwnerPrivateLockRoot(env)
	if err != nil {
		return filesystem.ForbiddenRoots{}, Error{Code: "runtime_contract_missing", Message: "cannot select publication lock root", Exit: contracts.ExitUnsupported}
	}
	cleanLockRoot, err := requiredAbsoluteRoot(string(lockRoot), "coordination lock")
	if err != nil {
		return filesystem.ForbiddenRoots{}, err
	}
	sourceRoots, err := repositorySourceRoots(artifact.inventory)
	if err != nil {
		return filesystem.ForbiddenRoots{}, err
	}
	runtimeRoots, err := inventoryRuntimeRoots(artifact.inventory)
	if err != nil {
		return filesystem.ForbiddenRoots{}, err
	}
	return filesystem.ForbiddenRoots{RepositorySourceRoots: sourceRoots, RuntimeRoots: runtimeRoots, StateRoot: stateRoot, LockRoot: cleanLockRoot}, nil
}

func selectedPublicationStateRoot(platform string, env filesystem.PlatformEnv, override contracts.AbsolutePath) (contracts.AbsolutePath, error) {
	if override != "" {
		clean := filepath.Clean(string(override))
		if !filepath.IsAbs(clean) {
			return "", Error{Code: "invalid_input", Message: "state root must be absolute", Exit: contracts.ExitInvalidInput}
		}
		return contracts.AbsolutePath(clean), nil
	}
	stateRoot, err := runtimes.DefaultStateRoot(platform, env)
	if err != nil {
		return "", Error{Code: "runtime_contract_missing", Message: "cannot select publication state root", Exit: contracts.ExitUnsupported}
	}
	return requiredAbsoluteRoot(string(stateRoot), "state")
}

func repositorySourceRoots(inventory contracts.Inventory) ([]contracts.AbsolutePath, error) {
	if len(inventory.Sources) == 0 {
		return nil, Error{Code: "runtime_contract_missing", Message: "repository source root proof is missing from inventory", Exit: contracts.ExitUnsupported}
	}
	roots := make([]contracts.AbsolutePath, 0, len(inventory.Sources))
	seen := map[string]struct{}{}
	for _, source := range inventory.Sources {
		root, err := requiredAbsoluteRoot(source.SourceIdentity, "repository source")
		if err != nil {
			return nil, err
		}
		if _, ok := seen[string(root)]; ok {
			continue
		}
		seen[string(root)] = struct{}{}
		roots = append(roots, root)
	}
	sort.Slice(roots, func(i, j int) bool { return roots[i] < roots[j] })
	return roots, nil
}

func inventoryRuntimeRoots(inventory contracts.Inventory) ([]contracts.AbsolutePath, error) {
	roots := make([]contracts.AbsolutePath, 0, len(inventory.RuntimeBindings))
	seen := map[string]struct{}{}
	for _, binding := range inventory.RuntimeBindings {
		root, err := requiredAbsoluteRoot(binding.Root, "runtime")
		if err != nil {
			return nil, err
		}
		if _, ok := seen[string(root)]; ok {
			continue
		}
		seen[string(root)] = struct{}{}
		roots = append(roots, root)
	}
	sort.Slice(roots, func(i, j int) bool { return roots[i] < roots[j] })
	return roots, nil
}

func requiredAbsoluteRoot(path string, label string) (contracts.AbsolutePath, error) {
	if path == "" {
		return "", Error{Code: "runtime_contract_missing", Message: label + " root proof is missing", Exit: contracts.ExitUnsupported}
	}
	clean := filepath.Clean(path)
	if !filepath.IsAbs(clean) {
		return "", Error{Code: "runtime_contract_missing", Message: label + " root proof is not absolute", Exit: contracts.ExitUnsupported}
	}
	return contracts.AbsolutePath(clean), nil
}

func inventoryDigest(artifact InventoryArtifact, _ contracts.Inventory) contracts.SHA256Hex {
	return contracts.SHA256(artifact.raw)
}

func hasObservedInstallation(inventory contracts.Inventory, installationID string) bool {
	for _, ownership := range inventory.Ownership {
		if ownership.InstallationID == installationID {
			return true
		}
	}
	return false
}

func hasObservedVerifiedBackup(inventory contracts.Inventory, backupSetID string) bool {
	for _, backup := range inventory.Backups {
		if backup.BackupSetID == backupSetID && backup.Verified {
			return true
		}
	}
	return false
}

func firstCapabilityBlocker(blockers []contracts.Blocker) error {
	for _, blocker := range blockers {
		if blocker.Code == "runtime_contract_missing" {
			return Error{Code: "runtime_contract_missing", Message: blocker.Message, Exit: contracts.ExitUnsupported}
		}
	}
	return nil
}

func backupRequirementFor(intent contracts.PlanIntent) contracts.BackupRequirement {
	switch intent {
	case contracts.IntentRestore:
		return contracts.BackupRequirement{Required: false, Reason: "restore consumes an observed verified backup set"}
	default:
		return contracts.BackupRequirement{Required: true, Reason: string(intent) + " requires a recoverable backup boundary"}
	}
}

func preconditionsFor(deployments []contracts.Deployment) []contracts.Precondition {
	preconditions := make([]contracts.Precondition, 0, len(deployments))
	for _, deployment := range deployments {
		preconditions = append(preconditions, contracts.Precondition{DeploymentID: deployment.DeploymentID, Code: "governed_slot_matches_inventory", Expected: deployment.GovernedSlotIdentity})
	}
	return preconditions
}

func verificationRequirementsFor(deployments []contracts.Deployment) []contracts.VerificationRequirement {
	var requirements []contracts.VerificationRequirement
	for _, deployment := range deployments {
		for _, binding := range deployment.RuntimeBindings {
			requirements = append(requirements, contracts.VerificationRequirement{DeploymentID: deployment.DeploymentID, Runtime: binding.Runtime, Required: true})
		}
	}
	sort.Slice(requirements, func(i, j int) bool {
		if requirements[i].DeploymentID != requirements[j].DeploymentID {
			return requirements[i].DeploymentID < requirements[j].DeploymentID
		}
		return requirements[i].Runtime < requirements[j].Runtime
	})
	return requirements
}

func rollbackStrategyFor(intent contracts.PlanIntent) string {
	switch intent {
	case contracts.IntentInstall:
		return "rollback_on_preterminal_failure"
	case contracts.IntentUninstall:
		return "restore_backup_on_preterminal_failure"
	case contracts.IntentRestore:
		return "preserve_current_state_on_preterminal_failure"
	default:
		return "rollback_on_preterminal_failure"
	}
}

func lineageTransitionFor(intent contracts.PlanIntent) contracts.LineageTransition {
	switch intent {
	case contracts.IntentInstall:
		return contracts.LineageTransition{From: "absent", To: "applied_unverified"}
	case contracts.IntentUninstall:
		return contracts.LineageTransition{From: "installed_verified", To: "removed_unverified"}
	case contracts.IntentRestore:
		return contracts.LineageTransition{From: "removed_or_damaged", To: "restored_unverified"}
	default:
		return contracts.LineageTransition{From: "unknown", To: "unknown"}
	}
}

func cloneSelector(selector *contracts.Selector) *contracts.Selector {
	if selector == nil {
		return nil
	}
	copy := *selector
	return &copy
}

func cloneInventory(in contracts.Inventory) contracts.Inventory {
	out := in
	out.Sources = append(make([]contracts.SourceObservation, 0, len(in.Sources)), in.Sources...)
	out.Deployments = cloneDeployments(in.Deployments)
	out.RuntimeBindings = append(make([]contracts.RuntimeBinding, 0, len(in.RuntimeBindings)), in.RuntimeBindings...)
	out.Ownership = append(make([]contracts.OwnershipSnapshot, 0, len(in.Ownership)), in.Ownership...)
	out.Backups = append(make([]contracts.BackupSetSnapshot, 0, len(in.Backups)), in.Backups...)
	out.Blockers = append(make([]contracts.Blocker, 0, len(in.Blockers)), in.Blockers...)
	return out
}

func cloneDeployments(in []contracts.Deployment) []contracts.Deployment {
	out := make([]contracts.Deployment, len(in))
	for i, deployment := range in {
		out[i] = deployment
		out[i].RuntimeBindings = append([]contracts.RuntimeBinding(nil), deployment.RuntimeBindings...)
		sortBindings(out[i].RuntimeBindings)
	}
	return out
}

func sortDeployments(deployments []contracts.Deployment) {
	sort.Slice(deployments, func(i, j int) bool {
		if deployments[i].GovernedSlotIdentity != deployments[j].GovernedSlotIdentity {
			return deployments[i].GovernedSlotIdentity < deployments[j].GovernedSlotIdentity
		}
		if deployments[i].SourceIdentity != deployments[j].SourceIdentity {
			return deployments[i].SourceIdentity < deployments[j].SourceIdentity
		}
		return deployments[i].DeploymentID < deployments[j].DeploymentID
	})
}

func sortBlockers(blockers []contracts.Blocker) {
	sort.Slice(blockers, func(i, j int) bool {
		if blockers[i].Code != blockers[j].Code {
			return blockers[i].Code < blockers[j].Code
		}
		if blockers[i].Severity != blockers[j].Severity {
			return blockers[i].Severity < blockers[j].Severity
		}
		return blockers[i].Message < blockers[j].Message
	})
}

func publishError(err error) error {
	switch {
	case errors.Is(err, filesystem.ErrDestinationExists):
		return Error{Code: "read_only_destination_exists", Message: "artifact destination already exists", Exit: contracts.ExitPreconditionFailed}
	case errors.Is(err, filesystem.ErrForbiddenDestination):
		return Error{Code: "safe_precondition_failed", Message: "artifact destination is forbidden", Exit: contracts.ExitPreconditionFailed}
	case errors.Is(err, filesystem.ErrUnsupportedCapability):
		return Error{Code: "runtime_contract_missing", Message: "artifact publishing is unsupported", Exit: contracts.ExitUnsupported}
	default:
		return Error{Code: "read_only_publish_failed", Message: "artifact publish failed", Exit: contracts.ExitStateOrIOFailure}
	}
}
