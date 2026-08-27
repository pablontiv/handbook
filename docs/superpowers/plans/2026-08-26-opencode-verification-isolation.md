# OpenCode Verification Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the non-deterministic OpenCode verification step with an inline-isolated, file-backed verifier, then safely resume the existing convergence run at Task 4 without changing persistent OpenCode configuration.

**Architecture:** Preserve the original signed plan, digest, approval, operation log, runtime links, and pre-correction verifier as immutable evidence. Add a new private verifier and tests under the existing active run; every OpenCode subprocess receives `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` in its own environment and writes stdout/stderr to private files before strict parsing. Once Pi, isolated OpenCode, and human-observed Claude discovery pass, resume the original Pi deduplication and final receipt flow, substituting only the new OpenCode verifier where the original plan referenced `verify_opencode.py`.

**Tech Stack:** Python 3 standard library (`unittest`, `subprocess`, `tempfile`, `pathlib`, `json`), Bash, Pi RPC, OpenCode 1.18.19 debug catalog, Claude Code trusted TUI, Rootline.

**Spec:** `docs/superpowers/specs/2026-08-26-opencode-verification-isolation-design.md`

## Global Constraints

- ADR 0017 is accepted and must validate with `rootline validate docs/adr/0017-aislar-discovery-opencode-solo-en-verificacion.md --strict` before execution.
- The original plan `docs/superpowers/plans/2026-08-26-skill-portfolio-convergence.md`, its private `plan.json`, digest `sha256:a43a815539f41c49d9b9bd52791b7995f31924da041858e9dd9623c9ce226310`, `approval.txt`, and existing operation rows are immutable historical evidence.
- Resume only the active run named by `${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence/active-run`; do not create a second run.
- Do not overwrite or delete `${run_dir}/verify_opencode.py`, `${run_dir}/opencode-skills.json`, or the interim Task 4 report. They document the failed pre-correction assumption.
- Do not persist `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS`; do not edit shell profiles, OpenCode configuration, launchers, aliases, runtime roots, or environment managers.
- Set `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` only in the environment passed to each governed `opencode debug skill` subprocess.
- Capture OpenCode stdout and stderr in private files, never with `subprocess.PIPE` or `capture_output=True`.
- Treat any stderr byte, nonzero exit, timeout, invalid JSON, missing governed name, duplicate governed name, wrong lexical location, unresolvable path, or wrong canonical target as failure.
- Permit non-governed OpenCode inventory entries; they do not affect pass/fail.
- Compare each governed reported location lexically to the exact absolute `~/.agents/skills/<name>/SKILL.md` path without resolving symlinks; separately resolve strictly to `<repo>/skills/<name>/SKILL.md`.
- Tests must use temporary homes and fake executables; they must never mutate the real home directory.
- Claude verification requires a trusted live normal-mode TUI observation. Launch `claude` with no `--bare` or `--safe-mode` flags for governed discovery verification; a filesystem link, cached catalog, reduced-mode catalog, or automated inference does not satisfy it.
- Reduced mode is incompatible with Claude discovery verification: verified `claude --bare --debug` evidence showed `[reduced mode] Skipping skill dir discovery`, `getSkills returning: 0 skill dir commands`, and `/adr` autocomplete had no match. Use `--debug` only for troubleshooting, not as a required gate condition.
- Do not remove `~/.pi/agent/skills/systemic-issue-triage` until corrected `runtime-verification.json.all_passed == true`.
- Preserve unrelated worktree changes and untracked files. Stage only the plan file when committing this plan.

---

### Task 1: Build the isolated OpenCode verifier with fixture-driven tests

**Files:**

- Create: `${run_dir}/verify_opencode_isolated.py`
- Create: `${run_dir}/test_verify_opencode_isolated.py`
- Create during tests only: temporary homes, canonical skill roots, fake `opencode` executables, and payload files under `tempfile.TemporaryDirectory()`
- Preserve read-only: `${run_dir}/verify_opencode.py`

**Interfaces:**

- Produces: `verify_opencode_isolated.py OUTPUT CANONICAL_REPO_SKILL_ROOT TIMEOUT_SECONDS`
- Produces: exclusive mode-`0600` JSON receipt at `OUTPUT`
- Receipt schema: `harness-skills.opencode-verification/v1`
- Exit success: prints `opencode_isolated_discovery_passed`
- Exit failure: one stable `opencode_*` reason on stderr, nonzero status, and no receipt

- [ ] **Step 1: Write the failing unittest suite**

Resolve the active run, require the new files to be absent, and write this test file exactly:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
test -d "$run_dir"
test ! -L "$run_dir"
test ! -e "$run_dir/test_verify_opencode_isolated.py"
test ! -e "$run_dir/verify_opencode_isolated.py"
cat > "$run_dir/test_verify_opencode_isolated.py" <<'PY'
#!/usr/bin/env python3
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REQUIRED = (
    "adr",
    "decision-calibrator",
    "model-optimizer",
    "remove-gentle-context",
    "systemic-issue-triage",
)
VERIFIER = Path(__file__).with_name("verify_opencode_isolated.py")


class IsolatedVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        self.payload = self.root / "payload.json"
        self.repo_skills = self.root / "repo" / "skills"
        self.home.mkdir()
        self.bin.mkdir()
        self.repo_skills.mkdir(parents=True)
        agents = self.home / ".agents" / "skills"
        agents.mkdir(parents=True)
        for name in REQUIRED:
            source = self.repo_skills / name
            source.mkdir()
            (source / "SKILL.md").write_text(f"---\nname: {name}\ndescription: fixture\n---\n", encoding="utf-8")
            (agents / name).symlink_to(source, target_is_directory=True)
        fake = self.bin / "opencode"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, sys, time\n"
            "if os.environ.get('OPENCODE_DISABLE_CLAUDE_CODE_SKILLS') != '1':\n"
            "    print('inline_flag_missing', file=sys.stderr); raise SystemExit(91)\n"
            "delay = float(os.environ.get('FAKE_OPENCODE_DELAY', '0'))\n"
            "if delay: time.sleep(delay)\n"
            "stderr = os.environ.get('FAKE_OPENCODE_STDERR', '')\n"
            "if stderr: sys.stderr.write(stderr)\n"
            "payload = pathlib.Path(os.environ['FAKE_OPENCODE_PAYLOAD']).read_bytes()\n"
            "sys.stdout.buffer.write(payload)\n"
            "raise SystemExit(int(os.environ.get('FAKE_OPENCODE_EXIT', '0')))\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)

    def items(self):
        values = []
        for name in REQUIRED:
            values.append({
                "name": name,
                "description": "fixture",
                "location": str(self.home / ".agents" / "skills" / name / "SKILL.md"),
            })
        return values

    def run_verifier(self, items=None, raw=None, timeout="3", extra_env=None, output_name="receipt.json"):
        if raw is None:
            raw = json.dumps(self.items() if items is None else items)
        self.payload.write_text(raw, encoding="utf-8")
        output = self.root / output_name
        env = os.environ.copy()
        env.update({
            "HOME": str(self.home),
            "PATH": str(self.bin) + os.pathsep + env.get("PATH", ""),
            "FAKE_OPENCODE_PAYLOAD": str(self.payload),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(
            [sys.executable, str(VERIFIER), str(output), str(self.repo_skills), timeout],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            timeout=8,
        )
        return result, output

    def assert_failure(self, expected, **kwargs):
        result, output = self.run_verifier(**kwargs)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(expected, result.stderr)
        self.assertFalse(output.exists())

    def test_valid_large_payload_extra_names_and_receipt_paths(self):
        items = self.items()
        items.append({"name": "unmanaged", "description": "x" * 70000, "location": "/tmp/unmanaged/SKILL.md"})
        result, output = self.run_verifier(items=items)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("opencode_isolated_discovery_passed", result.stdout)
        receipt = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(receipt["schema"], "harness-skills.opencode-verification/v1")
        self.assertEqual(receipt["governed_names"], list(REQUIRED))
        self.assertEqual(receipt["full_inventory_count"], 6)
        self.assertEqual(receipt["non_governed_count"], 1)
        self.assertEqual(receipt["inline_environment"], {"OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1"})
        for name in REQUIRED:
            entry = receipt["entries"][name]
            expected_lexical = str(self.home / ".agents" / "skills" / name / "SKILL.md")
            expected_resolved = str((self.repo_skills / name / "SKILL.md").resolve(strict=True))
            self.assertEqual(entry["reported_lexical"], expected_lexical)
            self.assertEqual(entry["expected_lexical"], expected_lexical)
            self.assertEqual(entry["reported_resolved"], expected_resolved)
            self.assertEqual(entry["expected_resolved"], expected_resolved)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)

    def test_duplicate_governed_name_fails(self):
        items = self.items() + [self.items()[0]]
        self.assert_failure("opencode_duplicate_name:adr", items=items)

    def test_missing_governed_name_fails(self):
        self.assert_failure("opencode_missing", items=self.items()[:-1])

    def test_claude_location_fails(self):
        items = self.items()
        items[0]["location"] = str(self.home / ".claude" / "skills" / "adr" / "SKILL.md")
        self.assert_failure("opencode_wrong_lexical_source:adr", items=items)

    def test_opencode_config_location_fails(self):
        items = self.items()
        items[0]["location"] = str(self.home / ".config" / "opencode" / "skills" / "adr" / "SKILL.md")
        self.assert_failure("opencode_wrong_lexical_source:adr", items=items)

    def test_agents_descendant_but_not_exact_path_fails(self):
        items = self.items()
        items[0]["location"] = str(self.home / ".agents" / "skills" / "adr" / "nested" / "SKILL.md")
        self.assert_failure("opencode_wrong_lexical_source:adr", items=items)

    def test_wrong_canonical_target_fails(self):
        wrong = self.root / "wrong" / "adr"
        wrong.mkdir(parents=True)
        (wrong / "SKILL.md").write_text("wrong\n", encoding="utf-8")
        link = self.home / ".agents" / "skills" / "adr"
        link.unlink()
        link.symlink_to(wrong, target_is_directory=True)
        self.assert_failure("opencode_wrong_resolved_source:adr")

    def test_missing_path_component_fails(self):
        link = self.home / ".agents" / "skills" / "adr"
        link.unlink()
        self.assert_failure("opencode_path_resolution_failed:adr")

    def test_symlink_loop_fails(self):
        link = self.home / ".agents" / "skills" / "adr"
        link.unlink()
        link.symlink_to(link)
        self.assert_failure("opencode_path_resolution_failed:adr")

    def test_permission_error_fails(self):
        blocked = self.root / "blocked"
        source = blocked / "adr"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("blocked\n", encoding="utf-8")
        link = self.home / ".agents" / "skills" / "adr"
        link.unlink()
        link.symlink_to(source, target_is_directory=True)
        blocked.chmod(0)
        self.addCleanup(lambda: blocked.chmod(0o700))
        self.assert_failure("opencode_path_resolution_failed:adr")

    def test_invalid_json_fails(self):
        self.assert_failure("opencode_invalid_json", raw="{not-json")

    def test_invalid_inventory_shape_fails(self):
        self.assert_failure("opencode_invalid_inventory", raw=json.dumps({"name": "adr"}))

    def test_stderr_fails_even_with_zero_exit(self):
        self.assert_failure("opencode_stderr", extra_env={"FAKE_OPENCODE_STDERR": "warning\n"})

    def test_nonzero_exit_fails(self):
        self.assert_failure("opencode_nonzero_exit:7", extra_env={"FAKE_OPENCODE_EXIT": "7"})

    def test_timeout_fails_cleanly(self):
        self.assert_failure("opencode_timeout", timeout="0.05", extra_env={"FAKE_OPENCODE_DELAY": "1"})

    def test_existing_output_fails_without_overwrite(self):
        output = self.root / "receipt.json"
        output.write_text("sentinel\n", encoding="utf-8")
        result, actual = self.run_verifier(output_name="receipt.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("opencode_output_exists", result.stderr)
        self.assertEqual(actual.read_text(encoding="utf-8"), "sentinel\n")


if __name__ == "__main__":
    unittest.main()
PY
chmod 700 "$run_dir/test_verify_opencode_isolated.py"
```

- [ ] **Step 2: Run the tests to verify they fail before implementation**

Run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
PYTHONDONTWRITEBYTECODE=1 python3 "$run_dir/test_verify_opencode_isolated.py" -v
```

Expected: FAIL because `${run_dir}/verify_opencode_isolated.py` does not exist; no real home path is mutated.

- [ ] **Step 3: Write the minimal isolated verifier**

Write this implementation exactly:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
test ! -e "$run_dir/verify_opencode_isolated.py"
cat > "$run_dir/verify_opencode_isolated.py" <<'PY'
#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REQUIRED = (
    "adr",
    "decision-calibrator",
    "model-optimizer",
    "remove-gentle-context",
    "systemic-issue-triage",
)
SCHEMA = "harness-skills.opencode-verification/v1"
INLINE_FLAG = "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"


class VerificationError(Exception):
    pass


def lexical_absolute(value):
    return Path(os.path.abspath(os.path.expanduser(os.fspath(value))))


def write_json_exclusive(path, value):
    path = Path(path)
    if os.path.lexists(path):
        raise VerificationError("opencode_output_exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def run_catalog(timeout):
    environment = os.environ.copy()
    environment[INLINE_FLAG] = "1"
    with tempfile.TemporaryDirectory(prefix="harness-opencode-") as temporary:
        temporary_path = Path(temporary)
        stdout_path = temporary_path / "stdout.json"
        stderr_path = temporary_path / "stderr.txt"
        try:
            with stdout_path.open("wb") as stdout_stream, stderr_path.open("wb") as stderr_stream:
                result = subprocess.run(
                    ["opencode", "debug", "skill"],
                    check=False,
                    stdout=stdout_stream,
                    stderr=stderr_stream,
                    timeout=timeout,
                    env=environment,
                )
        except subprocess.TimeoutExpired as error:
            raise VerificationError("opencode_timeout") from error
        stderr = stderr_path.read_bytes()
        if result.returncode != 0:
            raise VerificationError(f"opencode_nonzero_exit:{result.returncode}")
        if stderr:
            raise VerificationError(f"opencode_stderr:{stderr[:200]!r}")
        stdout = stdout_path.read_bytes()
        if not stdout:
            raise VerificationError("opencode_stdout_empty")
        try:
            text = stdout.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise VerificationError("opencode_stdout_not_utf8") from error
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise VerificationError("opencode_invalid_json") from error
    if not isinstance(value, list):
        raise VerificationError("opencode_invalid_inventory")
    return value


def verify(items, canonical_repo_skill_root):
    agents_root = lexical_absolute(Path.home() / ".agents" / "skills")
    try:
        canonical_root = Path(canonical_repo_skill_root).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError("opencode_canonical_root_unresolvable") from error
    if not canonical_root.is_dir():
        raise VerificationError("opencode_canonical_root_not_directory")
    selected = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name not in REQUIRED:
            continue
        if name in selected:
            raise VerificationError(f"opencode_duplicate_name:{name}")
        selected[name] = item
    missing = sorted(set(REQUIRED) - set(selected))
    if missing:
        raise VerificationError(f"opencode_missing:{missing}")
    entries = {}
    for name in REQUIRED:
        location = selected[name].get("location")
        if not isinstance(location, str) or not location:
            raise VerificationError(f"opencode_location_invalid:{name}")
        reported_lexical = lexical_absolute(location)
        expected_lexical = lexical_absolute(agents_root / name / "SKILL.md")
        if reported_lexical != expected_lexical:
            raise VerificationError(f"opencode_wrong_lexical_source:{name}:{reported_lexical}")
        try:
            reported_resolved = reported_lexical.resolve(strict=True)
            expected_resolved = (canonical_root / name / "SKILL.md").resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise VerificationError(f"opencode_path_resolution_failed:{name}") from error
        if reported_resolved != expected_resolved:
            raise VerificationError(f"opencode_wrong_resolved_source:{name}:{reported_resolved}")
        entries[name] = {
            "reported_lexical": str(reported_lexical),
            "expected_lexical": str(expected_lexical),
            "reported_resolved": str(reported_resolved),
            "expected_resolved": str(expected_resolved),
        }
    return {
        "schema": SCHEMA,
        "command": ["opencode", "debug", "skill"],
        "capture": "file-backed",
        "inline_environment": {INLINE_FLAG: "1"},
        "full_inventory_count": len(items),
        "non_governed_count": len(items) - len(selected),
        "governed_names": list(REQUIRED),
        "entries": entries,
        "status": "passed",
    }


def main():
    if len(sys.argv) != 4:
        raise VerificationError(
            "usage: verify_opencode_isolated.py OUTPUT CANONICAL_REPO_SKILL_ROOT TIMEOUT_SECONDS"
        )
    output = Path(sys.argv[1])
    if os.path.lexists(output):
        raise VerificationError("opencode_output_exists")
    try:
        timeout = float(sys.argv[3])
    except ValueError as error:
        raise VerificationError("opencode_timeout_invalid") from error
    if timeout <= 0 or timeout > 300:
        raise VerificationError("opencode_timeout_invalid")
    receipt = verify(run_catalog(timeout), sys.argv[2])
    write_json_exclusive(output, receipt)
    print("opencode_isolated_discovery_passed")


if __name__ == "__main__":
    try:
        main()
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
PY
chmod 700 "$run_dir/verify_opencode_isolated.py"
python3 -m py_compile "$run_dir/verify_opencode_isolated.py"
```

- [ ] **Step 4: Run the tests and verify all fixtures pass**

Run:

```bash
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
PYTHONDONTWRITEBYTECODE=1 python3 "$run_dir/test_verify_opencode_isolated.py" -v
```

Expected: 16 tests pass; the large-payload test exceeds 65,536 bytes; no path under the real home is created, replaced, or removed.

- [ ] **Step 5: Record script identities without modifying the original operation log**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

run = Path(sys.argv[1])
record = {
    "schema": "harness-skills.corrective-verifier/v1",
    "adr": "docs/adr/0017-aislar-discovery-opencode-solo-en-verificacion.md",
    "spec": "docs/superpowers/specs/2026-08-26-opencode-verification-isolation-design.md",
    "artifacts": {},
}
for name in ("verify_opencode_isolated.py", "test_verify_opencode_isolated.py"):
    path = run / name
    info = path.lstat()
    if not path.is_file() or path.is_symlink() or info.st_uid != os.getuid():
        raise SystemExit(f"unsafe_corrective_artifact:{path}")
    record["artifacts"][name] = {
        "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        "mode": info.st_mode & 0o777,
    }
output = run / "corrective-verifier.json"
if os.path.lexists(output):
    raise SystemExit("corrective_verifier_record_exists")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
fd = os.open(output, flags, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(record, stream, sort_keys=True, indent=2)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
print(json.dumps(record, sort_keys=True, indent=2))
PY
```

Expected: `corrective-verifier.json` records both mode-`0700` scripts and their SHA-256 digests; `operations.ndjson` remains unchanged with five completed original operations.

---

### Task 2: Re-establish the three-runtime Task 4 gate

**Files:**

- Create: `${run_dir}/pi-skills-corrected-pre-dedup.json`
- Create: `${run_dir}/opencode-skills-isolated-pre-dedup.json`
- Create after trusted observation: `${run_dir}/claude-tui-observation-pre-dedup.json`
- Create: `${run_dir}/runtime-verification.json`
- Preserve read-only: `${run_dir}/pi-skills.json`, `${run_dir}/opencode-skills.json`, `${run_dir}/verify_pi.py`, `${run_dir}/verify_opencode.py`

**Interfaces:**

- Consumes: `verify_pi.py OUTPUT pi`
- Consumes: `verify_opencode_isolated.py OUTPUT <repo>/skills 30`
- Consumes: trusted human observation of five Claude TUI skill names
- Produces: `runtime-verification.json` schema `harness-skills.runtime-verification/v2`
- Gate: `all_passed == true` and `opencode_isolation.adr == "0017"`

- [ ] **Step 1: Revalidate governance, source integrity, and the pre-dedup Pi symlink**

Run:

```bash
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
test "$repo" = "/Users/Shared/harness/skills"
rootline validate "$repo/docs/adr/0017-aislar-discovery-opencode-solo-en-verificacion.md" --strict
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
test "$(cat "$run_dir/approval.txt")" = "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["digest"])' "$run_dir/plan.json")"
python3 "$run_dir/capture.py" verify "$repo" "$run_dir/plan.json" unlink-pi-systemic-issue-triage
```

Expected: ADR valid and `preimage_verified:unlink-pi-systemic-issue-triage`. This command also rechecks all five tracked source digests.

- [ ] **Step 2: Run fresh Pi and isolated OpenCode verification**

Run:

```bash
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
test ! -e "$run_dir/pi-skills-corrected-pre-dedup.json"
test ! -e "$run_dir/opencode-skills-isolated-pre-dedup.json"
python3 "$run_dir/verify_pi.py" "$run_dir/pi-skills-corrected-pre-dedup.json" pi
python3 "$run_dir/verify_opencode_isolated.py" \
  "$run_dir/opencode-skills-isolated-pre-dedup.json" \
  "$repo/skills" \
  30
```

Expected: `pi_discovery_passed` and `opencode_isolated_discovery_passed`. OpenCode's full inventory may contain non-governed names; its governed receipt contains exactly the five names with exact lexical `~/.agents` locations and canonical resolved targets.

- [ ] **Step 3: Perform the trusted Claude TUI observation**

Run in a visible trusted terminal:

```bash
claude
```

Type `/`, then type/filter each governed name without pressing `Enter`. Confirm all five names are visibly offered in the normal TUI:

```text
adr
decision-calibrator
model-optimizer
remove-gentle-context
systemic-issue-triage
```

Exit with `Escape`/`Ctrl-C` without invoking a skill and without sending a model request. Do not write the observation artifact unless all five names are visible in the live TUI.

After the human confirms the observation, record it exclusively:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir/claude-tui-observation-pre-dedup.json" <<'PY'
import datetime
import json
import os
import sys

path = sys.argv[1]
if os.path.lexists(path):
    raise SystemExit("claude_observation_exists")
value = {
    "schema": "harness-skills.claude-tui-observation/v1",
    "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "names": [
        "adr",
        "decision-calibrator",
        "model-optimizer",
        "remove-gentle-context",
        "systemic-issue-triage",
    ],
    "all_visible": True,
    "launch_mode": "normal",
    "reduced_mode": False,
    "skill_invoked": False,
    "model_request_sent": False,
    "observer": "human",
}
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
fd = os.open(path, flags, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(value, stream, sort_keys=True, indent=2)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
print("claude_tui_observation_recorded")
PY
```

Expected: a mode-`0600` observation records only what the human saw in normal launch mode; it does not infer discovery from filesystem state. If reduced-mode output shows zero skill commands or autocomplete misses `/adr`, treat that as evidence of reduced-mode incompatibility, not as a Claude discovery failure.

- [ ] **Step 4: Write the corrected combined runtime gate exclusively**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir" <<'PY'
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

run = Path(sys.argv[1])
output = run / "runtime-verification.json"
if os.path.lexists(output):
    raise SystemExit("runtime_verification_exists")
pi_path = run / "pi-skills-corrected-pre-dedup.json"
opencode_path = run / "opencode-skills-isolated-pre-dedup.json"
claude_path = run / "claude-tui-observation-pre-dedup.json"
for path in (pi_path, opencode_path, claude_path):
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"runtime_evidence_missing_or_unsafe:{path}")
pi = json.loads(pi_path.read_text(encoding="utf-8"))
opencode = json.loads(opencode_path.read_text(encoding="utf-8"))
claude = json.loads(claude_path.read_text(encoding="utf-8"))
required = [
    "adr",
    "decision-calibrator",
    "model-optimizer",
    "remove-gentle-context",
    "systemic-issue-triage",
]
if set(pi) != set(required):
    raise SystemExit("pi_receipt_name_set_invalid")
for name in required:
    if name == "systemic-issue-triage":
        expected_pi = Path.home() / ".pi" / "agent" / "skills" / name / "SKILL.md"
    else:
        expected_pi = Path.home() / ".agents" / "skills" / name / "SKILL.md"
    if Path(pi[name]["sourceInfo"]["path"]) != expected_pi:
        raise SystemExit(f"pi_receipt_source_invalid:{name}")
if opencode.get("schema") != "harness-skills.opencode-verification/v1":
    raise SystemExit("opencode_receipt_schema_invalid")
if opencode.get("status") != "passed" or opencode.get("governed_names") != required:
    raise SystemExit("opencode_receipt_not_passed")
if opencode.get("inline_environment") != {"OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1"}:
    raise SystemExit("opencode_inline_isolation_missing")
if claude.get("all_visible") is not True or claude.get("names") != required:
    raise SystemExit("claude_observation_not_passed")
if claude.get("launch_mode") != "normal" or claude.get("reduced_mode") is not False:
    raise SystemExit("claude_launch_mode_invalid")
if claude.get("observer") != "human":
    raise SystemExit("claude_observer_invalid")
if claude.get("skill_invoked") is not False or claude.get("model_request_sent") is not False:
    raise SystemExit("claude_observation_unsafe")
value = {
    "schema": "harness-skills.runtime-verification/v2",
    "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "pi": "passed",
    "opencode": "passed",
    "claude_tui": "passed",
    "all_passed": True,
    "pi_evidence": str(pi_path),
    "opencode_evidence": str(opencode_path),
    "claude_evidence": str(claude_path),
    "opencode_isolation": {
        "adr": "0017",
        "inline_environment": {"OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1"},
        "capture": "file-backed",
        "persistent_configuration_changed": False,
    },
    "versions": {
        "pi": subprocess.check_output(["pi", "--version"], text=True).strip(),
        "opencode": subprocess.check_output(["opencode", "--version"], text=True).strip(),
        "claude": subprocess.check_output(["claude", "--version"], text=True).strip(),
    },
}
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
fd = os.open(output, flags, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(value, stream, sort_keys=True, indent=2)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
print(json.dumps(value, sort_keys=True, indent=2))
PY
```

Expected: `runtime-verification.json` is mode `0600`, schema v2, and binds fresh Pi evidence, isolated OpenCode evidence, the trusted Claude observation, ADR 0017, file-backed capture, and the absence of persistent configuration changes.

---

### Task 3: Execute the approved Pi deduplication after the corrected gate

**Files:**

- Remove symlink only: `~/.pi/agent/skills/systemic-issue-triage`
- Create: `${run_dir}/pi-skills-after-dedup.json`
- Append exactly one original-plan row: `${run_dir}/operations.ndjson`

**Interfaces:**

- Consumes: `runtime-verification.json` schema v2 with `all_passed == true` and ADR 0017 isolation evidence
- Consumes: original approved operation `unlink-pi-systemic-issue-triage`
- Produces: Pi discovery of all five governed names from `~/.agents/skills`
- Rollback: recreate the exact raw target recorded in the original `plan.json`

- [ ] **Step 1: Revalidate the corrected runtime gate and original operation preimage**

Run:

```bash
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir/runtime-verification.json" <<'PY'
import json
import sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
if value.get("schema") != "harness-skills.runtime-verification/v2":
    raise SystemExit("runtime_gate_schema_invalid")
if value.get("all_passed") is not True:
    raise SystemExit("runtime_gate_not_passed")
isolation = value.get("opencode_isolation", {})
if isolation.get("adr") != "0017":
    raise SystemExit("opencode_adr_gate_missing")
if isolation.get("inline_environment") != {"OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1"}:
    raise SystemExit("opencode_inline_gate_missing")
if isolation.get("persistent_configuration_changed") is not False:
    raise SystemExit("persistent_configuration_scope_violation")
PY
python3 "$run_dir/capture.py" verify \
  "$repo" "$run_dir/plan.json" unlink-pi-systemic-issue-triage
```

Expected: `preimage_verified:unlink-pi-systemic-issue-triage` after the corrected runtime gate passes.

- [ ] **Step 2: Unlink only the exact verified Pi duplicate**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
target="$HOME/.pi/agent/skills/systemic-issue-triage"
raw_target="$(python3 - "$run_dir/plan.json" <<'PY'
import json
import sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
operation = next(item for item in plan["operations"] if item["id"] == "unlink-pi-systemic-issue-triage")
print(operation["before"]["target"])
PY
)"
python3 - "$target" "$raw_target" <<'PY'
from pathlib import Path
import os
import sys
path = Path(sys.argv[1])
raw_expected = sys.argv[2]
repo_expected = Path("/Users/Shared/harness/skills/skills/systemic-issue-triage").resolve(strict=True)
if not path.is_symlink():
    raise SystemExit("pi_duplicate_not_symlink")
if os.readlink(path) != raw_expected:
    raise SystemExit("pi_duplicate_raw_target_drift")
if path.resolve(strict=True) != repo_expected:
    raise SystemExit("pi_duplicate_resolved_target_drift")
print(raw_expected)
PY
unlink "$target"
test ! -e "$target"
test ! -L "$target"
```

Expected: prints the original raw target and removes only the symlink. The canonical repository source remains untouched.

- [ ] **Step 3: Prove Pi resolves all five governed names from `~/.agents`, with immediate rollback on failure**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
target="$HOME/.pi/agent/skills/systemic-issue-triage"
raw_target="$(python3 - "$run_dir/plan.json" <<'PY'
import json
import sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
operation = next(item for item in plan["operations"] if item["id"] == "unlink-pi-systemic-issue-triage")
print(operation["before"]["target"])
PY
)"
test ! -e "$run_dir/pi-skills-after-dedup.json"
if ! python3 "$run_dir/verify_pi.py" "$run_dir/pi-skills-after-dedup.json" agents; then
  test ! -e "$target"
  test ! -L "$target"
  ln -s "$raw_target" "$target"
  printf 'pi_duplicate_restored_after_verification_failure\n' >&2
  exit 1
fi
```

Expected: `pi_discovery_passed`; every governed Pi command reports `~/.agents/skills/<name>/SKILL.md`. Failure recreates the exact original raw symlink target before returning nonzero.

- [ ] **Step 4: Append the sixth original operation exactly once**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir/operations.ndjson" "$run_dir/plan.json" <<'PY'
import datetime
import json
import os
import sys

path, plan_path = sys.argv[1:]
plan = json.load(open(plan_path, encoding="utf-8"))
operation_id = "unlink-pi-systemic-issue-triage"
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
if any(row.get("operation_id") == operation_id for row in rows):
    raise SystemExit("unlink_operation_already_recorded")
expected_prior = {
    "replace-agents-model-optimizer",
    "link-agents-remove-gentle-context",
    "link-claude-model-optimizer",
    "link-claude-remove-gentle-context",
    "link-claude-systemic-issue-triage",
}
actual_prior = {row.get("operation_id") for row in rows if row.get("status") == "completed"}
if actual_prior != expected_prior:
    raise SystemExit(f"prior_operation_set_invalid:{sorted(actual_prior)}")
record = {
    "operation_id": operation_id,
    "plan_digest": plan["digest"],
    "status": "completed",
    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open(path, "a", encoding="utf-8") as stream:
    stream.write(json.dumps(record, sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())
print(json.dumps(record, sort_keys=True))
PY
```

Expected: `operations.ndjson` contains exactly six completed original operation IDs and the new row retains the original approved plan digest.

---

### Task 4: Run corrected final verification, restore drill, and close the run

**Files:**

- Create: `${run_dir}/pi-skills-final.json`
- Create: `${run_dir}/opencode-skills-isolated-final.json`
- Create after trusted observation: `${run_dir}/claude-tui-observation-final.json`
- Create: `${run_dir}/runtime-verification-final.json`
- Create: `${run_dir}/backups/model-optimizer/restore-drill/`
- Create: `${run_dir}/receipt.json`
- Move: `${state_root}/active-run` to `${state_root}/last-completed-run`

**Interfaces:**

- Consumes: six original operation rows, corrected pre-dedup gate, verified backups, and new isolated verifier
- Produces: corrected final runtime evidence schema v2 and convergence receipt
- Completion: no governed Pi/OpenCode runtime duplicate remains; all ten shared/Claude links remain canonical; rollback material is usable

- [ ] **Step 1: Verify final filesystem topology and operation evidence**

Run:

```bash
set -euo pipefail
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
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir/operations.ndjson" "$run_dir/plan.json" <<'PY'
import json
import sys
rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
plan = json.load(open(sys.argv[2], encoding="utf-8"))
expected = {item["id"] for item in plan["operations"]}
completed = [row["operation_id"] for row in rows if row.get("status") == "completed"]
if len(completed) != len(set(completed)):
    raise SystemExit("duplicate_operation_receipt")
if set(completed) != expected:
    raise SystemExit(f"operation_receipt_mismatch:{sorted(expected - set(completed))}")
print("operation_evidence_passed")
PY
```

Expected: `filesystem_topology_passed` and `operation_evidence_passed`.

- [ ] **Step 2: Run corrected final Pi and OpenCode discovery**

Run:

```bash
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
test ! -e "$run_dir/pi-skills-final.json"
test ! -e "$run_dir/opencode-skills-isolated-final.json"
python3 "$run_dir/verify_pi.py" "$run_dir/pi-skills-final.json" agents
python3 "$run_dir/verify_opencode_isolated.py" \
  "$run_dir/opencode-skills-isolated-final.json" \
  "$repo/skills" \
  30
```

Expected: both pass; Pi reports all five through `~/.agents`, and the isolated OpenCode receipt proves exact lexical and strict canonical targets for the governed subset.

- [ ] **Step 3: Repeat the trusted Claude TUI observation and record it exclusively**

Run `claude` in a visible trusted terminal, type `/`, type/filter each governed name without pressing `Enter`, confirm the same five names in the normal TUI, then exit without invoking a skill or sending a model request.

After the human confirms, record:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir/claude-tui-observation-final.json" <<'PY'
import datetime
import json
import os
import sys
path = sys.argv[1]
if os.path.lexists(path):
    raise SystemExit("claude_final_observation_exists")
value = {
    "schema": "harness-skills.claude-tui-observation/v1",
    "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "names": ["adr", "decision-calibrator", "model-optimizer", "remove-gentle-context", "systemic-issue-triage"],
    "all_visible": True,
    "launch_mode": "normal",
    "reduced_mode": False,
    "skill_invoked": False,
    "model_request_sent": False,
    "observer": "human",
}
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
fd = os.open(path, flags, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(value, stream, sort_keys=True, indent=2)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
print("claude_final_observation_recorded")
PY
```

Expected: a fresh human-observed final Claude artifact exists at mode `0600` and records `launch_mode: "normal"` with `reduced_mode: False`. Reduced-mode misses remain troubleshooting evidence only, because reduced mode skips skill directory discovery.

- [ ] **Step 4: Write corrected final runtime evidence**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir" <<'PY'
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
run = Path(sys.argv[1])
output = run / "runtime-verification-final.json"
if os.path.lexists(output):
    raise SystemExit("final_runtime_verification_exists")
pi_path = run / "pi-skills-final.json"
opencode_path = run / "opencode-skills-isolated-final.json"
claude_path = run / "claude-tui-observation-final.json"
pre_gate = json.loads((run / "runtime-verification.json").read_text(encoding="utf-8"))
if pre_gate.get("all_passed") is not True or pre_gate.get("opencode_isolation", {}).get("adr") != "0017":
    raise SystemExit("corrected_pre_dedup_gate_missing")
pi = json.loads(pi_path.read_text(encoding="utf-8"))
opencode = json.loads(opencode_path.read_text(encoding="utf-8"))
claude = json.loads(claude_path.read_text(encoding="utf-8"))
required = ["adr", "decision-calibrator", "model-optimizer", "remove-gentle-context", "systemic-issue-triage"]
if set(pi) != set(required):
    raise SystemExit("final_pi_receipt_name_set_invalid")
for name in required:
    expected_pi = Path.home() / ".agents" / "skills" / name / "SKILL.md"
    if Path(pi[name]["sourceInfo"]["path"]) != expected_pi:
        raise SystemExit(f"final_pi_receipt_source_invalid:{name}")
if opencode.get("status") != "passed" or opencode.get("governed_names") != required:
    raise SystemExit("final_opencode_not_passed")
if opencode.get("inline_environment") != {"OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1"}:
    raise SystemExit("final_opencode_isolation_missing")
if claude.get("all_visible") is not True or claude.get("names") != required:
    raise SystemExit("final_claude_not_passed")
if claude.get("launch_mode") != "normal" or claude.get("reduced_mode") is not False:
    raise SystemExit("final_claude_launch_mode_invalid")
if claude.get("observer") != "human":
    raise SystemExit("final_claude_observer_invalid")
if claude.get("skill_invoked") is not False or claude.get("model_request_sent") is not False:
    raise SystemExit("final_claude_observation_unsafe")
value = {
    "schema": "harness-skills.runtime-verification/v2",
    "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "pi": "passed",
    "opencode": "passed",
    "claude_tui": "passed",
    "all_passed": True,
    "pi_evidence": str(pi_path),
    "opencode_evidence": str(opencode_path),
    "claude_evidence": str(claude_path),
    "opencode_isolation": {
        "adr": "0017",
        "inline_environment": {"OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1"},
        "capture": "file-backed",
        "persistent_configuration_changed": False,
    },
    "versions": {
        "pi": subprocess.check_output(["pi", "--version"], text=True).strip(),
        "opencode": subprocess.check_output(["opencode", "--version"], text=True).strip(),
        "claude": subprocess.check_output(["claude", "--version"], text=True).strip(),
    },
}
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
fd = os.open(output, flags, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(value, stream, sort_keys=True, indent=2)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
print(json.dumps(value, sort_keys=True, indent=2))
PY
```

Expected: final schema-v2 evidence binds the post-dedup Pi result, isolated OpenCode result, second trusted Claude observation, and ADR 0017.

- [ ] **Step 5: Prove backup usability without touching the live target**

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

Expected: all three digests equal the original approved preimage digest; the live `~/.agents/skills/model-optimizer` symlink remains untouched.

- [ ] **Step 6: Write the final receipt and close the active-run pointer**

Run:

```bash
set -euo pipefail
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/harness-skills/convergence"
run_dir="$(cat "$state_root/active-run")"
python3 - "$run_dir" <<'PY'
import datetime
import json
import os
import sys
from pathlib import Path
run = Path(sys.argv[1])
output = run / "receipt.json"
if os.path.lexists(output):
    raise SystemExit("receipt_exists")
plan = json.loads((run / "plan.json").read_text(encoding="utf-8"))
rows = [json.loads(line) for line in (run / "operations.ndjson").read_text(encoding="utf-8").splitlines() if line]
completed = [row["operation_id"] for row in rows if row.get("status") == "completed"]
expected = {operation["id"] for operation in plan["operations"]}
if len(completed) != len(set(completed)) or set(completed) != expected:
    raise SystemExit("operation_receipt_mismatch")
runtime = json.loads((run / "runtime-verification-final.json").read_text(encoding="utf-8"))
if runtime.get("schema") != "harness-skills.runtime-verification/v2" or runtime.get("all_passed") is not True:
    raise SystemExit("final_runtime_verification_not_passed")
receipt = {
    "schema": "harness-skills.convergence-receipt/v2",
    "plan_digest": plan["digest"],
    "corrective_governance": {
        "adr": "0017",
        "spec": "docs/superpowers/specs/2026-08-26-opencode-verification-isolation-design.md",
        "plan": "docs/superpowers/plans/2026-08-26-opencode-verification-isolation.md",
    },
    "status": "completed",
    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "operations": sorted(completed),
    "runtime_verification": runtime,
    "backup_original": str(run / "backups/model-optimizer/original"),
    "backup_copy": str(run / "backups/model-optimizer/verified-copy"),
    "restore_drill": str(run / "backups/model-optimizer/restore-drill"),
}
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
fd = os.open(output, flags, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(receipt, stream, sort_keys=True, indent=2)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
print(json.dumps(receipt, sort_keys=True, indent=2))
PY
test ! -e "$state_root/last-completed-run"
mv "$state_root/active-run" "$state_root/last-completed-run"
test "$(cat "$state_root/last-completed-run")" = "$run_dir"
printf 'convergence_receipt=%s\n' "$run_dir/receipt.json"
```

Expected: receipt schema v2 binds the original approved plan and the corrective governance/evidence; no evidence is deleted; `last-completed-run` points to the completed immutable run.

---

## Plan Self-Review Checklist

- [ ] Every ADR 0017/spec requirement maps to Task 1 or Task 2.
- [ ] The original signed plan, approval, operation rows, failed verifier, and failed evidence remain immutable.
- [ ] No command persists OpenCode configuration or edits a runtime root before the corrected three-runtime gate passes.
- [ ] All OpenCode subprocess output uses file-backed capture with inline isolation.
- [ ] Fixture tests cover the governed subset, extra non-governed names, duplicates, missing names, wrong roots, exact lexical paths, strict canonical resolution, invalid JSON, stderr, nonzero exits, timeout, exclusive output, and payloads larger than 65,536 bytes.
- [ ] Task 3 retains the original plan digest and exact raw symlink rollback authority.
- [ ] Task 4 substitutes the isolated verifier for the original Task 6 OpenCode command and records ADR 0017 in the final receipt.
- [ ] Unrelated worktree state remains unstaged and untouched.
