package main

import (
	"bytes"
	"testing"

	"waywarden/internal/distribution/contracts"
)

func TestVersion(t *testing.T) {
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"--version"}, &stdout, &stderr)

	if exitCode != 0 {
		t.Fatalf("exit code = %d, want 0", exitCode)
	}
	if got := stdout.String(); got != "waywarden 0.0.0-dev\n" {
		t.Fatalf("stdout = %q, want %q", got, "waywarden 0.0.0-dev\n")
	}
	if got := stderr.String(); got != "" {
		t.Fatalf("stderr = %q, want empty", got)
	}
}

func TestVersionJSONEmitsCanonicalCommandResult(t *testing.T) {
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"--version", "--output", "json"}, &stdout, &stderr)

	if exitCode != 0 {
		t.Fatalf("exit code = %d, want 0; stderr=%q", exitCode, stderr.String())
	}
	if got := stderr.String(); got != "" {
		t.Fatalf("stderr = %q, want empty", got)
	}
	var result contracts.CommandResult
	if err := contracts.StrictParseCanonical(stdout.Bytes(), &result); err != nil {
		t.Fatalf("stdout is not canonical command result: %v\n%s", err, stdout.String())
	}
	if result.Schema != contracts.SchemaCommandResult || result.Kind != contracts.ResultArtifact || result.Command != "version" || result.Status != contracts.ResultStatusSuccess {
		t.Fatalf("unexpected result: %+v", result)
	}
	if result.Artifact == nil || result.Artifact.Schema != contracts.SchemaCommandResult || result.Artifact.Label != "waywarden 0.0.0-dev" {
		t.Fatalf("unexpected version artifact: %+v", result.Artifact)
	}
	if err := contracts.ValidateSchema(contracts.SchemaCommandResult, stdout.Bytes()); err != nil {
		t.Fatalf("command result schema validation failed: %v", err)
	}
}

func TestOutputFlagRejectsUnknownFormat(t *testing.T) {
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"--version", "--output", "yaml"}, &stdout, &stderr)

	if exitCode != 2 {
		t.Fatalf("exit code = %d, want 2", exitCode)
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q, want empty", stdout.String())
	}
}
