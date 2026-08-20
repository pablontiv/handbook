# remove-gentle-context contracts

This reference is normative for artifacts, approvals, authority, publication, recovery, and stable CLI behavior. `SKILL.md` is intentionally concise; use this file when implementing or reviewing automation.

## Exact CLI signatures

```bash
python scripts/cleanup.py inventory --home <absolute-home> --platform <linux|macos|windows> --output <inventory.json>
python scripts/cleanup.py plan --inventory <inventory.json> --output <plan.json>
python scripts/cleanup.py apply --inventory <inventory.json> --plan <plan.json> --approve <plan-digest> --receipt <receipt.json>
python scripts/cleanup.py verify --inventory <inventory.json> --plan <plan.json> --receipt <receipt.json> --output <verification.json>
python scripts/cleanup.py restore --manifest <backup-manifest.json> --receipt <receipt.json> --approve <manifest-digest> --output <restore.json>
```

`inventory` also accepts repeatable `--env KEY=VALUE` for bounded runtime roots and repeatable `--project-root <absolute-project>` for project-scoped discovery. Do not substitute shell `grep`, `find`, `rm`, editor macros, or client restart commands for these signatures.

## Approval format

After `plan`, present the digest and ask for this exact text:

```text
I approve remove-gentle-context plan sha256:<64-lower-hex>
```

Pass only the digest value to `apply --approve`. A changed byte in the plan invalidates the digest. `restore` has separate restore authority: pass the backup manifest digest to `restore --approve`; never reuse the plan digest as restore approval.

## Digest rules

All digests are canonical JSON SHA-256 strings (`sha256:<64-lower-hex>`). The plan and manifest digests omit their own digest field before hashing. Receipts and verification artifacts also compute their digest over the artifact with `digest` removed. Digest mismatches are artifact failures, not prompts to continue manually.

## Artifact examples

Compact examples show required shape, not exhaustive client payloads.

### Inventory JSON

```json
{"schema":"remove-gentle-context.inventory/v1","os_name":"linux","home":"/example/home","root_map":{"home":"/example/home","state":"/example/state"},"environment":{"XDG_STATE_HOME":"/example/state"},"adapter_versions":{"claude":"1"},"adapter_layouts":{"claude":"builtin"},"candidates":[{"id":"claude:CLAUDE.md:1","client":"claude","artifact_class":"active","ownership":"owned","path":"/example/home/.claude/CLAUDE.md","proposed_action":"remove"}],"findings":[],"digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

### Plan JSON

```json
{"schema":"remove-gentle-context.plan/v1","inventory_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","os_name":"linux","home":"/example/home","root_map":{"home":"/example/home","state":"/example/state"},"adapter_versions":{"claude":"1"},"adapter_layouts":{"claude":"builtin"},"operations":[{"id":"op-1","kind":"remove_block","path":"/example/home/.claude/CLAUDE.md","candidate_id":"claude:CLAUDE.md:1","preimage":{"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","size":80}}],"blocked_candidate_ids":[],"dependencies":[],"lifecycle_actions":[],"preservation_assertions":["mcp unchanged","history unchanged"],"digest":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}
```

### Backup manifest JSON

```json
{"schema":"remove-gentle-context.backup/v1","inventory_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","plan_digest":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","created_at":"2026-08-20T00:00:00Z","root_map":{"home":"/example/home","state":"/example/state"},"entries":[{"operation_id":"op-1","path":"/example/home/.claude/CLAUDE.md","backup_path":"/example/state/remove-gentle-context/backups/op-1","preimage_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","size":80}],"digest":"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"}
```

### Receipt JSON

```json
{"schema":"remove-gentle-context.receipt/v1","operation_outcomes":[{"operation_id":"op-1","status":"applied","backup_path":"/example/state/remove-gentle-context/backups/op-1"}],"backup_manifest_path":"/example/state/remove-gentle-context/backups/manifest.json","lifecycle_outcomes":[],"checks":[{"name":"preimage","status":"passed"}],"status":"completed","inventory":{"schema":"remove-gentle-context.inventory/v1","digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"plan":{"schema":"remove-gentle-context.plan/v1","digest":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"},"digest":"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"}
```

### Verification JSON

```json
{"schema":"remove-gentle-context.verification/v1","status":"passed","checks":[{"name":"live_state","status":"passed"},{"name":"preservation","status":"passed"}],"digest":"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"}
```

## root/environment binding

Inventory is the exact authority for `home`, `os_name`, `root_map`, and bounded environment keys. Later phases load that authority from the artifact; inherited environment overrides are ignored unless they were captured by inventory. Roots must be absolute, canonical, and not symlinks, junctions, or reparse points. Any path escape, OS mismatch, home mismatch, or plan/inventory binding mismatch fails closed.

## fd-bound validation and preimages

Before mutation, the implementation validates paths through canonical roots, rejects link traversal, and compares recorded preimages to live bytes. A changed preimage aborts before backup or mutation. A textual marker, name, path, fingerprint, or author field is evidence only when combined with catalog ownership and artifact authority.

## Stable exit codes

- `EXIT_USAGE = 2` — invalid arguments or unsupported Python runtime.
- `EXIT_UNSAFE_PATH = 11` — unsafe root, path escape, symlink, junction, or reparse-point condition.
- `EXIT_ARTIFACT = 12` — malformed schema, unknown fields, digest mismatch, or artifact binding failure.
- `EXIT_IO = 13` — operating-system I/O failure while reading or publishing artifacts.
- `EXIT_APPROVAL = 20` — plan or restore approval digest mismatch.
- `EXIT_APPLY = 21` — transaction failed after approval; inspect receipt and recovery state.
- `EXIT_VERIFY_FAILED = 30` — independent live verification failed.
- `EXIT_RESTORE = 40` — restore failed or restore authority was invalid.

## Atomic publication

The atomic publication contract is mandatory. Artifact and backup publication must be atomic: write to a temporary sibling, flush, and replace. Previous artifacts remain valid after interrupted publication. Apply must create a verified backup manifest before governed bytes are replaced. If any operation fails after backup, atomic rollback restores byte-identical preimages before reporting.

## recovery states

- `not_started`: no mutation attempted; rerun inventory or plan.
- `blocked`: ambiguous ownership, missing authority, unsupported structure, or Pi process probe unavailable; report only and replan after evidence changes.
- `backed_up`: verified backup exists, but mutation has not completed; restore authority is the manifest digest.
- `rolled_back`: apply failed and atomic rollback restored all preimages; run verify and report receipt.
- `completed`: receipt written and live verification is still required.
- `verified`: independent live verification passed.
- `restore_required`: live verification failed or manual recovery is needed; use `restore` with manifest digest approval.

## Receipt and live verification

The receipt records operation outcomes, lifecycle outcomes, checks, status, embedded inventory/plan authority, and backup manifest path. Verification must reread live state rather than trusting the receipt. Report receipt path, backup manifest path/digest, verification path, and any manual recovery note in the final answer.
