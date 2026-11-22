"""Accounts, sessions and failed logins, in the app's own SQLite file.

Email lives in n8n's data table; this file holds only who may log in.
"""

import sqlite3
import threading
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    pw_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL,
    last_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS login_failures (
    key TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS login_failures_key ON login_failures(key, at);
CREATE TABLE IF NOT EXISTS google_starts (
    state_hash TEXT PRIMARY KEY,
    verifier TEXT NOT NULL,
    nonce TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""
# Added after the first release: an existing users table gets the column on start.
GOOGLE_SUB = "ALTER TABLE users ADD COLUMN google_sub TEXT"
GOOGLE_SUB_INDEX = "CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub ON users(google_sub) WHERE google_sub IS NOT NULL"
NO_PASSWORD = "!"  # pw_hash of a Google-only account: no password ever matches it


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str
    pw_hash: str
    is_admin: bool
    active: bool
    google_sub: str | None = None

    @property
    def google_only(self) -> bool:
        return self.pw_hash == NO_PASSWORD


def normal_email(email: str) -> str:
    return email.strip().lower()


class Store:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)
            if "google_sub" not in {row["name"] for row in self._db.execute("PRAGMA table_info(users)")}:
                self._db.execute(GOOGLE_SUB)
            self._db.execute(GOOGLE_SUB_INDEX)

    def _run(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    @staticmethod
    def _user(row: sqlite3.Row | None) -> User | None:
        if row is None:
            return None
        return User(
            row["id"], row["email"], row["name"], row["pw_hash"], bool(row["is_admin"]), bool(row["active"]), row["google_sub"]
        )

    # users

    def add_user(self, email: str, name: str, pw_hash: str, is_admin: bool) -> int:
        try:
            with self._lock:
                cursor = self._db.execute(
                    "INSERT INTO users (email, name, pw_hash, is_admin) VALUES (?, ?, ?, ?)",
                    (normal_email(email), name.strip(), pw_hash, int(is_admin)),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"{normal_email(email)} already has an account") from error
        return cursor.lastrowid

    def user_by_email(self, email: str) -> User | None:
        rows = self._run("SELECT * FROM users WHERE email = ?", (normal_email(email),))
        return self._user(rows[0] if rows else None)

    def user_by_id(self, user_id: int) -> User | None:
        rows = self._run("SELECT * FROM users WHERE id = ?", (user_id,))
        return self._user(rows[0] if rows else None)

    def list_users(self) -> list[User]:
        return [self._user(r) for r in self._run("SELECT * FROM users ORDER BY name, email")]

    def user_by_google_sub(self, sub: str) -> User | None:
        rows = self._run("SELECT * FROM users WHERE google_sub = ?", (sub,))
        return self._user(rows[0] if rows else None)

    def link_google(self, user_id: int, sub: str) -> None:
        self._run("UPDATE users SET google_sub = ? WHERE id = ? AND google_sub IS NULL", (sub, user_id))

    def set_password(self, user_id: int, pw_hash: str) -> None:
        """New password; every session of that user ends."""
        self._run("UPDATE users SET pw_hash = ? WHERE id = ?", (pw_hash, user_id))
        self.end_sessions_of(user_id)

    def set_active(self, user_id: int, active: bool) -> None:
        self._run("UPDATE users SET active = ? WHERE id = ?", (int(active), user_id))
        if not active:
            self.end_sessions_of(user_id)

    # sessions

    def add_session(self, token_hash: str, user_id: int, now: float) -> None:
        self._run("INSERT INTO sessions VALUES (?, ?, ?, ?)", (token_hash, user_id, now, now))

    def session(self, token_hash: str) -> sqlite3.Row | None:
        rows = self._run("SELECT * FROM sessions WHERE token_hash = ?", (token_hash,))
        return rows[0] if rows else None

    def touch_session(self, token_hash: str, now: float) -> None:
        self._run("UPDATE sessions SET last_seen = ? WHERE token_hash = ?", (now, token_hash))

    def end_session(self, token_hash: str) -> None:
        self._run("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def end_sessions_of(self, user_id: int) -> None:
        self._run("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def dump_sessions(self) -> list[tuple]:
        return [tuple(r) for r in self._run("SELECT * FROM sessions")]

    # failed logins

    def add_failure(self, key: str, now: float) -> None:
        self._run("INSERT INTO login_failures VALUES (?, ?)", (key, now))

    def failures_since(self, key: str, since: float) -> int:
        return self._run("SELECT COUNT(*) FROM login_failures WHERE key = ? AND at > ?", (key, since))[0][0]

    def forget_failures(self, key: str) -> None:
        self._run("DELETE FROM login_failures WHERE key = ?", (key,))

    def prune(self, failures_before: float, sessions_before: float) -> None:
        """Drop failed logins, sessions and abandoned Google sign-ins too old to matter."""
        self._run("DELETE FROM login_failures WHERE at < ?", (failures_before,))
        self._run("DELETE FROM sessions WHERE created_at < ?", (sessions_before,))
        self._run("DELETE FROM google_starts WHERE created_at < ?", (failures_before,))

    # Google sign-in in progress: one row per click on "Continue with Google", used once

    def add_google_start(self, state_hash: str, verifier: str, nonce: str, now: float) -> None:
        self._run("INSERT INTO google_starts VALUES (?, ?, ?, ?)", (state_hash, verifier, nonce, now))

    def take_google_start(self, state_hash: str, since: float) -> tuple[str, str] | None:
        """(verifier, nonce) of a start made after `since`; the row is gone afterwards either way."""
        rows = self._run("DELETE FROM google_starts WHERE state_hash = ? RETURNING verifier, nonce, created_at", (state_hash,))
        if not rows or rows[0]["created_at"] <= since:
            return None
        return rows[0]["verifier"], rows[0]["nonce"]
