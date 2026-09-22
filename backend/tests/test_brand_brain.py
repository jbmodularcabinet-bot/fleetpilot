import sqlite3
import tempfile
import unittest
from pathlib import Path

from creativeos_db.brand_brain import fleetpilot_fixture, validate_brand_payload
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.migrations import MIGRATION_1_UP
from creativeos_db.store import CreativeOSStore


class BrandBrainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "creativeos.sqlite3"
        self.store = CreativeOSStore(self.db_path)
        self.assertEqual(self.store.migrate_to_latest(), 8)
        self.service = BrandBrainService(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_validation_and_immutable_default(self) -> None:
        data = validate_brand_payload({"name": " Acme ", "palette_json": ["#112233"], "fonts_json": ["Inter"], "default_immutable_ui": True})
        self.assertEqual(data["name"], "Acme")
        self.assertTrue(data["default_immutable_ui"])
        with self.assertRaises(ValueError):
            validate_brand_payload({"name": "", "palette_json": []})
        with self.assertRaises(ValueError):
            validate_brand_payload({"name": "Bad", "palette_json": ["mint"]})
    def test_fixture_crud_memory_and_restart_persistence(self) -> None:
        brand = self.service.load_fleetpilot_fixture()
        self.assertEqual(brand["name"], "FleetPilot")
        self.assertTrue(brand["default_immutable_ui"])
        self.assertIn("trip profitability", brand["messaging_json"])
        updated = self.service.update(brand["id"], {"tone_of_voice": "Clear, operational, confident"})
        self.assertEqual(updated["tone_of_voice"], "Clear, operational, confident")
        memory = self.service.add_memory(brand["id"], "accepted", "Use real product UI first.", "golden-fixture")
        self.assertEqual(memory["decision_type"], "accepted")
        brand_id = brand["id"]
        self.store.close()
        self.store = CreativeOSStore(self.db_path)
        self.service = BrandBrainService(self.store)
        loaded = self.service.get(brand_id)
        self.assertEqual(loaded["tone_of_voice"], "Clear, operational, confident")
        self.assertTrue(loaded["default_immutable_ui"])
        self.assertEqual(len(self.store.list("creative_memory", {"brand_profile_id": brand_id})), 1)

    def test_duplicate_name_and_bad_path_are_rejected(self) -> None:
        self.service.create({"name": "Alpha", "palette_json": [], "fonts_json": []})
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.create({"name": "alpha", "palette_json": [], "fonts_json": []})
        with self.assertRaises(ValueError):
            self.service.create({"name": "Bad Path", "palette_json": [], "fonts_json": [], "logo_path": "relative/logo.png"})

    def test_batch2_data_survives_v1_to_v2_migration(self) -> None:
        other = Path(self.tmp.name) / "upgrade.sqlite3"
        store = CreativeOSStore(other)
        store.conn.executescript(MIGRATION_1_UP)
        store.conn.commit()
        store.conn.execute("INSERT INTO brand_profiles(id,name,palette_json,fonts_json,created_at,updated_at) VALUES(?,?,?,?,?,?)", ("legacy-brand", "Legacy", "[\"#112233\"]", "[]", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"))
        store.conn.commit()
        self.assertEqual(store.schema_version(), 1)
        self.assertEqual(store.migrate_to_latest(), 8)
        self.assertEqual(store.get("brand_profiles", "legacy-brand")["name"], "Legacy")
        self.assertEqual(store.rollback_to(1), 1)
        self.assertEqual(store.get("brand_profiles", "legacy-brand")["name"], "Legacy")
        self.assertEqual(store.migrate_to_latest(), 8)
        store.close()
