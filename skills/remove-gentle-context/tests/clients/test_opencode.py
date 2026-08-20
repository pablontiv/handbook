from __future__ import annotations

import base64
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helper.clients.opencode import OpenCodeAdapter
from helper.engine import build_inventory, build_plan
from helper.models import ArtifactClass, OperationKind, Ownership, PlatformProfile, RuntimeContext
from helper.ownership import canonical_tree_sha256, load_ownership_catalog
from helper.transaction import apply_operations, create_backup
from tests.support import assert_test_home

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "opencode"


def context_for(home: Path, **env: str) -> RuntimeContext:
    authority_keys = {"XDG_STATE_HOME", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA"}
    normalized = {key: (str(Path(value).resolve(strict=False)) if key in authority_keys else value) for key, value in env.items()}
    return RuntimeContext(PlatformProfile("linux", home, normalized))


def build_opencode_fixture(temp_root: Path) -> Path:
    home = temp_root / "home"
    home.mkdir(parents=True)
    config = home / ".config" / "opencode"
    config.mkdir(parents=True)
    shutil.copy2(FIXTURE_ROOT / "opencode.json", config / "opencode.json")
    shutil.copy2(FIXTURE_ROOT / "tui.json", config / "tui.json")
    shutil.copy2(FIXTURE_ROOT / "package.json", config / "package.json")
    (config / "node_modules" / "opencode-sdd-engram-manage").mkdir(parents=True)
    return home


def plan_for(context: RuntimeContext, adapter: OpenCodeAdapter):
    inventory = build_inventory(context, (adapter,))
    return build_plan(inventory, context, (adapter,))


def apply_to_fixture(plan, context: RuntimeContext) -> None:
    manifest = create_backup(plan, context)
    apply_operations(plan, manifest, context)


class OpenCodeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)
        self.home = build_opencode_fixture(self.temp_root)
        assert_test_home(self.home, self.temp_root)
        self.context = context_for(self.home, XDG_STATE_HOME=str(self.home / ".local" / "state"))
        self.config_dir = self.home / ".config" / "opencode"
        self.config = self.config_dir / "opencode.json"
        self.tui = self.config_dir / "tui.json"
        self.package = self.config_dir / "package.json"
        self.catalog = load_ownership_catalog()
        self.original_mcp = json.loads(self.config.read_text())["mcp"]

    def test_finds_broken_logo_and_sdd_plugin_registrations(self) -> None:
        candidates = OpenCodeAdapter(self.catalog).inventory(self.context)
        kinds = {(c.details.get("plugin"), c.artifact_class) for c in candidates}
        self.assertIn(("gentle-logo.tsx", ArtifactClass.BROKEN_REGISTRATION), kinds)
        self.assertIn(("opencode-sdd-engram-manage", ArtifactClass.ACTIVE_SOURCE), kinds)

    def test_compile_preserves_package_mcp_unrelated_plugins_and_order(self) -> None:
        data = json.loads(self.config.read_text())
        data["agent"]["gentle-orchestrator"]["managed_marker"] = "<!-- gentle-ai:gentle-orchestrator -->"
        data["agent"]["sdd-apply"]["managed_marker"] = "<!-- gentle-ai:sdd-apply -->"
        self.config.write_text(json.dumps(data, indent=2) + "\n")

        plan = plan_for(self.context, OpenCodeAdapter(self.catalog))
        apply_to_fixture(plan, self.context)
        OpenCodeAdapter(self.catalog).verify(type("ReceiptLike", (), {"operation_outcomes": (), "checks": ()})(), self.context)

        tui = json.loads(self.tui.read_text())
        package = json.loads(self.package.read_text())
        config = json.loads(self.config.read_text())

        self.assertEqual(tui["plugin"], ["opencode-subagent-statusline", "./relative-gentle-logo.tsx", "third-party-missing-plugin"])
        self.assertIn("opencode-sdd-engram-manage", package["dependencies"])
        self.assertTrue((self.config_dir / "node_modules" / "opencode-sdd-engram-manage").is_dir())
        self.assertEqual(config["mcp"], self.original_mcp)
        self.assertEqual(config["default_agent"], "general")
        self.assertNotIn("gentle-orchestrator", config["agent"])
        self.assertNotIn("sdd-apply", config["agent"])
        self.assertIn("unrelated-agent", config["agent"])
        self.assertIn("sdd-apply", config["command"])
        self.assertIn("keep-command", config["command"])
        self.assertIn("keep-skill", config["skill"])

    def test_default_agent_fails_closed_without_general_or_documented_fallback(self) -> None:
        data = json.loads(self.config.read_text())
        data["agent"].pop("general")
        self.config.write_text(json.dumps(data, indent=2) + "\n")

        inventory = build_inventory(self.context, (OpenCodeAdapter(self.catalog, general_builtin_fallback=False),))
        defaults = [candidate for candidate in inventory.candidates if candidate.details.get("kind") == "default_agent"]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0].ownership, Ownership.AMBIGUOUS)
        self.assertEqual(defaults[0].proposed_action, "report_only")
        plan = build_plan(inventory, self.context, (OpenCodeAdapter(self.catalog, general_builtin_fallback=False),))
        self.assertIn(defaults[0].candidate_id, plan.blocked_candidate_ids)

    def test_package_dependency_and_node_modules_are_preservation_assertions_not_operations(self) -> None:
        inventory = build_inventory(self.context, (OpenCodeAdapter(self.catalog),))
        plan = build_plan(inventory, self.context, (OpenCodeAdapter(self.catalog),))

        preserved = {Path(assertion.path).name for assertion in plan.preservation_assertions}
        self.assertIn("package.json", preserved)
        self.assertIn("opencode-sdd-engram-manage", preserved)
        self.assertNotIn(str(self.package), {operation.path for operation in plan.operations})
        self.assertFalse(any("node_modules" in operation.path for operation in plan.operations))

    def test_malformed_json_blocks_inventory_visibly(self) -> None:
        self.tui.write_text('{"plugin": [')

        inventory = build_inventory(self.context, (OpenCodeAdapter(self.catalog),))

        self.assertEqual(len(inventory.findings), 1)
        self.assertEqual(inventory.findings[0].client, "opencode")
        self.assertIn("opencode_json_malformed:tui.json", inventory.findings[0].message)
        self.assertEqual(inventory.candidates, ())

    def test_absent_unrelated_plugin_file_does_not_authorize_removal(self) -> None:
        plan = plan_for(self.context, OpenCodeAdapter(self.catalog))
        postimages = [operation for operation in plan.operations if operation.path == str(self.tui)]
        self.assertEqual(len(postimages), 1)
        decoded = json.loads(base64.b64decode(postimages[0].postimage_base64 or ""))
        self.assertIn("third-party-missing-plugin", decoded["plugin"])

    def test_local_plugin_file_deletes_only_with_standalone_managed_marker_evidence(self) -> None:
        owned = self.config_dir / "managed-gentle-plugin.tsx"
        owned.write_text("<!-- gentle-ai:opencode-plugin -->\nexport default {}\n")
        commented_marker = self.config_dir / "commented-marker-plugin.tsx"
        commented_marker.write_text("// <!-- gentle-ai:opencode-plugin -->\nexport default {}\n")
        prose_marker = self.config_dir / "prose-marker-plugin.tsx"
        prose_marker.write_text("A prose note mentions gentle-ai:opencode-plugin but is not managed metadata.\n")
        unowned = self.config_dir / "unowned-gentle-plugin.tsx"
        unowned.write_text("export default {}\n")
        data = json.loads(self.tui.read_text())
        data["plugin"].extend([str(owned), str(commented_marker), str(prose_marker), str(unowned)])
        self.tui.write_text(json.dumps(data, indent=2) + "\n")

        inventory = build_inventory(self.context, (OpenCodeAdapter(self.catalog),))
        plan = build_plan(inventory, self.context, (OpenCodeAdapter(self.catalog),))

        delete_paths = {operation.path for operation in plan.operations if operation.kind is OperationKind.DELETE_FILE}
        self.assertIn(str(owned), delete_paths)
        self.assertNotIn(str(commented_marker), delete_paths)
        self.assertNotIn(str(prose_marker), delete_paths)
        self.assertNotIn(str(unowned), {operation.path for operation in plan.operations})
        for target in (commented_marker, prose_marker, unowned):
            ambiguous = [candidate for candidate in inventory.candidates if candidate.path == str(target)]
            self.assertEqual(len(ambiguous), 1)
            self.assertEqual(ambiguous[0].ownership, Ownership.AMBIGUOUS)

    def test_structured_config_entries_require_managed_proof_not_catalog_key_alone(self) -> None:
        data = json.loads(self.config.read_text())
        data["default_agent"] = "general"
        data["agent"]["sdd-apply"] = {"description": "User-authored same-name agent must remain"}
        data["command"]["sdd-apply"] = {
            "description": "Managed command can be removed",
            "managed_marker": "<!-- gentle-ai:sdd-apply -->",
        }
        self.config.write_text(json.dumps(data, indent=2) + "\n")

        inventory = build_inventory(self.context, (OpenCodeAdapter(self.catalog),))
        plan = build_plan(inventory, self.context, (OpenCodeAdapter(self.catalog),))
        postimages = [operation for operation in plan.operations if operation.path == str(self.config)]
        self.assertEqual(len(postimages), 1)
        decoded = json.loads(base64.b64decode(postimages[0].postimage_base64 or ""))

        self.assertIn("sdd-apply", decoded["agent"])
        self.assertNotIn("sdd-apply", decoded["command"])
        ambiguous = [
            candidate
            for candidate in inventory.candidates
            if candidate.details.get("kind") == "config_entry"
            and candidate.details.get("family") == "agent"
            and candidate.details.get("name") == "sdd-apply"
        ]
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0].ownership, Ownership.AMBIGUOUS)

    def test_default_agent_change_requires_proven_removable_registration(self) -> None:
        data = json.loads(self.config.read_text())
        data["agent"]["general"] = {"description": "fallback"}
        data["agent"]["gentle-orchestrator"] = {"description": "User-authored same-name default"}
        self.config.write_text(json.dumps(data, indent=2) + "\n")

        inventory = build_inventory(self.context, (OpenCodeAdapter(self.catalog),))
        plan = build_plan(inventory, self.context, (OpenCodeAdapter(self.catalog),))
        config_operations = [operation for operation in plan.operations if operation.path == str(self.config)]
        self.assertEqual(config_operations, [])
        defaults = [candidate for candidate in inventory.candidates if candidate.details.get("kind") == "default_agent"]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0].ownership, Ownership.AMBIGUOUS)
        self.assertIn(defaults[0].candidate_id, plan.blocked_candidate_ids)

    def test_plural_agents_proven_default_migrates_to_configured_general_fallback(self) -> None:
        data = json.loads(self.config.read_text())
        data.pop("agent")
        data["agents"] = {
            "general": {"description": "Configured fallback"},
            "gentle-orchestrator": {
                "description": "Gentle OpenCode orchestrator",
                "managed_marker": "<!-- gentle-ai:gentle-orchestrator -->",
            },
            "unrelated-agent": {"description": "Keep this agent"},
        }
        self.config.write_text(json.dumps(data, indent=2) + "\n")

        plan = plan_for(self.context, OpenCodeAdapter(self.catalog, general_builtin_fallback=False))
        postimages = [operation for operation in plan.operations if operation.path == str(self.config)]
        self.assertEqual(len(postimages), 1)
        decoded = json.loads(base64.b64decode(postimages[0].postimage_base64 or ""))

        self.assertEqual(decoded["default_agent"], "general")
        self.assertNotIn("gentle-orchestrator", decoded["agents"])
        self.assertIn("general", decoded["agents"])
        self.assertIn("unrelated-agent", decoded["agents"])

    def test_plural_agents_proven_default_without_allowed_fallback_is_blocked_not_dangling(self) -> None:
        data = json.loads(self.config.read_text())
        data.pop("agent")
        data["agents"] = {
            "gentle-orchestrator": {
                "description": "Gentle OpenCode orchestrator",
                "managed_marker": "<!-- gentle-ai:gentle-orchestrator -->",
            },
            "unrelated-agent": {"description": "Keep this agent"},
        }
        self.config.write_text(json.dumps(data, indent=2) + "\n")

        inventory = build_inventory(self.context, (OpenCodeAdapter(self.catalog, general_builtin_fallback=False),))
        plan = build_plan(inventory, self.context, (OpenCodeAdapter(self.catalog, general_builtin_fallback=False),))
        config_operations = [operation for operation in plan.operations if operation.path == str(self.config)]
        self.assertEqual(config_operations, [])
        defaults = [candidate for candidate in inventory.candidates if candidate.details.get("kind") == "default_agent"]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0].ownership, Ownership.AMBIGUOUS)
        self.assertIn(defaults[0].candidate_id, plan.blocked_candidate_ids)

        config = json.loads(self.config.read_text())
        self.assertEqual(config["default_agent"], "gentle-orchestrator")
        self.assertIn("gentle-orchestrator", config["agents"])

    def test_default_agent_conflicting_singular_plural_proof_fails_closed(self) -> None:
        data = json.loads(self.config.read_text())
        data["agent"]["general"] = {"description": "Configured fallback"}
        data["agent"]["gentle-orchestrator"] = {"description": "User-authored same-name default"}
        data["agents"] = {
            "general": {"description": "Configured fallback"},
            "gentle-orchestrator": {
                "description": "Gentle OpenCode orchestrator",
                "managed_marker": "<!-- gentle-ai:gentle-orchestrator -->",
            },
        }
        self.config.write_text(json.dumps(data, indent=2) + "\n")

        inventory = build_inventory(self.context, (OpenCodeAdapter(self.catalog),))
        plan = build_plan(inventory, self.context, (OpenCodeAdapter(self.catalog),))
        config_operations = [operation for operation in plan.operations if operation.path == str(self.config)]
        self.assertEqual(config_operations, [])
        defaults = [candidate for candidate in inventory.candidates if candidate.details.get("kind") == "default_agent"]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0].ownership, Ownership.AMBIGUOUS)
        self.assertIn(defaults[0].candidate_id, plan.blocked_candidate_ids)

    def test_personal_author_marker_vetoes_open_code_skill_file_delete_without_full_chain(self) -> None:
        skill = self.config_dir / "skill" / "systemic-issue-triage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\n"
            "name: systemic-issue-triage\n"
            "metadata:\n"
            "  author: pablontiv\n"
            "  version: 1.0.0\n"
            "---\n"
            "<!-- gentle-ai:systemic-issue-triage -->\n"
            "Personal adaptation with an adversarial marker.\n"
        )

        inventory = build_inventory(self.context, (OpenCodeAdapter(self.catalog),))
        candidates = [candidate for candidate in inventory.candidates if candidate.path == str(skill)]
        plan = build_plan(inventory, self.context, (OpenCodeAdapter(self.catalog),))

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].ownership, Ownership.AMBIGUOUS)
        self.assertEqual(candidates[0].proposed_action, "report_only")
        self.assertNotIn(str(skill), {operation.path for operation in plan.operations})

    def test_personal_skill_ownership_vetoes_open_code_skill_file_delete(self) -> None:
        skill = self.config_dir / "skill" / "systemic-issue-triage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\n"
            "name: systemic-issue-triage\n"
            "metadata:\n"
            "  author: pablontiv\n"
            "  created: 2026-01-01\n"
            "  updated: 2026-01-02\n"
            "  version: 1.0.0\n"
            "  upstream-author: Alan-TheGentleman\n"
            "  upstream-repository: https://github.com/Gentleman-Programming/gentle-ai\n"
            "  upstream-commit: d1e1777faafc91a34656ba94bd712972dbe427a1\n"
            "  ownership: personal\n"
            "---\n"
            "<!-- gentle-ai:systemic-issue-triage -->\n"
            "Personal adaptation.\n"
        )
        release_catalog = dict(self.catalog)
        release_commit = "b" * 40
        release_catalog["personal_skill_releases"] = {
            "systemic-issue-triage": {
                "source_repository": "https://github.com/pablontiv/skills",
                "personal_source_commit": release_commit,
                "canonical_tree_sha256": canonical_tree_sha256(skill),
            }
        }
        receipts = self.home / "receipts"
        receipts.mkdir()
        receipt = {
            "skill_name": "systemic-issue-triage",
            "skill_version": "1.0.0",
            "personal_source_repository": "https://github.com/pablontiv/skills",
            "personal_source_commit": release_commit,
            "installed_path": str(skill),
            "installed_content_sha256": "sha256:" + __import__("hashlib").sha256(skill.read_bytes()).hexdigest(),
            "installation_timestamp": "2026-08-19T00:00:00Z",
            "canonical_tree_sha256": canonical_tree_sha256(skill),
        }
        (receipts / "systemic-issue-triage.json").write_text(json.dumps(receipt, sort_keys=True))
        context = context_for(self.home, XDG_STATE_HOME=str(self.home / ".local" / "state"), SKILLS_RECEIPTS_DIR=str(receipts))

        inventory = build_inventory(context, (OpenCodeAdapter(release_catalog),))
        candidates = [candidate for candidate in inventory.candidates if candidate.path == str(skill)]

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].ownership, Ownership.PRESERVED)
        plan = build_plan(inventory, context, (OpenCodeAdapter(release_catalog),))
        self.assertNotIn(str(skill), {operation.path for operation in plan.operations})

    def test_second_inventory_plan_after_apply_has_no_open_code_mutations(self) -> None:
        adapter = OpenCodeAdapter(self.catalog)
        first_inventory = build_inventory(self.context, (adapter,))
        first_plan = build_plan(first_inventory, self.context, (adapter,))
        self.assertTrue(first_plan.operations)

        manifest = create_backup(first_plan, self.context)
        outcomes = apply_operations(first_plan, manifest, self.context)
        adapter.verify(type("ReceiptLike", (), {"operation_outcomes": outcomes, "checks": ()})(), self.context)
        second_inventory = build_inventory(self.context, (OpenCodeAdapter(self.catalog),))
        second_plan = build_plan(second_inventory, self.context, (OpenCodeAdapter(self.catalog),))

        self.assertEqual(second_plan.operations, ())
        self.assertFalse(any(candidate.client == "opencode" and candidate.ownership is Ownership.PROVEN and candidate.proposed_action != "report_only" for candidate in second_inventory.candidates))


if __name__ == "__main__":
    unittest.main()
