import sqlite3
import tempfile
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "creativeos.sqlite3"
        self.store = CreativeOSStore(self.db_path)
        self.assertEqual(self.store.migrate_to_latest(), 9)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def seed_graph(self) -> dict[str, dict]:
        brand = self.store.create("brand_profiles", {"name": "Test Brand", "palette_json": ["#111111"]})
        campaign = self.store.create("campaigns", {"brand_profile_id": brand["id"], "title": "Launch"})
        board = self.store.create("storyboards", {"campaign_id": campaign["id"], "title": "Main"})
        scene = self.store.create("scenes", {"storyboard_id": board["id"], "position": 1, "title": "Hook"})
        return {"brand": brand, "campaign": campaign, "board": board, "scene": scene}

    def test_forward_rollback_reapply(self) -> None:
        self.assertEqual(self.store.schema_version(), 9)
        self.assertEqual(self.store.rollback_to(0), 0)
        self.assertEqual(self.store.schema_version(), 0)
        self.assertEqual(self.store.migrate_to_latest(), 9)
        tables = {row[0] for row in self.store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in {"brand_profiles", "campaigns", "storyboards", "scenes", "assets", "generation_jobs", "qa_results", "export_jobs", "creative_memory", "asset_requirements", "generated_assets"}:
            self.assertIn(name, tables)

    def test_crud_for_all_domain_entities(self) -> None:
        graph = self.seed_graph()
        asset = self.store.create("assets", {"campaign_id": graph["campaign"]["id"], "scene_id": graph["scene"]["id"], "asset_type": "screenshot", "path": "asset.png", "immutable_ui": True})
        job = self.store.create("generation_jobs", {"scene_id": graph["scene"]["id"], "provider": "mock", "model": "mock-video"})
        qa = self.store.create("qa_results", {"campaign_id": graph["campaign"]["id"], "scene_id": graph["scene"]["id"], "check_type": "resolution", "status": "PASS"})
        export = self.store.create("export_jobs", {"campaign_id": graph["campaign"]["id"], "preset": "16:9"})
        self.assertEqual(self.store.update("brand_profiles", graph["brand"]["id"], {"positioning": "Clear value"})["positioning"], "Clear value")
        self.assertEqual(self.store.get("assets", asset["id"])["immutable_ui"], 1)
        self.assertEqual(self.store.get("generation_jobs", job["id"])["state"], "DRAFT")
        self.assertEqual(self.store.get("qa_results", qa["id"])["status"], "PASS")
        self.assertEqual(self.store.get("export_jobs", export["id"])["preset"], "16:9")
        self.assertEqual(len(self.store.list("scenes", {"storyboard_id": graph["board"]["id"]})), 1)

    def test_foreign_key_enforcement(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create("campaigns", {"brand_profile_id": "missing", "title": "Invalid"})
        self.assertEqual(self.store.foreign_key_violations(), [])

    def test_restart_persistence(self) -> None:
        graph = self.seed_graph()
        brand_id = graph["brand"]["id"]
        self.store.close()
        self.store = CreativeOSStore(self.db_path)
        self.assertEqual(self.store.schema_version(), 9)
        self.assertEqual(self.store.get("brand_profiles", brand_id)["name"], "Test Brand")

    def test_delete_and_cascade(self) -> None:
        graph = self.seed_graph()
        self.store.create("generation_jobs", {"scene_id": graph["scene"]["id"], "provider": "mock", "model": "video"})
        self.store.delete("storyboards", graph["board"]["id"])
        self.assertEqual(self.store.list("scenes"), [])
        self.assertEqual(self.store.list("generation_jobs"), [])

    def test_scene_positions_are_unique_per_storyboard(self) -> None:
        graph = self.seed_graph()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create("scenes", {"storyboard_id": graph["board"]["id"], "position": 1, "title": "Duplicate"})


if __name__ == "__main__":
    unittest.main()
