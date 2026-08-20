from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "cleanup.py"
FIXTURES = SKILL_ROOT / "tests" / "fixtures"
CONTRACTS = SKILL_ROOT / "references" / "contracts.md"
PRESERVATION = SKILL_ROOT / "references" / "preservation.md"
README = REPO_ROOT / "README.md"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOC_PATHS = (SKILL_ROOT / "SKILL.md", CONTRACTS, PRESERVATION, README)
REMOVED_MODE_ENV = "REMOVE_GENTLE_CONTEXT_" + "TEST" + "_MODE"
REMOVED_HOME_ENV = "REMOVE_GENTLE_CONTEXT_" + "TEST" + "_HOME"
REMOVED_ATOMIC_ENV = "REMOVE_GENTLE_CONTEXT_" + "INJECT" + "_ATOMIC_FAIL"


def load_cleanup_module():
    spec = importlib.util.spec_from_file_location("remove_gentle_context_cleanup", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cleanup module spec unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CliResult:
    def __init__(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.returncode = completed.returncode
        self.stdout = completed.stdout
        self.stderr = completed.stderr
        try:
            self.json = json.loads(completed.stdout) if completed.stdout.strip() else {}
        except json.JSONDecodeError:
            self.json = {}
        self.output_path = Path(self.json["output_path"]) if "output_path" in self.json else None
        self.digest = self.json.get("digest")


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name).resolve(strict=True)
        self.home = self.temp_root / "home"
        self.home.mkdir()
        self.project = self.temp_root / "project"
        self.project.mkdir()
        self.artifacts = self.temp_root / "artifacts"
        self.artifacts.mkdir()
        self.env = {
            **os.environ,
            REMOVED_MODE_ENV: "1",
            "PYTHONPATH": str(SKILL_ROOT),
            "XDG_STATE_HOME": str(self.temp_root / "state"),
        }

    def run_cli(self, *args: str, env: dict[str, str] | None = None) -> CliResult:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=SKILL_ROOT,
            env=self.env if env is None else env,
            text=True,
            capture_output=True,
            check=False,
        )
        return CliResult(completed)

    def run_ok(self, *args: str) -> CliResult:
        result = self.run_cli(*args)
        if result.returncode != 0:
            self.fail(f"CLI failed with {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
        return result

    def contract_json_example(self, heading: str) -> dict[str, object]:
        text = CONTRACTS.read_text(encoding="utf-8")
        pattern = rf"(?ms)^### {re.escape(heading)}\n\n```json\n(?P<body>.*?)\n```"
        match = re.search(pattern, text)
        if match is None:
            self.fail(f"missing JSON example for {heading}")
        data = json.loads(match.group("body"))
        if not isinstance(data, dict):
            self.fail(f"JSON example for {heading} is not an object")
        return data

    def write_contract_json_example(self, name: str, data: dict[str, object]) -> Path:
        path = self.artifacts / name
        path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        return path

    def inventory(self) -> CliResult:
        return self.run_ok(
            "inventory",
            "--home",
            str(self.home),
            "--platform",
            "linux",
            "--project-root",
            str(self.project),
            "--output",
            str(self.artifacts / "inventory.json"),
        )

    def plan(self, inventory: CliResult) -> CliResult:
        assert inventory.output_path is not None
        self.last_inventory_path = inventory.output_path
        return self.run_ok("plan", "--inventory", str(inventory.output_path), "--output", str(self.artifacts / "plan.json"))

    def apply(self, plan: CliResult, *, receipt_name: str = "receipt.json") -> CliResult:
        assert plan.output_path is not None
        assert isinstance(plan.digest, str)
        return self.run_ok("apply", "--inventory", str(self.last_inventory_path), "--plan", str(plan.output_path), "--approve", plan.digest, "--receipt", str(self.artifacts / receipt_name))

    def verify(self, receipt: CliResult, plan: CliResult | None = None) -> CliResult:
        plan_path = Path(plan.output_path) if plan is not None and plan.output_path is not None else self.artifacts / "plan.json"
        return self.run_ok("verify", "--inventory", str(self.last_inventory_path), "--plan", str(plan_path), "--receipt", str(receipt.json["receipt_path"]), "--output", str(self.artifacts / "verification.json"))

    def restore(self, manifest_path: str, digest: str, receipt_path: str) -> CliResult:
        return self.run_ok("restore", "--manifest", manifest_path, "--receipt", receipt_path, "--approve", digest, "--output", str(self.artifacts / "restore.json"))

    def seed_cross_client_fixture(self) -> None:
        # Claude: owned marker block and exact generated theme.
        claude = self.home / ".claude"
        (claude / "themes").mkdir(parents=True)
        (claude / "CLAUDE.md").write_text(
            "Keep this line.\n"
            "<!-- gentle-ai:sdd-orchestrator -->\n"
            "Managed Claude instruction.\n"
            "<!-- /gentle-ai:sdd-orchestrator -->\n",
            encoding="utf-8",
        )
        shutil.copy2(FIXTURES / "claude" / "gentleman.json", claude / "themes" / "gentleman.json")

        # Codex: active profile in config only; no runtime file, avoiding real lifecycle in tests.
        codex = self.home / ".codex"
        codex.mkdir()
        shutil.copy2(FIXTURES / "codex" / "config.toml", codex / "config.toml")
        (codex / "sessions").mkdir()
        (codex / "sessions" / "history.jsonl").write_text('{"keep":"history"}\n', encoding="utf-8")

        # OpenCode: config/tui/package fixtures preserve MCP and package infrastructure.
        opencode = self.home / ".config" / "opencode"
        opencode.mkdir(parents=True)
        for name in ("opencode.json", "tui.json", "package.json"):
            shutil.copy2(FIXTURES / "opencode" / name, opencode / name)
        (opencode / "node_modules" / "opencode-sdd-engram-manage").mkdir(parents=True)

        # Pi: package registration is removed; package infrastructure is preserved.
        pi = self.home / ".pi"
        pi.mkdir()
        shutil.copy2(FIXTURES / "pi" / "settings.json", pi / "settings.json")
        (pi / "node_modules" / "gentle-pi").mkdir(parents=True)
        (pi / "node_modules" / ".bin").mkdir()
        (pi / "node_modules" / ".bin" / "gentle-pi").write_text("#!/usr/bin/env node\n", encoding="utf-8")

        # Bundled declarative adapter fixture.
        hermes = self.home / ".hermes"
        hermes.mkdir()
        (hermes / "gentle-helper.json").write_text('{"managedBy":"gentle-ai"}\n', encoding="utf-8")

    def seed_pi_registry_fixture(self) -> Path:
        registry = self.project / ".atl" / "skill-registry.md"
        registry.parent.mkdir()
        shutil.copy2(FIXTURES / "pi" / "skill-registry.md", registry)
        return registry

    def git_blob_bytes(self, path: Path) -> bytes:
        relative = path.relative_to(REPO_ROOT).as_posix()
        completed = subprocess.run(
            ["git", "cat-file", "blob", f"HEAD:{relative}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            self.fail(completed.stderr.decode("utf-8", errors="replace"))
        return completed.stdout

    def test_repository_eol_policy_preserves_byte_sensitive_fixtures(self) -> None:
        attributes_path = REPO_ROOT / ".gitattributes"
        attributes_lines = attributes_path.read_text(encoding="utf-8").splitlines()
        crlf_fixture = FIXTURES / "declarative" / "json-surgery-crlf.json"
        lf_fixture = FIXTURES / "declarative" / "json-surgery-formatting.json"
        crlf_fixture_attr = crlf_fixture.relative_to(REPO_ROOT).as_posix() + " -text"

        self.assertIn("* text=auto eol=lf", attributes_lines)
        self.assertIn(crlf_fixture_attr, attributes_lines)

        crlf_blob = self.git_blob_bytes(crlf_fixture)
        lf_blob = self.git_blob_bytes(lf_fixture)
        self.assertIn(b"\r\n", crlf_blob, "intentional CRLF fixture must stay byte-for-byte CRLF in Git")
        self.assertNotIn(b"\r\n", lf_blob, "ordinary JSON fixture blobs must stay LF in Git")

    def test_receipt_artifact_serializes_backup_manifest_path_with_forward_slashes(self) -> None:
        cleanup = load_cleanup_module()
        windows_manifest = PureWindowsPath("C:/gentle-example/state/remove-gentle-context/backups/example/manifest.json")
        receipt = cleanup.Receipt(backup_manifest_path=windows_manifest, status=cleanup.ReceiptStatus.COMPLETED)

        artifact = cleanup.receipt_artifact(receipt)

        self.assertIs(receipt.backup_manifest_path, windows_manifest)
        self.assertEqual(artifact["backup_manifest_path"], "C:/gentle-example/state/remove-gentle-context/backups/example/manifest.json")
        self.assertNotIn("\\", artifact["backup_manifest_path"])

        apply_summary = cleanup.receipt_command_summary(
            command="apply",
            receipt_path=PureWindowsPath("C:/gentle-example/state/remove-gentle-context/receipt.json"),
            receipt=receipt,
            artifact=artifact,
            backup_manifest_digest=None,
            counts={"operations": 0, "lifecycle": 0},
        )
        restore_summary = cleanup.receipt_command_summary(
            command="restore",
            receipt_path=PureWindowsPath("C:/gentle-example/state/remove-gentle-context/restore.json"),
            receipt=receipt,
            artifact=artifact,
        )

        self.assertEqual(apply_summary["backup_manifest_path"], artifact["backup_manifest_path"])
        self.assertEqual(restore_summary["backup_manifest_path"], artifact["backup_manifest_path"])
        self.assertIn("backup_manifest_digest", apply_summary)
        self.assertIsNone(apply_summary["backup_manifest_digest"])
        self.assertNotIn("backup_manifest_digest", restore_summary)
        self.assertNotIn("\\", apply_summary["backup_manifest_path"])
        self.assertNotIn("\\", restore_summary["backup_manifest_path"])

        native_manifest = self.artifacts / "manifest.json"
        native_manifest.write_text('{"schema":"remove-gentle-context.backup/v1"}\n', encoding="utf-8")
        native_receipt = cleanup.Receipt(backup_manifest_path=native_manifest, status=cleanup.ReceiptStatus.COMPLETED)
        native_artifact = cleanup.receipt_artifact(native_receipt)
        native_receipt_path = self.write_contract_json_example("native-receipt.json", native_artifact)
        loaded_native_receipt = cleanup.load_receipt(native_receipt_path)

        self.assertIsInstance(loaded_native_receipt.backup_manifest_path, Path)
        self.assertEqual(loaded_native_receipt.backup_manifest_path.read_text(encoding="utf-8"), native_manifest.read_text(encoding="utf-8"))

    def test_cli_file_has_portable_shebang_and_posix_executable_mode(self) -> None:
        first_line = SCRIPT.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, "#!/usr/bin/env python3")
        if os.name == "posix":
            self.assertTrue(os.access(SCRIPT, os.X_OK), "cleanup.py must be executable on POSIX")

    def test_help_lists_exact_five_commands(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("inventory", result.stdout)
        self.assertIn("plan", result.stdout)
        self.assertIn("apply", result.stdout)
        self.assertIn("verify", result.stdout)
        self.assertIn("restore", result.stdout)

        inventory_help = self.run_cli("inventory", "--help")
        self.assertEqual(inventory_help.returncode, 0)
        self.assertIn("--home", inventory_help.stdout)
        self.assertIn("--platform", inventory_help.stdout)
        self.assertIn("--env", inventory_help.stdout)

    def test_skill_mentions_every_phase_and_never_authorizes_freeform_delete(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for command in ("inventory", "plan", "apply", "verify", "restore"):
            self.assertIn(f"cleanup.py {command}", text)
        self.assertIn("--approve", text)
        self.assertIn("Never improvise deletion commands outside scripts/cleanup.py.", text)

    def test_skill_frontmatter_and_trigger_description_are_agentskills_compatible(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        end = text.index("\n---\n", 4)
        frontmatter = text[4:end]
        self.assertRegex(frontmatter, r"(?m)^name: remove-gentle-context$")
        description_lines = []
        capture = False
        for line in frontmatter.splitlines():
            if line.startswith("description: >-"):
                capture = True
                continue
            if capture:
                if line.startswith("  "):
                    description_lines.append(line.strip())
                else:
                    break
        description = " ".join(description_lines)
        self.assertTrue(description.startswith("Use when"), description)
        forbidden_workflow_terms = ("inventory", "back up", "backup", "remove", "verify", "preserve", "approval", "digest")
        for term in forbidden_workflow_terms:
            self.assertNotIn(term, description.lower())

    def test_skill_quick_path_has_exactly_five_command_signatures(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        expected = [
            "python scripts/cleanup.py inventory --home <absolute-home> --platform <linux|macos|windows> --output <inventory.json>",
            "python scripts/cleanup.py plan --inventory <inventory.json> --output <plan.json>",
            "python scripts/cleanup.py apply --inventory <inventory.json> --plan <plan.json> --approve <plan-digest> --receipt <receipt.json>",
            "python scripts/cleanup.py verify --inventory <inventory.json> --plan <plan.json> --receipt <receipt.json> --output <verification.json>",
            "python scripts/cleanup.py restore --manifest <backup-manifest.json> --receipt <receipt.json> --approve <manifest-digest> --output <restore.json>",
        ]
        command_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("python scripts/cleanup.py ")]
        self.assertEqual(command_lines, expected)

    def test_reference_contracts_define_artifacts_codes_authority_and_recovery(self) -> None:
        text = CONTRACTS.read_text(encoding="utf-8")
        required_terms = (
            "remove-gentle-context.inventory/v1",
            "remove-gentle-context.plan/v1",
            "remove-gentle-context.backup/v1",
            "remove-gentle-context.receipt/v1",
            "remove-gentle-context.verification/v1",
            "plan and manifest digests omit their own digest field",
            "EXIT_USAGE = 2",
            "EXIT_UNSAFE_PATH = 11",
            "EXIT_ARTIFACT = 12",
            "EXIT_IO = 13",
            "EXIT_APPROVAL = 20",
            "EXIT_APPLY = 21",
            "EXIT_VERIFY_FAILED = 30",
            "EXIT_RESTORE = 40",
            "restore authority",
            "root/environment binding",
            "atomic publication",
            "recovery states",
        )
        for term in required_terms:
            self.assertIn(term, text)
        signature_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("python scripts/cleanup.py ")]
        self.assertEqual(len(signature_lines), 5)

    def test_reference_contract_json_examples_validate_against_production_schemas(self) -> None:
        cleanup = load_cleanup_module()
        examples = {
            heading: self.contract_json_example(heading)
            for heading in (
                "Inventory JSON",
                "Plan JSON",
                "Backup manifest JSON",
                "Receipt JSON",
                "Verification JSON",
            )
        }
        serialized_examples = json.dumps(examples, sort_keys=True)
        self.assertIn("C:/gentle-example/home", serialized_examples)
        self.assertNotIn("$HOME", serialized_examples)

        inventory_path = self.write_contract_json_example("contract-inventory.json", examples["Inventory JSON"])
        plan_path = self.write_contract_json_example("contract-plan.json", examples["Plan JSON"])
        manifest_path = self.write_contract_json_example("contract-manifest.json", examples["Backup manifest JSON"])
        receipt_path = self.write_contract_json_example("contract-receipt.json", examples["Receipt JSON"])

        inventory = cleanup.load_inventory(inventory_path)
        self.assertEqual(cleanup.inventory_artifact(inventory), examples["Inventory JSON"])
        plan = cleanup.load_plan(plan_path)
        self.assertEqual(cleanup.plan_artifact(plan), examples["Plan JSON"])
        self.assertEqual(inventory.os_name, "windows")
        self.assertEqual(plan.inventory_digest, inventory.digest)
        self.assertEqual(plan.home, inventory.home)
        self.assertEqual(plan.os_name, inventory.os_name)
        self.assertEqual(dict(plan.root_map), dict(inventory.root_map))

        manifest = cleanup.load_backup_manifest(manifest_path)
        self.assertEqual(cleanup.backup_manifest_digest(manifest_path), examples["Backup manifest JSON"]["digest"])
        self.assertEqual(manifest.to_dict(), examples["Backup manifest JSON"])
        self.assertEqual(manifest.plan_digest, plan.digest)
        operations_by_index = {index: operation for index, operation in enumerate(plan.operations)}
        for entry in manifest.entries:
            operation = operations_by_index[entry.operation_index]
            self.assertEqual(entry.kind, str(operation.kind))
            self.assertEqual(entry.original_path, operation.path)
            self.assertEqual(entry.sha256, operation.preimage_sha256)

        receipt = cleanup.load_receipt(receipt_path)
        self.assertEqual(cleanup.receipt_artifact(receipt), examples["Receipt JSON"])
        cleanup.assert_receipt_binding(receipt, inventory, plan, phase="docs")
        self.assertEqual(receipt.backup_manifest_path.as_posix(), examples["Receipt JSON"]["backup_manifest_path"])
        self.assertEqual(tuple(receipt.checks), ())
        for outcome in receipt.operation_outcomes:
            operation = operations_by_index[outcome.operation_index]
            self.assertEqual(outcome.kind, str(operation.kind))
            self.assertEqual(outcome.path, operation.path)
            self.assertEqual(outcome.status, "completed")

        runtime_context = cleanup.RuntimeContext(cleanup.PlatformProfile("linux", self.home, {}))
        runtime_inventory = cleanup.build_inventory(runtime_context, ())
        runtime_plan = cleanup.build_plan(runtime_inventory, runtime_context, ())
        runtime_receipt = cleanup.execute_plan(runtime_plan, runtime_plan.digest, runtime_context, object(), inventory=runtime_inventory)
        runtime_receipt_artifact = cleanup.receipt_artifact(runtime_receipt)
        self.assertEqual(runtime_receipt.status, cleanup.ReceiptStatus.COMPLETED)
        self.assertEqual(runtime_receipt_artifact["checks"], [])
        self.assertEqual(runtime_receipt_artifact["checks"], examples["Receipt JSON"]["checks"])

        verification_data = examples["Verification JSON"]
        verification_path = self.artifacts / "contract-verification.json"
        cleanup.require_schema(verification_data, cleanup.VERIFICATION_SCHEMA, phase="verification", path=verification_path)
        cleanup.reject_unknown(verification_data, {"schema", "status", "checks", "digest"}, phase="verification", path=verification_path)
        cleanup.require_keys(verification_data, {"schema", "status", "checks", "digest"}, phase="verification", path=verification_path)
        self.assertEqual(verification_data["digest"], cleanup.digest_json(cleanup.data_without_digest(verification_data)))
        from helper.verifier import REQUIRED_CODES, SUPPORT_CODES

        allowed_verification_codes = set(REQUIRED_CODES + SUPPORT_CODES)
        verification_check_items = cleanup.require_list(verification_data["checks"], phase="verification", path=verification_path)
        for item in verification_check_items:
            self.assertIsInstance(item, dict)
            self.assertIn(cleanup.require_str(item, "code", phase="verification", path=verification_path), allowed_verification_codes)
        verification_checks = tuple(
            cleanup.check_from_dict(item, phase="verification", path=verification_path)
            for item in verification_check_items
        )
        verification = cleanup.VerificationResult(
            status=cleanup.require_str(verification_data, "status", phase="verification", path=verification_path),
            checks=verification_checks,
        )
        self.assertEqual(cleanup.verification_artifact(verification), verification_data)

        runtime_verification = cleanup.verify_receipt(runtime_receipt, runtime_context, ())
        obtainable_checks = {
            (check.code, check.status, check.severity, json.dumps(check.evidence, sort_keys=True, separators=(",", ":")))
            for check in runtime_verification.checks
        }
        for check in verification_checks:
            self.assertIn(
                (check.code, check.status, check.severity, json.dumps(check.evidence, sort_keys=True, separators=(",", ":"))),
                obtainable_checks,
            )

    def test_preservation_reference_covers_required_scopes_and_vetoes(self) -> None:
        text = PRESERVATION.read_text(encoding="utf-8")
        required_terms = (
            "MCP",
            "Engram",
            "packages",
            "binaries",
            "source",
            "node_modules",
            "history",
            "prompts",
            "messages",
            "caches",
            "backups",
            ".git/gentle-ai",
            "pablontiv",
            "personal skill veto",
            "provenance",
            "Pi registry authority",
            "report-only",
        )
        for term in required_terms:
            self.assertIn(term, text)

    def test_docs_have_no_personal_absolute_paths(self) -> None:
        forbidden = ("/Users/", "C:\\Users\\", "\\Users\\", "/home/pablontiv", "/home/pablo")
        for path in DOC_PATHS:
            text = path.read_text(encoding="utf-8")
            for term in forbidden:
                self.assertNotIn(term, text, f"{path} contains {term}")

    def test_readme_quick_discovery_is_platform_neutral(self) -> None:
        text = README.read_text(encoding="utf-8")
        self.assertIn("[`skills/remove-gentle-context/`](skills/remove-gentle-context/)", text)
        self.assertIn("Python 3.11+ executable", text)
        self.assertIn("python3", text)
        self.assertNotIn("ls skills/remove-gentle-context", text)

    def test_workflow_matrix_uses_three_operating_systems_and_portable_commands(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ubuntu-latest", text)
        self.assertIn("macos-latest", text)
        self.assertIn("windows-latest", text)
        self.assertEqual(text.count('python-version: "3.11"'), 1)
        self.assertIn("working-directory: skills/remove-gentle-context", text)
        self.assertIn("python -m unittest discover -s tests -t . -v", text)
        self.assertIn("python -m py_compile scripts/cleanup.py", text)
        self.assertIn("python scripts/cleanup.py --help", text)
        self.assertNotIn("cd skills/remove-gentle-context", text)
        self.assertNotIn("./scripts/cleanup.py", text)

    def test_pressure_contract_requires_canonical_safe_flow(self) -> None:
        text = "\n".join(path.read_text(encoding="utf-8") for path in DOC_PATHS)
        required_terms = (
            "canonical inventory",
            "plan approval",
            "fd-bound validation",
            "verified backup",
            "atomic rollback",
            "receipt",
            "live verification",
            "exact authority",
            "ambiguity blockers",
        )
        for term in required_terms:
            self.assertIn(term, text)
        forbidden_patterns = (
            r"(?:may|can|should|safe to|authorized? to)\s+[^.\n]*(?:delete|remove)\s+[^.\n]*(?:marker|name|path|text|fingerprint|author)",
            r"grep\s+[^.\n]*(?:then|and)\s+[^.\n]*(?:delete|remove)",
            r"(?:may|can|should|safe to|authorized? to)\s+[^.\n]*implicit restart",
            r"(?:may|can|should|safe to|authorized? to)\s+[^.\n]*skip(?:ped)? plan approval",
        )
        for pattern in forbidden_patterns:
            self.assertIsNone(__import__("re").search(pattern, text, __import__("re").IGNORECASE), pattern)

    def test_apply_requires_exact_approval(self) -> None:
        result = self.run_cli("apply", "--plan", str(self.artifacts / "plan.json"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("--approve", result.stderr)

    def test_programmatic_invalid_arguments_return_usage_without_system_exit(self) -> None:
        cleanup = load_cleanup_module()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = cleanup.main(["apply", "--plan", str(self.artifacts / "plan.json")])

        self.assertEqual(result, cleanup.EXIT_USAGE)
        self.assertIn("usage:", stderr.getvalue())
        self.assertIn("--approve", stderr.getvalue())

    def test_environment_artifact_round_trips_semantic_keys_and_default_state_path(self) -> None:
        appdata = self.temp_root / "roaming"
        localappdata = self.temp_root / "local"
        xdg_state = self.temp_root / "xdg-state"
        xdg_config = self.temp_root / "xdg-config"
        for root in (appdata, localappdata, xdg_state, xdg_config):
            root.mkdir()

        inventory = self.run_ok(
            "inventory",
            "--home",
            str(self.home),
            "--platform",
            "windows",
            "--env",
            f"LOCALAPPDATA={localappdata}",
            "--env",
            f"APPDATA={appdata}",
            "--env",
            f"XDG_STATE_HOME={xdg_state}",
            "--env",
            f"XDG_CONFIG_HOME={xdg_config}",
            "--output",
            str(self.artifacts / "windows-inventory.json"),
        )
        artifact = json.loads(Path(inventory.output_path).read_text())
        self.assertEqual(artifact["environment"]["APPDATA"], str(appdata.resolve()))
        self.assertEqual(artifact["environment"]["LOCALAPPDATA"], str(localappdata.resolve()))
        self.assertEqual(artifact["environment"]["XDG_STATE_HOME"], str(xdg_state.resolve()))
        self.assertEqual(set(artifact["environment"]), {"APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_STATE_HOME"})

        plan = self.run_ok("plan", "--inventory", str(inventory.output_path))
        self.assertTrue(str(plan.output_path).startswith(str(localappdata / "remove-gentle-context" / "state" / "artifacts")))

        linux_inventory = self.run_ok(
            "inventory",
            "--home",
            str(self.home),
            "--platform",
            "linux",
            "--env",
            f"XDG_STATE_HOME={xdg_state}",
        )
        self.assertTrue(str(linux_inventory.output_path).startswith(str(xdg_state / "remove-gentle-context" / "artifacts")))

    def test_inventory_environment_does_not_leak_unapproved_inherited_env(self) -> None:
        xdg_state = self.temp_root / "state-authority"
        xdg_state.mkdir()
        noisy_env = {**self.env, "APPDATA_SHADOW": str(self.temp_root / "shadow"), "GENTLE_PRIVATE_ROOT": str(self.temp_root / "private")}
        inventory = self.run_cli(
            "inventory",
            "--home",
            str(self.home),
            "--platform",
            "linux",
            "--env",
            f"XDG_STATE_HOME={xdg_state}",
            "--output",
            str(self.artifacts / "bounded-env-inventory.json"),
            env=noisy_env,
        )
        self.assertEqual(inventory.returncode, 0)

        artifact = json.loads(Path(inventory.output_path).read_text())
        self.assertEqual(artifact["environment"], {"XDG_STATE_HOME": str(xdg_state.resolve())})
        self.assertNotIn("APPDATA_SHADOW", json.dumps(artifact, sort_keys=True))
        self.assertNotIn("GENTLE_PRIVATE_ROOT", json.dumps(artifact, sort_keys=True))

    def test_inventory_loader_requires_and_validates_environment_field(self) -> None:
        cleanup = load_cleanup_module()
        inventory = self.inventory()
        assert inventory.output_path is not None
        original = json.loads(Path(inventory.output_path).read_text())

        missing = self.artifacts / "missing-environment.json"
        missing_data = dict(original)
        missing_data.pop("environment", None)
        missing.write_text(json.dumps(missing_data, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        with self.assertRaisesRegex(cleanup.CliError, "artifact_missing_field"):
            cleanup.load_inventory(missing)

        relative = self.artifacts / "relative-environment.json"
        relative_data = dict(original)
        relative_data["environment"] = {"XDG_STATE_HOME": "relative-state"}
        unsigned = {key: value for key, value in relative_data.items() if key not in {"schema", "digest"}}
        relative_data["digest"] = cleanup.digest_json(unsigned)
        relative.write_text(json.dumps(relative_data, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        with self.assertRaisesRegex(cleanup.CliError, "environment"):
            cleanup.load_inventory(relative)

        unknown = self.artifacts / "unknown-environment.json"
        unknown_data = dict(original)
        unknown_data["environment"] = {"GENTLE_PRIVATE_ROOT": str(self.temp_root / "private")}
        unsigned = {key: value for key, value in unknown_data.items() if key not in {"schema", "digest"}}
        unknown_data["digest"] = cleanup.digest_json(unsigned)
        unknown.write_text(json.dumps(unknown_data, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        with self.assertRaisesRegex(cleanup.CliError, "environment"):
            cleanup.load_inventory(unknown)

    def test_receipt_embedded_inventory_requires_environment_field(self) -> None:
        self.seed_cross_client_fixture()
        receipt = self.apply(self.plan(self.inventory()))
        cleanup = load_cleanup_module()
        data = json.loads(Path(receipt.json["receipt_path"]).read_text())
        data["inventory"].pop("environment", None)
        data["digest"] = cleanup.digest_json(cleanup.data_without_digest(data))
        tampered = self.artifacts / "receipt-missing-env.json"
        tampered.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")), encoding="utf-8")

        with self.assertRaisesRegex(cleanup.CliError, "artifact_missing_field"):
            cleanup.load_receipt(tampered)

    def test_full_five_command_flow_is_idempotent_in_temporary_home(self) -> None:
        self.seed_cross_client_fixture()
        history = self.home / ".codex" / "sessions" / "history.jsonl"
        history_before = history.read_bytes()
        opencode_config = self.home / ".config" / "opencode" / "opencode.json"
        opencode_mcp_before = json.loads(opencode_config.read_text())["mcp"]

        inventory = self.inventory()
        self.assertEqual(inventory.json["status"], "ok")
        self.assertGreater(inventory.json["counts"]["active"], 0)
        plan = self.plan(inventory)
        self.assertEqual(plan.json["approval"], plan.digest)
        receipt = self.apply(plan)
        self.assertEqual(receipt.json["status"], "completed")
        verification = self.verify(receipt)
        self.assertEqual(verification.json["status"], "passed")

        self.assertEqual(history.read_bytes(), history_before)
        self.assertEqual(json.loads(opencode_config.read_text())["mcp"], opencode_mcp_before)
        self.assertTrue((self.home / ".pi" / "node_modules" / "gentle-pi").is_dir())
        self.assertTrue((self.home / ".config" / "opencode" / "node_modules" / "opencode-sdd-engram-manage").is_dir())
        self.assertNotIn("npm:gentle-pi@latest", json.loads((self.home / ".pi" / "settings.json").read_text())["packages"])

        restored = self.restore(receipt.json["backup_manifest_path"], receipt.json["backup_manifest_digest"], receipt.json["receipt_path"])
        self.assertEqual(restored.json["status"], "completed")
        self.assertIn("npm:gentle-pi", json.loads((self.home / ".pi" / "settings.json").read_text())["packages"])

        reapplied_inventory = self.inventory()
        reapplied_plan = self.plan(reapplied_inventory)
        reapplied_receipt = self.apply(reapplied_plan, receipt_name="receipt-2.json")
        self.assertEqual(reapplied_receipt.json["status"], "completed")
        second = self.inventory()
        self.assertEqual(second.json["counts"]["active"], 0)

    def test_approval_rejection_tamper_symlink_drift_and_verify_failure_exit_codes(self) -> None:
        self.seed_cross_client_fixture()
        inventory = self.inventory()
        plan = self.plan(inventory)

        wrong = self.run_cli("apply", "--inventory", str(self.last_inventory_path), "--plan", str(plan.output_path), "--approve", "sha256:" + "0" * 64, "--receipt", str(self.artifacts / "bad-receipt.json"))
        self.assertEqual(wrong.returncode, 20)
        self.assertIn("approval", wrong.stderr)

        tampered_plan = self.artifacts / "tampered-plan.json"
        data = json.loads(Path(plan.output_path).read_text())
        data["operations"] = []
        tampered_plan.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        tampered = self.run_cli("apply", "--inventory", str(self.last_inventory_path), "--plan", str(tampered_plan), "--approve", plan.digest or "")
        self.assertEqual(tampered.returncode, 12)
        self.assertIn("digest", tampered.stderr)

        symlink = self.artifacts / "plan-link.json"
        symlink.symlink_to(plan.output_path)
        linked = self.run_cli("apply", "--inventory", str(self.last_inventory_path), "--plan", str(symlink), "--approve", plan.digest or "")
        self.assertEqual(linked.returncode, 11)
        self.assertIn("symlink", linked.stderr)

        # Removed fake home overrides are ignored; artifact authority remains the inventory home/root map.
        ignored_env = {**self.env, REMOVED_HOME_ENV: str(self.temp_root / "other-home")}
        (self.temp_root / "other-home").mkdir()
        ignored = self.run_cli("plan", "--inventory", str(inventory.output_path), "--output", str(self.artifacts / "ignored-env-plan.json"), env=ignored_env)
        self.assertEqual(ignored.returncode, 0)

        receipt = self.apply(plan)
        (self.home / ".pi" / "settings.json").write_text('{"packages":["npm:gentle-pi"]}\n', encoding="utf-8")
        failed_verify = self.run_cli("verify", "--inventory", str(self.last_inventory_path), "--plan", str(plan.output_path), "--receipt", receipt.json["receipt_path"], "--output", str(self.artifacts / "failed-verification.json"))
        self.assertEqual(failed_verify.returncode, 30)
        self.assertEqual(failed_verify.json["status"], "failed")

    def test_restore_rejects_wrong_approval_and_wrong_root(self) -> None:
        self.seed_cross_client_fixture()
        receipt = self.apply(self.plan(self.inventory()))
        wrong_approval = self.run_cli("restore", "--manifest", receipt.json["backup_manifest_path"], "--receipt", receipt.json["receipt_path"], "--approve", "sha256:" + "1" * 64, "--output", str(self.artifacts / "restore-wrong.json"))
        self.assertEqual(wrong_approval.returncode, 20)
        self.assertIn("approval", wrong_approval.stderr)

        wrong_root_env = {**self.env, REMOVED_HOME_ENV: str(self.temp_root / "wrong-root")}
        (self.temp_root / "wrong-root").mkdir()
        ignored_root = self.run_cli("restore", "--manifest", receipt.json["backup_manifest_path"], "--receipt", receipt.json["receipt_path"], "--approve", receipt.json["backup_manifest_digest"], "--output", str(self.artifacts / "restore-ignored-root.json"), env=wrong_root_env)
        self.assertEqual(ignored_root.returncode, 0)

    def test_atomic_output_interruption_leaves_previous_artifact_intact(self) -> None:
        output = self.artifacts / "inventory.json"
        output.write_text('{"previous":true}\n', encoding="utf-8")
        cleanup = load_cleanup_module()
        stderr = io.StringIO()
        with mock.patch.object(cleanup, "write_json_atomic", side_effect=OSError("simulated atomic failure")), contextlib.redirect_stderr(stderr):
            failed = cleanup.main(["inventory", "--home", str(self.home), "--platform", "linux", "--output", str(output)])
        self.assertEqual(failed, 13)
        self.assertIn("OSError", stderr.getvalue())
        self.assertEqual(output.read_text(encoding="utf-8"), '{"previous":true}\n')

        ignored_env = {**self.env, REMOVED_ATOMIC_ENV: str(output)}
        succeeded = self.run_cli("inventory", "--home", str(self.home), "--platform", "linux", "--output", str(output), env=ignored_env)
        self.assertEqual(succeeded.returncode, 0)
        self.assertNotEqual(output.read_text(encoding="utf-8"), '{"previous":true}\n')

    def test_cli_apply_writes_receipt_before_nonzero_exit_for_contained_transaction_failure(self) -> None:
        cleanup = load_cleanup_module()
        target = self.home / "cli-contained-failure.txt"
        target.write_text("before", encoding="utf-8")
        context = cleanup.RuntimeContext(cleanup.PlatformProfile("linux", self.home, {"XDG_STATE_HOME": str(self.temp_root / "state")}))
        inventory = cleanup.Inventory(
            os_name=context.profile.os_name,
            home=str(self.home),
            root_map=dict(sorted(cleanup.root_map(context).items())),
            environment=dict(sorted(context.profile.env.items())),
            adapter_versions={"fixture": "1.0"},
            adapter_layouts={"fixture": "layout-v1"},
        ).with_digest()
        before = b"before"
        after = b"after"
        before_digest = "sha256:" + hashlib.sha256(before).hexdigest()
        after_digest = "sha256:" + hashlib.sha256(after).hexdigest()
        plan = cleanup.Plan(
            inventory_digest=inventory.digest,
            os_name=inventory.os_name,
            home=inventory.home,
            root_map=dict(sorted(inventory.root_map.items())),
            adapter_versions={"fixture": "1.0"},
            adapter_layouts={"fixture": "layout-v1"},
            operations=(
                cleanup.Operation(
                    kind=cleanup.OperationKind.WRITE_FILE,
                    path=str(target),
                    preimage_base64=base64.b64encode(before).decode("ascii"),
                    preimage_sha256=before_digest,
                    postimage_base64=base64.b64encode(after).decode("ascii"),
                    postimage_sha256=after_digest,
                ),
            ),
        ).with_digest()
        inventory_path = self.artifacts / "contained-inventory.json"
        plan_path = self.artifacts / "contained-plan.json"
        receipt_path = self.artifacts / "contained-receipt.json"
        inventory_path.write_text(json.dumps(cleanup.inventory_artifact(inventory), sort_keys=True, separators=(",", ":")), encoding="utf-8")
        plan_path.write_text(json.dumps(cleanup.plan_artifact(plan), sort_keys=True, separators=(",", ":")), encoding="utf-8")
        fake_receipt = cleanup.Receipt(
            operation_outcomes=(cleanup.OperationOutcome(0, str(cleanup.OperationKind.WRITE_FILE), str(target), "failed", "backup_failed"),),
            status=cleanup.ReceiptStatus.NOT_STARTED,
            plan=plan,
            inventory=inventory,
        )
        class StdoutCapture:
            def __init__(self) -> None:
                self.buffer = io.BytesIO()

            def write(self, _text: str) -> int:
                return 0

            def flush(self) -> None:
                return

        stdout = StdoutCapture()
        stderr = io.StringIO()
        argv = ["apply", "--inventory", str(inventory_path), "--plan", str(plan_path), "--approve", plan.digest or "", "--receipt", str(receipt_path)]

        with mock.patch.object(cleanup, "execute_plan", return_value=fake_receipt), mock.patch.object(cleanup.sys, "stdout", stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                cleanup.main(argv)

        self.assertEqual(raised.exception.code, cleanup.EXIT_APPLY)
        self.assertTrue(receipt_path.is_file())
        persisted = cleanup.load_receipt(receipt_path)
        self.assertEqual(persisted.status, cleanup.ReceiptStatus.NOT_STARTED)
        self.assertEqual(persisted.operation_outcomes[0].error, "backup_failed")
        self.assertEqual(json.loads(stdout.buffer.getvalue())["status"], "not_started")
        self.assertIn("apply_not_started", stderr.getvalue())

    def test_pi_registry_without_reliable_probe_is_blocked_and_not_deleted(self) -> None:
        registry = self.seed_pi_registry_fixture()
        inventory = self.inventory()
        candidates = [candidate for candidate in json.loads(Path(inventory.output_path).read_text())["candidates"] if candidate["client"] == "pi"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["ownership"], "ambiguous")
        self.assertEqual(candidates[0]["proposed_action"], "report_only")
        self.assertIn("process_probe_unavailable", json.dumps(candidates[0], sort_keys=True))

        plan = self.plan(inventory)
        plan_data = json.loads(Path(plan.output_path).read_text())
        self.assertEqual(plan_data.get("operations", []), [])
        self.assertEqual(plan.json["counts"]["blocked"], 1)
        receipt = self.apply(plan)
        self.assertEqual(receipt.json["status"], "completed")
        self.assertEqual(receipt.json["counts"], {"operations": 0, "lifecycle": 0})
        self.assertIn("backup_manifest_digest", receipt.json)
        self.assertIsNone(receipt.json["backup_manifest_digest"])
        self.assertTrue(registry.is_file())

    def test_inventory_context_roots_must_be_absolute_canonical_and_not_links(self) -> None:
        relative_home = self.run_cli("inventory", "--home", "relative-home", "--platform", "linux", "--output", str(self.artifacts / "relative.json"))
        self.assertEqual(relative_home.returncode, 2)
        self.assertIn("root", relative_home.stderr)

        symlink_home = self.temp_root / "home-link"
        symlink_home.symlink_to(self.home, target_is_directory=True)
        linked_home = self.run_cli("inventory", "--home", str(symlink_home), "--platform", "linux", "--output", str(self.artifacts / "linked.json"))
        self.assertEqual(linked_home.returncode, 2)
        self.assertIn("root", linked_home.stderr)

        relative_env = self.run_cli("inventory", "--home", str(self.home), "--platform", "linux", "--env", "XDG_CONFIG_HOME=relative-config", "--output", str(self.artifacts / "relative-env.json"))
        self.assertEqual(relative_env.returncode, 2)
        self.assertIn("env", relative_env.stderr)

        canonical_env_root = self.temp_root / "xdg-config"
        canonical_env_root.mkdir()
        valid = self.run_cli("inventory", "--home", str(self.home), "--platform", "linux", "--env", f"XDG_CONFIG_HOME={canonical_env_root}", "--output", str(self.artifacts / "valid-env.json"))
        self.assertEqual(valid.returncode, 0)

    def test_deterministic_plan_bytes(self) -> None:
        self.seed_cross_client_fixture()
        inventory = self.inventory()
        first = self.plan(inventory)
        first_bytes = Path(first.output_path).read_bytes()
        second = self.run_ok("plan", "--inventory", str(inventory.output_path), "--output", str(self.artifacts / "plan-second.json"))
        self.assertEqual(first_bytes, Path(second.output_path).read_bytes())
        self.assertEqual(first.digest, second.digest)


if __name__ == "__main__":
    unittest.main()
