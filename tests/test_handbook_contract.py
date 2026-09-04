from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
AGENTS_PATH = ROOT / "AGENTS.md"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
HERO = (
    "Un handbook para convertir el trabajo de desarrollo improvisado en un "
    "método reproducible, verificable y adaptable."
)
SUPPORT = (
    "Reúne reglas, skills, herramientas y memoria para orientar el trabajo "
    "de personas y agentes."
)
APPROVED_IDENTITY_BLOCK = f"# Handbook\n\n{HERO}\n\n{SUPPORT}"
REMOVE_GENTLE_CONTEXT_LINK = "[`skills/remove-gentle-context/`](skills/remove-gentle-context/)"
LINK_PATTERN = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
REQUIRED_AGENT_CLAUSES = (
    "portable working handbook",
    "Every top-level artifact family must be globally useful, portable, publicly distributable, and explicitly owned.",
    "Give each artifact one explicit owner and keep its runtime dependencies with it.",
    "Add a top-level artifact family only when real content exists; do not scaffold empty categories.",
    "Document how each new family contributes to the handbook, how it is verified, and where its portability boundary lies.",
    "Treat agent runtimes and external tools as integrations, not as the handbook's category.",
    "Keep every skill self-contained under `skills/<name>/` and avoid dependencies between sibling skills.",
    "Treat inventory and planning as read-only operations.",
    "Require explicit, digest-bound approval before destructive actions.",
    "Support macOS, Linux, and Windows without hard-coded user paths.",
    "Prefer the Python standard library for helpers.",
    "Before implementation, identify and review the accepted ADR that governs the change.",
    "Validate each new or modified ADR with `rootline validate .workspace/docs/adr/NNNN-slug.md --strict`.",
    "Before work, resolve the operational workspace policy from `.workspace/config.yaml`.",
    "Keep documentation synchronized with executable behavior.",
    "Run the complete test suite before committing.",
    "Integrate changes through pull requests.",
)


class HandbookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README_PATH.read_text(encoding="utf-8")
        cls.agents = AGENTS_PATH.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def assert_readme_leads_with_approved_identity(self, text: str) -> None:
        self.assertTrue(
            text.startswith(APPROVED_IDENTITY_BLOCK),
            "README must begin with the approved Handbook identity before category, vendor, or runtime branding.",
        )

    def assert_agents_contract(self, text: str) -> None:
        for clause in REQUIRED_AGENT_CLAUSES:
            self.assertIn(clause, text)
        self.assertNotIn(
            "This repository publishes independent, portable Agent Skills.",
            text,
        )

    def assert_remove_gentle_context_portability(self, text: str) -> None:
        bullet = next(
            (
                line
                for line in text.splitlines()
                if line.startswith(f"- {REMOVE_GENTLE_CONTEXT_LINK}")
            ),
            "",
        )
        self.assertTrue(bullet, "README must expose the exact remove-gentle-context discovery link.")
        self.assertIn("Python 3.11+ executable", bullet)
        self.assertIn("`python`", bullet)
        self.assertIn("`python3`", bullet)
        self.assertIn("equivalent", bullet)
        self.assertNotIn("with `python3`", bullet)

    def test_readme_leads_with_approved_identity(self) -> None:
        self.assert_readme_leads_with_approved_identity(self.readme)

    def test_readme_rejects_prepended_category_or_vendor_branding(self) -> None:
        for branding in (
            "# Agent Skills\n\nPublic collection of portable Agent Skills.\n\n",
            "# Pi Handbook\n\nVendor-specific agent runtime guidance.\n\n",
        ):
            with self.subTest(branding=branding.splitlines()[0]):
                with self.assertRaises(AssertionError):
                    self.assert_readme_leads_with_approved_identity(
                        f"{branding}{APPROVED_IDENTITY_BLOCK}\n"
                    )

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
            "profiles/",
            "skills/",
            "output-styles/",
            ".workspace/docs/adr/",
            ".workspace/docs/superpowers/",
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
        self.assert_agents_contract(self.agents)

    def test_agent_contract_rejects_removal_of_required_clauses(self) -> None:
        for clause in REQUIRED_AGENT_CLAUSES:
            with self.subTest(clause=clause):
                mutated = self.agents.replace(clause, "", 1)
                with self.assertRaises(AssertionError):
                    self.assert_agents_contract(mutated)

    def test_github_actions_are_pinned_to_commits(self) -> None:
        action_refs = re.findall(r"^\s*- uses: \S+@([^\s]+)$", self.workflow, re.MULTILINE)
        self.assertTrue(action_refs)
        for ref in action_refs:
            with self.subTest(ref=ref):
                self.assertRegex(ref, r"^[0-9a-f]{40}$")

    def test_checkout_does_not_persist_credentials(self) -> None:
        self.assertIn("persist-credentials: false", self.workflow)

    def test_no_legacy_document_authority_remains(self) -> None:
        self.assertFalse((ROOT / "docs").exists())
        self.assertNotIn("(docs/adr/)", self.readme)
        self.assertNotIn("(docs/superpowers/)", self.readme)

    def test_profile_is_published(self) -> None:
        self.assertIn("(profiles/pablontiv/)", self.readme)
        self.assertIn("Pi", self.readme)
        self.assertIn("Rootline", self.readme)
        self.assertIn("Backscroll", self.readme)

    def test_remove_gentle_context_readme_discovery_is_portable(self) -> None:
        self.assert_remove_gentle_context_portability(self.readme)


if __name__ == "__main__":
    unittest.main()
