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
{"adapter_layouts":{"claude":"builtin"},"adapter_versions":{"claude":"1"},"candidates":[{"artifact_class":"active-source","candidate_id":"claude:CLAUDE.md","client":"claude","dependencies":[],"details":{},"evidence":[{"marker":"gentle-ai:sdd-orchestrator"}],"ownership":"proven","path":"C:/gentle-example/home/.claude/CLAUDE.md","preimage":{"path":"C:/gentle-example/home/.claude/CLAUDE.md"},"proposed_action":"remove","reason":"generated Gentle context block"}],"digest":"sha256:37d161cfb15032353356681d6efd9af8a373ef31612fc5529ac7f0e34724a9cb","environment":{},"home":"C:/gentle-example/home","os_name":"windows","root_map":{"home":"C:/gentle-example/home"},"schema":"remove-gentle-context.inventory/v1"}
```

### Plan JSON

```json
{"adapter_layouts":{"claude":"builtin"},"adapter_versions":{"claude":"1"},"digest":"sha256:e6155b366e69a21d9863c9b1383c41e962b1124f464a5ad19aac01e1330a90d0","home":"C:/gentle-example/home","inventory_digest":"sha256:37d161cfb15032353356681d6efd9af8a373ef31612fc5529ac7f0e34724a9cb","operations":[{"candidate_id":"claude:CLAUDE.md","kind":"delete_file","path":"C:/gentle-example/home/.claude/CLAUDE.md","preimage_base64":"R2VudGxlIGNvbnRleHQK","preimage_sha256":"sha256:c43de5b456d36a8be030846166ad789f0eaed8686da1cf7ee2fd829c920fdf53"}],"os_name":"windows","preservation_assertions":[{"client":"claude","evidence":[{"scope":"mcp"}],"path":"C:/gentle-example/home/.claude/settings.json","reason":"MCP configuration is preservation-scoped"}],"root_map":{"home":"C:/gentle-example/home"},"schema":"remove-gentle-context.plan/v1"}
```

### Backup manifest JSON

```json
{"digest":"sha256:b0b8eb51c73d5a9b216ea5aa060589afb3d568ad08af371a0dc586f5f64e8cb9","entries":[{"kind":"delete_file","mode":384,"operation_index":0,"original_path":"C:/gentle-example/home/.claude/CLAUDE.md","payload_path":"rootfs/home/.claude/CLAUDE.md","relative_path":".claude/CLAUDE.md","root_id":"home","sha256":"sha256:c43de5b456d36a8be030846166ad789f0eaed8686da1cf7ee2fd829c920fdf53","size":15,"target_type":"file"}],"plan_digest":"sha256:e6155b366e69a21d9863c9b1383c41e962b1124f464a5ad19aac01e1330a90d0","schema":"remove-gentle-context.backup/v1"}
```

### Receipt JSON

```json
{"backup_manifest_path":"C:/gentle-example/state/remove-gentle-context/backups/example/manifest.json","checks":[{"code":"backup_manifest_digest","evidence":{"manifest_digest":"sha256:b0b8eb51c73d5a9b216ea5aa060589afb3d568ad08af371a0dc586f5f64e8cb9"},"severity":"info","status":"passed"}],"digest":"sha256:e71dba4dc7ff95b6be3d6d75df2bf8e0668c7f8301ae2c5a9fbb1bd9bfbe1474","inventory":{"adapter_layouts":{"claude":"builtin"},"adapter_versions":{"claude":"1"},"candidates":[{"artifact_class":"active-source","candidate_id":"claude:CLAUDE.md","client":"claude","dependencies":[],"details":{},"evidence":[{"marker":"gentle-ai:sdd-orchestrator"}],"ownership":"proven","path":"C:/gentle-example/home/.claude/CLAUDE.md","preimage":{"path":"C:/gentle-example/home/.claude/CLAUDE.md"},"proposed_action":"remove","reason":"generated Gentle context block"}],"digest":"sha256:37d161cfb15032353356681d6efd9af8a373ef31612fc5529ac7f0e34724a9cb","environment":{},"home":"C:/gentle-example/home","os_name":"windows","root_map":{"home":"C:/gentle-example/home"}},"lifecycle_outcomes":[],"operation_outcomes":[{"kind":"delete_file","operation_index":0,"path":"C:/gentle-example/home/.claude/CLAUDE.md","status":"completed"}],"plan":{"adapter_layouts":{"claude":"builtin"},"adapter_versions":{"claude":"1"},"digest":"sha256:e6155b366e69a21d9863c9b1383c41e962b1124f464a5ad19aac01e1330a90d0","home":"C:/gentle-example/home","inventory_digest":"sha256:37d161cfb15032353356681d6efd9af8a373ef31612fc5529ac7f0e34724a9cb","operations":[{"candidate_id":"claude:CLAUDE.md","kind":"delete_file","path":"C:/gentle-example/home/.claude/CLAUDE.md","preimage_base64":"R2VudGxlIGNvbnRleHQK","preimage_sha256":"sha256:c43de5b456d36a8be030846166ad789f0eaed8686da1cf7ee2fd829c920fdf53"}],"os_name":"windows","preservation_assertions":[{"client":"claude","evidence":[{"scope":"mcp"}],"path":"C:/gentle-example/home/.claude/settings.json","reason":"MCP configuration is preservation-scoped"}],"root_map":{"home":"C:/gentle-example/home"}},"schema":"remove-gentle-context.receipt/v1","status":"completed"}
```

### Verification JSON

```json
{"checks":[{"code":"verify_receipt_status","evidence":{"status":"completed"},"severity":"info","status":"passed"},{"code":"verify_operation_outcome","evidence":{"operation_index":0},"severity":"info","status":"passed"}],"digest":"sha256:7aae5166e786954cefed1462ac2a8bc780e15f4987e010f7fa8c012aa57662aa","schema":"remove-gentle-context.verification/v1","status":"passed"}
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
