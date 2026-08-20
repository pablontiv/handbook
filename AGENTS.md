# Repository guidance

## Purpose

This repository publishes independent, portable Agent Skills. Keep every skill self-contained under `skills/<name>/` and avoid dependencies between sibling skills.

## Safety

- Treat inventory and planning as read-only operations.
- Require explicit, digest-bound approval before destructive actions.
- Back up and verify governed files before mutation.
- Fail closed on ambiguous ownership, path drift, symlinks, junctions, or unsupported structures.
- Never treat a textual match alone as permission to delete.

## Portability

- Support macOS, Linux, and Windows without hard-coded user paths.
- Prefer the Python standard library for helpers.
- Resolve user data from platform APIs and environment conventions.
- Test filesystem behavior in temporary homes; tests must never mutate the real home directory.

## Delivery

- Before implementation, identify and review the accepted ADR that governs the change. If a significant decision is not covered, add or update an ADR under `docs/adr/` and obtain acceptance before modifying code.
- Validate every new or modified ADR with `rootline validate --strict`.
- Use conventional commits.
- Keep documentation synchronized with executable behavior.
- Run the complete test suite before committing.
- Integrate changes through pull requests. Direct delivery to `main` requires an explicit human exception recorded with its rationale and accepted risk.
- In each pull request, list the ADRs reviewed, created, or modified and disclose unresolved governance conflicts.
