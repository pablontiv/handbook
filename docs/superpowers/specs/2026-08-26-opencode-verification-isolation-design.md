# OpenCode Verification Isolation Design

**Date:** 2026-08-26

**Status:** Approved correction

**Governing ADR:** ADR 0017

**Related specification:** `docs/superpowers/specs/2026-08-26-skill-ownership-and-distribution-design.md`

## Context and Evidence

The skill ownership and distribution design requires this repository's five first-party global skills to be discoverable through the shared `~/.agents/skills` root for Pi and OpenCode while preserving Claude discovery through `~/.claude/skills`.

OpenCode 1.18.19 also discovers skills from `~/.claude/skills`. On this host, OpenCode discovery across `~/.agents/skills` and `~/.claude/skills` is concurrent and unbounded. When both roots contain the same skill name, OpenCode can nondeterministically report either root as the winning location even when both entries are symlinks to the same canonical repository source.

The observed failure is therefore not repository source drift. It is verifier nondeterminism caused by duplicate runtime discovery roots. The approved evidence recorded in ADR 0017 establishes these host facts:

- OpenCode 1.18.19 can resolve duplicate skill names nondeterministically between `~/.agents/skills` and `~/.claude/skills`.
- The governed OpenCode gate must prove the shared OpenCode/Pi root, `~/.agents/skills`, not whichever duplicate root wins a race.
- Pipe-based command capture on this host truncates the approximately 343 KB `opencode debug skill` JSON payload at 65,536 bytes.
- File-backed stdout and stderr capture is required for reliable JSON parsing.
- Normal OpenCode configuration and user behavior are outside this repository's ownership boundary.

## Decision

Governed OpenCode verification is isolated per command invocation. Every governed `opencode debug skill` invocation must set the environment variable inline:

```bash
OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1 opencode debug skill
```

The repository must not persist, install, or manage this OpenCode setting. In particular, corrective work must not edit shell startup files, OpenCode configuration files, profile files, runtime roots, or private run artifacts to enforce this behavior globally.

The verifier must capture stdout and stderr to files and parse the stdout file after command completion. It must not rely on pipe capture for the JSON payload on this host.

The gate passes only when the parsed OpenCode skill inventory contains exactly these five names exactly once, and each corresponding `location` is under `~/.agents/skills`:

- `adr`
- `decision-calibrator`
- `model-optimizer`
- `remove-gentle-context`
- `systemic-issue-triage`

Claude links remain required and canonical for Claude discovery. The inline OpenCode isolation is a verification harness constraint only; it does not change the normal installation topology.

## Scope

This design governs only OpenCode discovery verification for this repository's first-party global skills during the approved ownership/distribution convergence work.

In scope:

- the verifier interface for `opencode debug skill`;
- inline per-invocation `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1`;
- file-backed stdout and stderr capture;
- fail-closed parsing and root assertions for the five governed skill names;
- documentation needed to resume the signed runtime work safely in a later corrective plan.

## Non-goals

This design does not:

- change normal OpenCode configuration or behavior;
- create, edit, or delete OpenCode configuration files;
- edit `~/.zshenv`, shell profiles, login hooks, or environment managers;
- remove or weaken required Claude skill links in `~/.claude/skills`;
- accept `~/.claude/skills` as an OpenCode verification root for the governed gate;
- mutate runtime skill roots;
- rewrite the original signed implementation plan or private run history;
- implement the verifier.

## Verifier Interface and Data Flow

The future verifier should expose one OpenCode verification step with this logical interface:

```text
verify_opencode_shared_root(expected_names, agents_root, timeout) -> verification_result
```

Required inputs:

| Input | Required value |
| --- | --- |
| `expected_names` | The exact five governed names listed in this design. |
| `agents_root` | The resolved `~/.agents/skills` directory for the current host. |
| `timeout` | A finite command timeout chosen by the implementation plan. |
| environment | Inline `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` for this command only. |

Required data flow:

1. Create a private temporary capture directory outside all runtime skill discovery roots.
2. Invoke `opencode debug skill` with `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` in that process environment.
3. Redirect stdout to a file and stderr to a separate file.
4. Wait for command completion with a finite timeout.
5. Reject nonzero exits, timeouts, and any stderr content before trusting stdout.
6. Read the stdout file as the complete JSON payload.
7. Parse the JSON strictly.
8. Extract OpenCode skill entries and normalize each reported location for comparison.
9. Filter to the five governed names.
10. Assert that every governed name appears exactly once.
11. Assert that every governed location is under `~/.agents/skills`.
12. Emit a machine-readable receipt containing command metadata, capture file paths or digests, parsed names, locations, and pass/fail reasons.

The verifier must treat the inline flag as an input precondition, not as an ambient shell assumption. If the implementation cannot prove that the invocation environment contained `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1`, it must fail before accepting OpenCode discovery output.

## Failure Handling

The OpenCode gate must fail closed for every condition that prevents deterministic proof of shared-root discovery:

| Condition | Required result |
| --- | --- |
| Inline `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` is absent or unprovable | Fail. |
| `opencode debug skill` times out | Fail. |
| `opencode debug skill` exits nonzero | Fail. |
| stderr is nonempty | Fail. |
| stdout capture file is missing, empty, truncated, or unreadable | Fail. |
| stdout is not valid JSON | Fail. |
| JSON shape does not contain the expected skill inventory | Fail. |
| Any governed name is missing | Fail. |
| Any governed name appears more than once | Fail. |
| Any governed name resolves outside `~/.agents/skills` | Fail. |
| Any path comparison is ambiguous because of symlink, resolution, permission, or normalization errors | Fail. |

Failures should be reported with enough structured evidence to distinguish verifier defects from runtime inventory defects. The report must not recommend persistent OpenCode configuration as remediation.

## Testing

A later implementation must test the verifier without mutating the real home directory.

Required fixture coverage:

- valid OpenCode JSON containing exactly the five governed names under `~/.agents/skills`;
- duplicate governed names;
- a missing governed name;
- a governed name under `~/.claude/skills`;
- a governed name under `~/.config/opencode/skills`;
- invalid JSON;
- command stderr;
- nonzero command exit;
- timeout;
- absent or unprovable inline `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1`;
- stdout payload larger than 65,536 bytes, read from a file-backed capture path.

Required live verification before any future corrective commit or runtime mutation:

1. Validate ADR 0017 with `rootline validate docs/adr/0017-aislar-discovery-opencode-solo-en-verificacion.md --strict`.
2. Run the complete repository test suite.
3. Run the OpenCode verifier with inline isolation and file-backed capture.
4. Confirm the receipt lists exactly the five governed names exactly once under `~/.agents/skills`.

## Governance and Resume Sequence

ADR 0017 is the accepted governance record for this correction. This specification documents how that decision constrains future implementation work.

The original signed runtime plan and any private run history remain immutable until a later corrective plan is written. A later corrective plan must explicitly resume from the signed state and incorporate this design before performing or re-verifying OpenCode runtime discovery.

Safe resume sequence:

1. Keep the existing Claude links required by the ownership specification.
2. Validate ADR 0017.
3. Commit this corrective specification and the concise reference from the original ownership specification.
4. Write a later corrective implementation plan that supersedes only the OpenCode verification portions of the current runtime plan.
5. Implement file-backed, inline-isolated OpenCode verification in that later plan.
6. Re-run governed verification and record the new receipt.

## Alternatives Rejected

### Persist `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` in shell startup files

Rejected. This repository does not own the user's shell environment or normal OpenCode behavior. Persisting the setting in `~/.zshenv`, profiles, or environment managers would create a global side effect outside the repository's scope.

### Manage OpenCode configuration from this repository

Rejected. The repository owns the first-party skill sources and their governed distribution expectations, not OpenCode runtime configuration. Editing OpenCode config files would blur product and repository ownership boundaries.

### Accept either `~/.agents/skills` or `~/.claude/skills` in the OpenCode gate

Rejected. The gate is intended to prove shared-root discovery through `~/.agents/skills`. Accepting either root would preserve nondeterminism and could hide a broken shared-root installation.

### Remove Claude links to avoid duplicate OpenCode names

Rejected. Claude links are required and canonical for Claude discovery. OpenCode verification must be isolated without breaking another runtime's required installation topology.

### Continue using pipe capture

Rejected. On this host, pipe capture truncates the approximately 343 KB OpenCode JSON payload at 65,536 bytes. File-backed capture is required before strict JSON parsing can be trusted.

### Rewrite the current signed implementation plan immediately

Rejected. The current plan and private runtime history are treated as immutable historical artifacts until a later corrective plan is explicitly written. This documentation correction records the approved design without altering that history.
