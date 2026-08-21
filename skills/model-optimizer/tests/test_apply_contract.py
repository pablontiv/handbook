from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from helper.models import RuntimeKind
from helper.optimizer import discover_agent_contracts
from tests.support import ApprovedChange, ApplyTarget, Route, simulate_approved_apply


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class ApplyContractTests(unittest.TestCase):
    def test_approved_change_is_constructed_only_after_explicit_approval(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "subagents.json"
            target.write_text('{"model_profiles":{"worker":{"model":"old","effort":"low"}}}', encoding="utf-8")
            apply_target = ApplyTarget(runtime="pi", scope="project", path=target, format="pi-json")
            with self.assertRaisesRegex(ValueError, "approval_required"):
                ApprovedChange.after_approval(
                    approved=False,
                    agent="worker",
                    previous_route=Route("old", "low"),
                    selected_route=Route("new", "high"),
                    apply_target=apply_target,
                    source_digest=_digest(target),
                )

    def test_pi_project_and_global_scope_success_and_rollback_are_exact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            project = root / "project"
            configured_global = root / "pi-global"
            home.mkdir()
            project.mkdir()
            configured_global.mkdir()
            (project / ".pi").mkdir()

            global_config = configured_global / "subagents.json"
            project_config = project / ".pi" / "subagents.json"
            global_config.write_text(
                '{\n'
                '  "model_profiles": {\n'
                '    "reviewer": {"model": "global/reviewer-old", "effort": "medium", "temperature": 0.1},\n'
                '    "worker": {"model": "global/worker-old", "effort": "medium", "temperature": 0.2}\n'
                '  },\n'
                '  "unrelated": {"keep": true}\n'
                '}\n',
                encoding="utf-8",
            )
            project_config.write_text(
                '{\n'
                '  "model_profiles": {\n'
                '    "worker": {"model": "project/worker-old", "effort": "low", "temperature": 0.3},\n'
                '    "observer": {"model": "project/observer", "effort": "minimal"}\n'
                '  },\n'
                '  "unrelated": ["byte", "stable"]\n'
                '}\n',
                encoding="utf-8",
            )
            global_before = global_config.read_bytes()
            project_before = project_config.read_bytes()

            contracts = discover_agent_contracts(RuntimeKind.PI, home, project, {"PI_CODING_AGENT_DIR": str(configured_global)})
            by_name = {contract.name: contract for contract in contracts}
            self.assertEqual(by_name["worker"].scope, "project")
            self.assertEqual(by_name["worker"].apply_target, str(project_config))
            self.assertEqual(by_name["reviewer"].scope, "global")
            self.assertEqual(by_name["reviewer"].apply_target, str(global_config))

            change = ApprovedChange.after_approval(
                approved=True,
                agent="worker",
                previous_route=Route("project/worker-old", "low"),
                selected_route=Route("selected/worker", "high"),
                apply_target=ApplyTarget(runtime="pi", scope="project", path=Path(by_name["worker"].apply_target), format="pi-json"),
                source_digest=_digest(project_config),
            )
            success = simulate_approved_apply(change, temp_root=root, timestamp="20260820T010203Z")
            expected_project = project_before.replace(b'"model": "project/worker-old"', b'"model": "selected/worker"').replace(
                b'"effort": "low"', b'"effort": "high"'
            )
            self.assertTrue(success.applied)
            self.assertEqual(project_config.read_bytes(), expected_project)
            self.assertEqual(global_config.read_bytes(), global_before)
            self.assertEqual(success.backup_path.read_bytes(), project_before)
            self.assertEqual(success.changed_fields, ("model_profiles.worker.model", "model_profiles.worker.effort"))
            self.assertEqual(success.events, ("backup", "edit", "validate:forward", "reload:first", "verify:selected"))
            parsed = json.loads(project_config.read_text(encoding="utf-8"))
            self.assertEqual(parsed["model_profiles"]["observer"], {"model": "project/observer", "effort": "minimal"})
            self.assertEqual(parsed["unrelated"], ["byte", "stable"])

            fallback_home_config = home / ".pi" / "agent" / "subagents.json"
            fallback_home_config.parent.mkdir(parents=True)
            fallback_home_config.write_text(
                '{"model_profiles":{"fallback":{"model":"home/fallback-old","effort":"medium","extra":"stable"}}}\n',
                encoding="utf-8",
            )
            fallback_before = fallback_home_config.read_bytes()
            fallback_contracts = discover_agent_contracts(RuntimeKind.PI, home, root / "empty-project", {})
            fallback = {contract.name: contract for contract in fallback_contracts}["fallback"]
            self.assertEqual(fallback.scope, "global")
            self.assertEqual(fallback.apply_target, str(fallback_home_config))

            rollback_change = ApprovedChange.after_approval(
                approved=True,
                agent="fallback",
                previous_route=Route("home/fallback-old", "medium"),
                selected_route=Route("selected/fallback", "high"),
                apply_target=ApplyTarget(runtime="pi", scope="global", path=Path(fallback.apply_target), format="pi-json"),
                source_digest=_digest(fallback_home_config),
            )
            rollback = simulate_approved_apply(
                rollback_change,
                temp_root=root,
                timestamp="20260820T010204Z",
                fail_at="verify:selected",
            )
            self.assertFalse(rollback.applied)
            self.assertTrue(rollback.rollback_applied)
            self.assertEqual(fallback_home_config.read_bytes(), fallback_before)
            self.assertEqual(rollback.backup_path.read_bytes(), fallback_before)
            self.assertEqual(rollback.events, (
                "backup",
                "edit",
                "validate:forward",
                "reload:first",
                "verify:selected",
                "restore:os.replace",
                "validate:restored",
                "reload:second",
                "verify:restored",
            ))
            self.assertEqual(json.loads(fallback_home_config.read_text(encoding="utf-8"))["model_profiles"]["fallback"]["model"], "home/fallback-old")

    def test_opencode_json_project_partial_override_does_not_copy_inherited_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            xdg = root / "xdg"
            project = root / "project"
            (xdg / "opencode").mkdir(parents=True)
            project.mkdir()
            home.mkdir()
            global_config = xdg / "opencode" / "opencode.json"
            project_config = project / "opencode.json"
            global_config.write_text(
                '{\n'
                '  "agent": {\n'
                '    "builder": {"model": "global/builder-old", "variant": "high", "permission": {"bash": "deny"}},\n'
                '    "scout": {"model": "global/scout", "variant": "minimal"}\n'
                '  },\n'
                '  "theme": "stable"\n'
                '}\n',
                encoding="utf-8",
            )
            project_config.write_text(
                '{\n'
                '  "agent": {\n'
                '    "builder": {"model": "project/builder-old", "permission": {"edit": {"*.py": "ask"}}}\n'
                '  },\n'
                '  "profile": {"name": "project-stable"}\n'
                '}\n',
                encoding="utf-8",
            )
            global_before = global_config.read_bytes()
            project_before = project_config.read_bytes()

            contracts = discover_agent_contracts(RuntimeKind.OPENCODE, home, project, {"XDG_CONFIG_HOME": str(xdg)})
            builder = {contract.name: contract for contract in contracts}["builder"]
            self.assertEqual(builder.scope, "project")
            self.assertEqual(builder.model, "project/builder-old")
            self.assertIsNone(builder.effort)
            self.assertEqual(builder.apply_target, str(project_config))

            change = ApprovedChange.after_approval(
                approved=True,
                agent="builder",
                previous_route=Route("project/builder-old", "high"),
                selected_route=Route("selected/builder", "high"),
                apply_target=ApplyTarget(runtime="opencode", scope="project", path=Path(builder.apply_target), format="opencode-json"),
                source_digest=_digest(project_config),
            )
            success = simulate_approved_apply(change, temp_root=root, timestamp="20260820T020304Z")
            expected_project = project_before.replace(b'"model": "project/builder-old"', b'"model": "selected/builder"')
            self.assertEqual(project_config.read_bytes(), expected_project)
            self.assertEqual(global_config.read_bytes(), global_before)
            self.assertNotIn(b'"variant"', project_config.read_bytes())
            self.assertEqual(success.changed_fields, ("agent.builder.model",))
            self.assertEqual(success.backup_path.read_bytes(), project_before)
            self.assertEqual(success.events, ("backup", "edit", "validate:forward", "restart:first", "verify:selected"))

            rollback_change = ApprovedChange.after_approval(
                approved=True,
                agent="builder",
                previous_route=Route("selected/builder", "high"),
                selected_route=Route("selected/builder-v2", "high"),
                apply_target=ApplyTarget(runtime="opencode", scope="project", path=project_config, format="opencode-json"),
                source_digest=_digest(project_config),
            )
            rollback_before = project_config.read_bytes()
            rollback = simulate_approved_apply(
                rollback_change,
                temp_root=root,
                timestamp="20260820T020305Z",
                fail_at="reload:first",
            )
            self.assertFalse(rollback.applied)
            self.assertTrue(rollback.rollback_applied)
            self.assertEqual(project_config.read_bytes(), rollback_before)
            self.assertEqual(rollback.backup_path.read_bytes(), rollback_before)
            self.assertEqual(rollback.events, (
                "backup",
                "edit",
                "validate:forward",
                "restart:first",
                "restore:os.replace",
                "validate:restored",
                "restart:second",
                "verify:restored",
            ))

    def test_opencode_markdown_frontmatter_success_and_rollback_preserve_body_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            agent_path = root / "project" / ".opencode" / "agents" / "reviewer.md"
            agent_path.parent.mkdir(parents=True)
            agent_path.write_text(
                '---\n'
                'name: reviewer\n'
                'description: Review changes.\n'
                'model: old/reviewer\n'
                'variant: medium\n'
                'tools: read\n'
                '---\n'
                'Body bytes must stay identical, including: model: not-frontmatter\n',
                encoding="utf-8",
            )
            before = agent_path.read_bytes()
            change = ApprovedChange.after_approval(
                approved=True,
                agent="reviewer",
                previous_route=Route("old/reviewer", "medium"),
                selected_route=Route("selected/reviewer", "high"),
                apply_target=ApplyTarget(runtime="opencode", scope="project", path=agent_path, format="opencode-markdown"),
                source_digest=_digest(agent_path),
            )
            success = simulate_approved_apply(change, temp_root=root, timestamp="20260820T030405Z")
            expected = before.replace(b"model: old/reviewer", b"model: selected/reviewer").replace(
                b"variant: medium", b"variant: high"
            )
            self.assertTrue(success.applied)
            self.assertEqual(agent_path.read_bytes(), expected)
            self.assertEqual(success.changed_fields, ("frontmatter.model", "frontmatter.variant"))
            self.assertEqual(success.backup_path.read_bytes(), before)
            self.assertEqual(success.events, ("backup", "edit", "validate:forward", "restart:first", "verify:selected"))
            self.assertIn(b"Body bytes must stay identical, including: model: not-frontmatter", agent_path.read_bytes())

            rollback_before = agent_path.read_bytes()
            rollback_change = ApprovedChange.after_approval(
                approved=True,
                agent="reviewer",
                previous_route=Route("selected/reviewer", "high"),
                selected_route=Route("selected/reviewer-v2", "minimal"),
                apply_target=ApplyTarget(runtime="opencode", scope="project", path=agent_path, format="opencode-markdown"),
                source_digest=_digest(agent_path),
            )
            rollback = simulate_approved_apply(
                rollback_change,
                temp_root=root,
                timestamp="20260820T030406Z",
                fail_at="verify:selected",
            )
            self.assertFalse(rollback.applied)
            self.assertTrue(rollback.rollback_applied)
            self.assertEqual(agent_path.read_bytes(), rollback_before)
            self.assertEqual(rollback.backup_path.read_bytes(), rollback_before)
            self.assertEqual(rollback.events, (
                "backup",
                "edit",
                "validate:forward",
                "restart:first",
                "verify:selected",
                "restore:os.replace",
                "validate:restored",
                "restart:second",
                "verify:restored",
            ))
