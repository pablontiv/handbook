# Skills

Public collection of portable Agent Skills maintained by Pablo Ontiveros.

Each skill is self-contained under `skills/<name>/` and may include deterministic helpers, references, fixtures, and tests. Repository-wide documentation lives under `docs/`.

Public repository URL: `https://github.com/pablontiv/gentle-ai`.

## Available skills

### `remove-gentle-context`

Use when active Gentle AI context must be cleared from supported clients while preserving infrastructure and history.

Quick discovery:

```bash
ls skills/remove-gentle-context
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

## Planned skills

- None currently listed.

## Contributing

Pull requests are disabled. Use GitHub Issues to report defects or request capabilities.

## License

MIT
