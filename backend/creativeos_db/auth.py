from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4

from .store import CreativeOSStore, now_iso

ITERATIONS = 600_000
SESSION_SECONDS = 8 * 60 * 60


class AccessError(PermissionError):
    def __init__(self, message="Access denied", status=403, code="FORBIDDEN"):
        super().__init__(message)
        self.status, self.code = status, code


def token_hash(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"{salt}:{digest}"


class RequestConnection:
    """Keep service commits inside one authorized, serialized request transaction."""
    def __init__(self, raw):
        self.raw = raw
        self.depth = 0
        self.failed = False

    def execute(self, sql, parameters=()):
        if sql.strip().upper().startswith("BEGIN"):
            self.depth += 1
            return self.raw.execute(f"SAVEPOINT service_{self.depth}")
        return self.raw.execute(sql, parameters)

    def commit(self):
        if self.depth:
            self.raw.execute(f"RELEASE SAVEPOINT service_{self.depth}")
            self.depth -= 1

    def rollback(self):
        if self.depth:
            self.raw.execute(f"ROLLBACK TO SAVEPOINT service_{self.depth}")
            self.raw.execute(f"RELEASE SAVEPOINT service_{self.depth}")
            self.depth -= 1
        else:
            self.failed = True
            self.raw.rollback()

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self.raw, name)


@dataclass(frozen=True)
class RequestContext:
    user_id: str
    organization_id: str
    brand_profile_id: str
    role: str
    platform_admin: bool
    version: int
    session_hash: str
    store: CreativeOSStore


class AuthService:
    def __init__(self, db_path):
        self.db_path = str(db_path)

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def provision_user(self, username, password, *, is_platform_admin=False):
        username = str(username).strip().lower()
        if not username or len(username) > 120 or not 12 <= len(password) <= 256:
            raise ValueError("Username and a password of 12-256 characters are required")
        user_id = str(uuid4())
        conn = self.connect()
        try:
            with conn:
                conn.execute("INSERT INTO auth_users VALUES(?,?,?,?,?,?)",
                    (user_id, username, password_hash(password), int(is_platform_admin), 1, now_iso()))
            return {"id": user_id, "username": username}
        finally:
            conn.close()

    def grant_membership(self, user_id, organization_id, role):
        if role not in {"OWNER", "EDITOR", "VIEWER"}:
            raise ValueError("Invalid membership role")
        conn = self.connect()
        try:
            with conn:
                conn.execute("""INSERT INTO organization_memberships VALUES(?,?,?,1,1)
                    ON CONFLICT(user_id,organization_id) DO UPDATE
                    SET role=excluded.role,active=1,version=organization_memberships.version+1""",
                    (user_id, organization_id, role))
        finally:
            conn.close()

    def revoke_membership(self, user_id, organization_id):
        conn = self.connect()
        try:
            with conn:
                conn.execute("""UPDATE organization_memberships SET active=0,version=version+1
                    WHERE user_id=? AND organization_id=?""", (user_id, organization_id))
        finally:
            conn.close()

    def login(self, username, password):
        username = str(username).strip().lower()
        if not isinstance(password, str) or len(password) > 256:
            raise AccessError("Invalid credentials", 401, "UNAUTHENTICATED")
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            attempt = conn.execute("SELECT * FROM login_attempts WHERE username=?", (username,)).fetchone()
            now = int(time.time())
            if attempt and attempt["failures"] >= 5 and now - attempt["last_attempt"] < 300:
                raise AccessError("Try signing in again later", 429, "RATE_LIMITED")
            user = conn.execute("SELECT * FROM auth_users WHERE username=?", (username,)).fetchone()
            encoded = user["password_hash"] if user else ("00" * 16 + ":" + "00" * 32)
            actual = password_hash(password, encoded.split(":")[0])
            if not hmac.compare_digest(actual, encoded) or not user or not user["enabled"]:
                count = attempt["failures"] + 1 if attempt and now - attempt["last_attempt"] < 300 else 1
                conn.execute("INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)", (username, count, now))
                conn.commit()
                raise AccessError("Invalid credentials", 401, "UNAUTHENTICATED")
            conn.execute("DELETE FROM login_attempts WHERE username=?", (username,))
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            conn.execute("INSERT INTO auth_sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)",
                         (token_hash(token), user["id"], csrf, now + SESSION_SECONDS))
            conn.commit()
            return {"token": token, "csrf": csrf, **self.session(token)}
        finally:
            conn.close()

    def _session(self, conn, token):
        row = conn.execute("""SELECT s.*,u.username,u.platform_admin,u.enabled
            FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id WHERE token_hash=?""",
            (token_hash(token),)).fetchone()
        if not row or not row["enabled"] or row["expires_at"] <= int(time.time()):
            raise AccessError("Sign in required", 401, "UNAUTHENTICATED")
        return dict(row)

    def _membership(self, conn, user_id, organization_id):
        row = conn.execute("""SELECT * FROM organization_memberships
            WHERE user_id=? AND organization_id=? AND active=1""", (user_id, organization_id)).fetchone()
        if not row:
            raise AccessError("Organization membership required", 403, "MEMBERSHIP_REVOKED")
        return dict(row)

    def _csrf(self, session, csrf):
        if not isinstance(csrf, str) or not hmac.compare_digest(session["csrf"], csrf):
            raise AccessError("Invalid request confirmation", 403, "CSRF")

    def _version(self, session, expected):
        if type(expected) is not int or session["version"] != expected:
            raise AccessError("Workspace changed; reload current context", 409, "STALE_SCOPE")

    def _validate_scope(self, conn, session, require_brand=True):
        if not session["organization_id"] or (require_brand and not session["brand_profile_id"]):
            raise AccessError("Select an organization and brand", 409, "SCOPE_REQUIRED")
        membership = self._membership(conn, session["user_id"], session["organization_id"])
        if membership["version"] != session["membership_version"]:
            raise AccessError("Membership changed; select context again", 409, "STALE_SCOPE")
        if not session["brand_profile_id"]:
            return membership
        brand = conn.execute("SELECT organization_id FROM brand_profiles WHERE id=?",
                             (session["brand_profile_id"],)).fetchone()
        if not brand or brand["organization_id"] != session["organization_id"]:
            raise AccessError("Brand does not belong to the selected organization", 403, "INVALID_BRAND")
        return membership

    def _public(self, conn, session):
        organizations = [dict(r) for r in conn.execute("""SELECT o.id,o.name,o.classification,m.role
            FROM organizations o JOIN organization_memberships m ON m.organization_id=o.id
            WHERE m.user_id=? AND m.active=1 ORDER BY o.name""", (session["user_id"],))]
        scope = None
        if session["organization_id"]:
            scope = {"organization_id": session["organization_id"], "brand_profile_id": session["brand_profile_id"]}
        return {"user": {"id": session["user_id"], "username": session["username"],
                         "platform_admin": bool(session["platform_admin"])},
                "organizations": organizations, "scope": scope,
                "version": session["version"], "csrf": session["csrf"]}

    def session(self, token):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            session = self._session(conn, token)
            if session["organization_id"]:
                try:
                    membership = self._membership(conn, session["user_id"], session["organization_id"])
                    if membership["version"] != session["membership_version"]:
                        raise AccessError()
                    if session["brand_profile_id"]:
                        self._validate_scope(conn, session)
                except AccessError:
                    conn.execute("""UPDATE auth_sessions SET organization_id=NULL,brand_profile_id=NULL,
                        membership_version=NULL,version=version+1 WHERE token_hash=?""", (session["token_hash"],))
                    session = self._session(conn, token)
            result = self._public(conn, session)
            conn.commit()
            return result
        finally:
            conn.close()

    def brands(self, token, organization_id):
        conn = self.connect()
        try:
            conn.execute("BEGIN")
            session = self._session(conn, token)
            self._membership(conn, session["user_id"], organization_id)
            return [dict(r) for r in conn.execute("""SELECT id,name,entity_type FROM brand_profiles
                WHERE organization_id=? ORDER BY name""", (organization_id,))]
        finally:
            conn.close()

    def select_scope(self, token, csrf, expected_version, organization_id, brand_profile_id):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            session = self._session(conn, token)
            self._csrf(session, csrf)
            self._version(session, expected_version)
            member = self._membership(conn, session["user_id"], organization_id)
            if brand_profile_id is not None:
                row = conn.execute("SELECT organization_id FROM brand_profiles WHERE id=?", (brand_profile_id,)).fetchone()
                if not row or row["organization_id"] != organization_id:
                    raise AccessError("Brand does not belong to organization", 403, "INVALID_BRAND")
            conn.execute("""UPDATE auth_sessions SET organization_id=?,brand_profile_id=?,
                membership_version=?,version=version+1 WHERE token_hash=?""",
                (organization_id, brand_profile_id, member["version"], session["token_hash"]))
            result = self._public(conn, self._session(conn, token))
            conn.commit()
            return result
        finally:
            conn.close()

    def logout(self, token, csrf):
        conn = self.connect()
        try:
            with conn:
                session = self._session(conn, token)
                self._csrf(session, csrf)
                conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (session["token_hash"],))
        finally:
            conn.close()

    @contextmanager
    def request(self, token, *, expected_version, csrf=None, write=False, require_brand=True):
        store = CreativeOSStore(self.db_path)
        raw = store.conn
        try:
            raw.execute("PRAGMA busy_timeout=60000")
            raw.execute("BEGIN IMMEDIATE")
            session = self._session(raw, token)
            if write:
                self._csrf(session, csrf)
            self._version(session, expected_version)
            member = self._validate_scope(raw, session, require_brand)
            if write and member["role"] not in {"OWNER", "EDITOR"}:
                raise AccessError("Write membership required")
            store.scope = (session["organization_id"], session["brand_profile_id"])
            connection = RequestConnection(raw)
            store.conn = connection
            yield RequestContext(session["user_id"], *store.scope, member["role"],
                                 bool(session["platform_admin"]), session["version"], session["token_hash"], store)
            if connection.failed or connection.depth:
                raise RuntimeError("Request transaction was not completed")
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
