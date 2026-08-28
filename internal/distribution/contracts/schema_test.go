package contracts

import "testing"

func TestSchemaIDsHaveExactLiterals(t *testing.T) {
	want := []SchemaID{
		SchemaManifest,
		SchemaInventory,
		SchemaPlan,
		SchemaBackupManifest,
		SchemaOwnership,
		SchemaReceipt,
		SchemaVerification,
		SchemaOperatorObservation,
		SchemaCommandResult,
		SchemaError,
	}
	got := []string{
		"waywarden.manifest/v1",
		"waywarden.inventory/v1",
		"waywarden.plan/v1",
		"waywarden.backup-manifest/v1",
		"waywarden.ownership/v1",
		"waywarden.receipt/v1",
		"waywarden.verification/v1",
		"waywarden.operator-observation/v1",
		"waywarden.command-result/v1",
		"waywarden.error/v1",
	}
	for i := range want {
		if string(want[i]) != got[i] {
			t.Fatalf("schema ID[%d] = %q, want %q", i, want[i], got[i])
		}
	}
}

func TestValidateSchemaAcceptsMinimalCanonicalArtifactForEachSchema(t *testing.T) {
	for _, artifact := range MinimalCanonicalArtifactsForTest() {
		t.Run(string(artifact.Schema), func(t *testing.T) {
			if err := ValidateSchema(artifact.Schema, artifact.Data); err != nil {
				t.Fatalf("ValidateSchema() error = %v\n%s", err, artifact.Data)
			}
		})
	}
}

func TestValidateSchemaRejectsWrongSchemaAndNonCanonicalBytes(t *testing.T) {
	artifact := MinimalCanonicalArtifactsForTest()[0]
	if err := ValidateSchema(SchemaInventory, artifact.Data); err == nil {
		t.Fatalf("ValidateSchema() accepted artifact with wrong schema const")
	}
	if err := ValidateSchema(artifact.Schema, append(append([]byte{}, artifact.Data...), '\n')); err == nil {
		t.Fatalf("ValidateSchema() accepted noncanonical bytes")
	}
}

func TestEmbeddedSchemasAreDraft202012AndClosed(t *testing.T) {
	for _, id := range AllSchemaIDs() {
		t.Run(string(id), func(t *testing.T) {
			schema, err := LoadSchema(id)
			if err != nil {
				t.Fatalf("LoadSchema() error = %v", err)
			}
			var doc map[string]any
			if err := StrictParseCanonical(schema, &doc); err != nil {
				t.Fatalf("embedded schema is not canonical: %v\n%s", err, schema)
			}
			if doc["$schema"] != "https://json-schema.org/draft/2020-12/schema" {
				t.Fatalf("$schema = %v", doc["$schema"])
			}
			if doc["$id"] != string(id) {
				t.Fatalf("$id = %v, want %s", doc["$id"], id)
			}
			if doc["additionalProperties"] != false {
				t.Fatalf("additionalProperties = %v, want false", doc["additionalProperties"])
			}
		})
	}
}

func TestOwnershipAndReceiptSchemasCloseEveryNestedObject(t *testing.T) {
	for _, id := range []SchemaID{SchemaOwnership, SchemaReceipt} {
		t.Run(string(id), func(t *testing.T) {
			schema, err := LoadSchema(id)
			if err != nil {
				t.Fatalf("LoadSchema() error = %v", err)
			}
			var doc map[string]any
			if err := StrictParseCanonical(schema, &doc); err != nil {
				t.Fatalf("embedded schema is not canonical: %v\n%s", err, schema)
			}
			assertSchemaObjectsClosed(t, "$", doc)
		})
	}
}

func assertSchemaObjectsClosed(t *testing.T, path string, node any) {
	t.Helper()
	switch value := node.(type) {
	case map[string]any:
		if value["type"] == "object" {
			if value["additionalProperties"] != false {
				t.Fatalf("%s object lacks additionalProperties:false", path)
			}
			props, ok := value["properties"].(map[string]any)
			if !ok || len(props) == 0 {
				t.Fatalf("%s object lacks explicit nested properties", path)
			}
			if _, ok := value["required"].([]any); !ok {
				t.Fatalf("%s object lacks required list", path)
			}
		}
		for key, child := range value {
			assertSchemaObjectsClosed(t, path+"."+key, child)
		}
	case []any:
		for _, child := range value {
			assertSchemaObjectsClosed(t, path+"[]", child)
		}
	}
}
