# Context Save and Sweep Migration Design

**Date:** 2026-09-02

**Status:** Approved

**Governing ADRs:** ADR 0016, ADR 0018, ADR 0019

## Purpose

Adopt `context-save` and `sweep` into the dedicated skills repository, distribute them without copies, and remove skill ownership from chezmoi while preserving repository-local `chezmoi-drift` guidance.

## Canonical ownership

- `skills/context-save/` becomes the canonical global, portable adaptation of the Praxis skill. It preserves `source: pablontiv/praxis` and bundles the upstream PolyForm Noncommercial 1.0.0 license.
- `skills/sweep/` becomes the canonical self-contained bundle for the sweep workflow, portable shell assets, references, deterministic tests, and separate Claude/Pi subagent definitions.
- `/Users/Shared/infra/dotfiles/.agents/skills/chezmoi-drift/` becomes repository-local. It is excluded from chezmoi deployment and is never installed globally by dotfiles.

## Context-save contract

The migration starts from the current Praxis source rather than stale distributed copies. The adaptation:

- preserves save, restore, and list behavior;
- retains Rootline as a required runtime dependency and Backscroll as optional enrichment;
- uses current Rootline v2 schema vocabulary (`values`, not legacy `enum`);
- uses harness-neutral invocation wording rather than Claude-only `$ARGUMENTS` assumptions;
- writes project state under `.claude/session-state/` for compatibility with existing records;
- remains a documented process skill; it does not add an executable mutation helper;
- bundles provenance and the applicable upstream license.

## Sweep contract

The migration preserves the existing inspect-first workflow and the `--apply` authorization boundary. The bundle contains:

- `SKILL.md`;
- `assets/enumerate.sh`, `assets/facts.sh`, `assets/preflight.sh`, and `assets/test-assets.sh`;
- five reference documents;
- Claude adapters under `agents/claude/`;
- Pi adapters under `agents/pi/`;
- deterministic contract and asset tests.

The helpers remain POSIX shell and rely only on `git`, authenticated `gh`, and standard Unix utilities. `timeout` remains optional. Host roots are arguments, not embedded defaults in helpers.

Claude adapters use Claude tool names and return results through the parent-visible agent delivery mechanism. Pi adapters use lowercase Pi tool names, omit Claude-only model and color metadata, and return their final response directly to `subagent_run`. Neither adapter receives write tools. Because Bash cannot enforce read-only Git semantics, both retain explicit command prohibitions and the orchestrator independently verifies every deletion-supporting claim.

OpenCode receives the skill through `~/.agents/skills` but no subagent definitions in this delivery.

## Distribution topology

After the skills PR is merged:

```text
~/.agents/skills/context-save -> /Users/Shared/harness/skills/skills/context-save
~/.claude/skills/context-save -> /Users/Shared/harness/skills/skills/context-save
~/.agents/skills/sweep        -> /Users/Shared/harness/skills/skills/sweep
~/.claude/skills/sweep        -> /Users/Shared/harness/skills/skills/sweep

~/.claude/agents/{sweep-scout,sweep-triage,pr-investigator}.md
  -> /Users/Shared/harness/skills/skills/sweep/agents/claude/<name>.md

~/.pi/agent/subagents/{sweep-scout,sweep-triage,pr-investigator}.md
  -> /Users/Shared/harness/skills/skills/sweep/agents/pi/<name>.md
```

Gemini and OpenCode discover global skills from `~/.agents/skills`; no runtime-specific copy is created for either.

## Migration safety

1. Inventory each governed live path with `lstat`, resolved targets, chezmoi source mapping, and SHA-256 hashes.
2. Back up real directories/files outside discovery roots and verify backup hashes.
3. Bind the approved operation set to a digest before mutation.
4. Run `chezmoi forget` only for confirmed managed skill targets.
5. Replace approved paths with direct symlinks to the merged canonical checkout, never a temporary worktree.
6. Verify frontmatter discovery in Pi, Claude-path resolution, and subagent registration without running destructive sweep behavior.
7. Perform a restore drill from the backup manifest.
8. Do not run a global `chezmoi apply`.

## Dotfiles cleanup

- Move `dot_claude/skills/chezmoi-drift/SKILL.md` to `.agents/skills/chezmoi-drift/SKILL.md` and exclude `.agents/` in `.chezmoiignore`.
- Remove `dot_claude/skills/sweep/` and `dot_gemini/skills/symlink_context-save.tmpl`.
- Remove obsolete Git-hook logic that synchronizes `.claude/skills` globally.
- Update current architecture documentation that claims dotfiles owns or synchronizes global skills. Historical plans remain historical records.

## Testing and acceptance

- Each new skill begins with a failing deterministic contract test.
- Existing sweep asset tests pass unchanged except for portable path expectations.
- The complete existing repository suite remains green.
- ADR 0019 validates strictly.
- Both skills are delivered in one skills pull request referencing issue #11 and ADRs 0018/0019.
- Dotfiles contains no globally deployable `context-save`, `sweep`, or `chezmoi-drift` source.
- Live runtime links resolve to the merged canonical checkout and no temporary worktree.
