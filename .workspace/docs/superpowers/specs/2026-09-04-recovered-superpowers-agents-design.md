# Recovered Superpowers Agents Preservation Design

**Date:** 2026-09-04

**Status:** Approved design; preservation implementation pending

**Governing ADR:** ADR 0028

## Purpose

Preserve six owner-authored Superpowers agent definitions recovered after their accidental unbacked removal, making the Handbook their public canonical source without installing or activating them in any agent runtime.

## Source evidence

Immediately before the removal, a Pi session captured the complete bytes of all six files by printing each source file with `cat`. The preserved legacy runtime SQLite independently confirms that each recovered Markdown body is the prefix of the latest persisted `system_prompt` for the corresponding agent.

The recovered files and immutable content identities are:

| Agent definition | Bytes | SHA-256 |
| --- | ---: | --- |
| `superpowers-architecture-reviewer.md` | 805 | `26cac96c581f85433bd43752e5e67a2c88cb892292fdd9724e9e52fbb95d3ace` |
| `superpowers-debugger.md` | 795 | `841f9f30f8a43a07933009e9b38e30c2f8ba89b28990c36c7e43ed9895eb304c` |
| `superpowers-final-reviewer.md` | 814 | `945ff92aba278316eaf26940d568e06f4bf6ee210db445411d315461d7f040ab` |
| `superpowers-integration-worker.md` | 858 | `0f373d8964441ee840b7ac375a624c5139862aacb7ac478275137193cef93ad1` |
| `superpowers-mechanical-implementer.md` | 849 | `da191def49093359dd0917bf4ecb478283a08ed104a7bc19300e4499c017c3a6` |
| `superpowers-task-reviewer.md` | 805 | `e6e3c0658806c3dcbdd222c290b3f9a2d7e640c8646be6367abb0e8125ebce79` |

Original filesystem inode, birth time, modification time, and mode are not recoverable from the transcript. They are not part of the published content identity.

## Ownership and license

The repository owner confirmed that the six prompts are original, publicly distributable work. They are owned by the Handbook and published under the repository's MIT License. The word “Superpowers” describes their role family; it does not claim that the files are copied from or distributed by the external Superpowers package.

## Architecture

Create one top-level artifact family:

```text
agents/
├── README.md
└── superpowers/
    ├── provenance.json
    ├── superpowers-architecture-reviewer.md
    ├── superpowers-debugger.md
    ├── superpowers-final-reviewer.md
    ├── superpowers-integration-worker.md
    ├── superpowers-mechanical-implementer.md
    └── superpowers-task-reviewer.md
```

The six agent files are copied byte for byte from the verified recovery bundle. `provenance.json` records only portable evidence: schema, status, ownership, license, capture and deletion timestamps, recovery method, file names, byte counts, and hashes. It must not contain user names, home-directory paths, session paths, database paths, or host-specific identifiers.

`agents/README.md` explains the family's purpose, ownership, verification method, and portability boundary. The repository README links the family as preserved agent role definitions.

## Requirements

### R1 — Exact recovered content

The six published `.md` files MUST match the byte counts and SHA-256 values in Source evidence. This delivery MUST NOT normalize whitespace, modernize frontmatter, rename tools, combine roles, or change prompt wording.

### R2 — Portable provenance

`agents/superpowers/provenance.json` MUST be valid JSON and cover exactly the six published definitions. Its recorded byte counts and hashes MUST match the files. It MUST describe the capture as a pre-removal exact file print corroborated by persisted runtime prompts, without exposing local absolute paths or account identifiers.

### R3 — Explicit ownership and boundary

Documentation MUST identify the Handbook as owner and the repository MIT License as the distribution license. It MUST state that the definitions use Pi-oriented tool names and that `mem_save` requires a compatible memory integration.

### R4 — No activation

This delivery MUST NOT create or modify package manifests, Pi settings, runtime agent directories, symlinks, installers, model mappings, discovery configuration, or agent aliases. The recovered files remain reference artifacts until a later approved adaptation and activation decision.

### R5 — No new test surface

Per the owner's explicit scope, this delivery adds no test files and changes no existing tests. Verification is limited to direct content hashing, provenance parsing and comparison, documentation inspection, Rootline validation for governed records, repository diagnostics, and the complete existing suite required before commit.

## Non-goals

- Replace or disable any `pi-subagents` builtin.
- Adapt the historical definitions to current `pi-subagents` frontmatter or tool contracts.
- Restore the legacy `subagents.json` model profiles.
- Publish the private SQLite or session transcript used as corroborating evidence.
- Add automated installation, synchronization, recovery, or drift detection.
- Claim that the recovered definitions are currently executable on every supported runtime.

## Portability boundary

The content is portable as readable Markdown with simple YAML frontmatter. Execution is Pi-oriented because the tool lists name Pi tools and include `mem_save`. A consumer must map or provide those tools and independently validate runtime semantics before activation. The artifact family is not itself an agent runtime, package, or installer.

## Verification

Before commit:

1. compare every copied file byte-for-byte with the private recovery bundle;
2. recompute all six SHA-256 values and byte counts;
3. parse `provenance.json` and compare its inventory with the files;
4. scan published files for absolute home-directory or recovery-source paths;
5. verify the active Pi settings and subagent configuration hashes are unchanged;
6. validate ADR 0028 and this specification with Rootline;
7. run repository diagnostics and the complete existing test suite;
8. inspect the full Git diff and confirm no activation surface changed.

Delivery uses a pull request. Merge requires an independent review, green repository checks, and the owner's explicit merge authorization already granted for this bounded preservation change.
