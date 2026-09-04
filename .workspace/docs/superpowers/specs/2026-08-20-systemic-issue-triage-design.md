# Systemic Issue Triage Skill Design

## Context

GitHub issue #1 requests a personal copy of the upstream `systemic-issue-triage` skill in this repository. The source is `Gentleman-Programming/gentle-ai` at commit `d1e1777faafc91a34656ba94bd712972dbe427a1`, authored by `Alan-TheGentleman` and declared under Apache-2.0. The verified upstream `SKILL.md` SHA-256 is `d0562fa1e2f8cee55222a208878821936922e0ac5d8702c204ae53aa0963f014`.

## Goal

Add one self-contained skill at `skills/systemic-issue-triage/`. Preserve the upstream root-class and clustering discipline while making the smallest changes needed for personal provenance and the repository workflow.

## Scope

The skill contains:

- `SKILL.md` with Agent Skills-compatible frontmatter and instructions;
- Apache-2.0 attribution inside the skill directory;
- skill-local pressure evidence required to verify the adaptation.

This change does not add an installer, receipts, a release registry, repository-wide metadata migration, cleanup integration, Router or harness integration, or any package-management mechanism.

## Skill contract

The adaptation retains these upstream behaviors:

- classify every source issue into exactly one bucket;
- cluster defects by root cause rather than proposing one patch per report;
- require verifiable source issues and named test evidence;
- reject unnecessary states, flags, verbs, gates, or parallel representations;
- distinguish symptoms from an issue's proposed mechanism.

Its output contains:

- verified source issues or tickets;
- bucket counts and per-issue classification;
- root-cause clusters;
- a proposed systemic initiative boundary;
- priority and dependency evidence;
- urgent flags;
- `brainstorming` as the named next skill for an approved initiative candidate.

The skill stops after triage. It must not design, plan, implement, mutate issues, or reproduce the delivery behavior of `brainstorming`, `writing-plans`, or other Superpowers skills.

## Metadata and attribution

`SKILL.md` declares:

- `name: systemic-issue-triage`;
- an activation-focused description;
- `license: Apache-2.0`;
- string metadata for personal author, created/updated dates, version, upstream author, upstream repository, upstream commit, and personal ownership.

Attribution remains explicit and self-contained in the skill directory. The adaptation must not be byte-identical to the upstream file because its provenance and output boundary differ.

## Verification

Before finalizing the adapted instructions:

1. Record RED pressure scenarios showing that the unadapted/local-missing state cannot provide the required triage output and boundary.
2. Run the same scenarios against the adaptation.
3. Verify root-class clustering, named evidence, initiative-boundary output, and handoff to `brainstorming`.
4. Verify that the skill never crosses into design, planning, implementation, or issue mutation.
5. Validate Agent Skills frontmatter and run the repository's complete existing test suite.

All test artifacts remain inside `skills/systemic-issue-triage/`; no sibling skill may depend on them.

## Files affected

Only the following product area is added:

```text
skills/systemic-issue-triage/
```

The design document and later implementation plan are delivery artifacts. Existing skills and runtime configuration remain unchanged.
