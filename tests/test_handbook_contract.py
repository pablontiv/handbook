from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
AGENTS_PATH = ROOT / "AGENTS.md"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
DEPENDABOT_PATH = ROOT / ".github" / "dependabot.yml"
TEST_REQUIREMENTS_PATH = ROOT / "requirements-test.txt"
HERO = (
    "Un handbook para convertir el trabajo de desarrollo improvisado en un "
    "método reproducible, verificable y adaptable."
)
SUPPORT = (
    "Reúne reglas, skills, herramientas y memoria para orientar el trabajo "
    "de personas y agentes."
)
APPROVED_IDENTITY_BLOCK = f"# Handbook\n\n{HERO}\n\n{SUPPORT}"
REMOVE_GENTLE_CONTEXT_LINK = (
    "[`skills/remove-gentle-context/`](skills/remove-gentle-context/)"
)
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


def load_skill_frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"{path} must begin with YAML frontmatter")
    _, raw_frontmatter, _ = text.split("---", 2)
    parsed = yaml.safe_load(raw_frontmatter)
    if not isinstance(parsed, dict):
        raise AssertionError(f"{path} frontmatter must be a mapping")
    return parsed


class HandbookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README_PATH.read_text(encoding="utf-8")
        cls.agents = AGENTS_PATH.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.dependabot = yaml.safe_load(DEPENDABOT_PATH.read_text(encoding="utf-8"))
        if not isinstance(cls.dependabot, dict):
            raise TypeError("dependabot.yml must contain a mapping")
        cls.test_requirements = TEST_REQUIREMENTS_PATH.read_text(encoding="utf-8")

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
        self.assertTrue(
            bullet, "README must expose the exact remove-gentle-context discovery link."
        )
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
            with (
                self.subTest(branding=branding.splitlines()[0]),
                self.assertRaises(AssertionError),
            ):
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

    def test_every_published_skill_declares_pablontiv_author(self) -> None:
        skill_paths = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertTrue(skill_paths)
        for path in skill_paths:
            with self.subTest(skill=path.parent.name):
                frontmatter = load_skill_frontmatter(path)
                metadata = frontmatter.get("metadata")
                self.assertIsInstance(metadata, dict, path.relative_to(ROOT))
                if not isinstance(metadata, dict):
                    continue
                self.assertEqual(
                    metadata.get("author"),
                    "pablontiv",
                    path.relative_to(ROOT),
                )

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
        for workflow_path in sorted(
            (ROOT / ".github" / "workflows").glob("*.yml")
        ):
            workflow = workflow_path.read_text(encoding="utf-8")
            with self.subTest(workflow=workflow_path.name):
                action_refs = re.findall(
                    r"^\s*- uses: \S+@([^\s]+)$", workflow, re.MULTILINE
                )
                self.assertTrue(action_refs)
                for ref in action_refs:
                    with self.subTest(ref=ref):
                        self.assertRegex(ref, r"^[0-9a-f]{40}$")

    def test_checkout_does_not_persist_credentials(self) -> None:
        for workflow_path in sorted(
            (ROOT / ".github" / "workflows").glob("*.yml")
        ):
            workflow = workflow_path.read_text(encoding="utf-8")
            with self.subTest(workflow=workflow_path.name):
                self.assertIn("persist-credentials: false", workflow)

    def test_dependabot_updates_are_weekly_and_grouped(self) -> None:
        self.assertEqual(self.dependabot.get("version"), 2)
        updates = self.dependabot.get("updates")
        self.assertIsInstance(updates, list)
        assert isinstance(updates, list)
        self.assertEqual(
            {
                (update.get("package-ecosystem"), update.get("directory"))
                for update in updates
            },
            {("pip", "/"), ("github-actions", "/")},
        )
        self.assertEqual(len(updates), 2)
        for update in updates:
            ecosystem = update["package-ecosystem"]
            with self.subTest(ecosystem=ecosystem):
                self.assertEqual(update.get("schedule"), {"interval": "weekly"})
                self.assertEqual(update.get("cooldown"), {"default-days": 7})
                groups = update.get("groups")
                self.assertIsInstance(groups, dict)
                assert isinstance(groups, dict)
                self.assertEqual(
                    {group.get("applies-to") for group in groups.values()},
                    {"version-updates", "security-updates"},
                )
                for group in groups.values():
                    self.assertEqual(group.get("patterns"), ["*"])

    def test_python_cache_artifacts_are_ignored(self) -> None:
        candidates = (
            "nested/__pycache__/metadata.txt",
            "nested/module.pyc",
            "nested/module.py",
        )
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin"],
            cwd=ROOT,
            input=("\n".join(candidates) + "\n").encode("ascii"),
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(
            result.stdout.decode("ascii").splitlines(),
            list(candidates[:2]),
            "Python bytecode must be ignored without hiding source files.",
        )

    def test_profile_test_dependency_is_pinned_installed_and_documented(self) -> None:
        install = (
            "python -m pip install --disable-pip-version-check --no-deps "
            "-r requirements-test.txt"
        )
        profile_tests = (
            "python -m unittest discover -s profiles/pablontiv/tests "
            '-t profiles/pablontiv -p "test_*.py" -v'
        )
        self.assertEqual(self.test_requirements.strip(), "PyYAML==6.0.3")
        self.assertIn(install, " ".join(self.workflow.split()))
        self.assertIn(install, self.readme)
        self.assertIn(profile_tests, self.readme)

    def test_ci_validates_every_rootline_boundary(self) -> None:
        for target in (
            ".workspace/docs/adr",
            ".workspace/docs/superpowers",
            "profiles/pablontiv",
        ):
            with self.subTest(target=target):
                self.assertIn(f"rootline validate --all {target}", self.workflow)

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
