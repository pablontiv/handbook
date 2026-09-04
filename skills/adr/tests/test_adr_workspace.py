from __future__ import annotations

import importlib
import subprocess
import tempfile
import unittest
from pathlib import Path

shell_support = importlib.import_module("tests.shell_support")

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "adr.sh"
BASH = shell_support.resolve_bash()


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, str(SCRIPT), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def init_git(root: Path) -> None:
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )


class AdrWorkspaceTests(unittest.TestCase):
    def test_detect_prefers_workspace_authority(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".workspace/docs/adr").mkdir(parents=True)
            (root / ".workspace/config.yaml").write_text(
                "schema_version: workspace-control/v1\n"
            )
            (root / ".workspace/docs/adr/.stem").write_text("version: 2\nroot: true\n")
            result = run(root, "detect")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), ".workspace/docs/adr")

    def test_detect_from_nested_directory_uses_git_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_git(root)
            (root / ".workspace/docs/adr").mkdir(parents=True)
            (root / ".workspace/config.yaml").write_text(
                "schema_version: workspace-control/v1\n"
            )
            (root / ".workspace/docs/adr/.stem").write_text("version: 2\n")
            nested = root / "packages/service"
            nested.mkdir(parents=True)
            result = run(nested, "detect")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), ".workspace/docs/adr")

    def test_adopted_workspace_never_falls_back_to_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".workspace").mkdir()
            (root / ".workspace/config.yaml").write_text(
                "schema_version: workspace-control/v1\n"
            )
            (root / "docs/adr").mkdir(parents=True)
            (root / "docs/adr/.stem").write_text("version: 2\nroot: true\n")
            result = run(root, "detect")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

    def test_non_workspace_repository_keeps_legacy_detection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "docs/adr").mkdir(parents=True)
            (root / "docs/adr/.stem").write_text("version: 2\nroot: true\n")
            result = run(root, "detect")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "docs/adr")

    def test_versioned_init_from_nested_directory_inherits_workspace_stem(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_git(root)
            (root / ".workspace/docs").mkdir(parents=True)
            (root / ".workspace/config.yaml").write_text(
                "schema_version: workspace-control/v1\n"
            )
            (root / ".workspace/docs/.stem").write_text("version: 2\nroot: true\n")
            nested = root / "packages/service"
            nested.mkdir(parents=True)
            result = run(nested, "init", "versioned")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), ".workspace/docs/adr")
            stem = (root / ".workspace/docs/adr/.stem").read_text()
            self.assertNotIn("root: true", stem)
            self.assertIn("schema:", stem)
            self.assertFalse((nested / ".workspace").exists())

    def test_versioned_init_fails_without_workspace_parent_stem(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".workspace").mkdir()
            (root / ".workspace/config.yaml").write_text(
                "schema_version: workspace-control/v1\n"
            )
            result = run(root, "init", "versioned")
            self.assertEqual(result.returncode, 2)
            self.assertIn(".workspace/docs/.stem", result.stderr)
            self.assertFalse((root / ".workspace/docs/adr").exists())

    def test_legacy_versioned_init_retains_root_stem(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = run(root, "init", "versioned")
            self.assertEqual(result.returncode, 0, result.stderr)
            stem = (root / "docs/adr/.stem").read_text()
            self.assertIn("root: true", stem)

    def test_local_init_is_rejected_when_workspace_is_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".workspace").mkdir()
            (root / ".workspace/config.yaml").write_text(
                "schema_version: workspace-control/v1\n"
            )
            result = run(root, "init", "local")
            self.assertEqual(result.returncode, 2)
            self.assertIn("local ADR store is not allowed", result.stderr)
            self.assertFalse((root / ".adr").exists())

    def test_dry_run_uses_process_stdout_without_device_path(self) -> None:
        self.assertNotIn("/dev/stdout", SCRIPT.read_text())

    def test_propose_uses_maximum_existing_number_across_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adr = root / ".workspace/docs/adr"
            adr.mkdir(parents=True)
            (root / ".workspace/config.yaml").write_text(
                "schema_version: workspace-control/v1\n"
            )
            (root / ".workspace/docs/.stem").write_text("version: 2\nroot: true\n")
            (adr / ".stem").write_text("version: 2\n")
            (adr / "0001-first.md").write_text("")
            (adr / "0003-third.md").write_text("")
            result = run(
                root,
                "--dry-run",
                "propose",
                "next-decision",
                "contexto",
                "decisión",
                "alternativa",
                "consecuencia",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("# 0004. Next decision", result.stdout)
            self.assertIn("0004-next-decision.md", result.stderr)


if __name__ == "__main__":
    unittest.main()
