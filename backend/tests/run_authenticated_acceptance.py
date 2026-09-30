"""Run real Chromium acceptance against a disposable loopback server and database."""
import json
import os
import secrets
import subprocess
import tempfile
import threading
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.auth import AuthService
from creativeos_db.multibrand import MultiBrandService
from creativeos_db.server import create_server


def main():
    repo = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="creativeos-auth-acceptance-") as temp:
        root = Path(temp)
        db = root / "acceptance.sqlite3"
        auth = AuthService(db)
        accounts = []
        with CreativeOSStore(db) as store:
            store.migrate_to_latest()
            multi = MultiBrandService(store)
            for i, name in enumerate(("alice", "bob")):
                org = multi.create_organization(name + " organization", name)
                brand = multi.create_brand(org["id"], {"name": name + " brand"})
                second = multi.create_brand(org["id"], {"name": name + " second product"}, entity_type="PRODUCT")
                password = secrets.token_urlsafe(24)
                user = auth.provision_user(name, password, is_platform_admin=i == 0)
                auth.grant_membership(user["id"], org["id"], "OWNER")
                accounts.append({"username": name, "password": password, "org": org["id"], "brand": brand["id"], "secondBrand": second["id"]})
            legacy = store.create("brand_profiles", {"name": "Legacy Independent"})
            store.create("campaigns", {"brand_profile_id": legacy["id"], "title": "Legacy campaign"})
        server = create_server(db, root / "output", repo / "app" / "dist", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            fixture = {"base": f"http://127.0.0.1:{server.server_port}", "accounts": accounts, "legacyBrand": legacy["id"],
                       "screenshot": os.environ.get("CREATIVEOS_ACCEPTANCE_SCREENSHOT")}
            env = {**os.environ, "CREATIVEOS_ACCEPTANCE_FIXTURE": json.dumps(fixture)}
            result = subprocess.run(["node", str(repo / "app" / "tests" / "authenticated-acceptance.mjs")], env=env, timeout=180)
            if result.returncode:
                raise SystemExit(result.returncode)
            with CreativeOSStore(db) as store:
                assert store.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert not store.conn.execute("PRAGMA foreign_key_check").fetchall()
                assert store.conn.execute("SELECT count(*) FROM ownership_audit").fetchone()[0] == 1
                assert store.conn.execute("SELECT count(*) FROM export_jobs WHERE state='APPROVED'").fetchone()[0] == 2
                print("Database integrity, adoption audit, two approved exports: PASS")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    main()
