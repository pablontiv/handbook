package filesystem

import "testing"

func TestASCIICaseInsensitiveCollisionKeyKeepsExactIdentitiesDistinct(t *testing.T) {
	upper := `C:\Users\A\Skill`
	lower := `c:\users\a\skill`
	if upper == lower {
		t.Fatal("test requires distinct exact lexical identities")
	}

	upperKey, upperSupported := asciiCaseInsensitiveCollisionKey(upper)
	lowerKey, lowerSupported := asciiCaseInsensitiveCollisionKey(lower)
	if !upperSupported || !lowerSupported {
		t.Fatalf("ASCII identities marked unsupported: upper=%t lower=%t", upperSupported, lowerSupported)
	}
	if upperKey != lowerKey {
		t.Fatalf("collision keys differ: %q != %q", upperKey, lowerKey)
	}
	if upper != `C:\Users\A\Skill` || lower != `c:\users\a\skill` {
		t.Fatalf("exact identities were mutated: upper=%q lower=%q", upper, lower)
	}
}

func TestASCIICaseInsensitiveCollisionKeyMarksUnicodeUnsupported(t *testing.T) {
	_, supported := asciiCaseInsensitiveCollisionKey(`C:\Users\A\Skíll`)
	if supported {
		t.Fatal("Unicode case comparison was marked supported")
	}
}
