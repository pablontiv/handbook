from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "adr.sh"


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


class AdrWorkspaceTests(unittest.TestCase):
    def test_detect_prefers_workspace_authority(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".workspace/docs/adr").mkdir(parents=True)
            (root / ".workspace/config.yaml").write_text(
                "schema_version: workspace-control/v1\n"
            )
            (root / ".workspace/docs/adr/.stem").write_text(
                "version: 2\nroot: true\n"
            )
            result = run(root, "detect")
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

    def test_versioned_init_uses_workspace_destination_when_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".workspace").mkdir()
            (root / ".workspace/config.yaml").write_text(
                "schema_version: workspace-control/v1\n"
            )
            result = run(root, "init", "versioned")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), ".workspace/docs/adr")
            self.assertTrue((root / ".workspace/docs/adr/.stem").is_file())


if __name__ == "__main__":
    unittest.main()
