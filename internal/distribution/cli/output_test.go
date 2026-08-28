package cli

import (
	"bytes"
	"testing"

	"waywarden/internal/distribution/contracts"
)

func TestWriteHumanVersion(t *testing.T) {
	var buf bytes.Buffer
	WriteHumanVersion(&buf, "waywarden", "0.0.0-dev")
	if got, want := buf.String(), "waywarden 0.0.0-dev\n"; got != want {
		t.Fatalf("output = %q, want %q", got, want)
	}
}

func TestWriteCommandResultJSONUsesCanonicalContracts(t *testing.T) {
	var buf bytes.Buffer
	result := contracts.CommandResult{Schema: contracts.SchemaCommandResult, Kind: contracts.ResultArtifact, Command: "version", Status: contracts.ResultStatusSuccess, Artifact: &contracts.ArtifactResult{Schema: contracts.SchemaCommandResult, SHA256: contracts.SHA256([]byte("0.0.0-dev")), Bytes: "9", Label: "waywarden 0.0.0-dev"}}
	if err := WriteCommandResultJSON(&buf, result); err != nil {
		t.Fatalf("WriteCommandResultJSON() error = %v", err)
	}
	if err := contracts.ValidateSchema(contracts.SchemaCommandResult, buf.Bytes()); err != nil {
		t.Fatalf("stdout does not validate as command-result: %v\n%s", err, buf.String())
	}
	if bytes.HasSuffix(buf.Bytes(), []byte("\n")) {
		t.Fatalf("canonical command result must not end with newline: %q", buf.String())
	}
}

func TestWritePublicErrorJSONUsesCanonicalContracts(t *testing.T) {
	var buf bytes.Buffer
	publicErr := contracts.PublicError{Schema: contracts.SchemaError, Code: "invalid_input", Message: "Invalid input.", Exit: contracts.ExitInvalidInput, Command: "version", Evidence: []contracts.EvidenceRef{}}
	if err := WritePublicErrorJSON(&buf, publicErr); err != nil {
		t.Fatalf("WritePublicErrorJSON() error = %v", err)
	}
	if err := contracts.ValidateSchema(contracts.SchemaError, buf.Bytes()); err != nil {
		t.Fatalf("stdout does not validate as public error: %v\n%s", err, buf.String())
	}
}
