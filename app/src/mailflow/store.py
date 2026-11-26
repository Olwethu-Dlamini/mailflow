"""Accounts, sessions and failed logins, the team's own notes on each email (who has it, who did
what), and what admins connected (mailboxes, copies of n8n workflows before a change), in the app's
own SQLite file.

The email itself lives in n8n's data table; rows here refer to it by its row id.
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
CREATE TABLE IF NOT EXISTS assignments (
    row_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY,
    row_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id),
    at REAL NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS activity_row ON activity(row_id, at);
CREATE TABLE IF NOT EXISTS mailboxes (
    label TEXT PRIMARY KEY,
    workflow_id TEXT,      -- the collector the app made in n8n (NULL: made by hand in n8n)
    credential_id TEXT,    -- its IMAP credential in n8n
    smtp TEXT,             -- JSON (mailer.Smtp) when replies leave over SMTP, else NULL
    smtp_secret BLOB,      -- that SMTP password, sealed (vault.py)
    updated_by INTEGER REFERENCES users(id),
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS n8n_backups (
    id INTEGER PRIMARY KEY,
    at REAL NOT NULL,
    workflow_id TEXT NOT NULL,
    body TEXT NOT NULL,    -- the workflow as n8n returned it, before the app changed it
    by INTEGER REFERENCES users(id)
);
"""
NOTES_SECONDS = 120 * 24 * 3600  # n8n deletes emails after 90 days; notes on them go a month later
# Added after the first release: an existing users table gets the column on start.
GOOGLE_SUB = "ALTER TABLE users ADD COLUMN google_sub TEXT"
GOOGLE_SUB_INDEX = "CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub ON users(google_sub) WHERE google_sub IS NOT NULL"
NO_PASSWORD = "!"  # pw_hash of a Google-only account: no password ever matches it
BACKUPS_KEPT = 50


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

    def prune(self, failures_before: float, sessions_before: float, notes_before: float) -> None:
        """Drop failed logins, sessions, abandoned Google sign-ins and notes too old to matter."""
        self._run("DELETE FROM login_failures WHERE at < ?", (failures_before,))
        self._run("DELETE FROM sessions WHERE created_at < ?", (sessions_before,))
        self._run("DELETE FROM google_starts WHERE created_at < ?", (failures_before,))
        self._run("DELETE FROM assignments WHERE at < ?", (notes_before,))
        self._run("DELETE FROM activity WHERE at < ?", (notes_before,))

    # who has which email, and what was done to it

    def assignments(self) -> dict[int, int]:
        return {row["row_id"]: row["user_id"] for row in self._run("SELECT row_id, user_id FROM assignments")}

    def assignee(self, row_id: int) -> int | None:
        rows = self._run("SELECT user_id FROM assignments WHERE row_id = ?", (row_id,))
        return rows[0]["user_id"] if rows else None

    def set_assignee(self, row_id: int, user_id: int | None, now: float, expected: int | None) -> bool:
        """Give the email to `user_id` (None: nobody), only if `expected` still has it (None: nobody
        did); False when someone changed it in between, and then nothing is written."""
        with self._lock:
            if expected is None and user_id is not None:
                cursor = self._db.execute(
                    "INSERT INTO assignments VALUES (?, ?, ?) ON CONFLICT(row_id) DO NOTHING", (row_id, user_id, now))
            elif user_id is None:
                cursor = self._db.execute("DELETE FROM assignments WHERE row_id = ? AND user_id = ?", (row_id, expected))
            else:
                cursor = self._db.execute(
                    "UPDATE assignments SET user_id = ?, at = ? WHERE row_id = ? AND user_id = ?", (user_id, now, row_id, expected))
            return cursor.rowcount == 1

    def add_activity(self, row_id: int, user_id: int, text: str, now: float) -> None:
        self._run("INSERT INTO activity (row_id, user_id, at, text) VALUES (?, ?, ?, ?)", (row_id, user_id, now, text))

    def activity(self, row_id: int, limit: int = 50) -> list[dict]:
        """Newest first, with the name of whoever did it."""
        rows = self._run(
            "SELECT a.at, a.text, u.name FROM activity a JOIN users u ON u.id = a.user_id"
            " WHERE a.row_id = ? ORDER BY a.at DESC, a.id DESC LIMIT ?",
            (row_id, limit),
        )
        return [{"at": row["at"], "name": row["name"], "text": row["text"]} for row in rows]

    # what admins connected

    def mailboxes(self) -> dict[str, dict]:
        return {row["label"]: dict(row) for row in self._run("SELECT * FROM mailboxes")}

    def mailbox(self, label: str) -> dict | None:
        rows = self._run("SELECT * FROM mailboxes WHERE label = ?", (label,))
        return dict(rows[0]) if rows else None

    def save_collector(self, label: str, workflow_id: str, credential_id: str, by: int, now: float) -> None:
        self._run(
            "INSERT INTO mailboxes (label, workflow_id, credential_id, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(label) DO UPDATE SET workflow_id = excluded.workflow_id, credential_id = excluded.credential_id,"
            " updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (label, workflow_id, credential_id, by, now),
        )

    def save_smtp(self, label: str, smtp_json: str, sealed: bytes, by: int, now: float) -> None:
        self._run(
            "INSERT INTO mailboxes (label, smtp, smtp_secret, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(label) DO UPDATE SET smtp = excluded.smtp, smtp_secret = excluded.smtp_secret,"
            " updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (label, smtp_json, sealed, by, now),
        )

    def drop_smtp(self, label: str) -> None:
        self._run("UPDATE mailboxes SET smtp = NULL, smtp_secret = NULL WHERE label = ?", (label,))
        self._run("DELETE FROM mailboxes WHERE label = ? AND workflow_id IS NULL", (label,))

    def drop_mailbox(self, label: str) -> None:
        self._run("DELETE FROM mailboxes WHERE label = ?", (label,))

    def smtp_labels(self) -> list[str]:
        return [row["label"] for row in self._run("SELECT label FROM mailboxes WHERE smtp IS NOT NULL ORDER BY label")]

    def backup_workflow(self, workflow_id: str, body: str, by: int, now: float) -> None:
        """Keep the workflow as it was before a change; only the last BACKUPS_KEPT are kept."""
        self._run("INSERT INTO n8n_backups (at, workflow_id, body, by) VALUES (?, ?, ?, ?)", (now, workflow_id, body, by))
        self._run("DELETE FROM n8n_backups WHERE id NOT IN (SELECT id FROM n8n_backups ORDER BY id DESC LIMIT ?)", (BACKUPS_KEPT,))

    def backups(self, workflow_id: str) -> list[dict]:
        rows = self._run("SELECT at, body, by FROM n8n_backups WHERE workflow_id = ? ORDER BY id DESC", (workflow_id,))
        return [dict(row) for row in rows]

    # Google sign-in in progress: one row per click on "Continue with Google", used once

    def add_google_start(self, state_hash: str, verifier: str, nonce: str, now: float) -> None:
        self._run("INSERT INTO google_starts VALUES (?, ?, ?, ?)", (state_hash, verifier, nonce, now))

    def take_google_start(self, state_hash: str, since: float) -> tuple[str, str] | None:
        """(verifier, nonce) of a start made after `since`; the row is gone afterwards either way."""
        rows = self._run("DELETE FROM google_starts WHERE state_hash = ? RETURNING verifier, nonce, created_at", (state_hash,))
        if not rows or rows[0]["created_at"] <= since:
            return None
        return rows[0]["verifier"], rows[0]["nonce"]
