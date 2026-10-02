"""Same-origin authenticated server for loopback or explicit public-origin deployment."""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import sqlite3
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

from .creative_intelligence_api import ApplicationAPI
from .auth import AccessError, SESSION_SECONDS
from .store import CreativeOSStore


def create_server(
    db_path, output_root, dist_root, *, port=8000,
    bind_host="127.0.0.1", public_origin=None,
):
    api = ApplicationAPI(db_path, output_root)
    dist = Path(dist_root).resolve() if dist_root else None
    configured_origin = str(public_origin or "").rstrip("/")
    if configured_origin:
        parsed_origin = urlsplit(configured_origin)
        if parsed_origin.scheme not in {"http", "https"} or not parsed_origin.netloc:
            raise ValueError("public_origin must be an absolute http(s) origin")
        expected_host = parsed_origin.netloc
        secure_cookie = parsed_origin.scheme == "https"
    else:
        expected_host = None
        secure_cookie = False

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
                request_host = expected_host or f"127.0.0.1:{self.server.server_port}"
                request_origin = configured_origin or ("http://" + request_host)
                if self.headers.get("Host") != request_host:
                    raise AccessError("Invalid host")
                if self.command != "GET" and self.headers.get("Origin") != request_origin:
                    raise AccessError("Same-origin request required")
                if self.headers.get("Sec-Fetch-Site") not in {None, "same-origin", "none"}:
                    raise AccessError("Same-origin request required")
                path = urlsplit(self.path).path
                if path == "/health" and self.command == "GET":
                    with CreativeOSStore(db_path) as store:
                        return self.respond(200, {"status": "ok", "schema_version": store.schema_version()})
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
                    cookie_flags = "; Secure" if secure_cookie else ""
                    return self.respond(200, result, cookie=f"creativeos_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}{cookie_flags}")
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                token = cookie["creativeos_session"].value if "creativeos_session" in cookie else ""
                raw_version = self.headers.get("X-Scope-Version")
                version = int(raw_version) if raw_version is not None and raw_version.isdigit() else None
                result = api.dispatch(self.command, self.path, body, token, version, self.headers.get("X-CSRF-Token"))
                if isinstance(result, bytes):
                    return self.respond(200, result, "video/mp4")
                logout_flags = "; Secure" if secure_cookie else ""
                logout_cookie = f"creativeos_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{logout_flags}" if path == "/api/logout" else None
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

    server = ThreadingHTTPServer((bind_host, port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_origin = os.environ.get("CREATIVEOS_PUBLIC_ORIGIN")
    if not default_origin and os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
        default_origin = "https://" + os.environ["RAILWAY_PUBLIC_DOMAIN"]
    parser.add_argument("--db", default=os.environ.get("CREATIVEOS_DB_PATH"))
    parser.add_argument("--output", default=os.environ.get("CREATIVEOS_OUTPUT_ROOT"))
    parser.add_argument("--dist", default=os.environ.get("CREATIVEOS_DIST_ROOT"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--bind-host", default=os.environ.get("CREATIVEOS_BIND_HOST", "127.0.0.1"))
    parser.add_argument("--public-origin", default=default_origin)
    args = parser.parse_args()
    if not args.db or not args.output or not args.dist:
        parser.error("--db, --output and --dist (or their CREATIVEOS_* env vars) are required")
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).mkdir(parents=True, exist_ok=True)
    with CreativeOSStore(args.db) as store:
        if store.migrate_to_latest() != 13:
            parser.error("Database migration did not reach schema 13")
    server = create_server(
        args.db, args.output, args.dist, port=args.port,
        bind_host=args.bind_host, public_origin=args.public_origin,
    )
    origin = args.public_origin or f"http://{args.bind_host}:{server.server_port}"
    print(f"CreativeOS authenticated workspace: {origin}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
