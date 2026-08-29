package filesystem_test

import (
	"context"
	"errors"
	"testing"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

func TestRound5AuthorityReadNoFollowRejectsSymlinkAndLocalUnsupported(t *testing.T) {
	ctx := context.Background()
	memory := filesystem.NewMemoryAdapter()
	regular := contracts.AbsolutePath("/state/runs/" + string(contracts.SHA256([]byte("op"))) + "/plan.json")
	memory.PutFile(regular, []byte("{}"))
	if got, err := memory.ReadFileNoFollow(ctx, regular); err != nil || string(got) != "{}" {
		t.Fatalf("memory ReadFileNoFollow regular = %q, %v", got, err)
	}

	link := contracts.AbsolutePath("/state/runs/" + string(contracts.SHA256([]byte("op2"))) + "/plan.json")
	memory.PutSymlink(link, "/outside/plan.json")
	if _, err := memory.ReadFileNoFollow(ctx, link); !errors.Is(err, filesystem.ErrUnsupportedCapability) {
		t.Fatalf("memory ReadFileNoFollow symlink error = %v, want ErrUnsupportedCapability", err)
	}

	if _, err := filesystem.NewLocalAdapter().ReadFileNoFollow(ctx, regular); !errors.Is(err, filesystem.ErrUnsupportedCapability) {
		t.Fatalf("local ReadFileNoFollow error = %v, want ErrUnsupportedCapability", err)
	}
}
