import json
import tempfile
import unittest
from pathlib import Path

from helper.artifacts import canonical_bytes, digest_json, load_inventory, write_inventory
from helper.models import Inventory, RuntimeInfo, RuntimeKind


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
