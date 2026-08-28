package contracts

import "testing"

func MinimalPlanPayloadForTest() PlanPayload {
	inventory := Inventory{
		Schema:          SchemaInventory,
		ManifestDigest:  SHA256([]byte("manifest")),
		Sources:         []SourceObservation{},
		Deployments:     []PhysicalDeployment{},
		RuntimeBindings: []RuntimeBinding{},
		Ownership:       []OwnershipSnapshot{},
		Backups:         []BackupSetSnapshot{},
		Blockers:        []Blocker{},
	}
	inventoryBytes, err := CanonicalBytes(inventory)
	if err != nil {
		panic(err)
	}
	return PlanPayload{
		Inventory:                inventory,
		InventoryDigest:          SHA256(inventoryBytes),
		Intent:                   IntentInstall,
		Selector:                 nil,
		Deployments:              []PhysicalDeployment{},
		Blockers:                 []Blocker{},
		Preconditions:            []Precondition{},
		BackupRequirement:        BackupRequirement{Required: true, Reason: "install requires backup set"},
		VerificationRequirements: []VerificationRequirement{},
		RollbackStrategy:         "rollback_on_preterminal_failure",
		LineageTransition:        LineageTransition{From: "absent", To: "applied_unverified"},
	}
}

type canonicalArtifactForTest struct {
	Schema SchemaID
	Data   []byte
}

func MinimalCanonicalArtifactsForTest() []canonicalArtifactForTest {
	sha := SHA256([]byte("artifact"))
	op := string(SHA256([]byte("operation")))
	artifact := ArtifactRef{Path: "runs/" + op + "/artifact.json", SHA256: sha, Bytes: "2"}
	journal := JournalRef{OperationID: op, Path: "runs/" + op + "/journal.ndjson", SHA256: sha}
	approval := sha
	payload := MinimalPlanPayloadForTest()
	payloadDigest, err := PayloadDigest(payload)
	if err != nil {
		panic(err)
	}
	deployment := ownershipDeploymentForTest("deployment", artifact, sha)
	result := operationDeploymentResultForTest("deployment", artifact)
	values := []struct {
		schema SchemaID
		value  any
	}{
		{SchemaManifest, Manifest{Schema: SchemaManifest, Skills: []ManifestSkill{}, RuntimeRoots: []RuntimeRoot{}, Adapters: []AdapterBinding{}}},
		{SchemaInventory, payload.Inventory},
		{SchemaPlan, PlanEnvelope{Schema: SchemaPlan, ApprovalDigest: payloadDigest, Payload: payload}},
		{SchemaBackupManifest, BackupManifest{Schema: SchemaBackupManifest, BackupSetID: "backup", InstallationID: "install", Operation: "apply", Entries: []BackupEntry{}, Verified: true}},
		{SchemaOwnership, OwnershipRecord{Schema: SchemaOwnership, RecordID: "record", OperationID: OperationID(op), InstallationID: "install", DeploymentIDs: []string{"deployment"}, Deployments: []OwnershipDeploymentRecord{deployment}, PreviousHash: nil, PlanRef: artifact, InventoryRef: artifact, JournalRef: journal, BackupSetRef: &BackupSetRef{BackupSetID: "backup", SHA256: sha}, VerificationRef: nil, AggregateEvent: "applied_unverified", OperationResult: "verification_required", FailureCode: nil, CompensatingPriorState: nil}},
		{SchemaReceipt, Receipt{Schema: SchemaReceipt, ReceiptID: "receipt", OperationID: op, Command: "apply", ApprovalDigest: &approval, LedgerRecordHash: sha, ReadyJournalRef: journal, PlanRef: &artifact, InventoryRef: &artifact, BackupSetRef: &BackupSetRef{BackupSetID: "backup", SHA256: sha}, VerificationRef: nil, Preconditions: []Precondition{}, DeploymentResults: []OperationDeploymentResult{result}, RollbackResults: []OperationDeploymentResult{}, CleanupEvidenceRef: &artifact, RequiredVerificationStatus: "verification_required", OperationResult: "verification_required"}},
		{SchemaVerification, Verification{Schema: SchemaVerification, VerificationID: "verification", OperationID: op, Selector: Selector{Kind: SelectorInstallation, InstallationID: "install"}, Assertions: []VerificationAssertion{}, Status: "verified", OperatorRef: nil}},
		{SchemaOperatorObservation, OperatorObservation{Schema: SchemaOperatorObservation, ObservationID: "observation", Runtime: "claude", Challenge: "challenge", Declaration: "visible", Freshness: "fresh"}},
		{SchemaCommandResult, CommandResult{Schema: SchemaCommandResult, Kind: ResultArtifact, Command: "inventory", Status: ResultStatusSuccess, Artifact: &ArtifactResult{Schema: SchemaInventory, SHA256: sha, Bytes: "2", Label: "stdout"}}},
		{SchemaError, PublicError{Schema: SchemaError, Code: "invalid_input", Message: "Invalid input.", Exit: ExitInvalidInput, Command: "plan", Evidence: []EvidenceRef{}}},
	}
	out := make([]canonicalArtifactForTest, 0, len(values))
	for _, value := range values {
		data, err := CanonicalBytes(value.value)
		if err != nil {
			panic(err)
		}
		out = append(out, canonicalArtifactForTest{Schema: value.schema, Data: data})
	}
	return out
}

func ownershipDeploymentForTest(id string, artifact ArtifactRef, sha SHA256Hex) OwnershipDeploymentRecord {
	before := DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/skill", GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "missing", AttributesFingerprint: "attrs-before"}
	after := DeploymentObservation{ObservedType: "symlink", Path: "/runtime/skill", GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "object-" + id, ManagedLinkIdentity: "link-" + id, LexicalLinkTarget: "/repo/skill", SourceContentDigest: string(sha), AttributesFingerprint: "attrs-after"}
	return OwnershipDeploymentRecord{DeploymentID: id, BeforeObservation: before, AfterObservation: after, RuntimeBindingSummaries: []RuntimeBindingSummary{{Runtime: "pi", BindingIdentity: "pi:/runtime/skill", Status: "verification_required", EvidenceRef: &artifact}}, OriginalPreimage: before, InstalledPostimage: &after, BackupEntryRef: &artifact, VerificationRef: nil, CleanupEvidenceRef: &artifact, RollbackAuthorityRefs: []ArtifactRef{artifact}, Result: "verification_required"}
}

func operationDeploymentResultForTest(id string, artifact ArtifactRef) OperationDeploymentResult {
	before := DeploymentObservation{ObservedType: "typed_missing", Path: "/runtime/skill", GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "missing"}
	after := DeploymentObservation{ObservedType: "symlink", Path: "/runtime/skill", GovernedSlotIdentity: "slot-" + id, ManagedObjectIdentity: "object-" + id, ManagedLinkIdentity: "link-" + id}
	return OperationDeploymentResult{DeploymentID: id, Result: "verification_required", BeforeObservation: &before, AfterObservation: &after, RuntimeBindingSummaries: []RuntimeBindingSummary{{Runtime: "pi", BindingIdentity: "pi:/runtime/skill", Status: "verification_required", EvidenceRef: &artifact}}, BackupEntryRef: &artifact, CleanupEvidenceRef: &artifact}
}

func TestArtifactRefUsesRelativePathSHA256AndDecimalByteLength(t *testing.T) {
	op := string(SHA256([]byte("artifact-ref-op")))
	ref := ArtifactRef{Path: "runs/" + op + "/inventory.json", SHA256: SHA256([]byte("payload")), Bytes: "7"}
	data, err := CanonicalBytes(ref)
	if err != nil {
		t.Fatalf("CanonicalBytes() error = %v", err)
	}
	if err := ValidateArtifactRef(ref); err != nil {
		t.Fatalf("ValidateArtifactRef() error = %v; data=%s", err, data)
	}
	bad := []ArtifactRef{
		{Path: "/private/runs/" + op + "/inventory.json", SHA256: ref.SHA256, Bytes: ref.Bytes},
		{Path: "../escape", SHA256: ref.SHA256, Bytes: ref.Bytes},
		{Path: ref.Path, SHA256: "not-a-sha", Bytes: ref.Bytes},
		{Path: ref.Path, SHA256: ref.SHA256, Bytes: "01"},
	}
	for _, candidate := range bad {
		if err := ValidateArtifactRef(candidate); err == nil {
			t.Fatalf("ValidateArtifactRef(%+v) succeeded, want error", candidate)
		}
	}
}

func TestSelectorIntentCardinality(t *testing.T) {
	if err := ValidateIntentSelector(IntentInstall, nil); err != nil {
		t.Fatalf("install selector validation error = %v", err)
	}
	if err := ValidateIntentSelector(IntentInstall, &Selector{Kind: SelectorInstallation, InstallationID: "i1"}); err == nil {
		t.Fatalf("install selector accepted non-empty selector")
	}
	if err := ValidateIntentSelector(IntentUninstall, &Selector{Kind: SelectorInstallation, InstallationID: "i1"}); err != nil {
		t.Fatalf("uninstall selector validation error = %v", err)
	}
	if err := ValidateIntentSelector(IntentUninstall, &Selector{Kind: SelectorInstallation, InstallationID: "i1", BackupSetID: "b1"}); err == nil {
		t.Fatalf("uninstall selector accepted more than one selector value")
	}
	if err := ValidateIntentSelector(IntentRestore, &Selector{Kind: SelectorBackupSet, BackupSetID: "b1"}); err != nil {
		t.Fatalf("restore selector validation error = %v", err)
	}
	if err := ValidateIntentSelector(IntentRestore, &Selector{Kind: SelectorInstallation, InstallationID: "i1"}); err == nil {
		t.Fatalf("restore selector accepted installation selector")
	}
}

func TestVerifySelectorSelectsExactlyOneReceiptInstallationOrBackup(t *testing.T) {
	valid := []*Selector{
		{Kind: SelectorReceipt, ReceiptID: "r1"},
		{Kind: SelectorInstallation, InstallationID: "i1"},
		{Kind: SelectorBackupSet, BackupSetID: "b1"},
	}
	for _, selector := range valid {
		if err := ValidateIntentSelector(IntentVerify, selector); err != nil {
			t.Fatalf("ValidateIntentSelector(%+v) error = %v", selector, err)
		}
	}
	invalid := []*Selector{
		nil,
		{Kind: SelectorReceipt},
		{Kind: SelectorReceipt, ReceiptID: "r1", InstallationID: "i1"},
		{Kind: SelectorBackupSet, BackupSetID: "b1", ReceiptID: "r1"},
	}
	for _, selector := range invalid {
		if err := ValidateIntentSelector(IntentVerify, selector); err == nil {
			t.Fatalf("ValidateIntentSelector(%+v) succeeded, want error", selector)
		}
	}
}

func TestCommandResultAndPublicErrorCanonicalContracts(t *testing.T) {
	result := CommandResult{
		Schema:   SchemaCommandResult,
		Kind:     ResultArtifact,
		Command:  "inventory",
		Status:   ResultStatusSuccess,
		Artifact: &ArtifactResult{Schema: SchemaInventory, SHA256: SHA256([]byte("{}")), Bytes: "2", Label: "stdout"},
	}
	data, err := CanonicalBytes(result)
	if err != nil {
		t.Fatalf("CanonicalBytes(CommandResult) error = %v", err)
	}
	if err := ValidateSchema(SchemaCommandResult, data); err != nil {
		t.Fatalf("ValidateSchema(CommandResult) error = %v\n%s", err, data)
	}

	publicErr := PublicError{Schema: SchemaError, Code: "invalid_input", Message: "Invalid input.", Exit: ExitInvalidInput, Command: "plan", Evidence: []EvidenceRef{}}
	errData, err := CanonicalBytes(publicErr)
	if err != nil {
		t.Fatalf("CanonicalBytes(PublicError) error = %v", err)
	}
	if err := ValidateSchema(SchemaError, errData); err != nil {
		t.Fatalf("ValidateSchema(PublicError) error = %v\n%s", err, errData)
	}
}
