# Skills

Public collection of portable Agent Skills maintained by Pablo Ontiveros.

Each skill is self-contained under `skills/<name>/` and may include deterministic helpers, references, fixtures, and tests. Repository-wide documentation lives under `docs/`.

## Available skills

- `model-optimizer` — optimize Pi and OpenCode model assignments with runtime-local evidence. The skill includes a read-only Python 3.11+ helper for inventory and bounded live checks. It does not automatically apply configuration, configure providers, install runtimes, or create fallback routing; online sources are metadata only. Install manually by copying or installing the self-contained `skills/model-optimizer/` directory through your Agent Skills mechanism.

## Planned skills

- `remove-gentle-context` — inventory, back up, remove, and verify active Gentle AI context while preserving infrastructure and history.

## Contributing

Pull requests are disabled. Use GitHub Issues to report defects or request capabilities.

## License

MIT
