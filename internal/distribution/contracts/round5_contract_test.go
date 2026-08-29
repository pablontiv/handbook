package contracts_test

import (
	"encoding/json"
	"strings"
	"testing"

	"waywarden/internal/distribution/contracts"
)

func TestRound5SchemaExecutionRejectsNestedUnknownsAndInvalidEnums(t *testing.T) {
	valid := map[string]any{
		"schema":          string(contracts.SchemaBackupManifest),
		"backup_set_id":   hex64("backup"),
		"installation_id": hex64("installation"),
		"operation_id":    hex64("operation"),
		"operation":       "apply",
		"entries": []any{map[string]any{
			"deployment_id": hex64("deployment"),
			"kind":          "typed_missing",
			"payload":       nil,
			"metadata":      []any{},
		}},
		"verified": true,
	}
	bytes := canonicalMap(t, valid)
	if err := contracts.ValidateSchema(contracts.SchemaBackupManifest, bytes); err != nil {
		t.Fatalf("valid backup manifest rejected: %v\n%s", err, bytes)
	}

	withUnknown := cloneMap(valid)
	entry := cloneMap(withUnknown["entries"].([]any)[0].(map[string]any))
	entry["authority_bypass"] = true
	withUnknown["entries"] = []any{entry}
	if err := contracts.ValidateSchema(contracts.SchemaBackupManifest, canonicalMap(t, withUnknown)); err == nil {
		t.Fatalf("ValidateSchema accepted nested unknown backup entry property")
	}

	withBadKind := cloneMap(valid)
	badEntry := cloneMap(withBadKind["entries"].([]any)[0].(map[string]any))
	badEntry["kind"] = "junction"
	withBadKind["entries"] = []any{badEntry}
	if err := contracts.ValidateSchema(contracts.SchemaBackupManifest, canonicalMap(t, withBadKind)); err == nil {
		t.Fatalf("ValidateSchema accepted invalid backup entry kind")
	}
}

func TestRound5GeneratedIDValidatorsRejectPathAuthority(t *testing.T) {
	good := hex64("operation")
	for _, candidate := range []string{good[:63], strings.ToUpper(good), "/" + good, "..", "../" + good, good + "/manifest", "C:" + good, strings.Repeat("g", 64)} {
		if err := contracts.ValidateOperationID(candidate); err == nil {
			t.Fatalf("ValidateOperationID accepted %q", candidate)
		}
		if err := contracts.ValidateBackupSetID(candidate); err == nil {
			t.Fatalf("ValidateBackupSetID accepted %q", candidate)
		}
	}
	if err := contracts.ValidateOperationID(good); err != nil {
		t.Fatalf("ValidateOperationID rejected generated shape: %v", err)
	}
	if err := contracts.ValidateBackupSetID(good); err != nil {
		t.Fatalf("ValidateBackupSetID rejected generated shape: %v", err)
	}
}

func canonicalMap(t *testing.T, value map[string]any) []byte {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	var decoded any
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatal(err)
	}
	canonical, err := contracts.CanonicalBytes(decoded)
	if err != nil {
		t.Fatal(err)
	}
	return canonical
}

func cloneMap(in map[string]any) map[string]any {
	out := make(map[string]any, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}

func hex64(seed string) string { return string(contracts.SHA256([]byte("round5-" + seed))) }
