import tempfile
import unittest
from pathlib import Path
from creativeos_db import CreativeOSStore
from creativeos_db.auth import AuthService
from creativeos_db.migrations import MIGRATIONS


class AuthMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "migration.sqlite3"
    def tearDown(self):
        self.tmp.cleanup()

    def test_v11_v12_roundtrip_preserves_unowned_records_and_restores_ownership_locks(self):
        with CreativeOSStore(self.db) as store:
            for version in range(1, 12):
                store._migration_script(MIGRATIONS[version][0])
            legacy = store.create("brand_profiles", {"name": "Legacy evidence"})
            campaign = store.create("campaigns", {"brand_profile_id": legacy["id"], "title": "Keep me"})
            before = store.get("campaigns", campaign["id"])
            self.assertEqual(store.migrate_to_latest(), 13)
            self.assertEqual(store.get("campaigns", campaign["id"]), before)
            self.assertEqual(store.rollback_to(11), 11)
            self.assertEqual(store.get("campaigns", campaign["id"]), before)
            self.assertEqual(store.migrate_to_latest(), 13)
            self.assertEqual(store.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(store.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_nonempty_auth_rollback_is_refused_before_any_mutation(self):
        with CreativeOSStore(self.db) as store:
            store.migrate_to_latest()
        user = AuthService(self.db).provision_user("alice", "test-password-123")
        with CreativeOSStore(self.db) as store:
            with self.assertRaisesRegex(ValueError, "discard authentication"):
                store.rollback_to(10)
            self.assertEqual(store.schema_version(), 13)
            self.assertEqual(store.conn.execute("SELECT id FROM auth_users").fetchone()[0], user["id"])

    def test_failed_forward_migration_is_atomic(self):
        with CreativeOSStore(self.db) as store:
            for version in range(1, 12):
                store._migration_script(MIGRATIONS[version][0])
            with self.assertRaises(Exception):
                store._migration_script(MIGRATIONS[12][0] + "\nINVALID SQL;")
            self.assertEqual(store.schema_version(), 11)
            self.assertIsNone(store.conn.execute("SELECT name FROM sqlite_master WHERE name='auth_users'").fetchone())
            self.assertNotIn("render_job_id", store._columns("generation_requests"))
            self.assertEqual(store.migrate_to_latest(), 13)
