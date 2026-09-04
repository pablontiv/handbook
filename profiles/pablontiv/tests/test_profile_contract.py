from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

PROFILE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROFILE_ROOT.parents[1]
PROFILE_PATH = PROFILE_ROOT / "PROFILE.md"
BOOTSTRAP_PATH = PROFILE_ROOT / "bootstrap.md"
TEMPLATE_PATH = PROFILE_ROOT / "config.template.yaml"
SOURCE_PATH = PROFILE_ROOT / "references" / "engineering-handbook-v1.4.md"
SOURCE_SHA256 = "f5455e3eced13690358b02823053a1e00a6c7c06de5f17d9716805bf0a0cff26"

PROFILE_SECTIONS = (
    "Propósito",
    "Principios de diseño",
    "Modelo de workspace",
    "Resolución de configuración",
    "Contrato de los controles",
    "Ejes configurables",
    "Valores por defecto",
    "Flujo de trabajo",
    "Invariantes",
    "Configuración mínima por repositorio",
    "Ejemplo no normativo de binding",
    "Precedencia frente a steering y automatización",
    "Seguridad y sistemas externos",
    "Adopción",
    "Criterios de aceptación",
    "Fuera de alcance",
)

CONFIG_AXES = (
    "context_sources",
    "base_branch",
    "sync_strategy",
    "isolation_strategy",
    "development_workflow",
    "commit_policy",
    "delivery_mode",
    "delivery_gate",
    "pre_checks",
    "acceptance_checks",
    "review_checks",
    "post_checks",
    "monitoring",
    "external_effects",
    "credential_policy",
    "knowledge_policy",
    "cleanup_policy",
    "custom_rules",
)

BASE_CONTRACT_MARKERS = (
    "workspace → group → repository",
    "Los escalares de una capa más específica reemplazan",
    "Los mapas se combinan recursivamente",
    "Las listas se reemplazan completas",
    "passed",
    "failed",
    "unknown",
    "not_applicable",
    "INV-01",
    "INV-11",
    "Fase 0",
    "Fase 8",
)


def published_artifacts() -> set[str]:
    skills = {
        path.parent.name
        for path in (REPO_ROOT / "skills").glob("*/SKILL.md")
    }
    agents = {
        path.stem
        for path in (REPO_ROOT / "skills").glob("*/agents/pi/*.md")
    }
    styles = {
        path.stem
        for path in (REPO_ROOT / "output-styles").glob("*.md")
    }
    return skills | agents | styles


class ProfileContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = PROFILE_PATH.read_text(encoding="utf-8")
        cls.bootstrap = BOOTSTRAP_PATH.read_text(encoding="utf-8")
        cls.template = TEMPLATE_PATH.read_text(encoding="utf-8")

    def test_source_snapshot_has_approved_digest(self) -> None:
        self.assertEqual(
            hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
            SOURCE_SHA256,
        )

    def test_profile_preserves_all_base_sections(self) -> None:
        headings = set(
            re.findall(r"^## (?:\d+\. )?(.+)$", self.profile, re.MULTILINE)
        )
        self.assertEqual(set(PROFILE_SECTIONS) - headings, set())

    def test_profile_preserves_contract_categories(self) -> None:
        for marker in BASE_CONTRACT_MARKERS:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.profile)

    def test_template_preserves_layers_and_axes(self) -> None:
        for layer in ("workspace:", "groups:", "repositories:"):
            self.assertIn(layer, self.template)
        for axis in CONFIG_AXES:
            self.assertRegex(self.template, rf"(?m)^\s+{re.escape(axis)}:")

    def test_profile_routes_every_published_artifact(self) -> None:
        for artifact in sorted(published_artifacts()):
            with self.subTest(artifact=artifact):
                self.assertIn(f"`{artifact}`", self.profile)

    def test_profile_requires_rootline_backscroll_and_pi(self) -> None:
        for required in ("Rootline", "Backscroll", "Pi"):
            self.assertIn(required, self.profile)

    def test_remove_gentle_context_scope_is_bounded(self) -> None:
        paragraph = next(
            block
            for block in self.profile.split("\n\n")
            if "`remove-gentle-context`" in block
        )
        self.assertIn("contexto activo", paragraph)
        self.assertIn("no desinstala", paragraph)

    def test_bootstrap_preserves_safe_order(self) -> None:
        markers = (
            "inspección de solo lectura",
            "configuración candidata",
            "aprobación humana explícita",
            "escritura durable",
            "verificación posterior",
        )
        positions = [self.bootstrap.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("unknown", self.bootstrap)
        self.assertIn("bloquea", self.bootstrap)


if __name__ == "__main__":
    unittest.main()
