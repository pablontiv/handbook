package main

import (
	"os"
	"strings"
	"testing"
)

func TestGoModRetainsRequiredXSysPin(t *testing.T) {
	data, err := os.ReadFile("../../go.mod")
	if err != nil {
		t.Fatalf("read go.mod: %v", err)
	}
	if !strings.Contains(string(data), "golang.org/x/sys v0.47.0") {
		t.Fatalf("go.mod missing required pin for golang.org/x/sys v0.47.0")
	}
}
