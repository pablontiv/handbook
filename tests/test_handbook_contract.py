from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
AGENTS_PATH = ROOT / "AGENTS.md"
HERO = (
    "Un handbook para convertir el trabajo de desarrollo improvisado en un "
    "método reproducible, verificable y adaptable."
)
SUPPORT = (
    "Reúne reglas, skills, herramientas y memoria para orientar el trabajo "
    "de personas y agentes."
)
LINK_PATTERN = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


class HandbookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README_PATH.read_text(encoding="utf-8")
        cls.agents = AGENTS_PATH.read_text(encoding="utf-8")

    def test_readme_leads_with_approved_identity(self) -> None:
        self.assertIn(f"# Handbook\n\n{HERO}\n\n{SUPPORT}", self.readme)

    def test_every_published_skill_is_linked(self) -> None:
        skills = sorted(
            path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")
        )
        self.assertTrue(skills)
        for name in skills:
            with self.subTest(skill=name):
                self.assertIn(f"(skills/{name}/)", self.readme)

    def test_existing_artifact_families_are_linked(self) -> None:
        for target in (
            "AGENTS.md",
            "skills/",
            "output-styles/",
            "docs/adr/",
            "docs/superpowers/",
        ):
            with self.subTest(target=target):
                self.assertIn(f"({target})", self.readme)

    def test_relative_markdown_links_resolve(self) -> None:
        for raw_target in LINK_PATTERN.findall(self.readme):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith("#"):
                continue
            relative = unquote(parsed.path)
            with self.subTest(target=target):
                self.assertTrue((ROOT / relative).exists(), target)

    def test_stale_identity_claims_are_absent(self) -> None:
        stale = (
            "Public collection of portable Agent Skills",
            "https://github.com/pablontiv/gentle-ai",
            "Pull requests are disabled",
            "## Planned skills",
        )
        for claim in stale:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, self.readme)

    def test_agent_contract_uses_handbook_identity(self) -> None:
        self.assertIn("portable working handbook", self.agents)
        self.assertNotIn(
            "This repository publishes independent, portable Agent Skills.",
            self.agents,
        )
        self.assertIn("Keep every skill self-contained", self.agents)


if __name__ == "__main__":
    unittest.main()
