import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL = ROOT / "SKILL.md"
ASSETS = ROOT / "assets"
ASSET_TEST = ASSETS / "test-assets.sh"

REJECTED_PATH_SNIPPETS = ("/Users/Shared", "/Users/pones", "/home/pones")
REQUIRED_AGENTS = {"sweep-scout.md", "sweep-triage.md", "pr-investigator.md"}
REQUIRED_CLAUDE = REQUIRED_AGENTS
REQUIRED_PI = REQUIRED_AGENTS


class SweepContractTests(unittest.TestCase):
    def test_bundle_shape_and_runtime_contract(self):
        self.assertTrue(SKILL.exists(), "missing SKILL.md")
        self.assertTrue(ASSET_TEST.exists(), "missing asset test harness")

        skill = SKILL.read_text(encoding="utf-8")
        asset_test = ASSET_TEST.read_text(encoding="utf-8")

        for text in (skill, asset_test):
            for snippet in REJECTED_PATH_SNIPPETS:
                self.assertNotIn(snippet, text)

        for agent in REQUIRED_CLAUDE:
            text = (ROOT / "agents" / "claude" / agent).read_text(encoding="utf-8")
            for snippet in REJECTED_PATH_SNIPPETS:
                self.assertNotIn(snippet, text)

        def names(subdir: str) -> set[str]:
            return {path.name for path in (ROOT / "agents" / subdir).glob("*.md")}

        self.assertEqual(REQUIRED_CLAUDE, names("claude"))
        self.assertEqual(REQUIRED_PI, names("pi"))

        for agent in REQUIRED_CLAUDE:
            text = (ROOT / "agents" / "claude" / agent).read_text(encoding="utf-8")
            self.assertIn("Bash", text)
            self.assertIn("Read", text)
            self.assertIn("parent-visible", text)
            self.assertIn("delivery", text)

        for agent in REQUIRED_PI:
            text = (ROOT / "agents" / "pi" / agent).read_text(encoding="utf-8")
            self.assertIn("bash", text)
            self.assertIn("read", text)
            self.assertNotIn("SendMessage", text)
            self.assertNotIn("color", text)
            self.assertNotRegex(text, r"(?i)hard[- ]coded model")
            self.assertIn("final response directly", text)
            self.assertNotIn("/Users/Shared", text)
            self.assertNotIn("/Users/pones", text)
            self.assertNotIn("/home/pones", text)

        self.assertIn(".worktrees", asset_test)
        self.assertNotIn(".orca/worktrees", asset_test)
