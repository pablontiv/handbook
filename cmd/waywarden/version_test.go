package main

import (
	"bytes"
	"testing"
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
