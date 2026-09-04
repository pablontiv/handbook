# Skill Portfolio Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge the five skills currently owned by this repository onto direct, verified global symlinks for Pi, OpenCode, and Claude without deleting or overwriting unverified user data.

**Architecture:** This is a host operation, not an installer implementation. A read-only evidence collector writes a deterministic, digest-addressed plan outside every runtime discovery root; the executor then performs only the approved operations, backs up the stale `model-optimizer` directory before replacement, verifies Pi and OpenCode through deterministic discovery APIs, verifies Claude in its live TUI, and removes the Pi-specific duplicate only after shared-root discovery succeeds.

**Tech Stack:** POSIX shell on the current macOS host, Python 3 standard library for read-only evidence and JSON receipts, Pi RPC `get_commands`, OpenCode `debug skill`, Claude Code TUI, filesystem symlinks.

**Spec:** `docs/superpowers/specs/2026-08-26-skill-ownership-and-distribution-design.md`

## Global Constraints

- ADR 0016 must be accepted and present in the durable primary checkout before execution.
- Run this plan from the durable primary checkout, never from a disposable Git worktree; the resulting symlinks outlive the execution branch.
- The initial delivery has no installer. The Python evidence collector in this plan is read-only and remains outside the repository.
- Repository-owned skills link directly to `~/.agents/skills` for Pi/OpenCode and `~/.claude/skills` for Claude.
- Do not create repository-owned duplicates under `~/.pi/agent/skills` or `~/.config/opencode/skills`.
- Inventory and planning are read-only.
- Every mutation requires approval of the exact SHA-256 plan digest produced from the observed preimages.
- Back up and hash-verify the real `~/.agents/skills/model-optimizer` directory before moving or replacing it.
- Fail closed on unexpected files, path types, owners, symlink targets, source drift, name collisions, or missing runtime discovery evidence.
- Never use `rm -rf`, `ln -sf`, recursive deletion, textual matches as deletion authority, or copy-based installation.
- `unlink` is permitted only for an approved symlink whose current raw and resolved targets still match the plan.
- Tests and restore drills use the run state directory; they never mutate unrelated home content.
- The TypeScript installer and its `uninstall`/`restore` commands are out of scope for this plan.
- Preserve existing unrelated working-tree changes and untracked files.

---

## Locked Artifact Structure

No repository source file changes during execution. The operation creates private state below the platform state root:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence/
├── active-run                         # absolute path of the one approved active run
└── YYYYMMDDTHHMMSSZ/
    ├── capture.py                     # read-only inventory/plan/preimage verifier
    ├── inventory.json                 # observed source and target state
    ├── plan.json                      # deterministic operations + SHA-256 digest
    ├── approval.txt                   # exact approved digest, written after human approval
    ├── operations.ndjson              # append-only mutation evidence
    ├── runtime-verification.json      # Pi/OpenCode/Claude discovery evidence
    ├── receipt.json                   # final result and rollback evidence
    └── backups/
        └── model-optimizer/
            ├── verified-copy/         # pre-mutation copy with matching tree digest
            └── original/              # original directory moved intact before linking
```

The plan defines these operation IDs:

```text
replace-agents-model-optimizer
link-agents-remove-gentle-context
link-claude-model-optimizer
link-claude-remove-gentle-context
link-claude-systemic-issue-triage
unlink-pi-systemic-issue-triage
```

Operations already satisfied at capture time are omitted. Any other state is a blocker.

---

### Task 1: Capture exact state and obtain digest-bound approval

**Files:**

- Create: `${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence/active-run`
- Create: `${run_dir}/capture.py`
- Create: `${run_dir}/inventory.json`
- Create: `${run_dir}/plan.json`
- Create after approval: `${run_dir}/approval.txt`

**Interfaces:**

- Produces: `capture.py capture REPO OUTPUT_DIR -> inventory.json + plan.json`
- Produces: `capture.py verify REPO PLAN OPERATION_ID -> exit 0 only when source and operation preimages still match`
- Produces: `capture.py digest PATH -> sha256:<tree digest>`
- Produces: `plan.json` with `schema = "harness-skills.convergence-plan/v1"`, ordered `operations`, `blockers`, and `digest`
- Approval authority: the exact `plan.json.digest`, not a skill name or verbal instruction

- [ ] **Step 1: Establish a private run directory and verify the durable checkout**

Run:

```bash
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
test -d "$repo/.git"
test "$repo" = "/Users/Shared/harness/skills"
git -C "$repo" merge-base --is-ancestor 444129a HEAD
rootline validate "$repo/docs/adr/0016-gobernar-propiedad-y-distribucion-de-skills-globales.md" --strict

state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
test ! -L "$state_root"
mkdir -p -m 700 "$state_root"
python3 - "$state_root" <<'PY'
import os, stat, sys
info = os.lstat(sys.argv[1])
if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
    raise SystemExit("unsafe_state_root_type")
if info.st_uid != os.getuid():
    raise SystemExit("unsafe_state_root_owner")
PY
test ! -e "$state_root/active-run"
test ! -L "$state_root/active-run"
run_dir="$state_root/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$run_dir"
printf '%s\n' "$run_dir" > "$state_root/active-run"
chmod 600 "$state_root/active-run"
printf 'run_dir=%s\n' "$run_dir"
```

Expected: ADR validation reports valid; the checkout is the durable `/Users/Shared/harness/skills` checkout; a new private run directory exists. If `active-run` already exists, stop and resolve that run rather than overwriting its evidence.

- [ ] **Step 2: Write the complete read-only evidence collector**

Run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
cat > "$run_dir/capture.py" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "harness-skills.convergence-plan/v1"
NAMES = (
    "adr",
    "decision-calibrator",
    "model-optimizer",
    "remove-gentle-context",
    "systemic-issue-triage",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def tree_digest(path: Path) -> str:
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise RuntimeError(f"not_directory:{path}")
    entries: list[dict[str, Any]] = []
    for current, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name in directories:
            candidate = current_path / name
            info = os.lstat(candidate)
            if stat.S_ISLNK(info.st_mode):
                raise RuntimeError(f"unexpected_symlink_in_directory:{candidate}")
            if not stat.S_ISDIR(info.st_mode):
                raise RuntimeError(f"unexpected_directory_entry:{candidate}")
            entries.append({
                "path": candidate.relative_to(root).as_posix() + "/",
                "type": "directory",
                "mode": stat.S_IMODE(info.st_mode),
            })
        for name in files:
            candidate = current_path / name
            info = os.lstat(candidate)
            if stat.S_ISLNK(info.st_mode):
                raise RuntimeError(f"unexpected_symlink_in_directory:{candidate}")
            if not stat.S_ISREG(info.st_mode):
                raise RuntimeError(f"unexpected_file_entry:{candidate}")
            entries.append({
                "path": candidate.relative_to(root).as_posix(),
                "type": "file",
                "mode": stat.S_IMODE(info.st_mode),
                "size": info.st_size,
                "digest": hash_file(candidate),
            })
    return digest_value(entries)


def tracked_source_digest(repo: Path, name: str) -> str:
    prefix = f"skills/{name}/"
    output = subprocess.check_output(
        ["git", "-C", str(repo), "ls-files", "-z", "--", f"skills/{name}"],
    )
    relative_paths = sorted(
        Path(item.decode("utf-8")) for item in output.split(b"\0") if item
    )
    if Path(prefix + "SKILL.md") not in relative_paths:
        raise RuntimeError(f"missing_tracked_skill:{name}")
    entries: list[dict[str, Any]] = []
    for relative in relative_paths:
        candidate = repo / relative
        info = os.lstat(candidate)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError(f"tracked_source_not_regular:{candidate}")
        entries.append({
            "path": relative.as_posix(),
            "mode": stat.S_IMODE(info.st_mode),
            "size": info.st_size,
            "digest": hash_file(candidate),
        })
    return digest_value(entries)


def snapshot(path: Path) -> dict[str, Any]:
    if not os.path.lexists(path):
        return {"type": "missing"}
    info = os.lstat(path)
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        return {
            "type": "symlink",
            "mode": mode,
            "target": os.readlink(path),
            "resolved": str(path.resolve(strict=False)),
        }
    if stat.S_ISDIR(info.st_mode):
        return {
            "type": "directory",
            "mode": mode,
            "digest": tree_digest(path),
        }
    if stat.S_ISREG(info.st_mode):
        return {
            "type": "file",
            "mode": mode,
            "size": info.st_size,
            "digest": hash_file(path),
        }
    return {"type": "unsupported", "mode": mode}


def write_json_exclusive(path: Path, value: Any) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def build(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    repo = repo.resolve(strict=True)
    home = Path.home().resolve(strict=True)
    sources = {name: repo / "skills" / name for name in NAMES}
    source_digests = {name: tracked_source_digest(repo, name) for name in NAMES}
    roots = {
        "agents": home / ".agents" / "skills",
        "claude": home / ".claude" / "skills",
        "pi": home / ".pi" / "agent" / "skills",
        "opencode": home / ".config" / "opencode" / "skills",
    }
    targets = {
        f"{root}:{name}": snapshot(path / name)
        for root, path in roots.items()
        for name in NAMES
    }
    blockers: list[str] = []
    operations: list[dict[str, Any]] = []

    def require_link(root: str, name: str) -> None:
        key = f"{root}:{name}"
        expected = str(sources[name].resolve(strict=True))
        observed = targets[key]
        if observed.get("type") != "symlink" or observed.get("resolved") != expected:
            blockers.append(f"required_link_mismatch:{key}")

    def add_link_if_missing(root: str, name: str, operation_id: str) -> None:
        key = f"{root}:{name}"
        path = roots[root] / name
        expected = str(sources[name].resolve(strict=True))
        observed = targets[key]
        if observed.get("type") == "missing":
            operations.append({
                "id": operation_id,
                "phase": "link",
                "kind": "create_symlink",
                "path": str(path),
                "target": expected,
                "before": observed,
                "source": name,
            })
        elif observed.get("type") == "symlink" and observed.get("resolved") == expected:
            return
        else:
            blockers.append(f"additive_link_blocked:{key}")

    require_link("agents", "adr")
    require_link("agents", "decision-calibrator")
    require_link("agents", "systemic-issue-triage")
    require_link("claude", "adr")
    require_link("claude", "decision-calibrator")

    model_key = "agents:model-optimizer"
    model_path = roots["agents"] / "model-optimizer"
    model_target = str(sources["model-optimizer"].resolve(strict=True))
    model_observed = targets[model_key]
    if model_observed.get("type") == "directory":
        operations.append({
            "id": "replace-agents-model-optimizer",
            "phase": "replace",
            "kind": "replace_directory_with_symlink",
            "path": str(model_path),
            "target": model_target,
            "before": model_observed,
            "source": "model-optimizer",
        })
    elif model_observed.get("type") == "symlink" and model_observed.get("resolved") == model_target:
        pass
    else:
        blockers.append(f"replacement_blocked:{model_key}")

    add_link_if_missing(
        "agents",
        "remove-gentle-context",
        "link-agents-remove-gentle-context",
    )
    add_link_if_missing(
        "claude",
        "model-optimizer",
        "link-claude-model-optimizer",
    )
    add_link_if_missing(
        "claude",
        "remove-gentle-context",
        "link-claude-remove-gentle-context",
    )
    add_link_if_missing(
        "claude",
        "systemic-issue-triage",
        "link-claude-systemic-issue-triage",
    )

    pi_key = "pi:systemic-issue-triage"
    pi_path = roots["pi"] / "systemic-issue-triage"
    pi_target = str(sources["systemic-issue-triage"].resolve(strict=True))
    pi_observed = targets[pi_key]
    if pi_observed.get("type") == "symlink" and pi_observed.get("resolved") == pi_target:
        operations.append({
            "id": "unlink-pi-systemic-issue-triage",
            "phase": "post-verification",
            "kind": "remove_duplicate_symlink",
            "path": str(pi_path),
            "target": pi_observed["target"],
            "resolved_target": pi_target,
            "before": pi_observed,
            "source": "systemic-issue-triage",
        })
    elif pi_observed.get("type") != "missing":
        blockers.append(f"duplicate_unlink_blocked:{pi_key}")

    for name in ("adr", "decision-calibrator", "model-optimizer", "remove-gentle-context"):
        if targets[f"pi:{name}"].get("type") != "missing":
            blockers.append(f"unexpected_pi_duplicate:pi:{name}")
    for name in NAMES:
        if targets[f"opencode:{name}"].get("type") != "missing":
            blockers.append(f"unexpected_opencode_duplicate:opencode:{name}")

    inventory = {
        "schema": "harness-skills.convergence-inventory/v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "hostname": platform.node(),
            "uid": os.getuid(),
            "home": str(home),
            "repo": str(repo),
        },
        "source_digests": source_digests,
        "targets": targets,
    }
    unsigned_plan = {
        "schema": SCHEMA,
        "host": inventory["host"],
        "source_digests": source_digests,
        "operations": operations,
        "blockers": blockers,
    }
    plan = dict(unsigned_plan)
    plan["digest"] = digest_value(unsigned_plan)
    return inventory, plan


def load_plan(path: Path) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    supplied = plan.pop("digest")
    actual = digest_value(plan)
    if supplied != actual:
        raise RuntimeError("plan_digest_mismatch")
    plan["digest"] = supplied
    return plan


def verify(repo: Path, plan_path: Path, operation_id: str) -> None:
    plan = load_plan(plan_path)
    repo = repo.resolve(strict=True)
    for name, expected in plan["source_digests"].items():
        actual = tracked_source_digest(repo, name)
        if actual != expected:
            raise RuntimeError(f"source_drift:{name}")
    matches = [operation for operation in plan["operations"] if operation["id"] == operation_id]
    if len(matches) != 1:
        raise RuntimeError(f"operation_not_unique:{operation_id}")
    operation = matches[0]
    actual = snapshot(Path(operation["path"]))
    if actual != operation["before"]:
        raise RuntimeError(f"preimage_drift:{operation_id}")
    print(f"preimage_verified:{operation_id}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: capture.py capture REPO OUTPUT_DIR | verify REPO PLAN OPERATION_ID | digest PATH")
    command = sys.argv[1]
    if command == "capture" and len(sys.argv) == 4:
        repo = Path(sys.argv[2])
        output = Path(sys.argv[3])
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        inventory, plan = build(repo)
        write_json_exclusive(output / "inventory.json", inventory)
        write_json_exclusive(output / "plan.json", plan)
        print(plan["digest"])
        return
    if command == "verify" and len(sys.argv) == 5:
        verify(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
        return
    if command == "digest" and len(sys.argv) == 3:
        print(tree_digest(Path(sys.argv[2])))
        return
    raise SystemExit("invalid arguments")


if __name__ == "__main__":
    main()
PY
chmod 700 "$run_dir/capture.py"
python3 -m py_compile "$run_dir/capture.py"
```

Expected: compile exits 0. The script contains no mutation function and writes only new evidence files beneath the caller-provided run directory.

- [ ] **Step 3: Generate and inspect the deterministic plan**

Run:

```bash
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 "$run_dir/capture.py" capture "$repo" "$run_dir/capture"
cp "$run_dir/capture/inventory.json" "$run_dir/inventory.json"
cp "$run_dir/capture/plan.json" "$run_dir/plan.json"
chmod 600 "$run_dir/inventory.json" "$run_dir/plan.json"
python3 - "$run_dir/plan.json" <<'PY'
import json
import sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
print("digest:", plan["digest"])
print("blockers:", len(plan["blockers"]))
for blocker in plan["blockers"]:
    print("BLOCKER", blocker)
for operation in plan["operations"]:
    print(operation["id"], operation["kind"], operation["path"], "=>", operation["target"])
if plan["blockers"]:
    raise SystemExit(2)
PY
```

Expected on the inventoried host: zero blockers and exactly the six operation IDs listed in the locked structure. Any blocker or different operation set stops execution and requires revising this implementation plan before seeking approval.

- [ ] **Step 4: Present the exact plan and stop for approval**

Show the user:

```bash
python3 -m json.tool "$run_dir/plan.json"
```

Ask the user to approve the literal digest printed under `digest`. Do not mutate any target while waiting. General approval of the spec, this implementation plan, or “continue” does not approve the live plan digest.

After the user supplies the exact digest, require them to paste it and compare it mechanically with the plan:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
plan_digest="$(python3 - "$run_dir/plan.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["digest"])
PY
)"
printf 'Paste the exact approved digest: '
IFS= read -r user_supplied_digest
test "$user_supplied_digest" = "$plan_digest"
printf '%s\n' "$user_supplied_digest" > "$run_dir/approval.txt"
chmod 600 "$run_dir/approval.txt"
test "$(cat "$run_dir/approval.txt")" = "$plan_digest"
```

Expected: `approval.txt` contains exactly the digest pasted by the user and that value equals `plan.json.digest`. A general “approved” response or any different digest fails the `test` and stops.

---

### Task 2: Back up and replace the stale `model-optimizer` directory

**Files:**

- Read: `${run_dir}/plan.json`
- Create: `${run_dir}/backups/model-optimizer/verified-copy/`
- Move: `~/.agents/skills/model-optimizer/` to `${run_dir}/backups/model-optimizer/original/`
- Create symlink: `~/.agents/skills/model-optimizer`
- Append: `${run_dir}/operations.ndjson`

**Interfaces:**

- Consumes: approved plan operation `replace-agents-model-optimizer`
- Preserves: verified copy and intact moved original outside runtime discovery roots
- Produces: direct symlink resolving to `<repo>/skills/model-optimizer`
- Rollback authority: `${run_dir}/backups/model-optimizer/original/`

- [ ] **Step 1: Verify approval, source identity, and the exact operation preimage**

Run:

```bash
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
plan_digest="$(python3 - "$run_dir/plan.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["digest"])
PY
)"
test "$(cat "$run_dir/approval.txt")" = "$plan_digest"
python3 "$run_dir/capture.py" verify \
  "$repo" "$run_dir/plan.json" replace-agents-model-optimizer
```

Expected: `preimage_verified:replace-agents-model-optimizer`. Any mismatch means regenerate a new plan and obtain new approval.

- [ ] **Step 2: Copy and hash-verify the backup before replacement**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
source_dir="$HOME/.agents/skills/model-optimizer"
backup_root="$run_dir/backups/model-optimizer"
mkdir -p -m 700 "$backup_root"
test ! -e "$backup_root/verified-copy"
test ! -e "$backup_root/original"
cp -a "$source_dir" "$backup_root/verified-copy"
source_digest="$(python3 "$run_dir/capture.py" digest "$source_dir")"
copy_digest="$(python3 "$run_dir/capture.py" digest "$backup_root/verified-copy")"
test "$source_digest" = "$copy_digest"
printf 'backup_verified %s\n' "$copy_digest"
```

Expected: the two tree digests are identical. Do not continue on a mismatch.

- [ ] **Step 3: Move the original intact and create the direct symlink**

Run:

```bash
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
target="$HOME/.agents/skills/model-optimizer"
source="$repo/skills/model-optimizer"
original="$run_dir/backups/model-optimizer/original"

mv "$target" "$original"
if ! ln -s "$source" "$target"; then
  mv "$original" "$target"
  exit 1
fi
if ! python3 - "$target" "$source" <<'PY'
from pathlib import Path
import os, sys
link, expected = Path(sys.argv[1]), Path(sys.argv[2]).resolve(strict=True)
if not link.is_symlink() or link.resolve(strict=True) != expected:
    raise SystemExit(1)
print(os.readlink(link))
PY
then
  unlink "$target"
  mv "$original" "$target"
  exit 1
fi
```

Expected: the command prints the raw target and the symlink resolves to the repository's `skills/model-optimizer` directory. Failure restores the intact original directory immediately.

- [ ] **Step 4: Record mutation evidence**

Run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir/operations.ndjson" "$run_dir/plan.json" <<'PY'
import datetime, json, sys
path, plan_path = sys.argv[1:]
plan = json.load(open(plan_path, encoding="utf-8"))
record = {
    "operation_id": "replace-agents-model-optimizer",
    "plan_digest": plan["digest"],
    "status": "completed",
    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open(path, "a", encoding="utf-8") as stream:
    stream.write(json.dumps(record, sort_keys=True) + "\n")
PY
chmod 600 "$run_dir/operations.ndjson"
```

Expected: one append-only JSON line records the approved operation and digest.

---

### Task 3: Add the four missing direct links

**Files:**

- Create symlink: `~/.agents/skills/remove-gentle-context`
- Create symlink: `~/.claude/skills/model-optimizer`
- Create symlink: `~/.claude/skills/remove-gentle-context`
- Create symlink: `~/.claude/skills/systemic-issue-triage`
- Append: `${run_dir}/operations.ndjson`

**Interfaces:**

- Consumes: four approved `create_symlink` operations and unchanged repository source digests
- Produces: direct links from both global roots to repository skill directories
- Safety property: `ln -s` without `-f` cannot replace an unexpected path

- [ ] **Step 1: Verify all four missing-path preimages before creating anything**

Run:

```bash
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
plan_digest="$(python3 - "$run_dir/plan.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["digest"])
PY
)"
test "$(cat "$run_dir/approval.txt")" = "$plan_digest"
for operation in \
  link-agents-remove-gentle-context \
  link-claude-model-optimizer \
  link-claude-remove-gentle-context \
  link-claude-systemic-issue-triage
do
  python3 "$run_dir/capture.py" verify "$repo" "$run_dir/plan.json" "$operation"
done
```

Expected: four `preimage_verified:` lines. A missing operation means the live state no longer matches this implementation plan; stop and revise the plan rather than editing commands ad hoc.

- [ ] **Step 2: Create the direct links without force or overwrite flags**

Run these four commands after all four approved preimages pass. The error trap removes only links created by this step and only while each still resolves to its recorded source:

```bash
set -eEuo pipefail
repo="$(git rev-parse --show-toplevel)"
created_paths=()
created_sources=()
rollback_created_links() {
  local index path source
  for ((index=${#created_paths[@]} - 1; index >= 0; index--)); do
    path="${created_paths[index]}"
    source="${created_sources[index]}"
    if python3 - "$path" "$source" <<'PY'
from pathlib import Path
import sys
path, source = Path(sys.argv[1]), Path(sys.argv[2]).resolve(strict=True)
raise SystemExit(0 if path.is_symlink() and path.resolve(strict=True) == source else 1)
PY
    then
      unlink "$path"
    else
      printf 'manual_recovery_required:%s\n' "$path" >&2
    fi
  done
}
trap rollback_created_links ERR
create_link() {
  local source="$1" path="$2"
  ln -s "$source" "$path"
  created_sources+=("$source")
  created_paths+=("$path")
}
create_link "$repo/skills/remove-gentle-context" \
  "$HOME/.agents/skills/remove-gentle-context"
create_link "$repo/skills/model-optimizer" \
  "$HOME/.claude/skills/model-optimizer"
create_link "$repo/skills/remove-gentle-context" \
  "$HOME/.claude/skills/remove-gentle-context"
create_link "$repo/skills/systemic-issue-triage" \
  "$HOME/.claude/skills/systemic-issue-triage"
python3 - <<'PY'
from pathlib import Path
repo = Path("/Users/Shared/harness/skills").resolve(strict=True)
checks = {
    Path.home() / ".agents/skills/remove-gentle-context": repo / "skills/remove-gentle-context",
    Path.home() / ".claude/skills/model-optimizer": repo / "skills/model-optimizer",
    Path.home() / ".claude/skills/remove-gentle-context": repo / "skills/remove-gentle-context",
    Path.home() / ".claude/skills/systemic-issue-triage": repo / "skills/systemic-issue-triage",
}
for path, source in checks.items():
    if not path.is_symlink() or path.resolve(strict=True) != source.resolve(strict=True):
        raise SystemExit(f"created_link_verification_failed:{path}")
PY
trap - ERR
```

Expected: all commands and the post-creation verification exit 0. Any failure triggers bounded rollback; an unexpected changed link is preserved and reported as `manual_recovery_required` rather than unlinked.

- [ ] **Step 3: Verify every repository-owned global link**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
repo = Path("/Users/Shared/harness/skills").resolve(strict=True)
roots = (Path.home() / ".agents" / "skills", Path.home() / ".claude" / "skills")
names = (
    "adr",
    "decision-calibrator",
    "model-optimizer",
    "remove-gentle-context",
    "systemic-issue-triage",
)
for root in roots:
    for name in names:
        link = root / name
        expected = (repo / "skills" / name).resolve(strict=True)
        if not link.is_symlink():
            raise SystemExit(f"not_symlink:{link}")
        if link.resolve(strict=True) != expected:
            raise SystemExit(f"wrong_target:{link}")
        print(f"verified:{link}")
PY
```

Expected: ten `verified:` lines.

- [ ] **Step 4: Append evidence for the four approved link operations**

Run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir/operations.ndjson" "$run_dir/plan.json" <<'PY'
import datetime, json, sys
path, plan_path = sys.argv[1:]
plan = json.load(open(plan_path, encoding="utf-8"))
allowed = {
    "link-agents-remove-gentle-context",
    "link-claude-model-optimizer",
    "link-claude-remove-gentle-context",
    "link-claude-systemic-issue-triage",
}
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
with open(path, "a", encoding="utf-8") as stream:
    for operation in plan["operations"]:
        if operation["id"] in allowed:
            stream.write(json.dumps({
                "operation_id": operation["id"],
                "plan_digest": plan["digest"],
                "status": "completed",
                "completed_at": now,
            }, sort_keys=True) + "\n")
PY
```

Expected: one evidence row for each link operation present in the approved plan.

---

### Task 4: Verify Pi, OpenCode, and Claude discovery before duplicate removal

**Files:**

- Create: `${run_dir}/verify_pi.py`
- Create: `${run_dir}/verify_opencode.py`
- Create: `${run_dir}/runtime-verification.json`
- Read only: Pi RPC command catalog
- Read only: OpenCode debug skill catalog
- Read only: Claude Code live slash-command completion

**Interfaces:**

- Consumes: the ten verified filesystem links
- Produces: `verify_pi.py OUTPUT EXPECTED_SYSTEMIC_ROOT`, where the root is `pi` before deduplication and `agents` afterward
- Produces: `verify_opencode.py OUTPUT`, requiring all five names from `~/.agents/skills`
- Produces: deterministic Pi and OpenCode catalogs plus a human-observed Claude TUI result
- Gate: `runtime-verification.json.all_passed == true` is required before Task 5

- [ ] **Step 1: Create and run the Pi RPC verifier without an LLM call**

Run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
cat > "$run_dir/verify_pi.py" <<'PY'
#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 3 or sys.argv[2] not in {"pi", "agents"}:
    raise SystemExit("usage: verify_pi.py OUTPUT EXPECTED_SYSTEMIC_ROOT")
output = Path(sys.argv[1])
systemic_root = sys.argv[2]
required = {
    "adr",
    "decision-calibrator",
    "model-optimizer",
    "remove-gentle-context",
    "systemic-issue-triage",
}
process = subprocess.Popen(
    ["pi", "--mode", "rpc", "--no-session", "--offline"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
stdout, stderr = process.communicate(
    json.dumps({"id": "skills", "type": "get_commands"}) + "\n",
    timeout=30,
)
if process.returncode != 0 or stderr.strip():
    raise SystemExit(f"pi_rpc_failed:{process.returncode}:{stderr[:200]}")
response = None
for line in stdout.splitlines():
    message = json.loads(line)
    if message.get("id") == "skills" and message.get("command") == "get_commands":
        response = message
if response is None or not response.get("success"):
    raise SystemExit("pi_get_commands_missing")
selected = {}
for command in response["data"]["commands"]:
    name = command.get("name", "").removeprefix("skill:")
    if name in required:
        if name in selected:
            raise SystemExit(f"pi_duplicate_name:{name}")
        selected[name] = command
if set(selected) != required:
    raise SystemExit(f"pi_missing:{sorted(required - set(selected))}")
for name, command in selected.items():
    if name == "systemic-issue-triage" and systemic_root == "pi":
        expected = Path.home() / ".pi" / "agent" / "skills" / name / "SKILL.md"
    else:
        expected = Path.home() / ".agents" / "skills" / name / "SKILL.md"
    path = Path(command["sourceInfo"]["path"])
    if path != expected:
        raise SystemExit(f"pi_wrong_source:{name}:{path}")
output.write_text(json.dumps(selected, sort_keys=True, indent=2) + "\n", encoding="utf-8")
print("pi_discovery_passed")
PY
chmod 700 "$run_dir/verify_pi.py"
python3 -m py_compile "$run_dir/verify_pi.py"
python3 "$run_dir/verify_pi.py" "$run_dir/pi-skills.json" pi
```

Expected: `pi_discovery_passed`. Before Task 5, `systemic-issue-triage` resolves from the approved Pi-specific duplicate; all other names resolve from `~/.agents`.

- [ ] **Step 2: Create and run the OpenCode debug verifier**

Run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
cat > "$run_dir/verify_opencode.py" <<'PY'
#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: verify_opencode.py OUTPUT")
required = {
    "adr",
    "decision-calibrator",
    "model-optimizer",
    "remove-gentle-context",
    "systemic-issue-triage",
}
result = subprocess.run(
    ["opencode", "debug", "skill"],
    check=True,
    capture_output=True,
    text=True,
    timeout=30,
)
items = json.loads(result.stdout)
selected = {}
for item in items:
    name = item.get("name")
    if name in required:
        if name in selected:
            raise SystemExit(f"opencode_duplicate_name:{name}")
        selected[name] = item
if set(selected) != required:
    raise SystemExit(f"opencode_missing:{sorted(required - set(selected))}")
for name, item in selected.items():
    expected = Path.home() / ".agents" / "skills" / name / "SKILL.md"
    if Path(item["location"]) != expected:
        raise SystemExit(f"opencode_wrong_source:{name}:{item['location']}")
Path(sys.argv[1]).write_text(
    json.dumps(selected, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print("opencode_discovery_passed")
PY
chmod 700 "$run_dir/verify_opencode.py"
python3 -m py_compile "$run_dir/verify_opencode.py"
python3 "$run_dir/verify_opencode.py" "$run_dir/opencode-skills.json"
```

Expected: `opencode_discovery_passed`, with exactly one entry per required name and every location under `~/.agents/skills`.

- [ ] **Step 3: Verify Claude Code discovery in the live TUI**

Run:

```bash
claude --bare
```

In the trusted TUI, type `/` and confirm that all five names are offered as skills:

```text
adr
decision-calibrator
model-optimizer
remove-gentle-context
systemic-issue-triage
```

Exit without invoking a skill or sending a model request. Record the observation only if all five names are visible. A filesystem link alone does not satisfy this step.

- [ ] **Step 4: Write the combined runtime gate**

After the Claude observation passes, run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir" <<'PY'
import datetime
import json
import subprocess
import sys
from pathlib import Path

run = Path(sys.argv[1])
required_files = (run / "pi-skills.json", run / "opencode-skills.json")
if not all(path.is_file() for path in required_files):
    raise SystemExit("deterministic_runtime_evidence_missing")
versions = {
    "pi": subprocess.check_output(["pi", "--version"], text=True).strip(),
    "opencode": subprocess.check_output(["opencode", "--version"], text=True).strip(),
    "claude": subprocess.check_output(["claude", "--version"], text=True).strip(),
}
result = {
    "schema": "harness-skills.runtime-verification/v1",
    "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "pi": "passed",
    "opencode": "passed",
    "claude_tui": "passed",
    "all_passed": True,
    "versions": versions,
}
(run / "runtime-verification.json").write_text(
    json.dumps(result, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
PY
chmod 600 "$run_dir/runtime-verification.json"
```

Expected: `runtime-verification.json` records three passing runtimes and their exact versions.

---

### Task 5: Remove the approved Pi-specific duplicate and reverify Pi

**Files:**

- Remove symlink only: `~/.pi/agent/skills/systemic-issue-triage`
- Append: `${run_dir}/operations.ndjson`
- Create: `${run_dir}/pi-skills-after-dedup.json`

**Interfaces:**

- Consumes: `runtime-verification.json.all_passed == true`
- Consumes: approved operation `unlink-pi-systemic-issue-triage`
- Produces: Pi discovery of `systemic-issue-triage` from `~/.agents/skills`
- Rollback: recreate the exact raw target recorded in `plan.json`

- [ ] **Step 1: Revalidate the runtime gate and exact symlink preimage**

Run:

```bash
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir/runtime-verification.json" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
if value.get("all_passed") is not True:
    raise SystemExit("runtime_gate_not_passed")
PY
python3 "$run_dir/capture.py" verify \
  "$repo" "$run_dir/plan.json" unlink-pi-systemic-issue-triage
```

Expected: `preimage_verified:unlink-pi-systemic-issue-triage`.

- [ ] **Step 2: Unlink only the verified duplicate**

Run:

```bash
set -euo pipefail
target="$HOME/.pi/agent/skills/systemic-issue-triage"
python3 - "$target" <<'PY'
from pathlib import Path
import os, sys
path = Path(sys.argv[1])
expected = Path("/Users/Shared/harness/skills/skills/systemic-issue-triage").resolve(strict=True)
if not path.is_symlink():
    raise SystemExit("pi_duplicate_not_symlink")
if path.resolve(strict=True) != expected:
    raise SystemExit("pi_duplicate_target_drift")
print(os.readlink(path))
PY
unlink "$target"
test ! -e "$target"
```

Expected: the command prints the raw target, removes only the symlink, and leaves the repository source intact.

- [ ] **Step 3: Prove Pi now resolves all five names from `~/.agents`**

Run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
target="$HOME/.pi/agent/skills/systemic-issue-triage"
raw_target="$(python3 - "$run_dir/plan.json" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
operation = next(item for item in plan["operations"] if item["id"] == "unlink-pi-systemic-issue-triage")
print(operation["target"])
PY
)"
if ! python3 "$run_dir/verify_pi.py" "$run_dir/pi-skills-after-dedup.json" agents; then
  test ! -e "$target"
  test ! -L "$target"
  ln -s "$raw_target" "$target"
  printf 'pi_duplicate_restored_after_verification_failure\n' >&2
  exit 1
fi
```

Expected: `pi_discovery_passed`, exactly one Pi command per required skill, and every `sourceInfo.path` under `~/.agents/skills`. Failure recreates the exact raw symlink target recorded by the approved plan before exiting nonzero.

- [ ] **Step 4: Record the approved unlink operation**

Run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir/operations.ndjson" "$run_dir/plan.json" <<'PY'
import datetime, json, sys
path, plan_path = sys.argv[1:]
plan = json.load(open(plan_path, encoding="utf-8"))
record = {
    "operation_id": "unlink-pi-systemic-issue-triage",
    "plan_digest": plan["digest"],
    "status": "completed",
    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open(path, "a", encoding="utf-8") as stream:
    stream.write(json.dumps(record, sort_keys=True) + "\n")
PY
```

Expected: the sixth approved operation is recorded when all six were required by the plan.

---

### Task 6: Run final verification and prove rollback material is usable

**Files:**

- Create: `${run_dir}/backups/model-optimizer/restore-drill/`
- Create: `${run_dir}/runtime-verification-final.json`
- Create: `${run_dir}/receipt.json`
- Move: `${state_root}/active-run` to `${state_root}/last-completed-run`

**Interfaces:**

- Consumes: approved plan, operation evidence, runtime evidence, verified backup copy, and intact original
- Produces: `receipt.json` with final filesystem/runtime status and rollback drill digest
- Completion condition: no repository-owned runtime duplicates and all five skills resolve through the approved shared roots

- [ ] **Step 1: Verify final filesystem topology and absence of runtime-specific duplicates**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
import os

repo = Path("/Users/Shared/harness/skills").resolve(strict=True)
names = (
    "adr",
    "decision-calibrator",
    "model-optimizer",
    "remove-gentle-context",
    "systemic-issue-triage",
)
for root in (Path.home() / ".agents" / "skills", Path.home() / ".claude" / "skills"):
    for name in names:
        link = root / name
        expected = (repo / "skills" / name).resolve(strict=True)
        if not link.is_symlink() or link.resolve(strict=True) != expected:
            raise SystemExit(f"final_link_failure:{link}")
for root in (Path.home() / ".pi" / "agent" / "skills", Path.home() / ".config" / "opencode" / "skills"):
    for name in names:
        if os.path.lexists(root / name):
            raise SystemExit(f"runtime_duplicate_remaining:{root / name}")
print("filesystem_topology_passed")
PY
```

Expected: `filesystem_topology_passed`.

- [ ] **Step 2: Re-run deterministic runtime discovery**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 "$run_dir/verify_pi.py" "$run_dir/pi-skills-final.json" agents
python3 "$run_dir/verify_opencode.py" "$run_dir/opencode-skills-final.json"
claude --bare
```

In the trusted Claude TUI, type `/` and confirm `adr`, `decision-calibrator`, `model-optimizer`, `remove-gentle-context`, and `systemic-issue-triage`, then exit without sending a model request.

After that observation passes, bind the final evidence:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir" <<'PY'
import datetime
import json
import subprocess
import sys
from pathlib import Path

run = Path(sys.argv[1])
for name in ("pi-skills-final.json", "opencode-skills-final.json"):
    if not (run / name).is_file():
        raise SystemExit(f"final_runtime_evidence_missing:{name}")
result = {
    "schema": "harness-skills.runtime-verification/v1",
    "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "pi": "passed",
    "opencode": "passed",
    "claude_tui": "passed",
    "all_passed": True,
    "pi_evidence": str(run / "pi-skills-final.json"),
    "opencode_evidence": str(run / "opencode-skills-final.json"),
    "versions": {
        "pi": subprocess.check_output(["pi", "--version"], text=True).strip(),
        "opencode": subprocess.check_output(["opencode", "--version"], text=True).strip(),
        "claude": subprocess.check_output(["claude", "--version"], text=True).strip(),
    },
}
(run / "runtime-verification-final.json").write_text(
    json.dumps(result, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
PY
chmod 600 "$run_dir/runtime-verification-final.json"
```

Expected: Pi and OpenCode each report one entry per name from `~/.agents`; Claude offers all five names from its global skill root; `runtime-verification-final.json` binds the post-deduplication evidence.

- [ ] **Step 3: Prove the backed-up directory can be restored without touching the live target**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
backup_root="$run_dir/backups/model-optimizer"
restore_drill="$backup_root/restore-drill"
test ! -e "$restore_drill"
cp -a "$backup_root/original" "$restore_drill"
original_digest="$(python3 "$run_dir/capture.py" digest "$backup_root/original")"
copy_digest="$(python3 "$run_dir/capture.py" digest "$backup_root/verified-copy")"
drill_digest="$(python3 "$run_dir/capture.py" digest "$restore_drill")"
test "$original_digest" = "$copy_digest"
test "$original_digest" = "$drill_digest"
printf 'restore_drill_passed %s\n' "$drill_digest"
```

Expected: all three directory digests match. This proves the backup material can reconstruct the preimage without replacing the live symlink.

- [ ] **Step 4: Write and validate the final receipt**

Run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir" <<'PY'
import datetime
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
plan = json.load(open(run / "plan.json", encoding="utf-8"))
operation_rows = [
    json.loads(line)
    for line in (run / "operations.ndjson").read_text(encoding="utf-8").splitlines()
    if line
]
completed = {row["operation_id"] for row in operation_rows if row["status"] == "completed"}
expected = {operation["id"] for operation in plan["operations"]}
if completed != expected:
    raise SystemExit(f"operation_receipt_mismatch:{sorted(expected - completed)}")
runtime = json.load(open(run / "runtime-verification-final.json", encoding="utf-8"))
if runtime.get("all_passed") is not True:
    raise SystemExit("final_runtime_verification_not_passed")
receipt = {
    "schema": "harness-skills.convergence-receipt/v1",
    "plan_digest": plan["digest"],
    "status": "completed",
    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "operations": sorted(completed),
    "runtime_verification": runtime,
    "backup_original": str(run / "backups/model-optimizer/original"),
    "backup_copy": str(run / "backups/model-optimizer/verified-copy"),
    "restore_drill": str(run / "backups/model-optimizer/restore-drill"),
}
(run / "receipt.json").write_text(
    json.dumps(receipt, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(receipt, sort_keys=True, indent=2))
PY
chmod 600 "$run_dir/receipt.json"
```

Expected: every operation in the approved plan has exactly one completed evidence row and the receipt status is `completed`.

- [ ] **Step 5: Close the active-run pointer without deleting evidence**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
test -f "$run_dir/receipt.json"
test ! -e "$state_root/last-completed-run"
mv "$state_root/active-run" "$state_root/last-completed-run"
test "$(cat "$state_root/last-completed-run")" = "$run_dir"
printf 'convergence_receipt=%s\n' "$run_dir/receipt.json"
```

Expected: no evidence is deleted; the last completed run points to the immutable receipt and backups.

## Emergency Rollback Contract

Rollback is not part of a successful execution. Use it only if a post-mutation verification fails, and only against the active run whose plan digest matches `approval.txt`.

The rollback order is the reverse of mutation order:

1. Recreate `~/.pi/agent/skills/systemic-issue-triage` from the raw target recorded by `unlink-pi-systemic-issue-triage`, but only if the path is still absent.
2. `unlink` only the four additive links whose operation IDs appear in the approved plan and whose targets still resolve to the recorded repository sources.
3. `unlink ~/.agents/skills/model-optimizer` only if it still resolves to the recorded repository source.
4. Move `${run_dir}/backups/model-optimizer/original` back to `~/.agents/skills/model-optimizer` only when the destination is absent.
5. Re-run Pi, OpenCode, and Claude discovery and write a receipt with status `rolled_back` or `manual_recovery_required`.

Never restore over an existing path, never delete the verified backup copy, and never report rollback success without comparing the restored directory digest to the approved preimage digest.
