package state

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io/fs"
	"path/filepath"

	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
)

type Journal interface {
	Append(context.Context, contracts.JournalEntry) (contracts.JournalRef, error)
	Entries() []contracts.JournalEntry
	Path() string
}

type journal struct {
	fs      filesystem.Adapter
	roots   Roots
	op      contracts.OperationID
	command contracts.CommandName
	path    string
	entries []contracts.JournalEntry
}

func (s *store) OpenJournal(ctx context.Context, roots Roots, op contracts.OperationID, command contracts.CommandName) (Journal, error) {
	if err := validateRoots(ctx, s.fs, roots); err != nil {
		return nil, err
	}
	if err := contracts.ValidateOperationID(op); err != nil {
		return nil, err
	}
	j := &journal{fs: s.fs, roots: roots, op: op, command: command, path: filepath.ToSlash(filepath.Join("runs", string(op), "journal.ndjson"))}
	entries, err := j.read(ctx)
	if err != nil {
		return nil, err
	}
	j.entries = entries
	return j, nil
}

func (j *journal) Append(ctx context.Context, entry contracts.JournalEntry) (contracts.JournalRef, error) {
	entries, err := j.read(ctx)
	if err != nil {
		return contracts.JournalRef{}, err
	}
	if entry.OperationID == "" {
		entry.OperationID = string(j.op)
	}
	if entry.OperationID != string(j.op) {
		return contracts.JournalRef{}, fmt.Errorf("journal entry operation_id = %q, want %q", entry.OperationID, j.op)
	}
	entry = normalizeJournalEntry(entries, entry, j.command)
	if err := validateJournalTransition(entries, entry); err != nil {
		return contracts.JournalRef{}, err
	}
	line, err := contracts.CanonicalBytes(entry)
	if err != nil {
		return contracts.JournalRef{}, err
	}
	appendBytes := append(append([]byte(nil), line...), '\n')
	if err := j.fs.EnsureDirSync(ctx, contracts.AbsolutePath(filepath.Dir(string(j.absolutePath())))); err != nil {
		return contracts.JournalRef{}, err
	}
	if err := j.fs.AppendFileSync(ctx, j.absolutePath(), appendBytes); err != nil {
		return contracts.JournalRef{}, err
	}
	data, err := j.fs.ReadFile(ctx, j.absolutePath())
	if err != nil {
		return contracts.JournalRef{}, err
	}
	j.entries = append(entries, entry)
	return contracts.JournalRef{OperationID: string(j.op), Path: j.path, SHA256: contracts.SHA256(data)}, nil
}

func (j *journal) Entries() []contracts.JournalEntry {
	return append([]contracts.JournalEntry(nil), j.entries...)
}

func (j *journal) Path() string { return j.path }

func (j *journal) absolutePath() contracts.AbsolutePath {
	return contracts.AbsolutePath(filepath.Join(string(j.roots.StateRoot), filepath.FromSlash(j.path)))
}

func (j *journal) read(ctx context.Context) ([]contracts.JournalEntry, error) {
	data, err := j.fs.ReadFile(ctx, j.absolutePath())
	if errors.Is(err, fs.ErrNotExist) {
		return []contracts.JournalEntry{}, nil
	}
	if err != nil {
		return nil, err
	}
	if len(data) == 0 {
		return []contracts.JournalEntry{}, nil
	}
	if !bytes.HasSuffix(data, []byte("\n")) {
		return nil, fmt.Errorf("journal has a partial tail")
	}
	lines := bytes.Split(bytes.TrimSuffix(data, []byte("\n")), []byte("\n"))
	entries := make([]contracts.JournalEntry, 0, len(lines))
	for _, line := range lines {
		if len(line) == 0 {
			return nil, fmt.Errorf("journal contains an empty entry")
		}
		var entry contracts.JournalEntry
		if err := contracts.StrictParseCanonical(line, &entry); err != nil {
			return nil, err
		}
		if entry.OperationID != string(j.op) {
			return nil, fmt.Errorf("journal operation_id mismatch")
		}
		if err := validateJournalTransition(entries, entry); err != nil {
			return nil, err
		}
		entries = append(entries, entry)
	}
	return entries, nil
}

func normalizeJournalEntry(entries []contracts.JournalEntry, entry contracts.JournalEntry, command contracts.CommandName) contracts.JournalEntry {
	if entry.Sequence == 0 {
		entry.Sequence = int64(len(entries) + 1)
	}
	if entry.Command == "" {
		entry.Command = string(command)
	}
	if entry.State == "" {
		entry.State = entry.Boundary
	}
	if isTerminalBoundary(entry.Boundary) {
		entry.Terminal = true
	}
	if entry.Boundary == "committed" && entry.FinalReceiptPath == "" {
		entry.FinalReceiptPath = entry.FinalArtifactPath
	}
	if entry.Boundary == "committed" && entry.FinalArtifactPath == "" {
		entry.FinalArtifactPath = entry.FinalReceiptPath
	}
	return entry
}

func validateJournalTransition(entries []contracts.JournalEntry, entry contracts.JournalEntry) error {
	next := entry.Boundary
	if next == "" {
		return fmt.Errorf("journal boundary is required")
	}
	if err := contracts.ValidateJournalEntry(entry, contracts.OperationID(entry.OperationID)); err != nil {
		return err
	}
	if entry.Sequence != int64(len(entries)+1) {
		return fmt.Errorf("journal sequence = %d, want %d", entry.Sequence, len(entries)+1)
	}
	if len(entries) == 0 {
		if next != "started" {
			return fmt.Errorf("journal must start with started")
		}
		return nil
	}
	last := entries[len(entries)-1].Boundary
	if isTerminalBoundary(last) {
		return fmt.Errorf("journal is terminal")
	}
	switch next {
	case "started":
		return fmt.Errorf("journal already started")
	case "ready_to_commit":
		if last != "started" {
			return fmt.Errorf("ready_to_commit must follow started")
		}
	case "committed":
		if last != "ready_to_commit" {
			return fmt.Errorf("committed must follow ready_to_commit")
		}
	case "rolled_back", "rollback_failed":
		if last == "committed" {
			return fmt.Errorf("rollback cannot follow committed")
		}
	default:
		return fmt.Errorf("unknown journal boundary %q", next)
	}
	return nil
}

func isTerminalBoundary(boundary string) bool {
	return boundary == "committed" || boundary == "rolled_back" || boundary == "rollback_failed"
}
