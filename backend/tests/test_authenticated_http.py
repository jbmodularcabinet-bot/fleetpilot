import http.cookiejar
import json
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from test_authenticated_scope import AuthFixture
from creativeos_db.server import create_server


class HTTPBoundaryTests(AuthFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = create_server(self.db, Path(self.tmp.name) / "output", None, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.cookies = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def send(self, method, path, body=None, headers=None, client=None):
        request = urllib.request.Request(self.base + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Origin": self.base, "Content-Type": "application/json", **(headers or {})})
        try:
            with (client or self.client).open(request) as response:
                data = response.read()
                return response.status, json.loads(data) if response.headers.get_content_type() == "application/json" else data, response.headers
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read()), error.headers

    def login(self):
        status, state, headers = self.send("POST", "/api/login", {"username": "alice", "password": "test-password-only-123"})
        self.assertEqual(status, 200)
        self.assertNotIn("token", state)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        return state

    def test_cookie_origin_csrf_and_scope_boundary(self):
        self.assertEqual(self.send("GET", "/api/workspace")[0], 401)
        self.assertEqual(self.send("POST", "/api/login", {}, {"Origin": "https://evil.invalid"})[0], 403)
        state = self.login()
        headers = {"X-Scope-Version": str(state["version"]), "X-CSRF-Token": state["csrf"]}
        body = {"organization_id": self.orgs[0]["id"], "brand_profile_id": self.brands[0]["id"]}
        self.assertEqual(self.send("POST", "/api/context", body, {"X-Scope-Version": "0"})[0], 403)
        status, scoped, _ = self.send("POST", "/api/context", body, headers)
        self.assertEqual(status, 200)
        self.assertEqual(self.send("GET", "/api/workspace", headers=headers)[0], 409)
        headers["X-Scope-Version"] = str(scoped["version"])
        self.assertEqual(self.send("GET", "/api/workspace", headers=headers)[0], 200)
        self.assertEqual(self.send("GET", "/api/workspace", headers={**headers, "Host": "evil.invalid"})[0], 403)
        self.assertEqual(self.send("POST", "/api/campaigns", {"title": "a"}, {**headers, "Origin": "https://evil.invalid"})[0], 403)
        self.assertEqual(self.send("POST", "/api/logout", {}, headers)[0], 200)
        self.assertEqual(self.send("GET", "/api/session")[0], 401)

    def test_no_static_access_to_database_or_output_and_no_raw_errors(self):
        self.assertEqual(self.send("GET", "/output/private.mp4")[0], 404)
        self.assertEqual(self.send("GET", "/../../auth.sqlite3")[0], 404)
        state = self.login()
        headers = {"X-Scope-Version": "0", "X-CSRF-Token": state["csrf"]}
        status, error, _ = self.send("POST", "/api/context", {"organization_id": "forged", "brand_profile_id": "forged"}, headers)
        self.assertEqual(status, 403)
        self.assertNotIn(str(self.db), json.dumps(error))
