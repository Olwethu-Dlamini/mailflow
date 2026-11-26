"""Secrets the app has to keep itself (the SMTP password of a mailbox), sealed with MAILFLOW_SECRET_KEY.

The key lives in the server's .env and the sealed values in the app's SQLite file, so a copy of the
database alone reveals no password. Lose or change the key and the passwords must be entered again.
Everything else an admin enters (IMAP passwords, AI keys, the Telegram token) goes to n8n, which
keeps its own credentials encrypted; the app never stores those.
"""

from cryptography.fernet import Fernet, InvalidToken


class VaultLocked(Exception):
    """No key is set, or a value was sealed with another key; the message is for people."""


def valid_key(key: str) -> bool:
    try:
        Fernet(key.encode())
    except ValueError:
        return False
    return True


class Vault:
    def __init__(self, key: str):
        self._fernet = Fernet(key.encode()) if key else None

    @property
    def ready(self) -> bool:
        return self._fernet is not None

    def _need(self) -> Fernet:
        if self._fernet is None:
            raise VaultLocked("MAILFLOW_SECRET_KEY is not set on the server, so the app cannot keep passwords.")
        return self._fernet

    def seal(self, text: str) -> bytes:
        return self._need().encrypt(text.encode())

    def open(self, sealed: bytes) -> str:
        try:
            return self._need().decrypt(sealed).decode()
        except InvalidToken:
            raise VaultLocked(
                "The saved SMTP password was sealed with another MAILFLOW_SECRET_KEY: enter it again."
            ) from None
