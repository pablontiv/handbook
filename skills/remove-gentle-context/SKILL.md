---
name: remove-gentle-context
description: >-
  Use when an agent must clear active Gentle AI context from supported AI clients, stale generated registrations are suspected, or a user asks for Gentle context cleanup/removal.
---

# Remove Gentle Context

Non-destructive rule: inventory and planning are read-only; no mutation is allowed until the user approves the exact plan digest. Never improvise deletion commands outside scripts/cleanup.py.

## Quick path: five commands

```bash
python scripts/cleanup.py inventory --home <absolute-home> --platform <linux|macos|windows> --output <inventory.json>
python scripts/cleanup.py plan --inventory <inventory.json> --output <plan.json>
python scripts/cleanup.py apply --inventory <inventory.json> --plan <plan.json> --approve <plan-digest> --receipt <receipt.json>
python scripts/cleanup.py verify --inventory <inventory.json> --plan <plan.json> --receipt <receipt.json> --output <verification.json>
python scripts/cleanup.py restore --manifest <backup-manifest.json> --receipt <receipt.json> --approve <manifest-digest> --output <restore.json>
```

## Required operating sequence

1. Confirm Python 3.11+ and run from `skills/remove-gentle-context/`.
2. Explain preserved scope before touching artifacts: MCP, Engram, packages, binaries, source, `node_modules`, history, prompts, messages, caches, backups, `.git/gentle-ai`, and ambiguous/provenance-protected personal skills.
3. Build the canonical inventory. Summarize active, runtime, generated, broken, historical, preserved, ambiguous, and blocked counts.
4. Build the plan. Show every planned mutation and lifecycle action, including report-only blockers.
5. Ask the user to approve exactly: `I approve remove-gentle-context plan <plan-digest>`.
6. Apply only with that digest. No skipped plan approval; no edited plan; no alternate authority.
7. Run independent live verification and report receipt, verified backup manifest, verification output, and any manual recovery notes.

## Hard stops and replanning

Fail closed with ambiguity blockers when ownership, root/environment binding, fd-bound validation, preimage hashes, symlinks, junctions, reparse points, process state, or Pi registry authority are ambiguous. Stop and replan if inventory or plan bytes change, if any preimage drift is detected, if backup publication is not verified, if atomic rollback is needed, or if live verification fails.

Reject grep-driven, name-only, path-only, text-only, marker-only, fingerprint-only, and author-only deletion heuristics. Do not infer permission from file names, paths, text matches, Gentle markers, fingerprints, or authorship alone. Do not restart clients implicitly; propose lifecycle actions in the plan and require explicit approval.

See `references/contracts.md` for artifact schemas, exit codes, approval, authority, and recovery states. See `references/preservation.md` for the remove/preserve/report-only matrix.
