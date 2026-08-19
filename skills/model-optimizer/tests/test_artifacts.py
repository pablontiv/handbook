import json
import tempfile
import unittest
from pathlib import Path

from helper.artifacts import (
    canonical_bytes,
    digest_json,
    inventory_with_digest,
    load_health,
    load_inventory,
    write_health,
    write_inventory,
)
from helper.models import (
    CurrentAssignment,
    HealthArtifact,
    HealthCheck,
    HealthStatus,
    Inventory,
    RuntimeInfo,
    RuntimeKind,
)
from tests.support import assert_test_path


class ArtifactTests(unittest.TestCase):
    def test_canonical_digest_ignores_mapping_insertion_order(self):
        self.assertEqual(canonical_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}')
        self.assertEqual(digest_json({"b": 2, "a": 1}), digest_json({"a": 1, "b": 2}))

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
