import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import helper.artifacts as artifacts_module
from helper.artifacts import (
    byte_inventory,
    canonical_bytes,
    digest_json,
    inventory_with_digest,
    load_health,
    load_inventory,
    write_health,
    write_inventory,
    write_json_atomic,
)
from helper.evaluator import EvaluationArtifact
from helper.models import (
    CurrentAssignment,
    HealthArtifact,
    HealthCheck,
    HealthStatus,
    Inventory,
    ModelRecord,
    RuntimeInfo,
    RuntimeKind,
)
from helper.optimizer import RouteKey
from helper.state import EvaluationKey, EvaluationSummary
from tests.support import assert_test_path


class ArtifactTests(unittest.TestCase):
    def test_evaluation_artifact_schema_is_bounded_and_privacy_preserving(self):
        secret = "sk" + "-artifact-secret"
        route = RouteKey(RuntimeKind.PI, "test", "nan/qwen3.6", "high")
        summary = EvaluationSummary(
            key=EvaluationKey(route, "sha256:agent", "sha256:tools", "mechanical-slugify", "1", "sha256:model"),
            created_at="2026-08-20T00:00:00Z",
            success=True,
            role_score=1.0,
            contract_success=True,
            elapsed_ms=10,
            metered_cost=None,
            reason_codes=("eval_pass",),
        )
        artifact = EvaluationArtifact(
            schema="model-optimizer.evaluation/v1",
            created_at="2026-08-20T00:00:00Z",
            inventory_digest="sha256:inventory",
            route=route,
            agent_digest="sha256:agent",
            fixture_id="mechanical-slugify",
            fixture_version="1",
            result=summary,
        ).to_dict()
        serialized = json.dumps({"artifact": artifact, "forbidden_probe": secret})
        artifact_only = json.dumps(artifact)
        self.assertEqual(artifact["schema"], "model-optimizer.evaluation/v1")
        self.assertEqual(artifact["route"]["model"], "nan/qwen3.6")
        self.assertIn("result", artifact)
        self.assertNotIn("final_text", artifact_only)
        self.assertNotIn("task", artifact_only)
        self.assertNotIn("tool_arguments", artifact_only)
        self.assertNotIn(secret, artifact_only)
        self.assertIn(secret, serialized)

    def test_byte_inventory_captures_before_after_config_boundaries(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_dir = root / ".config" / "opencode"
            config_dir.mkdir(parents=True)
            (config_dir / "opencode.json").write_text('{"permission":{"*":"deny"}}', encoding="utf-8")
            missing = root / ".pi" / "agent"
            before = byte_inventory((config_dir, missing))
            after = byte_inventory((config_dir, missing))
        self.assertEqual(before, after)
        self.assertEqual(before.status, "PASS")
        self.assertEqual(before.records[0]["kind"], "directory")
        self.assertEqual(before.records[0]["file_count"], 1)
        self.assertTrue(str(before.records[0]["digest"]).startswith("sha256:"))
        self.assertEqual(before.records[1]["kind"], "missing")
        self.assertIsNone(before.records[1]["digest"])

    def test_byte_inventory_brackets_genuine_disposable_pi_rpc_when_available(self):
        if shutil.which("pi") is None:
            self.skipTest("pi runtime unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pi_home = root / "home"
            pi_runtime = root / "pi-runtime"
            workspace = root / "workspace"
            pi_home.mkdir()
            pi_runtime.mkdir()
            workspace.mkdir()
            before = byte_inventory((pi_runtime,))
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": str(pi_home),
                "PI_CODING_AGENT_DIR": str(pi_runtime / "agent"),
                "PI_SESSION_DIR": str(pi_runtime / "sessions"),
                "XDG_CONFIG_HOME": str(pi_runtime / "xdg-config"),
                "XDG_DATA_HOME": str(pi_runtime / "xdg-data"),
                "XDG_CACHE_HOME": str(pi_runtime / "xdg-cache"),
                "NPM_CONFIG_USERCONFIG": str(pi_runtime / "npmrc"),
            }
            payload = '{"id":"state-1","type":"request","command":"get_state","params":{}}\n{"id":"abort-1","type":"request","command":"abort","params":{}}\n'
            command = subprocess.run(
                ["pi", "--offline", "--mode", "rpc", "--no-session", "--session-dir", str(pi_runtime / "sessions"), "--no-context-files", "--no-skills", "--no-prompt-templates", "--tools", "read"],
                cwd=workspace,
                env=env,
                input=payload,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
            )
            after = byte_inventory((pi_runtime,))
        self.assertEqual(command.returncode, 0, command.stderr[-500:])
        self.assertEqual(before.status, "PASS")
        self.assertEqual(after.status, "PASS")

    def test_byte_inventory_brackets_genuine_disposable_opencode_debug_when_available(self):
        if shutil.which("opencode") is None:
            self.skipTest("opencode runtime unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            opencode_runtime = root / "opencode-runtime"
            config_home = opencode_runtime / "config"
            data_home = opencode_runtime / "data"
            workspace.mkdir()
            config_home.mkdir(parents=True)
            data_home.mkdir(parents=True)
            before = byte_inventory((opencode_runtime,))
            command = subprocess.run(
                ["opencode", "debug", "config", "--pure"],
                cwd=workspace,
                env={"PATH": os.environ.get("PATH", ""), "XDG_CONFIG_HOME": str(config_home), "XDG_DATA_HOME": str(data_home)},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
            )
            after = byte_inventory((opencode_runtime,))
        self.assertEqual(command.returncode, 0, command.stderr[-500:])
        self.assertEqual(before.status, "PASS")
        self.assertEqual(after.status, "PASS")

    def test_byte_inventory_disposable_pi_and_opencode_boundaries_are_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pi_runtime = root / "pi-runtime"
            opencode_runtime = root / "opencode-runtime"
            before = byte_inventory((pi_runtime, opencode_runtime))
            pi_runtime.mkdir()
            opencode_runtime.mkdir()
            (pi_runtime / "state.json").write_text("{}", encoding="utf-8")
            (opencode_runtime / "opencode.json").write_text('{"permission":{"*":"deny"}}', encoding="utf-8")
            after = byte_inventory((pi_runtime, opencode_runtime))
        self.assertEqual(before.status, "PASS")
        self.assertEqual(after.status, "PASS")
        self.assertEqual(tuple(record["kind"] for record in before.records), ("missing", "missing"))
        self.assertEqual(tuple(record["kind"] for record in after.records), ("directory", "directory"))
        self.assertNotEqual(before.records, after.records)

    def test_byte_inventory_is_inconclusive_on_read_stat_and_walk_errors(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "file.txt"
            target.write_text("ok", encoding="utf-8")
            with mock.patch.object(Path, "open", side_effect=OSError("boom")):
                read_error = byte_inventory((target,))
            self.assertEqual(read_error.status, "INCONCLUSIVE")
            self.assertEqual(read_error.reason_codes, ("inventory_read_failed",))

            with mock.patch("helper.artifacts.os.lstat", side_effect=OSError("stat")):
                stat_error = byte_inventory((target,))
            self.assertEqual(stat_error.status, "INCONCLUSIVE")
            self.assertEqual(stat_error.reason_codes, ("inventory_stat_failed",))

            directory = root / "walk"
            directory.mkdir()
            with mock.patch("helper.artifacts.os.scandir", side_effect=OSError("walk")):
                walk_error = byte_inventory((directory,))
            self.assertEqual(walk_error.status, "INCONCLUSIVE")
            self.assertEqual(walk_error.reason_codes, ("inventory_walk_failed",))

    def test_byte_inventory_stops_scandir_incrementally_before_overconsuming_unbounded_iterators(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            directory = root / "many"
            directory.mkdir()
            for index in range(5):
                (directory / f"file-{index}.txt").write_text("x", encoding="utf-8")
            original_scandir = os.scandir
            counts = {"next": 0}

            class CountingScandir:
                def __init__(self, path):
                    self._inner = original_scandir(path)

                def __enter__(self):
                    self._inner.__enter__()
                    return self

                def __exit__(self, *args):
                    return self._inner.__exit__(*args)

                def __iter__(self):
                    return self

                def __next__(self):
                    counts["next"] += 1
                    return next(self._inner)

            with mock.patch("helper.artifacts.os.scandir", side_effect=lambda path: CountingScandir(path)), mock.patch.object(artifacts_module, "_MAX_INVENTORY_FILES", 1):
                result = byte_inventory((directory,))
            self.assertEqual(result.status, "INCONCLUSIVE")
            self.assertEqual(result.reason_codes, ("inventory_too_many_files",))
            self.assertLessEqual(counts["next"], 2)

    def test_byte_inventory_enforces_bounded_cardinality_and_paths_before_read(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            directory = root / "many"
            directory.mkdir()
            for index in range(5):
                (directory / f"file-{index}.txt").write_text("x", encoding="utf-8")
            with mock.patch.object(artifacts_module, "_MAX_INVENTORY_FILES", 2):
                too_many_files = byte_inventory((directory,))
            self.assertEqual(too_many_files.status, "INCONCLUSIVE")
            self.assertEqual(too_many_files.reason_codes, ("inventory_too_many_files",))

            with mock.patch.object(artifacts_module, "_MAX_INVENTORY_PATHS", 1):
                too_many_paths = byte_inventory((directory,))
            self.assertEqual(too_many_paths.status, "INCONCLUSIVE")
            self.assertEqual(too_many_paths.reason_codes, ("inventory_too_many_paths",))

            large = root / "large.bin"
            large.write_bytes(b"123456")
            with mock.patch.object(artifacts_module, "_MAX_INVENTORY_BYTES", 4), mock.patch.object(Path, "open", side_effect=AssertionError("open should not run")):
                too_many_bytes = byte_inventory((large,))
            self.assertEqual(too_many_bytes.status, "INCONCLUSIVE")
            self.assertEqual(too_many_bytes.reason_codes, ("inventory_too_many_bytes",))

    def test_canonical_digest_ignores_mapping_insertion_order(self):
        self.assertEqual(canonical_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}')
        self.assertEqual(digest_json({"b": 2, "a": 1}), digest_json({"a": 1, "b": 2}))

    def test_canonical_json_rejects_non_finite_numbers_with_stable_error(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "artifact_invalid_number") as caught:
                    canonical_bytes({"bad": value})
                self.assertNotIn(str(value), str(caught.exception))

    def test_inventory_and_model_non_finite_values_are_rejected_without_raw_data(self):
        bad_inventory = Inventory(
            schema="model-optimizer.inventory/v1",
            created_at="1970-01-01T00:00:00Z",
            runtime=RuntimeInfo(RuntimeKind.PI, "0.84.2", "/work"),
            sources=(), current_assignments=(),
            catalog_local=(ModelRecord("nan/qwen", "nan", "qwen", input_cost=math.nan),),
            provider_readiness=(), exclusions=(), warnings=(), digest="",
        )
        bad_health = HealthArtifact(
            schema="model-optimizer.health/v1",
            created_at="1970-01-01T00:00:00Z",
            inventory_digest="sha256:inventory",
            checks=(HealthCheck("nan/qwen", None, HealthStatus.PASS, math.inf, "ok", True, "ok"),),
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, writer, artifact in (
                ("inventory", write_inventory, bad_inventory),
                ("health", write_health, bad_health),
            ):
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, "artifact_invalid_number") as caught:
                        writer(root / f"{name}.json", artifact)
                    self.assertFalse((root / f"{name}.json").exists())
                    self.assertNotIn("nan", str(caught.exception).lower())
                    self.assertNotIn("inf", str(caught.exception).lower())

    def test_load_inventory_rejects_non_finite_json_constant_with_stable_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inventory.json"
            path.write_text('{"schema":"model-optimizer.inventory/v1","value":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact_invalid_number") as caught:
                load_inventory(path)
        self.assertNotIn("NaN", str(caught.exception))

    def test_inventory_round_trip_preserves_schema_and_digest(self):
        inventory = Inventory.empty(RuntimeInfo(RuntimeKind.PI, "0.84.2", "/work"))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inventory.json"
            write_inventory(path, inventory)
            loaded = load_inventory(path)
        self.assertEqual(loaded.schema, "model-optimizer.inventory/v1")
        self.assertEqual(loaded.digest, inventory.digest)

    def test_unknown_inventory_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inventory.json"
            path.write_text(json.dumps({"schema": "unknown/v9"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact_unknown_schema"):
                load_inventory(path)

    def test_malformed_inventory_parse_and_shape_errors_are_bounded_value_errors(self):
        attacker = "attacker-controlled-secret"
        malformed_values = (
            ("invalid-json", "{" + attacker),
            ("primitive-root", json.dumps(7)),
            ("list-root", json.dumps([])),
            ("schema-correct-missing-fields", json.dumps({"schema": "model-optimizer.inventory/v1"})),
            ("malformed-nested-shape", json.dumps({
                "schema": "model-optimizer.inventory/v1",
                "created_at": "1970-01-01T00:00:00Z",
                "runtime": [],
                "sources": [],
                "current_assignments": [],
                "catalog_local": {"attacker": attacker},
                "provider_readiness": [],
                "exclusions": [],
                "warnings": [],
                "digest": "sha256:not-a-valid-digest",
            })),
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inventory.json"
            for name, text in malformed_values:
                path.write_text(text, encoding="utf-8")
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, r"artifact_(invalid_json|invalid_shape)") as caught:
                        load_inventory(path)
                    self.assertNotIn(attacker, str(caught.exception))

    def test_inventory_invalid_utf8_is_bounded_stable_artifact_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inventory.json"
            path.write_bytes(b'\xff\xfe{"schema":"model-optimizer.inventory/v1","secret":"raw-secret"}')
            with self.assertRaisesRegex(ValueError, "artifact_invalid_encoding") as caught:
                load_inventory(path)
        message = str(caught.exception)
        self.assertNotIn("utf-8", message)
        self.assertNotIn("codec", message)
        self.assertNotIn("raw-secret", message)

    def test_current_assignment_options_are_deeply_immutable_and_alias_safe(self):
        options = {
            "reasoning": {"effort": "high"},
            "fallbacks": ["fast", {"model": "slow"}],
        }
        assignment = CurrentAssignment("agent", "model", options, "settings.json")

        options["reasoning"]["effort"] = "low"
        options["fallbacks"].append("surprise")
        options["fallbacks"][1]["model"] = "mutated"

        self.assertEqual(assignment.options["reasoning"]["effort"], "high")
        self.assertEqual(assignment.options["fallbacks"][1]["model"], "slow")
        with self.assertRaises(TypeError):
            assignment.options["new"] = "blocked"
        with self.assertRaises(TypeError):
            assignment.options["reasoning"]["effort"] = "blocked"
        self.assertIsInstance(assignment.options["fallbacks"], tuple)

        thawed = assignment.to_dict()["options"]
        self.assertEqual(thawed, {"reasoning": {"effort": "high"}, "fallbacks": ["fast", {"model": "slow"}]})
        self.assertIsInstance(thawed, dict)
        self.assertIsInstance(thawed["reasoning"], dict)
        self.assertIsInstance(thawed["fallbacks"], list)
        self.assertIsInstance(thawed["fallbacks"][1], dict)

    def test_current_assignment_options_from_dict_are_deeply_immutable_and_alias_safe(self):
        source = {
            "agent": "agent",
            "model": "model",
            "options": {"nested": {"enabled": True}, "array": [1, {"two": 2}]},
            "source": "settings.json",
        }
        assignment = CurrentAssignment.from_dict(source)

        source["options"]["nested"]["enabled"] = False
        source["options"]["array"][1]["two"] = 22

        self.assertEqual(assignment.to_dict()["options"], {"nested": {"enabled": True}, "array": [1, {"two": 2}]})
        with self.assertRaises(TypeError):
            assignment.options["nested"]["enabled"] = False

    def test_current_assignment_options_reject_non_json_values(self):
        with self.assertRaisesRegex(ValueError, "artifact_invalid_options"):
            CurrentAssignment("agent", "model", {"bad": {"set-members"}}, "settings.json")
        with self.assertRaisesRegex(ValueError, "artifact_invalid_options"):
            CurrentAssignment("agent", "model", {1: "non-string key"}, "settings.json")

    def test_current_assignment_options_freezing_is_idempotent_for_frozen_options(self):
        first = CurrentAssignment("agent", "model", {"array": ["a", {"b": True}]}, "settings.json")
        second = CurrentAssignment("agent", "model", first.options, "settings.json")
        self.assertEqual(second.to_dict()["options"], {"array": ["a", {"b": True}]})
        with self.assertRaises(TypeError):
            second.options["array"][1]["b"] = False

    def test_current_assignment_options_serialization_and_digest_remain_stable_after_alias_mutation(self):
        options = {"nested": {"items": ["a", "b"]}}
        assignment = CurrentAssignment("agent", "model", options, "settings.json")
        inventory = inventory_with_digest(Inventory(
            schema="model-optimizer.inventory/v1",
            created_at="1970-01-01T00:00:00Z",
            runtime=RuntimeInfo(RuntimeKind.PI, "0.84.2", "/work"),
            sources=(),
            current_assignments=(assignment,),
            catalog_local=(),
            provider_readiness=(),
            exclusions=(),
            warnings=(),
            digest="",
        ))
        before_dict = inventory.to_dict()
        before_digest = inventory.digest

        options["nested"]["items"].append("mutated")

        self.assertEqual(inventory.to_dict(), before_dict)
        self.assertEqual(inventory.digest, before_digest)
        self.assertEqual(inventory_with_digest(inventory).digest, before_digest)

    def test_inventory_digest_mismatch_is_rejected(self):
        inventory = Inventory.empty(RuntimeInfo(RuntimeKind.PI, "0.84.2", "/work"))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inventory.json"
            write_inventory(path, inventory)
            value = json.loads(path.read_text(encoding="utf-8"))
            value["created_at"] = "2026-08-19T00:00:00Z"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact_digest_mismatch"):
                load_inventory(path)

    def test_write_inventory_replaces_hardlink_without_overwriting_original_inode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = root / "settings.json"
            output = root / "inventory.json"
            config.write_bytes(b"original-config")
            try:
                os.link(config, output)
            except (AttributeError, NotImplementedError, OSError) as exc:
                self.skipTest(f"hardlinks unsupported: {exc}")
            before_inode = config.stat().st_ino

            write_inventory(output, Inventory.empty(RuntimeInfo(RuntimeKind.PI, "0.84.2", "/work")))

            self.assertEqual(config.read_bytes(), b"original-config")
            self.assertEqual(config.stat().st_ino, before_inode)
            self.assertNotEqual(output.stat().st_ino, before_inode)
            self.assertEqual(load_inventory(output).runtime.kind, RuntimeKind.PI)

    def test_write_health_replaces_hardlink_without_overwriting_original_inode(self):
        health = HealthArtifact(
            schema="model-optimizer.health/v1",
            created_at="1970-01-01T00:00:00Z",
            inventory_digest="sha256:inventory",
            checks=(),
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = root / "opencode.json"
            output = root / "health.json"
            config.write_bytes(b"original-config")
            try:
                os.link(config, output)
            except (AttributeError, NotImplementedError, OSError) as exc:
                self.skipTest(f"hardlinks unsupported: {exc}")
            before_inode = config.stat().st_ino

            write_health(output, health)

            self.assertEqual(config.read_bytes(), b"original-config")
            self.assertEqual(config.stat().st_ino, before_inode)
            self.assertNotEqual(output.stat().st_ino, before_inode)
            self.assertEqual(load_health(output).inventory_digest, "sha256:inventory")

    def test_concurrent_inventory_writes_leave_one_loadable_artifact_and_no_temp_debris(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "inventory.json"
            inventories = [Inventory.empty(RuntimeInfo(RuntimeKind.PI, f"0.84.{index}", "/work")) for index in range(8)]
            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(lambda inventory: write_inventory(output, inventory), inventories))

            loaded = load_inventory(output)
            self.assertIn(loaded.runtime.version, {inventory.runtime.version for inventory in inventories})
            self.assertEqual(list(root.glob(".inventory.json.*.tmp")), [])

    def test_concurrent_health_writes_leave_one_loadable_artifact_and_no_temp_debris(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "health.json"
            artifacts = [HealthArtifact(
                schema="model-optimizer.health/v1",
                created_at=f"1970-01-01T00:00:0{index}Z",
                inventory_digest=f"sha256:{index}",
                checks=(),
            ) for index in range(8)]
            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(lambda health: write_health(output, health), artifacts))

            loaded = load_health(output)
            self.assertIn(loaded.inventory_digest, {health.inventory_digest for health in artifacts})
            self.assertEqual(list(root.glob(".health.json.*.tmp")), [])

    def test_atomic_write_retries_transient_permission_error_from_replace(self):
        inventory = Inventory.empty(RuntimeInfo(RuntimeKind.PI, "0.84.2", "/work"))
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "inventory.json"
            real_replace = os.replace

            attempts = 0

            def flaky_replace(src: str, dst: str | os.PathLike[str]) -> None:
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError(5, "Access denied")
                real_replace(src, dst)

            with mock.patch("helper.artifacts.os.replace", side_effect=flaky_replace) as replace_mock, \
                    mock.patch("helper.artifacts.time.sleep") as sleep_mock:
                write_inventory(output, inventory)

            self.assertEqual(replace_mock.call_count, 2)
            sleep_mock.assert_called_once_with(artifacts_module._REPLACE_RETRY_SLEEP_SECONDS)
            self.assertEqual(load_inventory(output).digest, inventory.digest)
            self.assertEqual(list(Path(td).glob(".inventory.json.*.tmp")), [])

    def test_atomic_write_reraises_permission_error_after_bounded_retries_and_cleans_temp(self):
        inventory = Inventory.empty(RuntimeInfo(RuntimeKind.PI, "0.84.2", "/work"))
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "inventory.json"
            with mock.patch("helper.artifacts.os.replace", side_effect=PermissionError(5, "Access denied")) as replace_mock, \
                    mock.patch("helper.artifacts.time.sleep") as sleep_mock:
                with self.assertRaises(PermissionError):
                    write_inventory(output, inventory)

            self.assertEqual(replace_mock.call_count, artifacts_module._REPLACE_RETRY_ATTEMPTS)
            self.assertEqual(sleep_mock.call_count, artifacts_module._REPLACE_RETRY_ATTEMPTS - 1)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(td).glob(".inventory.json.*.tmp")), [])

    def test_same_target_replace_critical_section_is_serialized(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "inventory.json"
            inventories = [Inventory.empty(RuntimeInfo(RuntimeKind.PI, f"0.84.{index}", "/work")) for index in range(8)]
            start = threading.Barrier(len(inventories))
            counters_lock = threading.Lock()
            active = 0
            max_active = 0
            real_replace = os.replace

            def instrumented_replace(src: str, dst: str | os.PathLike[str]) -> None:
                nonlocal active, max_active
                with counters_lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.02)
                try:
                    real_replace(src, dst)
                finally:
                    with counters_lock:
                        active -= 1

            def write_one(inventory: Inventory) -> None:
                start.wait(timeout=5)
                write_inventory(output, inventory)

            with mock.patch("helper.artifacts.os.replace", side_effect=instrumented_replace):
                with ThreadPoolExecutor(max_workers=len(inventories)) as executor:
                    list(executor.map(write_one, inventories))

            self.assertEqual(max_active, 1)

    def test_write_json_atomic_creates_parents_and_writes_strict_sorted_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "nested" / "state.json"
            write_json_atomic(path, {"b": 2, "a": 1})
            self.assertEqual(path.read_text(encoding="utf-8"), '{\n  "a": 1,\n  "b": 2\n}\n')

    def test_write_json_atomic_rejects_non_finite_numbers_without_creating_target_or_temp_debris(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "state.json"
            with self.assertRaisesRegex(ValueError, "artifact_invalid_number") as caught:
                write_json_atomic(path, {"bad": math.inf})
            self.assertFalse(path.exists())
            self.assertEqual(list(root.glob(".state.json.*.tmp")), [])
            self.assertNotIn("inf", str(caught.exception).lower())

    def test_write_json_atomic_replaces_hardlink_without_overwriting_original_inode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = root / "settings.json"
            output = root / "state.json"
            config.write_bytes(b"original-config")
            try:
                os.link(config, output)
            except (AttributeError, NotImplementedError, OSError) as exc:
                self.skipTest(f"hardlinks unsupported: {exc}")
            before_inode = config.stat().st_ino

            write_json_atomic(output, {"schema": "model-optimizer.state/v1"})

            self.assertEqual(config.read_bytes(), b"original-config")
            self.assertEqual(config.stat().st_ino, before_inode)
            self.assertNotEqual(output.stat().st_ino, before_inode)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["schema"], "model-optimizer.state/v1")

    def test_concurrent_write_json_atomic_writes_leave_one_valid_document_and_no_temp_debris(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "state.json"
            values = [{"index": index, "items": list(range(index))} for index in range(12)]
            with ThreadPoolExecutor(max_workers=6) as executor:
                list(executor.map(lambda value: write_json_atomic(output, value), values))

            loaded = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn(loaded, values)
            self.assertEqual(list(root.glob(".state.json.*.tmp")), [])

    def test_write_json_atomic_reraises_bounded_replace_failure_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "state.json"
            with mock.patch("helper.artifacts.os.replace", side_effect=PermissionError(5, "Access denied")) as replace_mock, \
                    mock.patch("helper.artifacts.time.sleep") as sleep_mock:
                with self.assertRaises(PermissionError):
                    write_json_atomic(output, {"schema": "model-optimizer.state/v1"})

            self.assertEqual(replace_mock.call_count, artifacts_module._REPLACE_RETRY_ATTEMPTS)
            self.assertEqual(sleep_mock.call_count, artifacts_module._REPLACE_RETRY_ATTEMPTS - 1)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".state.json.*.tmp")), [])

    def test_health_round_trip_preserves_schema_without_self_digest(self):
        health = HealthArtifact(
            schema="model-optimizer.health/v1",
            created_at="1970-01-01T00:00:00Z",
            inventory_digest="sha256:inventory",
            checks=(HealthCheck(
                model="openai/gpt-5",
                effort=None,
                status=HealthStatus.PASS,
                elapsed_ms=123,
                reason_code="ok",
                response_matched=True,
                detail="sentinel matched",
            ),),
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "health.json"
            write_health(path, health)
            raw = json.loads(path.read_text(encoding="utf-8"))
            loaded = load_health(path)
        self.assertNotIn("digest", raw)
        self.assertEqual(loaded.to_dict(), health.to_dict())

    def test_unknown_health_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "health.json"
            path.write_text(json.dumps({"schema": "unknown/v9"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact_unknown_schema"):
                load_health(path)

    def test_assert_test_path_rejects_escape(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            assert_test_path(temp_root / "inside.json", temp_root)
            with self.assertRaisesRegex(AssertionError, "escaped temporary root"):
                assert_test_path(temp_root / ".." / "outside.json", temp_root)
