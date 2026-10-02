import tempfile
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.multibrand import MultiBrandService
from creativeos_db.auth import AuthService, AccessError


class AuthFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "auth.sqlite3"
        with CreativeOSStore(self.db) as store:
            store.migrate_to_latest()
            multi = MultiBrandService(store)
            self.orgs = [multi.create_organization(n, n) for n in ("alpha", "beta")]
            self.brands = [multi.create_brand(o["id"], {"name": o["name"]}) for o in self.orgs]
        self.auth = AuthService(self.db)
        self.users = [self.auth.provision_user(n, "test-password-only-123", is_platform_admin=i == 0)
                      for i, n in enumerate(("alice", "bob"))]
        for user, org in zip(self.users, self.orgs):
            self.auth.grant_membership(user["id"], org["id"], "OWNER")
        self.logins = [self.auth.login(n, "test-password-only-123") for n in ("alice", "bob")]

    def tearDown(self):
        self.tmp.cleanup()

    def select(self, n=0):
        login = self.logins[n]
        return self.auth.select_scope(login["token"], login["csrf"], 0,
                                      self.orgs[n]["id"], self.brands[n]["id"])

    def request(self, n=0, version=1, write=False):
        login = self.logins[n]
        return self.auth.request(login["token"], expected_version=version,
                                 csrf=login["csrf"], write=write)


class AuthenticatedScopeTests(AuthFixture, unittest.TestCase):
    def test_passwords_and_opaque_sessions_are_not_stored_in_plaintext(self):
        with CreativeOSStore(self.db) as store:
            raw = str([tuple(r) for r in store.conn.execute("SELECT * FROM auth_users")])
            sessions = str([tuple(r) for r in store.conn.execute("SELECT * FROM auth_sessions")])
        self.assertNotIn("test-password-only-123", raw)
        self.assertNotIn(self.logins[0]["token"], sessions)
        with self.assertRaises(AccessError):
            self.auth.login("alice", "wrong-password")
        with self.assertRaises(AccessError):
            self.auth.session("forged-session")

    def test_membership_required_for_organization_and_brand_selection(self):
        a = self.logins[0]
        for org, brand in ((self.orgs[1], self.brands[1]), (self.orgs[0], self.brands[1])):
            with self.assertRaises(AccessError):
                self.auth.select_scope(a["token"], a["csrf"], 0, org["id"], brand["id"])
        self.assertIsNone(self.auth.session(a["token"])["scope"])

    def test_missing_stale_and_revoked_scope_fail_closed(self):
        with self.assertRaises(AccessError):
            with self.request(version=0):
                pass
        self.select()
        with self.assertRaises(AccessError):
            with self.request(version=0):
                pass
        self.auth.revoke_membership(self.users[0]["id"], self.orgs[0]["id"])
        with self.assertRaises(AccessError):
            with self.request():
                pass
        self.auth.grant_membership(self.users[0]["id"], self.orgs[0]["id"], "OWNER")
        with self.assertRaises(AccessError):
            with self.request():
                pass

    def test_cross_tab_compare_and_swap_and_persisted_context(self):
        state = self.select()
        a = self.logins[0]
        with self.assertRaises(AccessError):
            self.auth.select_scope(a["token"], a["csrf"], 0, self.orgs[0]["id"], self.brands[0]["id"])
        fresh = AuthService(self.db).session(a["token"])
        self.assertEqual(fresh["scope"], state["scope"])
        self.auth.select_scope(a["token"], a["csrf"], 1, self.orgs[0]["id"], None)
        with self.assertRaises(AccessError):
            with self.request(version=1):
                pass

    def test_two_users_cannot_read_or_mutate_each_others_campaigns(self):
        for n in (0, 1):
            self.select(n)
        with self.request(0, write=True) as ctx:
            campaign = ctx.store.create("campaigns", {"organization_id": ctx.organization_id,
                "brand_profile_id": ctx.brand_profile_id, "title": "Alice private"})
        with self.request(1, write=True) as ctx:
            self.assertEqual(ctx.store.list("campaigns"), [])
            for operation in (
                lambda: ctx.store.get("campaigns", campaign["id"]),
                lambda: ctx.store.update("campaigns", campaign["id"], {"title": "forged"}),
            ):
                with self.assertRaises(PermissionError):
                    operation()
        with self.request(0) as ctx:
            self.assertEqual(ctx.store.get("campaigns", campaign["id"])["title"], "Alice private")

    def test_mutation_requires_csrf_and_write_membership(self):
        self.select()
        a = self.logins[0]
        with self.assertRaises(AccessError):
            with self.auth.request(a["token"], expected_version=1, csrf="forged", write=True):
                pass
        self.auth.grant_membership(self.users[0]["id"], self.orgs[0]["id"], "VIEWER")
        state = self.auth.session(a["token"])
        state = self.auth.select_scope(a["token"], a["csrf"], state["version"],
                                       self.orgs[0]["id"], self.brands[0]["id"])
        with self.assertRaises(AccessError):
            with self.request(version=state["version"], write=True):
                pass

    def test_request_transaction_rolls_back_partial_service_commits(self):
        self.select()
        with self.assertRaises(RuntimeError):
            with self.request(write=True) as ctx:
                ctx.store.create("campaigns", {"organization_id": ctx.organization_id,
                    "brand_profile_id": ctx.brand_profile_id, "title": "must roll back"})
                raise RuntimeError("later step failed")
        with self.request() as ctx:
            self.assertEqual(ctx.store.list("campaigns"), [])

    def test_revocation_serializes_with_authorized_request_and_blocks_next_request(self):
        import threading
        self.select()
        started, finished = threading.Event(), threading.Event()
        errors = []
        def revoke():
            started.set()
            try:
                self.auth.revoke_membership(self.users[0]["id"], self.orgs[0]["id"])
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()
        with self.request(write=True) as ctx:
            worker = threading.Thread(target=revoke)
            worker.start()
            self.assertTrue(started.wait(2))
            ctx.store.create("campaigns", {"organization_id": ctx.organization_id,
                "brand_profile_id": ctx.brand_profile_id, "title": "Authorized before revocation"})
            self.assertFalse(finished.wait(0.1), "Service commits must not release the request authority lock")
        worker.join(5)
        self.assertTrue(finished.is_set())
        self.assertEqual(errors, [])
        with self.assertRaises(AccessError):
            with self.request():
                pass


if __name__ == "__main__":
    unittest.main()
