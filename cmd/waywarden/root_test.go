package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestRootCommandHasExactlySixPrimarySubcommands(t *testing.T) {
	cmd := newRootCommand(&bytes.Buffer{}, &bytes.Buffer{})
	got := map[string]bool{}
	for _, sub := range cmd.Commands() {
		got[sub.Name()] = true
	}
	want := []string{"inventory", "plan", "apply", "verify", "uninstall", "restore"}
	if len(got) != len(want) {
		t.Fatalf("subcommands = %v, want %v", got, want)
	}
	for _, name := range want {
		if !got[name] {
			t.Fatalf("subcommands = %v, want %v", got, want)
		}
	}
}

func TestUnsupportedCommandExitsWithUsageErrorWithoutStackTrace(t *testing.T) {
	var stdout, stderr bytes.Buffer

	exitCode := Execute([]string{"unsupported"}, &stdout, &stderr)

	if exitCode != 2 {
		t.Fatalf("exit code = %d, want 2", exitCode)
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q, want empty", stdout.String())
	}
	if strings.Contains(stderr.String(), "panic:") || strings.Contains(stderr.String(), "goroutine ") {
		t.Fatalf("stderr contains stack trace: %q", stderr.String())
	}
}
