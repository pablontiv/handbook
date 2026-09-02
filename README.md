# Skills

Public collection of portable Agent Skills maintained by Pablo Ontiveros.

Each skill is self-contained under `skills/<name>/` and may include deterministic helpers, references, fixtures, and tests. Repository-wide documentation lives under `docs/`.

Public repository URL: `https://github.com/pablontiv/gentle-ai`.

## Available skills

### `adr`

Use when a significant decision has just been made or overturned in a repository and must be recorded, accepted, or superseded as an Architecture Decision Record.

- Browse [`skills/adr/`](skills/adr/) and read [`SKILL.md`](skills/adr/SKILL.md).
- Mechanics run through `skills/adr/adr.sh` over `rootline`; run it with no arguments for usage.

### `context-save`

Save, restore, and list cross-session context as rootline-validated markdown records under `.claude/session-state/`.

- Browse [`skills/context-save/`](skills/context-save/) and read [`SKILL.md`](skills/context-save/SKILL.md).
- Provenance: adapted from `pablontiv/praxis` at commit `ad40aa3c3f08aed2caffd1343edbabe1f1f9ae00`.
- Bundles the PolyForm Noncommercial License 1.0.0 in [`LICENSE`](skills/context-save/LICENSE).

### `decision-calibrator`

Use after a concrete trigger — a user correction that contradicts a prior assumption, a re-asked question, resumed work after context loss, a stalled research loop, or a tool/architecture choice with ongoing operating cost — to spend rigor only where it can still change the outcome. Records checkpoints through the `adr` skill.

- Browse [`skills/decision-calibrator/`](skills/decision-calibrator/) and read [`SKILL.md`](skills/decision-calibrator/SKILL.md).

### `sweep`

Sweep stale worktrees, branches, and open pull requests across explicit roots. The skill is inspect-only by default: it reports with command-level evidence and mutates only across the documented `--apply` boundary.

- Browse [`skills/sweep/`](skills/sweep/) and read [`SKILL.md`](skills/sweep/SKILL.md).
- Bundles deterministic shell helpers under `assets/` plus evidence, tiering, fan-out, fork-mirror, and apply references.
- Runtime boundary: Claude receives Claude-native adapters in `agents/claude/` with parent-visible `SendMessage` delivery; Pi receives Pi-native adapters in `agents/pi/` whose final responses are delivered through `subagent_run`; OpenCode receives the skill only, without bundled agent definitions.

### `remove-gentle-context`

Use when active Gentle AI context must be cleared from supported clients while preserving infrastructure and history.

Quick discovery:

- Browse [`skills/remove-gentle-context/`](skills/remove-gentle-context/) and read [`SKILL.md`](skills/remove-gentle-context/SKILL.md).
- Run the helper help with your Python 3.11+ executable; the examples use `python`, but some platforms expose it as `python3` or `python3.11`.

```bash
python skills/remove-gentle-context/scripts/cleanup.py --help
```

Manual install:

1. Copy `skills/remove-gentle-context/` into an Agent Skills-compatible skills directory.
2. Keep `SKILL.md`, `scripts/`, `helper/`, `references/`, and adapter JSON files together.
3. Use Python 3.11+; the helper uses only the Python standard library.

Quick use from the skill directory:

```bash
python scripts/cleanup.py inventory --home <absolute-home> --platform <linux|macos|windows> --output <inventory.json>
python scripts/cleanup.py plan --inventory <inventory.json> --output <plan.json>
python scripts/cleanup.py apply --inventory <inventory.json> --plan <plan.json> --approve <plan-digest> --receipt <receipt.json>
python scripts/cleanup.py verify --inventory <inventory.json> --plan <plan.json> --receipt <receipt.json> --output <verification.json>
python scripts/cleanup.py restore --manifest <backup-manifest.json> --receipt <receipt.json> --approve <manifest-digest> --output <restore.json>
```

Supported clients and platforms:

- Clients: Claude, Codex/ChatGPT, OpenCode, Pi, and bundled declarative adapters for Gemini, Hermes, Kimi, and VS Code Copilot.
- Platforms: Linux, macOS, and Windows.
- CI: three-OS Python 3.11 unittest, CLI help, and compile checks without secrets or network-dependent tests.

Safety guarantees:

- Canonical inventory and plan approval are required before any mutation.
- Exact authority is bound to inventory root/environment data and plan digest.
- fd-bound validation, preimage hashes, verified backup, receipt, atomic rollback, and independent live verification are part of the contract.
- Ambiguity blockers fail closed; the ambiguity blockers contract prefers report-only over unsafe mutation.
- MCP, Engram, packages, binaries, source, `node_modules`, history, prompts, messages, caches, backups, `.git/gentle-ai`, and provenance-protected personal skills are preserved unless explicit contract authority says otherwise.

Current limitations:

- Pi registry deletion blocks without reliable process probe; the registry entry is reported instead of removed.
- The skill removes active generated Gentle context, not package installations, history archives, client caches, or user-authored source.
- Do not use grep-driven, name-only, path-only, text-only, marker-only, fingerprint-only, or author-only deletion shortcuts, skipped plan approval, or implicit restart.

Review path:

- Pull requests are disabled.
- Use GitHub Issues to report defects, unsafe behavior, missing preservation coverage, or client/platform support requests.
- Include inventory/plan/receipt/verification paths and digests when safe to share.

### `model-optimizer`

Optimize Pi and OpenCode model assignments with runtime-local evidence. The skill includes a read-only Python 3.11+ helper for inventory, bounded live checks, runtime-exact confined evaluations, and benchmark-prior cache entries. It does not provide a helper `apply`, `write`, or `configure` command; native configuration edits occur only inside the approved skill workflow after explicit approval, backup, validation, reload, and affected agent-path verification.

Install manually by copying or installing the self-contained [`skills/model-optimizer/`](skills/model-optimizer/) directory through your Agent Skills mechanism. See [`skills/model-optimizer/references/optimization-flow.md`](skills/model-optimizer/references/optimization-flow.md), [`skills/model-optimizer/references/benchmark-sources.md`](skills/model-optimizer/references/benchmark-sources.md), and [`skills/model-optimizer/references/contracts.md`](skills/model-optimizer/references/contracts.md) for the implemented workflow and contracts.

## Planned skills

- None currently listed.

## Contributing

Pull requests are disabled. Use GitHub Issues to report defects or request capabilities.

## License

MIT
