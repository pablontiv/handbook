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

- Use conventional commits.
- Keep documentation synchronized with executable behavior.
- Run the complete test suite before committing.
- Pull requests are disabled; repository maintainers deliver changes directly.
