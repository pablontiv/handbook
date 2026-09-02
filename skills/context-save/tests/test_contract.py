import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL = ROOT / "SKILL.md"
LICENSE = ROOT / "LICENSE"


class ContextSaveContractTests(unittest.TestCase):
    def test_skill_and_license_contract(self):
        skill = SKILL.read_text(encoding="utf-8")
        license_text = LICENSE.read_text(encoding="utf-8")

        self.assertIn("name: context-save", skill)
        self.assertIn("source: pablontiv/praxis", skill)
        self.assertIn("values: [session-state]", skill)
        self.assertIn("values: [saved, restored, archived]", skill)
        self.assertNotRegex(skill, r"(?m)^[ \t]*enum\s*:")
        self.assertNotIn("$ARGUMENTS", skill)
        self.assertIn("save", skill)
        self.assertIn("restore", skill)
        self.assertIn("list", skill)
        self.assertIn("rootline", skill)
        self.assertRegex(skill, r"(?m)^[ \t]*backscroll\b[^\n]*\boptional\b")
        self.assertNotIn("/Users/", skill)
        self.assertNotIn("/home/", skill)
        self.assertIn("PolyForm Noncommercial License 1.0.0", license_text)
