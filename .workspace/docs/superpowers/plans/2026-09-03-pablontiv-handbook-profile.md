# Pablontiv Handbook Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a prose-first Pablontiv profile derived from Engineering Handbook v1.4 and dogfood it through a single `.workspace/config.yaml` governed by Rootline and informed by Backscroll.

**Architecture:** `profiles/pablontiv/` is the reusable reference package; `.workspace/config.yaml` is the operational instance with logical workspace, group, and repository layers. Workspace activation is atomic: configuration, durable-record migration, ADR routing, living guidance, tests, and CI change together so no commit advertises a half-migrated authority.

**Tech Stack:** Markdown, YAML, Python 3.11 standard-library `unittest`, Bash, Rootline 9.13.8, Backscroll, GitHub Actions

**Spec:** `.workspace/docs/superpowers/specs/2026-09-03-pablontiv-handbook-profile-design.md`

## Global Constraints

- Preserve the approved repository hero and support line verbatim.
- Preserve the sixteen-section semantic structure of Engineering Handbook v1.4.
- Keep version 1 prose-first: no control-plane executor, merge engine, bootstrap CLI, generated schema, or fabricated deterministic evidence.
- Pi is the only declared compatible runtime in version 1.
- Rootline and Backscroll are mandatory, non-substitutable profile dependencies.
- Every published skill, Pi agent, and output style must retain conditional routing.
- `remove-gentle-context` does not uninstall software and never runs routinely.
- `.workspace/config.yaml` flattens storage only; logical precedence remains workspace → group → repository.
- `.workspace/docs/` is the only final active durable-knowledge authority.
- Move historical Markdown records without rewriting their bodies.
- Use Python 3.11 standard library for new contract tests.
- Preserve macOS, Linux, and Windows compatibility.
- Run the complete repository suite before every commit.
- Do not push, create a pull request, merge, or mutate external systems without fresh read-only observation and explicit authorization.

---

## File Structure

### Reusable profile package

- `profiles/pablontiv/.stem` — Rootline boundary for profile Markdown and links.
- `profiles/pablontiv/PROFILE.md` — direct prose specialization of the sixteen v1.4 sections.
- `profiles/pablontiv/bootstrap.md` — Pi-executed adoption wizard derived from v1.4 section 14.
- `profiles/pablontiv/config.template.yaml` — prose-first flattened workspace template.
- `profiles/pablontiv/references/engineering-handbook-v1.4.md` — byte-faithful source snapshot.
- `profiles/pablontiv/tests/test_profile_contract.py` — source, semantics, catalog, configuration, bootstrap, and scope contract.

### Operational workspace

- `.workspace/config.yaml` — concrete dogfood instance for `pablontiv/handbook`.
- `.workspace/docs/.stem` — existing Rootline boundary that already governs this spec and plan.
- `.workspace/worktrees/` — locally excluded isolation root, created only when required by the adopted strategy.

### Durable-record relocation

- `docs/adr/` → `.workspace/docs/adr/`
- `docs/superpowers/specs/` → `.workspace/docs/superpowers/specs/`
- `docs/superpowers/plans/` → `.workspace/docs/superpowers/plans/`

### Living contracts

- `skills/adr/adr.sh` — fail-closed workspace ADR resolution with legacy behavior only outside adopted workspaces.
- `skills/adr/SKILL.md` — workspace-aware ADR policy.
- `skills/adr/tests/test_adr_workspace.py` — workspace/legacy routing tests.
- `AGENTS.md` — local contribution contract and canonical paths.
- `README.md` — profile discovery and canonical knowledge links.
- `tests/test_handbook_contract.py` — repository identity and active-authority contract.
- `.github/workflows/ci.yml` — profile, ADR, Rootline, and existing suite enforcement.

### Deliberately unchanged

- Historical ADR, spec, and plan bodies after relocation.
- `skills/remove-gentle-context/references/ownership-catalog-v1.json` and its historical `adr_path`, because it is provenance bound to authority commit `913bcde`, not current workspace routing.
- User-global Pi, Rootline, or Backscroll configuration.

---

### Task 1: Publish the Reusable Profile Package

**Files:**
- Create: `profiles/pablontiv/.stem`
- Create: `profiles/pablontiv/PROFILE.md`
- Create: `profiles/pablontiv/bootstrap.md`
- Create: `profiles/pablontiv/config.template.yaml`
- Create: `profiles/pablontiv/references/engineering-handbook-v1.4.md`
- Create: `profiles/pablontiv/tests/test_profile_contract.py`
- Reference: `.workspace/docs/superpowers/specs/2026-09-03-pablontiv-handbook-profile-design.md`

**Interfaces:**
- Consumes: Engineering Handbook v1.4 source bytes and the repository's published artifact tree.
- Produces: the reusable reference, adoption wizard, and template consumed by Task 3.

- [ ] **Step 1: Write the failing profile contract test**

Create `profiles/pablontiv/tests/test_profile_contract.py`:

```python
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
```

- [ ] **Step 2: Run the contract to verify RED**

```bash
python3 -m unittest discover \
  -s profiles/pablontiv/tests \
  -t profiles/pablontiv \
  -p 'test_*.py' -v
```

Expected: FAIL because the profile package files do not exist.

- [ ] **Step 3: Copy the exact v1.4 source snapshot**

```bash
mkdir -p profiles/pablontiv/references profiles/pablontiv/tests
cp /Users/Shared/incubadora/banco/engineering-handbook-v1.4.md \
  profiles/pablontiv/references/engineering-handbook-v1.4.md
shasum -a 256 profiles/pablontiv/references/engineering-handbook-v1.4.md
```

Expected digest:

```text
f5455e3eced13690358b02823053a1e00a6c7c06de5f17d9716805bf0a0cff26
```

The absolute path is an implementation-time source only. No committed file may retain it.

- [ ] **Step 4: Add the Rootline profile boundary**

Create `profiles/pablontiv/.stem`:

```yaml
version: 2
root: true
links:
  styles: [markdown]
  checks:
    resolve: true
    anchors: true
    encoding: true
```

- [ ] **Step 5: Write `PROFILE.md` as a direct specialization**

Create `profiles/pablontiv/PROFILE.md` in neutral professional Spanish. Preserve the exact sixteen headings from `PROFILE_SECTIONS`, in source order.

Under those headings, preserve every applicable invariant, state, merge rule, configurable axis, workflow phase, safety gate, minimum repository field, and out-of-scope boundary from the source. Specialize only these approved choices:

```text
Profile id: pablontiv/handbook
Base version: engineering-handbook 1.4
Base digest: f5455e3eced13690358b02823053a1e00a6c7c06de5f17d9716805bf0a0cff26
Runtime compatibility: Pi only
Configuration: .workspace/config.yaml
Knowledge root: .workspace/docs/
Isolation root: .workspace/worktrees/
Governance: Rootline, required, no substitutes
Episodic memory: Backscroll, required, no substitutes
Maturity: prose-first; deterministic controls deferred
```

The tool-routing subsection must include every artifact returned by `published_artifacts()` and state each artifact's real trigger. Include this exact bounded statement:

```markdown
`remove-gentle-context` se activa únicamente para retirar contexto activo de Gentle AI o investigar registros generados stale; no se ejecuta rutinariamente y no desinstala paquetes, binarios, source ni instalaciones del framework.
```

The Backscroll subsection must require project-scoped search first, one broader search on no result, tool-content search for command/path/error recall, bounded machine-readable agent output, and `unknown` if required history is unavailable.

Do not add executable control shorthands, a YAML schema, or claims of automatic execution.

- [ ] **Step 6: Write the prose-first template**

Create `profiles/pablontiv/config.template.yaml`:

```yaml
schema_version: workspace-control/v1

profile:
  id: pablontiv/handbook
  version: 1
  based_on:
    name: engineering-handbook
    version: "1.4"
    digest: f5455e3eced13690358b02823053a1e00a6c7c06de5f17d9716805bf0a0cff26

workspace:
  context_sources: []
  workflow:
    base_branch: unknown
    sync_strategy: unknown
    isolation_strategy: unknown
    development_workflow: |
      Describir el flujo de diseño, aprobación e implementación.
    commit_policy: |
      Describir la política de commits.
    delivery_mode: unknown
    delivery_gate: |
      Describir la aprobación y evidencia requeridas.
  pre_checks: []
  acceptance_checks: []
  review_checks: []
  post_checks: []
  monitoring: |
    Describir el monitoreo requerido o declarar que no aplica.
  external_effects: |
    Describir los efectos permitidos y sus gates.
  credential_policy: |
    Describir el mecanismo autorizado sin incluir secretos.
  knowledge_policy: |
    Rootline gobierna ADRs, specs y planes bajo .workspace/docs/.
  cleanup_policy: |
    Ofrecer cleanup; nunca eliminar automáticamente.
  custom_rules: []

groups: {}
repositories: {}
```

These are prose prompts, not claims about an adopted repository. Do not add executors or generated-schema references.

- [ ] **Step 7: Write the bootstrap wizard**

Create `profiles/pablontiv/bootstrap.md` as the operational expansion of v1.4 section 14. Use numbered stages and include the five exact marker phrases tested above in their required order.

The wizard must direct Pi to:

```text
identify canonical workspace/repository identity
→ read PROFILE.md and source provenance
→ inspect tools, steering, hooks, CI, provider policy, and practice read-only
→ query Backscroll through the official bounded workflow
→ preserve unresolved facts as unknown
→ render a candidate .workspace/config.yaml
→ show workspace/group/repository origins and conflicts
→ request explicit human approval
→ write only approved bytes
→ create .workspace/worktrees/ only when required and add
  /.workspace/worktrees/ idempotently to the Git-resolved local exclude file
→ validate governed Markdown with Rootline
→ verify written configuration and blockers
```

Do not copy this repository's `AGENTS.md`; inspect and preserve each consumer repository's local steering.

- [ ] **Step 8: Run profile validation and tests**

```bash
rootline validate profiles/pablontiv/PROFILE.md --strict
rootline validate profiles/pablontiv/bootstrap.md --strict
python3 -m unittest discover \
  -s profiles/pablontiv/tests \
  -t profiles/pablontiv \
  -p 'test_*.py' -v
```

Expected: Rootline valid; all profile tests PASS.

- [ ] **Step 9: Run the complete repository suite**

Run every command listed under Task 4, “Complete local verification.” Expected: all commands exit 0.

- [ ] **Step 10: Commit the reusable profile**

```bash
git add profiles/pablontiv
git commit -m "feat(profile): publish pablontiv handbook profile"
```

---

### Task 2: Add Workspace-Aware ADR Routing

**Files:**
- Modify: `skills/adr/adr.sh`
- Modify: `skills/adr/SKILL.md`
- Create: `skills/adr/tests/test_adr_workspace.py`
- Reference: `docs/adr/.stem`

**Interfaces:**
- Consumes: the future adopted-workspace marker `.workspace/config.yaml` and Rootline stem contract.
- Produces: routing that remains backward compatible before Task 3 and fails closed after workspace activation.

- [ ] **Step 1: Write failing routing tests**

Create `skills/adr/tests/test_adr_workspace.py`:

```python
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
```

- [ ] **Step 2: Run ADR tests to verify RED**

```bash
python3 -m unittest discover \
  -s skills/adr/tests \
  -t skills/adr \
  -p 'test_*.py' -v
```

Expected: workspace routing tests FAIL because `adr.sh` only detects legacy directories.

- [ ] **Step 3: Implement fail-closed workspace detection**

Replace `detect`, `need_dir`, and versioned destination selection in `skills/adr/adr.sh` with this behavior:

```bash
workspace_active() { [ -f .workspace/config.yaml ]; }

versioned_dir() {
  if workspace_active; then
    printf '%s\n' .workspace/docs/adr
  else
    printf '%s\n' docs/adr
  fi
}

detect() {
  if workspace_active; then
    [ -f .workspace/docs/adr/.stem ] || return 1
    printf '%s\n' .workspace/docs/adr
  elif [ -f docs/adr/.stem ]; then
    printf '%s\n' docs/adr
  elif [ -f .adr/.stem ]; then
    printf '%s\n' .adr
  else
    return 1
  fi
}

need_dir() {
  DIR=$(detect) || {
    echo "adr: no governed ADR store resolved for this workspace or repository" >&2
    exit 2
  }
}
```

In `cmd_init`, replace the fixed versioned destination with:

```bash
versioned) DIR=$(versioned_dir) ;;
```

Keep local `.adr` behavior only for repositories without `.workspace/config.yaml`.

- [ ] **Step 4: Update the ADR skill contract**

Update `skills/adr/SKILL.md` to state:

```text
.workspace/docs/adr is mandatory when .workspace/config.yaml exists.
Legacy docs/adr and .adr detection applies only outside adopted workspaces.
Missing workspace governance fails closed.
Rootline remains the sole ADR data interface.
```

Keep the current `docs/adr` quick-reference behavior explicitly labeled as legacy/non-adopted operation until Task 3 activates this repository.

- [ ] **Step 5: Run focused tests**

```bash
python3 -m unittest discover \
  -s skills/adr/tests \
  -t skills/adr \
  -p 'test_*.py' -v
skills/adr/adr.sh detect
```

Expected: tests PASS; current repository detection still prints `docs/adr` before Task 3.

- [ ] **Step 6: Run the complete repository suite**

Run every command listed under Task 4, “Complete local verification.” Expected: all commands exit 0.

- [ ] **Step 7: Commit ADR routing**

```bash
git add skills/adr
git commit -m "feat(adr): resolve workspace knowledge authority"
```

---

### Task 3: Atomically Activate the Dogfood Workspace

**Files:**
- Create: `.workspace/config.yaml`
- Verify: `.workspace/docs/.stem`
- Move: `docs/adr/` → `.workspace/docs/adr/`
- Move: `docs/superpowers/specs/*` → `.workspace/docs/superpowers/specs/`
- Move: `docs/superpowers/plans/*` → `.workspace/docs/superpowers/plans/`
- Modify: `.workspace/docs/adr/.stem`
- Modify: `skills/adr/SKILL.md`
- Modify: `profiles/pablontiv/tests/test_profile_contract.py`
- Modify: `tests/test_handbook_contract.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `.github/workflows/ci.yml`
- Verify unchanged: every moved historical `.md` body
- Verify unchanged: `skills/remove-gentle-context/references/ownership-catalog-v1.json`

**Interfaces:**
- Consumes: reusable profile from Task 1 and dual-mode ADR routing from Task 2.
- Produces: one coherent operational authority; no intermediate commit may retain two active durable stores or activate a config before its ADR store exists.

- [ ] **Step 1: Add failing dogfood contract tests**

Append to `profiles/pablontiv/tests/test_profile_contract.py`:

```python
DOGFOOD_CONFIG_PATH = REPO_ROOT / ".workspace" / "config.yaml"


def top_level_yaml_keys(text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"^([a-z][a-z0-9_]*):", text, re.MULTILINE)
    }


class DogfoodConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = DOGFOOD_CONFIG_PATH.read_text(encoding="utf-8")

    def test_config_has_all_logical_layers(self) -> None:
        self.assertTrue(
            {"schema_version", "profile", "workspace", "groups", "repositories"}
            <= top_level_yaml_keys(self.config)
        )

    def test_config_preserves_every_axis(self) -> None:
        for axis in CONFIG_AXES:
            with self.subTest(axis=axis):
                self.assertRegex(self.config, rf"(?m)^\s+{re.escape(axis)}:")

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
```

- [ ] **Step 2: Update handbook tests before living documentation**

In `tests/test_handbook_contract.py`, replace the path-sensitive entries in `REQUIRED_AGENT_CLAUSES` with:

```python
"Validate each new or modified ADR with `rootline validate .workspace/docs/adr/NNNN-slug.md --strict`.",
"Resolve the operational workspace policy from `.workspace/config.yaml`.",
```

Replace artifact-family targets with:

```python
for target in (
    "AGENTS.md",
    "profiles/",
    "skills/",
    "output-styles/",
    ".workspace/docs/adr/",
    ".workspace/docs/superpowers/",
):
```

Add:

```python
def test_no_legacy_document_authority_remains(self) -> None:
    self.assertFalse((ROOT / "docs").exists())
    self.assertNotIn("(docs/adr/)", self.readme)
    self.assertNotIn("(docs/superpowers/)", self.readme)


def test_profile_is_published(self) -> None:
    self.assertIn("(profiles/pablontiv/)", self.readme)
    self.assertIn("Pi", self.readme)
    self.assertIn("Rootline", self.readme)
    self.assertIn("Backscroll", self.readme)
```

- [ ] **Step 3: Run focused tests to verify RED**

```bash
python3 -m unittest discover \
  -s profiles/pablontiv/tests \
  -t profiles/pablontiv \
  -p 'test_*.py' -v
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: FAIL because the dogfood config, migrated paths, and updated living guidance do not exist yet.

- [ ] **Step 4: Validate and hash historical records before moving**

```bash
rootline validate docs/adr/0021-adoptar-perfil-pablontiv-gobernado-por-workspace.md --strict
manifest="$(mktemp)"
python3 - "$manifest" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

root = Path("docs")
rows = {
    str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(root.rglob("*.md"))
}
Path(sys.argv[1]).write_text(json.dumps(rows, sort_keys=True), encoding="utf-8")
print(f"recorded {len(rows)} historical Markdown files")
PY
printf 'manifest=%s\n' "$manifest"
```

Keep `$manifest` only for this task. Do not commit it.

- [ ] **Step 5: Verify the workspace Rootline boundary and move records**

Confirm `.workspace/docs/.stem` contains exactly:

```yaml
version: 2
root: true
```

Then move records:

```bash
git mv docs/adr .workspace/docs/adr
mkdir -p .workspace/docs/superpowers/specs \
  .workspace/docs/superpowers/plans
for path in docs/superpowers/specs/*.md; do
  git mv "$path" .workspace/docs/superpowers/specs/
done
for path in docs/superpowers/plans/*.md; do
  git mv "$path" .workspace/docs/superpowers/plans/
done
rmdir docs/superpowers/specs docs/superpowers/plans docs/superpowers docs
```

Remove only `root: true` from `.workspace/docs/adr/.stem` so the ADR schema inherits `.workspace/docs/.stem`. Retain every schema field unchanged.

- [ ] **Step 6: Verify historical Markdown bytes after moving**

```bash
python3 - "$manifest" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for relative, expected in before.items():
    target = Path(".workspace/docs") / relative
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"byte drift: {relative}")
print(f"verified {len(before)} historical Markdown files")
PY
```

Expected: every recorded Markdown body matches. The `.stem` edit is intentionally outside the manifest.

- [ ] **Step 7: Write the dogfood `.workspace/config.yaml`**

Create:

```yaml
schema_version: workspace-control/v1

profile:
  id: pablontiv/handbook
  version: 1
  based_on:
    name: engineering-handbook
    version: "1.4"
    digest: f5455e3eced13690358b02823053a1e00a6c7c06de5f17d9716805bf0a0cff26

workspace:
  context_sources:
    - |
      Backscroll es obligatorio cuando la historia pueda afectar el trabajo:
      buscar primero por proyecto, ampliar una vez si no hay resultados, usar
      contenido de tools para recordar comandos, rutas o errores y conservar
      unknown si la fuente requerida no está disponible.
  workflow:
    base_branch: main
    sync_strategy: unknown
    isolation_strategy: dedicated-worktree
    development_workflow: |
      Clasificar alcance, explorar contexto, aprobar el diseño aplicable,
      planificar cuando corresponda e implementar mediante TDD.
    commit_policy: |
      Usar conventional commits y ejecutar la suite completa antes del commit.
    delivery_mode: pull-request
    delivery_gate: |
      Requerir review y autorización humana antes de integrar.
  pre_checks:
    - |
      Revisar el ADR aceptado que gobierna el cambio.
    - |
      Confirmar Rootline antes de escribir conocimiento gobernado.
    - |
      Consultar Backscroll cuando la historia pueda cambiar la decisión.
  acceptance_checks:
    - |
      Mapear cada criterio de la spec aprobada a evidencia verificable.
  review_checks:
    - |
      Obtener al menos una revisión antes de la entrega mutante.
  post_checks:
    - |
      Confirmar que la revisión aprobada quedó realmente entregada.
  monitoring: |
    No se declara monitoreo para cambios puramente documentales; cualquier
    entrega con comportamiento operativo debe definirlo antes de mutar.
  external_effects: |
    Operar read-only hasta obtener autorización explícita y ligada al payload.
  credential_policy: |
    Usar únicamente mecanismos declarados y no persistir secretos.
  knowledge_policy: |
    Rootline gobierna ADRs en .workspace/docs/adr, specs en
    .workspace/docs/superpowers/specs y planes en
    .workspace/docs/superpowers/plans. No existe fallback activo a docs/.
  cleanup_policy: |
    Ofrecer cleanup y no eliminar automáticamente.
  custom_rules:
    - |
      Las herramientas oficiales del perfil no admiten sustituciones.
    - |
      La versión 1 declara compatibilidad únicamente con Pi.

groups:
  handbook:
    workflow:
      delivery_mode: pull-request

repositories:
  pablontiv/handbook:
    repo:
      id: pablontiv/handbook
      path: unknown
      group: handbook
      managed: true
      verified_revision: unknown
    context_sources:
      - AGENTS.md
```

Do not publish `/Users/Shared/harness/handbook` as a canonical user path. `path` remains `unknown` until a future resolver materializes a local effective view.

- [ ] **Step 8: Materialize the local worktree root safely**

Resolve the Git-local exclusion file, back it up temporarily, add the exact exclusion only if absent, and create the directory:

```bash
exclude="$(git rev-parse --git-path info/exclude)"
backup="$(mktemp)"
cp "$exclude" "$backup"
python3 - "$exclude" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
entry = "/.workspace/worktrees/"
lines = path.read_text(encoding="utf-8").splitlines()
if entry not in lines:
    lines.append(entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
mkdir -p .workspace/worktrees
grep -Fx '/.workspace/worktrees/' "$exclude"
```

Expected: one exact exclusion entry. Keep `$backup` until final local verification; restore it if this task aborts before acceptance. Do not add a versioned `.gitignore` under `.workspace/worktrees/`.

- [ ] **Step 9: Update the adopted ADR skill wording**

In `skills/adr/SKILL.md`, make `.workspace/docs/adr` the primary quick-reference path for adopted workspaces. Preserve a clearly labeled compatibility paragraph for non-adopted repositories using `docs/adr` or `.adr`. State that adopted workspaces never fall back silently.

- [ ] **Step 10: Update `AGENTS.md`**

Keep its local contribution purpose. Add:

```markdown
Before work, resolve the applicable policy from `.workspace/config.yaml`. The reusable profile under `profiles/pablontiv/` is reference material; repository-specific operation comes from the workspace configuration.
```

Replace living ADR paths with `.workspace/docs/adr/`. State that Rootline governs durable Markdown and Backscroll supplies episodic recall according to workspace policy.

Do not copy this repository's `AGENTS.md` into the reusable profile or instruct consumers to adopt it.

- [ ] **Step 11: Update `README.md`**

Preserve the exact hero/support opening. Add a capability section linking `profiles/pablontiv/` and explaining:

```text
PROFILE.md is reusable reference material.
bootstrap.md guides adoption.
.workspace/config.yaml is this repository's dogfood instance.
Version 1 supports Pi.
Rootline governs durable knowledge.
Backscroll supplies episodic recall.
Controls begin as prose and become deterministic incrementally.
```

Replace links to `docs/adr/` and `docs/superpowers/` with `.workspace/docs/adr/` and `.workspace/docs/superpowers/`.

Do not claim an executor, merge engine, bootstrap CLI, Claude/OpenCode parity, or automatic evidence.

- [ ] **Step 12: Preserve historical ownership provenance**

```bash
git diff --exit-code origin/main -- \
  skills/remove-gentle-context/references/ownership-catalog-v1.json
```

Expected: no diff. Its `docs/adr/...` value is historical provenance bound to commit `913bcde`, not a living workspace path.

- [ ] **Step 13: Update CI**

Add:

```yaml
- name: Run profile contract tests
  run: >-
    python -m unittest discover
    -s profiles/pablontiv/tests
    -t profiles/pablontiv
    -p "test_*.py"
    -v

- name: Run ADR workspace tests
  run: >-
    python -m unittest discover
    -s skills/adr/tests
    -t skills/adr
    -p "test_*.py"
    -v
```

Add pinned Rootline setup and validation:

```yaml
- uses: actions/setup-go@v5
  with:
    go-version: stable
- name: Install pinned Rootline
  run: >-
    go install
    github.com/pablontiv/rootline/cmd/rootline@14ee8aa4d5067c7ff6d0708d79e3aaebf27b7a56
- name: Validate governed knowledge
  run: rootline validate --all .workspace/docs/adr -o json
```

Do not install Backscroll in CI; version 1 tests verify its required profile role without pretending CI history is representative.

- [ ] **Step 14: Run focused GREEN checks**

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover \
  -s profiles/pablontiv/tests \
  -t profiles/pablontiv \
  -p 'test_*.py' -v
python3 -m unittest discover \
  -s skills/adr/tests \
  -t skills/adr \
  -p 'test_*.py' -v
skills/adr/adr.sh detect
rootline validate --all .workspace/docs/adr -o json
rootline validate \
  .workspace/docs/adr/0021-adoptar-perfil-pablontiv-gobernado-por-workspace.md \
  --strict
```

Expected: tests PASS; ADR detect prints `.workspace/docs/adr`; Rootline reports zero errors.

- [ ] **Step 15: Verify rename integrity and one active authority**

```bash
test ! -e docs
git diff --find-renames=100% --summary origin/main...HEAD
git grep -n -E 'docs/adr|docs/superpowers' -- \
  README.md AGENTS.md skills/adr tests .github && exit 1 || true
```

Expected: historical Markdown is detected as exact renames and no living path uses the old authority. Historical moved records and the commit-bound ownership catalog are outside this stale-path assertion.

- [ ] **Step 16: Run the complete repository suite**

Run every command listed under Task 4, “Complete local verification.” Expected: all commands exit 0.

- [ ] **Step 17: Commit atomic workspace activation**

```bash
git add .workspace README.md AGENTS.md profiles/pablontiv/tests \
  skills/adr/SKILL.md tests/test_handbook_contract.py \
  .github/workflows/ci.yml docs
git commit -m "feat(workspace): activate pablontiv handbook profile"
```

After the commit, verify `git status --short`; no implementation file may remain unstaged. Generated `__pycache__/` directories are not implementation files and must not be committed.

---

### Task 4: Verify Acceptance and Prepare Review Delivery

**Files:**
- Verify: `profiles/pablontiv/**`
- Verify: `.workspace/config.yaml`
- Verify: `.workspace/docs/**`
- Verify: `skills/adr/**`
- Verify: `README.md`
- Verify: `AGENTS.md`
- Verify: `tests/test_handbook_contract.py`
- Verify: `.github/workflows/ci.yml`
- Update only if evidence disproves a living claim owned by this change.

**Interfaces:**
- Consumes: every deliverable from Tasks 1–3.
- Produces: local acceptance evidence and a review-ready branch; no remote mutation without authorization.

- [ ] **Step 1: Verify source provenance**

```bash
shasum -a 256 \
  profiles/pablontiv/references/engineering-handbook-v1.4.md
```

Expected:

```text
f5455e3eced13690358b02823053a1e00a6c7c06de5f17d9716805bf0a0cff26
```

- [ ] **Step 2: Validate all Rootline-governed surfaces**

```bash
rootline validate profiles/pablontiv/PROFILE.md --strict
rootline validate profiles/pablontiv/bootstrap.md --strict
rootline validate --all .workspace/docs/adr -o json
rootline validate \
  .workspace/docs/adr/0021-adoptar-perfil-pablontiv-gobernado-por-workspace.md \
  --strict
```

Expected: all valid, zero errors.

- [ ] **Step 3: Complete local verification**

Run exactly:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover \
  -s profiles/pablontiv/tests \
  -t profiles/pablontiv \
  -p 'test_*.py' -v
python3 -m unittest discover \
  -s skills/adr/tests \
  -t skills/adr \
  -p 'test_*.py' -v
python3 -m unittest discover \
  -s skills/systemic-issue-triage/tests \
  -t skills/systemic-issue-triage \
  -p 'test_*.py' -v
python3 -m unittest discover \
  -s skills/context-save/tests \
  -t skills/context-save \
  -p 'test_*.py' -v
python3 -m unittest discover \
  -s skills/sweep/tests \
  -t skills/sweep \
  -p 'test_*.py' -v
python3 -m unittest discover \
  -s skills/remove-gentle-context/tests \
  -t skills/remove-gentle-context \
  -p 'test_*.py' -v
python3 -m unittest discover \
  -s skills/model-optimizer/tests \
  -t skills/model-optimizer \
  -p 'test_*.py' -v
sh skills/sweep/assets/test-assets.sh
python3 -m py_compile skills/remove-gentle-context/scripts/cleanup.py
python3 skills/remove-gentle-context/scripts/cleanup.py --help >/dev/null
```

Expected: all Python tests pass; sweep reports `5 passed, 0 failed`; compile/help exit 0.

- [ ] **Step 4: Run diagnostics before completion claims**

Run `lsp_diagnostics` over:

```text
profiles/pablontiv/
skills/adr/
tests/test_handbook_contract.py
```

Then run `lens_diagnostics(mode="all")`. Resolve every blocking issue introduced by this branch. A cache that never scanned a changed file is not clean evidence.

- [ ] **Step 5: Verify active-path and diff integrity**

```bash
test ! -e docs
git diff --check origin/main...HEAD
git diff --find-renames=100% --summary origin/main...HEAD
git status --short --branch
git log --oneline --decorate origin/main..HEAD
git diff --stat origin/main...HEAD
```

Expected: no active `docs/`; diff check passes; historical records are exact renames; implementation files are committed; conventional history is reviewable.

- [ ] **Step 6: Map spec acceptance R1–R10**

Present an in-chat matrix with one row per requirement:

```text
requirement | implemented files | verification command | evidence | passed/failed/unknown
```

Use these bindings:

```text
R1 → PROFILE.md + source digest + section/contract-marker tests
R2 → PROFILE.md + .workspace/config.yaml + README/AGENTS wording
R3 → config template/dogfood layer and axis tests
R4 → prose config + absence of executor/schema claims
R5 → both .stem boundaries + Rootline validation + CI
R6 → PROFILE/bootstrap/config Backscroll clauses + contract tests
R7 → dynamic artifact inventory test
R8 → moved tree + no-active-docs test + ADR detect
R9 → bootstrap ordering/unknown/blocking tests
R10 → PROFILE/bootstrap boundary + local AGENTS guidance
```

Any required `failed` or `unknown` keeps the task open and blocks delivery.

- [ ] **Step 7: Obtain independent code/document review**

Use `superpowers:requesting-code-review`. Provide the spec path, plan path, `origin/main...HEAD` diff, R1–R10 matrix, and complete verification output. Resolve all High and Medium findings before continuing; rerun affected tests and the complete suite after fixes.

- [ ] **Step 8: Observe GitHub read-only**

```bash
gh repo view pablontiv/handbook \
  --json nameWithOwner,defaultBranchRef,url

gh pr list --repo pablontiv/handbook \
  --state open \
  --json number,title,headRefName,baseRefName,isDraft,url
```

This establishes actual repository/default-branch/open-PR state. It does not authorize mutation.

- [ ] **Step 9: Prepare the exact PR body locally**

```bash
cat > /tmp/pablontiv-handbook-profile-pr-body.md <<'EOF'
## Summary
- publish the reusable prose-first Pablontiv profile derived from Engineering Handbook v1.4
- dogfood the profile through one `.workspace/config.yaml`
- centralize durable knowledge under Rootline-governed `.workspace/docs/`
- make ADR routing workspace-aware while retaining non-adopted compatibility

## Governance
- reviewed accepted ADR 0022 for repository identity
- superseded ADR 0002
- created and accepted ADR 0021
- implemented `.workspace/docs/superpowers/specs/2026-09-03-pablontiv-handbook-profile-design.md`
- followed `.workspace/docs/superpowers/plans/2026-09-03-pablontiv-handbook-profile.md`
- unresolved governance conflicts: none

## Verification
- source snapshot SHA-256 matches the approved digest
- Rootline strict validation passes
- historical Markdown byte comparison passes
- complete Python and shell suite passes
- R1–R10 acceptance matrix passes

## External effects
- no merge or deployment is included
EOF
```

- [ ] **Step 10: Request explicit live authorization**

Present:

```text
branch: docs/pablontiv-handbook-profile
head commit: output of git rev-parse HEAD
remote: output of gh repo view
base: observed default branch
push: git push -u origin docs/pablontiv-handbook-profile
PR title: feat(profile): publish pablontiv handbook profile
PR body digest: output of shasum -a 256 /tmp/pablontiv-handbook-profile-pr-body.md
```

Wait for explicit approval bound to that payload.

- [ ] **Step 11: Push and create the PR only after authorization**

```bash
git push -u origin docs/pablontiv-handbook-profile
gh pr create \
  --repo pablontiv/handbook \
  --base main \
  --head docs/pablontiv-handbook-profile \
  --title "feat(profile): publish pablontiv handbook profile" \
  --body-file /tmp/pablontiv-handbook-profile-pr-body.md
```

Do not merge. Integration requires a separate review and explicit human decision.
