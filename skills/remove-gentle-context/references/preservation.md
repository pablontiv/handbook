# Preservation matrix

Default stance: remove only artifact-contract-owned active Gentle AI context. Preserve infrastructure and history. Report-only when authority is ambiguous.

| Scope | Remove | Preserve | Report-only / blocker |
| --- | --- | --- | --- |
| Claude, Codex/ChatGPT, OpenCode active context | Owned generated registrations, governed config entries, and exact generated blocks present in inventory and plan | User-authored config, MCP settings, Engram links, non-Gentle prompts, messages, and historical sessions | Broken generated shapes, edited markers, unexpected ownership, or path/root ambiguity |
| MCP | Gentle-owned MCP registrations only when ownership catalog and preimage authority agree | Existing MCP servers, arguments, environment, and unrelated keys | Any uncertain MCP provenance; require user review |
| Engram | Active Gentle context pointer only when catalog-owned | Engram stores, chunks, indexes, package data, memory/history, and user content | Any Engram data-store mutation request; preserve and report |
| Packages, binaries, source | Declarative client registration entries that activate Gentle context | Installed packages, binaries, source trees, shims, lockfiles, and package-manager metadata | Package uninstall requests; this skill does not remove software installations |
| `node_modules` | Nothing by default | All `node_modules` contents, package infrastructure, and binary links | Report stale packages as preserved evidence only |
| History, prompts, messages | Nothing by default | Chat history, prompts, messages, transcripts, archives, caches, and backups | User asks to purge history; stop and replan outside this skill |
| Caches and backups | Nothing by default | Client caches, existing backups, generated receipts, backup manifests, and restore material | Cache cleanup requested; report limitation |
| `.git/gentle-ai` | Nothing by default | Repository-local Gentle metadata, locks, receipts, and review material | Any request to alter Git internals; stop unless a separate approved tool owns it |
| pablontiv personal skill veto/provenance | No personal skill removal | Personal skills, provenance notes, and user-owned skill registry entries | If provenance may identify a pablontiv personal skill, veto removal and report-only |
| Pi registry authority | Owned registry rows only when a reliable process probe and registry authority prove inactive generated context | Pi packages, package registry infrastructure, personal skills, and provenance | Current limitation: Pi registry deletion blocks without reliable process probe |
| Declarative adapters | Owned activation entries matching adapter contract | Adapter files, unrelated declarations, comments, source, packages, and runtime data | Unknown adapter version, ambiguous generated entry, or missing authority |
| Lifecycle actions | Planned explicit stop/start/reload actions after approval | Implicit restart is not allowed | If process identity is unreliable, block lifecycle action and replan |

## Practical rules

- Preserve beats remove when evidence conflicts.
- Report-only is success when the safe result is no mutation.
- Do not infer authority from grep hits, paths, names, markers, fingerprints, or author metadata alone.
- Ambiguity blockers require a new inventory and plan after evidence changes.
- Live verification must prove both removal targets and preservation assertions.
