package inventory

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"sort"
	"strconv"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	manifestloader "waywarden/internal/distribution/manifest"
	"waywarden/internal/distribution/planning"
	"waywarden/internal/distribution/runtimes"
)

type Service interface {
	Inventory(context.Context, Options) (contracts.ArtifactResult, error)
}

type Options struct {
	CWD           string
	ManifestPath  string
	StateRoot     contracts.AbsolutePath
	ArtifactLabel string
	ArtifactSink  func([]byte) error
	Destination   contracts.AbsolutePath
}

type Error struct {
	Code    string
	Message string
	Exit    int
}

func (e Error) Error() string { return e.Message }

type service struct {
	adapter filesystem.Adapter
}

func NewService(adapter filesystem.Adapter) Service {
	if adapter == nil {
		adapter = filesystem.NewLocalAdapter()
	}
	return service{adapter: adapter}
}

func (s service) Inventory(ctx context.Context, options Options) (contracts.ArtifactResult, error) {
	env, err := s.adapter.Environment(ctx)
	if err != nil {
		return contracts.ArtifactResult{}, Error{Code: "runtime_contract_missing", Message: "cannot read platform environment", Exit: contracts.ExitUnsupported}
	}
	stateRoot, err := selectedStateRoot(s.adapter.Platform(), env, options.StateRoot)
	if err != nil {
		return contracts.ArtifactResult{}, Error{Code: "invalid_input", Message: err.Error(), Exit: contracts.ExitInvalidInput}
	}
	lockRoot, err := s.adapter.OwnerPrivateLockRoot(env)
	if err != nil {
		return contracts.ArtifactResult{}, Error{Code: "runtime_contract_missing", Message: "cannot select lock root", Exit: contracts.ExitUnsupported}
	}

	loaded, err := manifestloader.Load(manifestloader.LoadOptions{CWD: options.CWD, ManifestPath: options.ManifestPath})
	if err != nil {
		return contracts.ArtifactResult{}, Error{Code: "invalid_input", Message: err.Error(), Exit: contracts.ExitInvalidInput}
	}

	blockers := []contracts.Blocker{}
	sources, sourceBlockers := s.sourceObservations(ctx, loaded)
	blockers = append(blockers, sourceBlockers...)

	deploymentSet, err := planning.BuildDeployments(loaded.Manifest, loaded.SourceRoot, env.Home)
	if err != nil {
		return contracts.ArtifactResult{}, Error{Code: "runtime_contract_missing", Message: err.Error(), Exit: contracts.ExitUnsupported}
	}
	blockers = append(blockers, deploymentSet.Blockers...)

	state, err := snapshotState(ctx, s.adapter, stateRoot, lockRoot)
	if err != nil {
		if errors.Is(err, filesystem.ErrUnsupportedCapability) {
			return contracts.ArtifactResult{}, Error{Code: "runtime_contract_missing", Message: "ownership ledger snapshot is unsupported", Exit: contracts.ExitUnsupported}
		}
		blockers = append(blockers, contracts.Blocker{Code: "runtime_contract_missing", Severity: "error", Message: "ownership ledger snapshot is unsupported"})
		state = stateSnapshot{Ownership: []contracts.OwnershipSnapshot{}, Backups: []contracts.BackupSetSnapshot{}}
	}

	sortBlockers(blockers)
	artifact := contracts.Inventory{
		Schema:          contracts.SchemaInventory,
		ManifestDigest:  loaded.Digest,
		Sources:         sources,
		Deployments:     deploymentSet.Deployments,
		RuntimeBindings: deploymentSet.RuntimeBindings,
		Ownership:       state.Ownership,
		Backups:         state.Backups,
		Blockers:        blockers,
	}
	canonical, err := contracts.CanonicalBytes(artifact)
	if err != nil {
		return contracts.ArtifactResult{}, err
	}
	if err := contracts.ValidateSchema(contracts.SchemaInventory, canonical); err != nil {
		return contracts.ArtifactResult{}, err
	}
	if options.Destination != "" {
		forbidden := forbiddenRoots(loaded.SourceRoot, env.Home, loaded.Manifest.RuntimeRoots, stateRoot, lockRoot)
		if err := s.adapter.PublishNoReplace(ctx, options.Destination, canonical, forbidden); err != nil {
			return contracts.ArtifactResult{}, publishError(err)
		}
	}
	if options.ArtifactSink != nil {
		if err := options.ArtifactSink(canonical); err != nil {
			return contracts.ArtifactResult{}, Error{Code: "read_only_publish_failed", Message: "artifact output failed", Exit: contracts.ExitStateOrIOFailure}
		}
	}
	label := options.ArtifactLabel
	if label == "" {
		label = "inventory artifact"
	}
	result := contracts.ArtifactResult{Schema: contracts.SchemaInventory, SHA256: contracts.SHA256(canonical), Bytes: strconv.Itoa(len(canonical)), Label: label}
	if len(blockers) > 0 {
		return result, Error{Code: "runtime_contract_missing", Message: "inventory completed with capability blockers", Exit: contracts.ExitUnsupported}
	}
	return result, nil
}

func (s service) sourceObservations(ctx context.Context, loaded manifestloader.LoadedManifest) ([]contracts.SourceObservation, []contracts.Blocker) {
	skills := append([]contracts.ManifestSkill(nil), loaded.Manifest.Skills...)
	sort.Slice(skills, func(i, j int) bool { return skills[i].SkillID < skills[j].SkillID })
	sources := make([]contracts.SourceObservation, 0, len(skills))
	blockers := []contracts.Blocker{}
	for _, skill := range skills {
		sourcePath := filepath.Join(loaded.SourceRoot, filepath.FromSlash(skill.SourcePath))
		sourceIdentity, err := filesystem.ContainedCanonicalIdentity(loaded.SourceRoot, sourcePath)
		if err != nil {
			blockers = append(blockers, contracts.Blocker{Code: "runtime_contract_missing", Severity: "error", Message: "source identity is unsupported for " + skill.SkillID})
			continue
		}
		snapshot, err := s.adapter.SnapshotTree(ctx, contracts.AbsolutePath(sourceIdentity))
		if err != nil {
			blockers = append(blockers, contracts.Blocker{Code: "runtime_contract_missing", Severity: "error", Message: "source snapshot is unsupported for " + skill.SkillID})
			continue
		}
		digest, err := filesystem.TreeDigest(snapshot)
		if err != nil {
			blockers = append(blockers, contracts.Blocker{Code: "runtime_contract_missing", Severity: "error", Message: "source digest is unsupported for " + skill.SkillID})
			continue
		}
		sources = append(sources, contracts.SourceObservation{SkillID: skill.SkillID, Path: filepath.ToSlash(skill.SourcePath), SourceIdentity: sourceIdentity, SHA256: digest})
	}
	return sources, blockers
}

func selectedStateRoot(platform string, env filesystem.PlatformEnv, override contracts.AbsolutePath) (contracts.AbsolutePath, error) {
	if override != "" {
		clean := filepath.Clean(string(override))
		if !filepath.IsAbs(clean) {
			return "", fmt.Errorf("state root must be absolute")
		}
		return contracts.AbsolutePath(clean), nil
	}
	return runtimes.DefaultStateRoot(platform, env)
}

func forbiddenRoots(sourceRoot string, home string, runtimeRoots []contracts.RuntimeRoot, stateRoot, lockRoot contracts.AbsolutePath) filesystem.ForbiddenRoots {
	roots := make([]contracts.AbsolutePath, 0, len(runtimeRoots))
	for _, root := range runtimeRoots {
		roots = append(roots, contracts.AbsolutePath(filepath.Join(home, filepath.FromSlash(root.Root))))
	}
	return filesystem.ForbiddenRoots{RepositorySourceRoot: contracts.AbsolutePath(sourceRoot), RuntimeRoots: roots, StateRoot: stateRoot, LockRoot: lockRoot}
}

func sortBlockers(blockers []contracts.Blocker) {
	sort.Slice(blockers, func(i, j int) bool {
		if blockers[i].Code != blockers[j].Code {
			return blockers[i].Code < blockers[j].Code
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
		return Error{Code: "read_only_unsupported", Message: "artifact publication is unsupported", Exit: contracts.ExitUnsupported}
	default:
		return Error{Code: "read_only_publish_failed", Message: "artifact publication failed", Exit: contracts.ExitStateOrIOFailure}
	}
}
