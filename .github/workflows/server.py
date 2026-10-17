#!/usr/bin/env python3
"""
KIT Services — landing page server + client auth API.

Standard-library HTTP server backed by a SQLite database
(users + sessions tables). Passwords hashed with bcrypt.
Requires the system `bcrypt` module (`python3-bcrypt` on Debian/Ubuntu).

Run:  python3 server.py            # -> http://127.0.0.1:8000
Env:  HOST=0.0.0.0 PORT=8000 DB_PATH=kit_services.db
"""

import json
import mimetypes
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import bcrypt

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DB_PATH = Path(os.environ.get("DB_PATH", str(ROOT / "kit_services.db")))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

SESSION_COOKIE = "kit_session"
SESSION_TTL = 7 * 24 * 3600          # 7 days
MAX_BODY = 64 * 1024                 # 64 KiB request cap
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

_bcrypt_lock = threading.Lock()
_db_lock = threading.Lock()


# --------------------------------------------------------------------------
# Database layer
# --------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    _db_lock.acquire()
    try:
        conn = get_db()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user  ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
            """
        )
        conn.commit()
        conn.close()
    finally:
        _db_lock.release()


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_user(name, email, password):
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    with _db_lock:
        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, email, pw_hash.decode("ascii"), utcnow()),
            )
            conn.commit()
            user_id = cur.lastrowid
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()
    return user_id


def find_user_by_email(email):
    with _db_lock:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)
        ).fetchone()
        conn.close()
    return dict(row) if row else None


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    with _db_lock:
        conn = get_db()
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, utcnow(), int(time.time()) + SESSION_TTL),
        )
        conn.commit()
        conn.close()
    return token


def user_for_token(token):
    if not token:
        return None
    with _db_lock:
        conn = get_db()
        row = conn.execute(
            "SELECT u.id, u.name, u.email FROM sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > ?",
            (token, int(time.time())),
        ).fetchone()
        conn.close()
    return dict(row) if row else None


def delete_session(token):
    if not token:
        return
    with _db_lock:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()


def touch_last_login(user_id):
    with _db_lock:
        conn = get_db()
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utcnow(), user_id))
        conn.commit()
        conn.close()


def count_members():
    with _db_lock:
        conn = get_db()
        n = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        conn.close()
    return n


def check_password(user, password):
    with _bcrypt_lock:
        return bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("ascii"))


# --------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------

class KitHandler(BaseHTTPRequestHandler):
    server_version = "KIT-Server/1.0"

    # -- helpers -----------------------------------------------------------
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _send(self, status, payload, content_type="application/json", extra_headers=()):
        body = payload.encode("utf-8") if isinstance(payload, str) else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        for name, value in extra_headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=HTTPStatus.OK, extra_headers=()):
        self._send(status, json.dumps(obj), extra_headers=extra_headers)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            return None
        return self.rfile.read(length)

    def _get_cookie(self, name):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return None
        morsel = cookie.get(name)
        return morsel.value if morsel else None

    def _session_user(self):
        token = self._get_cookie(SESSION_COOKIE)
        return user_for_token(token)

    # -- routing ------------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/me":
            self._api_me()
        elif path == "/api/stats":
            self._api_stats()
        elif path.startswith("/api/"):
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        else:
            self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/signup":
            self._api_signup()
        elif path == "/api/login":
            self._api_login()
        elif path == "/api/logout":
            self._api_logout()
        else:
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    # -- API endpoints -------------------------------------------------------
    def _api_me(self):
        user = self._session_user()
        if not user:
            self._json({"user": None})
            return
        self._json({"user": dict(user)})

    def _api_stats(self):
        self._json({"members": count_members()})

    def _api_signup(self):
        body = self._read_body()
        if body is None:
            self._json({"error": "Request body missing or too large."}, HTTPStatus.BAD_REQUEST)
            return

        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json({"error": "Malformed JSON payload."}, HTTPStatus.BAD_REQUEST)
            return

        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))

        if not (2 <= len(name) <= 80):
            self._json({"error": "Name must be between 2 and 80 characters."}, HTTPStatus.BAD_REQUEST)
            return
        if not EMAIL_RE.match(email) or len(email) > 254:
            self._json({"error": "Provide a valid e-mail address."}, HTTPStatus.BAD_REQUEST)
            return
        if len(password) < 8 or len(password) > 72:
            self._json({"error": "Access key must be 8–72 characters."}, HTTPStatus.BAD_REQUEST)
            return

        user_id = create_user(name, email, password)
        if user_id is None:
            self._json({"error": "That e-mail is already registered in the grid."}, HTTPStatus.CONFLICT)
            return

        token = create_session(user_id)
        user = {"id": user_id, "name": name, "email": email}
        self._json(
            {"user": user, "message": "Identity registered."},
            HTTPStatus.CREATED,
            extra_headers=[self._set_session_cookie(token)],
        )

    def _api_login(self):
        body = self._read_body()
        if body is None:
            self._json({"error": "Request body missing or too large."}, HTTPStatus.BAD_REQUEST)
            return

        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json({"error": "Malformed JSON payload."}, HTTPStatus.BAD_REQUEST)
            return

        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))

        user = find_user_by_email(email)
        if not user or not check_password(user, password):
            self._json(
                {"error": "Invalid credentials — check your e-mail and access key."},
                HTTPStatus.UNAUTHORIZED,
            )
            return

        token = create_session(user["id"])
        touch_last_login(user["id"])
        self._json(
            {"user": {"id": user["id"], "name": user["name"], "email": user["email"]}},
            extra_headers=[self._set_session_cookie(token)],
        )

    def _api_logout(self):
        token = self._get_cookie(SESSION_COOKIE)
        delete_session(token)
        cookie = SimpleCookie()
        cookie[SESSION_COOKIE] = ""
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["max-age"] = 0
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "lax"
        self._json({}, extra_headers=[("Set-Cookie", cookie[SESSION_COOKIE].OutputString())])

    def _set_session_cookie(self, token):
        cookie = SimpleCookie()
        cookie[SESSION_COOKIE] = token
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["max-age"] = SESSION_TTL
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "lax"
        return ("Set-Cookie", cookie[SESSION_COOKIE].OutputString())

    # -- static files ---------------------------------------------------------
    def _serve_static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        rel = Path(unquote_safe(path.lstrip("/")))
        file_path = (PUBLIC / rel).resolve()

        if not file_path.is_relative_to(PUBLIC.resolve()) or not file_path.is_file():
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        ctype, _ = mimetypes.guess_type(str(file_path))
        if ctype is None:
            ctype = "application/octet-stream"
        ctype = ctype + ("; charset=utf-8" if ctype.startswith("text/") else "")

        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def unquote_safe(value):
    from urllib.parse import unquote

    return unquote(value)


def main():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), KitHandler)
    print("=" * 60)
    print("  KIT SERVICES — grid uplink active")
    print(f"  Listening : http://127.0.0.1:{PORT}")
    print(f"  Database  : {DB_PATH}")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nChannel closing.")
        server.server_close()


if __name__ == "__main__":
    main()