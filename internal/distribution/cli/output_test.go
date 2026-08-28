package cli

import (
	"bytes"
	"testing"
)

func TestWriteHumanVersion(t *testing.T) {
	var buf bytes.Buffer
	WriteHumanVersion(&buf, "waywarden", "0.0.0-dev")
	if got, want := buf.String(), "waywarden 0.0.0-dev\n"; got != want {
		t.Fatalf("output = %q, want %q", got, want)
	}
}
