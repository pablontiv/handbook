# Handbook

Un handbook para convertir el trabajo de desarrollo improvisado en un método reproducible, verificable y adaptable.

Reúne reglas, skills, herramientas y memoria para orientar el trabajo de personas y agentes.

## What exists today

This repository is the handbook itself. Its current, versioned building blocks are:

- repository-wide operating rules in [`AGENTS.md`](AGENTS.md);
- portable agent workflows under [`skills/`](skills/);
- deterministic helpers, assets, references, fixtures, and tests bundled with their owning skills;
- cross-session memory guidance in [`context-save`](skills/context-save/);
- interaction contracts under [`output-styles/`](output-styles/);
- architecture decisions in [`docs/adr/`](docs/adr/) and design history in [`docs/superpowers/`](docs/superpowers/).

The integrated workspace method, workspace controller, and end-to-end delivery lifecycle are outside the current repository contract.

## Core model

The handbook organizes portable working artifacts around development needs rather than one agent runtime.

- **Rules** define repository-wide invariants and contribution boundaries.
- **Skills** provide self-contained workflows that agents can discover and follow.
- **Tools** provide deterministic evidence or guarded execution inside the artifact that owns them.
- **Memory** preserves context and decisions across sessions.
- **Records** preserve architecture and design history without rewriting past decisions.

Every published artifact must be globally useful, portable, publicly distributable, and explicitly owned. Product-coupled and repository-local workflows stay with their owning product or repository.

## Capabilities

### Make and preserve decisions

- [`adr`](skills/adr/) records, accepts, and supersedes architecture decisions through Rootline-governed records.
- [`decision-calibrator`](skills/decision-calibrator/) focuses rigor after corrections, context loss, stalled research, or high-operating-cost choices.

### Keep continuity across sessions

- [`context-save`](skills/context-save/) saves, restores, and lists structured session state with Rootline validation.

### Inspect repositories and portfolios

- [`systemic-issue-triage`](skills/systemic-issue-triage/) classifies a repository's issue backlog by verified systemic root causes and stops before design or delivery.
- [`sweep`](skills/sweep/) inventories and classifies stale worktrees, branches, and pull requests before any separately approved mutation.

### Optimize agent configuration with evidence

- [`model-optimizer`](skills/model-optimizer/) evaluates Pi and OpenCode model assignments with runtime-local evidence and explicit approval before native configuration edits.

### Remove active generated context safely

- [`skills/remove-gentle-context/`](skills/remove-gentle-context/) inventories, plans, applies, verifies, and restores supported Gentle AI context through digest-bound authority and verified backups. See its [`SKILL.md`](skills/remove-gentle-context/SKILL.md). Use a Python 3.11+ executable as `python`, `python3`, or an equivalent platform command.

### Shape agent interaction

- [`mentor-telemetria`](output-styles/mentor-telemetria.md) defines operating modes, decision telemetry, root-cause reporting, and post-task learning.

## Optional integrations

Individual artifacts may integrate with Pi, Claude Code, OpenCode, GitHub CLI, Rootline, Backscroll, or other tools. Those integrations are capability-specific; the linked artifact is the authority for supported runtimes, dependencies, and safety gates.

## References

- To use a skill capability, open its linked skill directory and read `SKILL.md`; for interaction style, open the linked output-style document.
- To contribute, follow [`AGENTS.md`](AGENTS.md).
- To understand current decisions, browse [`docs/adr/`](docs/adr/).
- To inspect approved designs and implementation history, browse [`docs/superpowers/`](docs/superpowers/).
- Repository content is available under the [`MIT License`](LICENSE), except where an artifact bundles and declares a different license.
