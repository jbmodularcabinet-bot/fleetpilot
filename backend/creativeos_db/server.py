"""Loopback-only same-origin server. This is not a production/public deployment."""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import sqlite3
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

from .creative_intelligence_api import ApplicationAPI
from .auth import AccessError, SESSION_SECONDS
from .store import CreativeOSStore


def create_server(db_path, output_root, dist_root, *, port=8000):
    api = ApplicationAPI(db_path, output_root)
    dist = Path(dist_root).resolve() if dist_root else None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, value, content_type="application/json", cookie=None):
            data = json.dumps(value).encode() if content_type == "application/json" else value
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(data)

        def handle_request(self):
            try:
                expected_host = f"127.0.0.1:{self.server.server_port}"
                origin = "http://" + expected_host
                if self.headers.get("Host") != expected_host:
                    raise AccessError("Invalid host")
                if self.command != "GET" and self.headers.get("Origin") != origin:
                    raise AccessError("Same-origin request required")
                if self.headers.get("Sec-Fetch-Site") not in {None, "same-origin", "none"}:
                    raise AccessError("Same-origin request required")
                path = urlsplit(self.path).path
                if not path.startswith("/api/"):
                    if self.command != "GET" or dist is None:
                        raise KeyError()
                    relative = unquote(path).lstrip("/") or "index.html"
                    candidate = (dist / relative).resolve()
                    if dist not in candidate.parents or not candidate.is_file():
                        raise KeyError()
                    return self.respond(200, candidate.read_bytes(), mimetypes.guess_type(str(candidate))[0] or "application/octet-stream")
                body = {}
                if self.command == "POST":
                    if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
                        raise ValueError("JSON body required")
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= length <= 65536:
                        raise ValueError("Request body too large")
                    body = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(body, dict):
                        raise ValueError("JSON object required")
                if self.command == "POST" and path == "/api/login":
                    result = api.auth.login(body.get("username", ""), body.get("password", ""))
                    token = result.pop("token")
                    return self.respond(200, result, cookie=f"creativeos_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}")
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                token = cookie["creativeos_session"].value if "creativeos_session" in cookie else ""
                raw_version = self.headers.get("X-Scope-Version")
                version = int(raw_version) if raw_version is not None and raw_version.isdigit() else None
                result = api.dispatch(self.command, self.path, body, token, version, self.headers.get("X-CSRF-Token"))
                if isinstance(result, bytes):
                    return self.respond(200, result, "video/mp4")
                logout_cookie = "creativeos_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" if path == "/api/logout" else None
                self.respond(200, result, cookie=logout_cookie)
            except AccessError as error:
                self.respond(error.status, {"error": str(error), "code": error.code})
            except PermissionError:
                self.respond(403, {"error": "Record is not authorized in the active workspace", "code": "FORBIDDEN"})
            except KeyError:
                self.respond(404, {"error": "Not found", "code": "NOT_FOUND"})
            except (ValueError, TypeError):
                self.respond(400, {"error": "Invalid request or workflow state", "code": "INVALID_REQUEST"})
            except sqlite3.IntegrityError:
                self.respond(409, {"error": "Record conflict; refresh before continuing", "code": "CONFLICT"})
            except Exception:
                logging.exception("Authenticated request failed")
                self.respond(500, {"error": "Operation failed; refresh current state", "code": "INTERNAL_ERROR"})

        do_GET = handle_request
        do_POST = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dist", required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with CreativeOSStore(args.db) as store:
        if store.schema_version() != 13:
            parser.error("Migrate and verify the database to schema 13 before starting")
    server = create_server(args.db, args.output, args.dist, port=args.port)
    print(f"CreativeOS local authenticated workspace: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
