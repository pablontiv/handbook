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
DOGFOOD_CONFIG_PATH = REPO_ROOT / ".workspace" / "config.yaml"

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
FORBIDDEN_CONTROL_FIELDS = (
    "executor",
    "timeout_seconds",
    "success",
    "on_failure",
)

BASE_CONTRACT_MARKERS = (
    "workspace → group → repository",
    "Los escalares de una capa más específica reemplazan",
    "Los mapas se combinan recursivamente",
    "Las listas se reemplazan completas",
)

INVARIANT_IDS = tuple(f"INV-{number:02d}" for number in range(1, 14))
WORKFLOW_PHASES = tuple(f"Fase {number}" for number in range(9))
CONTROL_STATES = (
    "pending",
    "passed",
    "failed",
    "skipped",
    "unknown",
    "not_applicable",
)
CONDITIONAL_TRIGGER = re.compile(
    r"\bse activa (?:al|como|cuando|después|para|tras|únicamente)\b"
)


def published_artifacts() -> set[str]:
    skills = {path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md")}
    agents = {path.stem for path in (REPO_ROOT / "skills").glob("*/agents/pi/*.md")}
    styles = {path.stem for path in (REPO_ROOT / "output-styles").glob("*.md")}
    return skills | agents | styles


def top_level_yaml_keys(text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"^([a-z][a-z0-9_]*):", text, re.MULTILINE)
    }


def yaml_mapping_body(text: str, key: str, indent: int = 0) -> str:
    lines = text.splitlines()
    marker = f"{' ' * indent}{key}:"
    start = lines.index(marker) + 1
    body = []
    for line in lines[start:]:
        leading = len(line) - len(line.lstrip())
        if line.strip() and leading <= indent:
            break
        body.append(line)
    return "\n".join(body)


def deterministic_control_fields(text: str) -> tuple[str, ...]:
    alternatives = "|".join(FORBIDDEN_CONTROL_FIELDS)
    return tuple(re.findall(rf"^\s+({alternatives}):", text, re.MULTILINE))


def h2_body(profile: str, heading: str) -> str:
    match = re.search(
        rf"^## (?:\d+\. )?{re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)",
        profile,
        re.MULTILINE | re.DOTALL,
    )
    return match.group("body") if match else ""


def section_contract_violations(profile: str) -> tuple[str, ...]:
    headings = tuple(re.findall(r"^## (?:\d+\. )?(.+)$", profile, re.MULTILINE))
    return () if headings == PROFILE_SECTIONS else ("ordered sections",)


def category_contract_violations(profile: str) -> tuple[str, ...]:
    violations = [
        f"missing marker: {marker}"
        for marker in BASE_CONTRACT_MARKERS
        if marker not in profile
    ]

    invariant_ids = tuple(
        re.findall(
            r"^\d+\. \*\*(INV-\d{2})\b",
            h2_body(profile, "Invariantes"),
            re.MULTILINE,
        )
    )
    if invariant_ids != INVARIANT_IDS:
        violations.append("invariant IDs")

    workflow_phases = tuple(
        re.findall(
            r"^### (Fase \d+)\b",
            h2_body(profile, "Flujo de trabajo"),
            re.MULTILINE,
        )
    )
    if workflow_phases != WORKFLOW_PHASES:
        violations.append("workflow phases")

    state_body = h2_body(profile, "Contrato de los controles").partition(
        "Los estados canónicos son:"
    )[2]
    control_states = tuple(re.findall(r"^- `([a-z_]+)`:", state_body, re.MULTILINE))
    if control_states != CONTROL_STATES:
        violations.append("canonical states")

    return tuple(violations)


def routed_artifacts(profile: str) -> tuple[tuple[str, str], ...]:
    routing_body = h2_body(profile, "Ejes configurables").partition(
        "### Routing de artefactos publicados"
    )[2]
    return tuple(
        (match.group("artifact"), match.group("prose"))
        for match in re.finditer(
            r"^(?:- )?`(?P<artifact>[a-z0-9-]+)`(?::)? "
            r"(?P<prose>[^\n]+)$",
            routing_body,
            re.MULTILINE,
        )
    )


def routing_contract_violations(
    profile: str,
    artifacts: set[str],
) -> tuple[str, ...]:
    routes = routed_artifacts(profile)
    routed_names = tuple(artifact for artifact, _ in routes)
    violations = []
    if set(routed_names) != artifacts or len(routed_names) != len(set(routed_names)):
        violations.append("artifact inventory")
    triggerless = sorted(
        artifact
        for artifact, prose in routes
        if CONDITIONAL_TRIGGER.search(prose) is None
    )
    if triggerless:
        violations.append("triggerless routes: " + ", ".join(triggerless))
    return tuple(violations)


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
        self.assertEqual(section_contract_violations(self.profile), ())

    def test_contract_rejects_reversed_headings(self) -> None:
        mutated = self.profile.replace("## 1. Propósito", "## SWAP", 1)
        mutated = mutated.replace("## 2. Principios de diseño", "## 1. Propósito", 1)
        mutated = mutated.replace("## SWAP", "## 2. Principios de diseño", 1)
        self.assertTrue(section_contract_violations(mutated))

    def test_profile_preserves_contract_categories(self) -> None:
        self.assertEqual(category_contract_violations(self.profile), ())

    def test_contract_rejects_removed_or_extra_categories(self) -> None:
        mutations = (
            ("missing invariant", self.profile.replace("**INV-13", "**RULE-13", 1)),
            ("missing phase", self.profile.replace("### Fase 4", "### Etapa 4", 1)),
            ("missing state", self.profile.replace("- `pending`:", "- `queued`:", 1)),
            (
                "extra state",
                self.profile.replace(
                    "- `passed`:",
                    "- `running`: ejecución iniciada;\n- `passed`:",
                    1,
                ),
            ),
        )
        for label, mutated in mutations:
            with self.subTest(label=label):
                self.assertTrue(category_contract_violations(mutated))

    def test_template_preserves_layers_and_axes(self) -> None:
        for layer in ("workspace:", "groups:", "repositories:"):
            self.assertIn(layer, self.template)
        for axis in CONFIG_AXES:
            self.assertRegex(self.template, rf"(?m)^\s+{re.escape(axis)}:")

    def test_profile_preserves_every_configurable_axis(self) -> None:
        axes = h2_body(self.profile, "Ejes configurables")
        for axis in CONFIG_AXES:
            with self.subTest(axis=axis):
                self.assertIn(f"| `{axis}` |", axes)

    def test_template_rejects_deterministic_control_fields(self) -> None:
        self.assertEqual(deterministic_control_fields(self.template), ())
        mutated = self.template.replace(
            "  custom_rules: []",
            "  custom_rules: []\n  executor: shell",
            1,
        )
        self.assertEqual(deterministic_control_fields(mutated), ("executor",))

    def test_profile_routes_every_published_artifact(self) -> None:
        self.assertEqual(
            routing_contract_violations(self.profile, published_artifacts()), ()
        )

    def test_contract_rejects_unlisted_and_stale_routes(self) -> None:
        published = published_artifacts()
        stale_route = (
            "\n- `retired-artifact`: se activa cuando aparece una señal retirada.\n"
        )
        mutated = self.profile.replace(
            "\n## 7. Valores por defecto",
            stale_route + "\n## 7. Valores por defecto",
            1,
        )
        cases = (
            (
                "unlisted published artifact",
                self.profile,
                published | {"future-artifact"},
            ),
            ("stale routed artifact", mutated, published),
        )
        for label, profile, artifacts in cases:
            with self.subTest(label=label):
                self.assertTrue(routing_contract_violations(profile, artifacts))

    def test_contract_rejects_triggerless_routes(self) -> None:
        mutated = self.profile.replace(
            "- `adr`: se activa", "- `adr`: está disponible", 1
        )
        self.assertTrue(routing_contract_violations(mutated, published_artifacts()))

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


class DogfoodConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = DOGFOOD_CONFIG_PATH.read_text(encoding="utf-8")
        cls.workspace = yaml_mapping_body(cls.config, "workspace")
        cls.repository = yaml_mapping_body(cls.config, "pablontiv/handbook", indent=2)

    def test_config_has_all_logical_layers(self) -> None:
        self.assertTrue(
            {"schema_version", "profile", "workspace", "groups", "repositories"}
            <= top_level_yaml_keys(self.config)
        )

    def test_workspace_config_preserves_every_axis(self) -> None:
        for axis in CONFIG_AXES:
            with self.subTest(axis=axis):
                self.assertRegex(self.workspace, rf"(?m)^\s+{re.escape(axis)}:")

    def test_repository_context_sources_preserve_backscroll(self) -> None:
        sources = yaml_mapping_body(
            self.repository,
            "context_sources",
            indent=4,
        )
        for required in (
            "Backscroll",
            "buscar primero por proyecto",
            "ampliar una vez",
            "contenido de tools",
            "unknown",
            "AGENTS.md",
        ):
            with self.subTest(required=required):
                self.assertIn(required, sources)

    def test_sync_strategy_is_observable_and_fail_closed(self) -> None:
        workflow = yaml_mapping_body(self.workspace, "workflow", indent=2)
        normalized = " ".join(workflow.split())
        self.assertNotIn("sync_strategy: unknown", workflow)
        for required in ("lectura", "origin/main", "revisión base", "pull", "unknown"):
            with self.subTest(required=required):
                self.assertIn(required, normalized)

    def test_config_rejects_deterministic_control_fields(self) -> None:
        self.assertEqual(deterministic_control_fields(self.config), ())
        mutated = self.config.replace(
            "  custom_rules:",
            "  executor: shell\n  timeout_seconds: 30\n  success: exit-zero\n"
            "  on_failure: stop\n  custom_rules:",
            1,
        )
        self.assertEqual(
            deterministic_control_fields(mutated),
            FORBIDDEN_CONTROL_FIELDS,
        )

    def test_config_names_required_authorities(self) -> None:
        for required in (
            "pablontiv/handbook",
            "AGENTS.md",
            "Rootline",
            "Backscroll",
            ".workspace/docs/adr",
            ".workspace/docs/superpowers/specs",
            ".workspace/docs/superpowers/plans",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.config)

    def test_config_keeps_unresolved_bindings_explicit(self) -> None:
        self.assertIn("unknown", self.config)
        self.assertNotIn("{" * 2, self.config)
        self.assertNotIn("TO" + "DO", self.config)


if __name__ == "__main__":
    unittest.main()
