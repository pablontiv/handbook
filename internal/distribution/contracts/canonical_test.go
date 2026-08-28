package contracts

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestCanonicalBytesRFC8785SubsetVectors(t *testing.T) {
	tests := []struct {
		name  string
		value any
		want  string
	}{
		{
			name:  "sorts object keys compactly without newline",
			value: map[string]any{"b": int64(2), "a": int64(1)},
			want:  `{"a":1,"b":2}`,
		},
		{
			name:  "sorts nested keys and preserves array order",
			value: map[string]any{"z": []any{int64(2), int64(1)}, "a": map[string]any{"b": true, "a": nil}},
			want:  `{"a":{"a":null,"b":true},"z":[2,1]}`,
		},
		{
			name:  "uses minimal string escapes from the JCS subset",
			value: map[string]any{"s": "line\nquote\"slash/"},
			want:  `{"s":"line\nquote\"slash/"}`,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := CanonicalBytes(tt.value)
			if err != nil {
				t.Fatalf("CanonicalBytes() error = %v", err)
			}
			if string(got) != tt.want {
				t.Fatalf("canonical = %s, want %s", got, tt.want)
			}
			if strings.HasSuffix(string(got), "\n") {
				t.Fatalf("canonical output has trailing newline: %q", got)
			}
		})
	}
}

func TestStrictParseCanonicalRejectsNonCanonicalInputs(t *testing.T) {
	tests := []struct {
		name string
		data []byte
	}{
		{name: "bom", data: []byte{0xEF, 0xBB, 0xBF, '{', '}'}},
		{name: "duplicate keys", data: []byte(`{"a":1,"a":2}`)},
		{name: "trailing bytes", data: []byte(`{"a":1} {}`)},
		{name: "invalid utf8", data: []byte{'{', '"', 'a', '"', ':', '"', 0xff, '"', '}'}},
		{name: "float", data: []byte(`{"a":1.25}`)},
		{name: "exponent", data: []byte(`{"a":1e2}`)},
		{name: "noncanonical key order", data: []byte(`{"b":2,"a":1}`)},
		{name: "pretty printed", data: []byte("{\n  \"a\": 1\n}")},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var dst any
			if err := StrictParseCanonical(tt.data, &dst); err == nil {
				t.Fatalf("StrictParseCanonical(%q) succeeded, want error", tt.data)
			}
		})
	}
}

func TestSafeIntegerBoundary(t *testing.T) {
	accepted := []string{
		`{"n":-9007199254740991}`,
		`{"n":-9007199254740990}`,
		`{"n":9007199254740990}`,
		`{"n":9007199254740991}`,
	}
	for _, input := range accepted {
		t.Run("accept "+input, func(t *testing.T) {
			var dst any
			if err := StrictParseCanonical([]byte(input), &dst); err != nil {
				t.Fatalf("StrictParseCanonical() error = %v", err)
			}
		})
	}

	rejected := []string{
		`{"n":-9007199254740992}`,
		`{"n":9007199254740992}`,
	}
	for _, input := range rejected {
		t.Run("reject "+input, func(t *testing.T) {
			var dst any
			if err := StrictParseCanonical([]byte(input), &dst); err == nil {
				t.Fatalf("StrictParseCanonical() succeeded for unsafe integer")
			}
		})
	}
}

func TestCanonicalBytesRejectsFloatsBinaryStringsAndInvalidUTF8(t *testing.T) {
	for _, value := range []any{1.5, map[string]any{"bad": 1.5}, []byte("binary"), string([]byte{0xff})} {
		if _, err := CanonicalBytes(value); err == nil {
			t.Fatalf("CanonicalBytes(%T) succeeded, want error", value)
		}
	}
}

func TestStrictParseCanonicalUnmarshalsTypedDestination(t *testing.T) {
	var got struct {
		Schema SchemaID  `json:"schema"`
		Digest SHA256Hex `json:"digest"`
	}
	input := []byte(`{"digest":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","schema":"waywarden.test/v1"}`)
	canonical, err := CanonicalBytes(map[string]any{
		"schema": "waywarden.test/v1",
		"digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
	})
	if err != nil {
		t.Fatal(err)
	}
	if string(canonical) != string(input) {
		t.Fatalf("test fixture no longer canonical: %s", canonical)
	}
	if err := StrictParseCanonical(input, &got); err != nil {
		t.Fatalf("StrictParseCanonical() error = %v", err)
	}
	if got.Schema != "waywarden.test/v1" || got.Digest == "" {
		b, _ := json.Marshal(got)
		t.Fatalf("decoded = %s", b)
	}
}
