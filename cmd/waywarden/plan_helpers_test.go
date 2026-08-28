package main

import "os"

func mustReadFile(t interface {
	Helper()
	Fatalf(string, ...any)
}, path string) []byte {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return data
}
