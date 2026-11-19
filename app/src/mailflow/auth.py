"""Passwords, login with lockout, and sessions.

The page is on the internet, so:
- passwords are stored as salted scrypt hashes and must be at least MIN_PASSWORD long;
- LOCK_AFTER failed logins for one email (existing or not) lock it for LOCK_SECONDS, and IP_LIMIT
  failures from one client address block that address for the same time;
- an unknown email and a wrong password get the same answer and take about as long;
- a session is a random token; only its SHA-256 is stored. It ends IDLE_SECONDS after its last use,
  MAX_SECONDS after login, at logout, or when the user's password changes or the user is disabled.
"""

import base64
import hashlib
import hmac
import secrets

from .store import Store, User, normal_email

MIN_PASSWORD = 12
LOCK_AFTER = 5
IP_LIMIT = 20
LOCK_SECONDS = 15 * 60
IDLE_SECONDS = 12 * 3600
MAX_SECONDS = 7 * 24 * 3600
TOUCH_EVERY = 60  # write last_seen at most once a minute per session

_N, _R, _P = 2**14, 8, 1
REFUSED = "Wrong email or password."
LOCKED = "Too many failed logins. Try again in 15 minutes."


class LoginRefused(Exception):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        name, n, r, p, salt, digest = stored.split("$")
        if name != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


_DUMMY_HASH = hash_password(secrets.token_hex(16))


def check_password_rule(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"The password needs at least {MIN_PASSWORD} characters.")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_not_locked(store: Store, email_key: str, ip_key: str, now: float) -> None:
    since = now - LOCK_SECONDS
    if store.failures_since(email_key, since) >= LOCK_AFTER or store.failures_since(ip_key, since) >= IP_LIMIT:
        raise LoginRefused(LOCKED)


def _fail(store: Store, email_key: str, ip_key: str, now: float) -> None:
    store.add_failure(email_key, now)
    store.add_failure(ip_key, now)


def login(store: Store, email: str, password: str, client_ip: str, now: float) -> tuple[str, User]:
    """Returns (session token, user) or raises LoginRefused."""
    email = normal_email(email)
    email_key, ip_key = f"email:{email}", f"ip:{client_ip}"
    store.prune(failures_before=now - 24 * 3600, sessions_before=now - MAX_SECONDS)
    _check_not_locked(store, email_key, ip_key, now)

    user = store.user_by_email(email)
    ok = verify_password(password, user.pw_hash if user else _DUMMY_HASH)
    if not (user and ok and user.active):
        _fail(store, email_key, ip_key, now)
        raise LoginRefused(REFUSED)

    store.forget_failures(email_key)
    token = secrets.token_urlsafe(32)
    store.add_session(_token_hash(token), user.id, now)
    return token, user


def check_current_password(store: Store, user: User, password: str, client_ip: str, now: float) -> None:
    """Before a password change. Wrong guesses count toward the same lockout as logins, so a
    left-open session cannot be used to try passwords without limit."""
    email_key, ip_key = f"email:{user.email}", f"ip:{client_ip}"
    _check_not_locked(store, email_key, ip_key, now)
    if not verify_password(password, user.pw_hash):
        _fail(store, email_key, ip_key, now)
        raise LoginRefused("The current password is wrong.")


def session_user(store: Store, token: str, now: float) -> User | None:
    if not token:
        return None
    key = _token_hash(token)
    session = store.session(key)
    if session is None:
        return None
    if now - session["last_seen"] > IDLE_SECONDS or now - session["created_at"] > MAX_SECONDS:
        store.end_session(key)
        return None
    user = store.user_by_id(session["user_id"])
    if user is None or not user.active:
        store.end_session(key)
        return None
    if now - session["last_seen"] > TOUCH_EVERY:
        store.touch_session(key, now)
    return user


def logout(store: Store, token: str) -> None:
    if token:
        store.end_session(_token_hash(token))
