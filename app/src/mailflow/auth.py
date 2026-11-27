"""Passwords, login with lockout, and sessions.

The page is on the internet, so:
- passwords are stored as salted scrypt hashes and must be at least MIN_PASSWORD long;
- LOCK_AFTER failed logins for one email (existing or not) lock it for LOCK_SECONDS, and IP_LIMIT
  failures from one client address (an IPv6 /64 counts as one) block that address for the same time;
  an attempt is counted before its password is checked, so attempts sent at once cannot get past;
- at most HASH_SLOTS passwords are checked at a time (scrypt needs 16 MiB each, the container 128 MB);
- an unknown email and a wrong password get the same answer and take about as long;
- a session is a random token; only its SHA-256 is stored. It ends IDLE_SECONDS after its last use,
  MAX_SECONDS after login, at logout, or when the user's password changes or the user is disabled.
- "Continue with Google" opens a session only for an existing, active account: matched on Google's
  account id once linked, else on the verified email (which links it) when Google is the authority
  for that address (Gmail, or a Workspace domain the token names). No account is ever created.
"""

import base64
import hashlib
import hmac
import ipaddress
import secrets
import threading
from contextlib import contextmanager

from .google import Identity
from .store import NOTES_SECONDS, Store, User, normal_email

MIN_PASSWORD = 12
LOCK_AFTER = 5
IP_LIMIT = 20
LOCK_SECONDS = 15 * 60
IDLE_SECONDS = 12 * 3600
MAX_SECONDS = 7 * 24 * 3600
TOUCH_EVERY = 60  # write last_seen at most once a minute per session
GOOGLE_START_SECONDS = 10 * 60  # a Google sign-in must come back within this
GOOGLE_STARTS_CAP = 1000  # Google sign-ins in progress at once
HASH_SLOTS = 2  # passwords checked at the same time
HASH_WAIT = 10  # seconds a sign-in waits for a free slot
PRUNE_EVERY = 60  # seconds between clean-ups of old rows

_N, _R, _P = 2**14, 8, 1
REFUSED = "Wrong email or password."
LOCKED = "Too many failed logins. Try again in 15 minutes."
BUSY = "Too many sign-ins at once. Try again in a moment."
NO_GOOGLE_ACCOUNT = "This Google account has no MailFlow account."

_hash_slots = threading.BoundedSemaphore(HASH_SLOTS)


class LoginRefused(Exception):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@contextmanager
def _hashing():
    """One of HASH_SLOTS places to run scrypt; LoginRefused(BUSY) after HASH_WAIT seconds."""
    if not _hash_slots.acquire(timeout=HASH_WAIT):
        raise LoginRefused(BUSY)
    try:
        yield
    finally:
        _hash_slots.release()


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


def _ip_key(client_ip: str) -> str:
    """One lockout key per IPv4 address, and per /64 for IPv6 (one customer's whole network)."""
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return f"ip:{client_ip}"
    if address.version == 6:
        if address.ipv4_mapped is not None:  # ::ffff:1.2.3.4 is the IPv4 visitor 1.2.3.4
            return f"ip:{address.ipv4_mapped}"
        return f"ip:{ipaddress.ip_network(f'{address}/64', strict=False)}"
    return f"ip:{address}"


def _attempt(store: Store, email_key: str, ip_key: str, now: float) -> list[int]:
    """Count this attempt now, before the password check; LoginRefused(LOCKED) at the limit."""
    ids = store.try_attempt([(email_key, LOCK_AFTER), (ip_key, IP_LIMIT)], now - LOCK_SECONDS, now)
    if ids is None:
        raise LoginRefused(LOCKED)
    return ids


def login(store: Store, email: str, password: str, client_ip: str, now: float) -> tuple[str, User]:
    """Returns (session token, user) or raises LoginRefused."""
    email = normal_email(email)
    email_key, ip_key = f"email:{email}", _ip_key(client_ip)
    _prune(store, now)
    with _hashing():
        attempt = _attempt(store, email_key, ip_key, now)
        user = store.user_by_email(email)
        # A Google-only account's placeholder hash would fail at once; hash against the dummy instead so
        # the answer takes as long as for an unknown email, and nothing tells the two apart.
        ok = verify_password(password, user.pw_hash if user and not user.google_only else _DUMMY_HASH)
    if user and user.google_only:
        ok = False
    if not (user and ok and user.active):
        raise LoginRefused(REFUSED)  # the attempt stays counted as a failure

    store.drop_attempts(attempt)
    store.forget_failures(email_key)
    return _open_session(store, user, now)


def _open_session(store: Store, user: User, now: float) -> tuple[str, User]:
    token = secrets.token_urlsafe(32)
    store.add_session(_token_hash(token), user.id, now)
    return token, user


def google_begin(store: Store, state: str, verifier: str, nonce: str, now: float) -> None:
    if not store.add_google_start(_token_hash(state), verifier, nonce, now, now - GOOGLE_START_SECONDS, GOOGLE_STARTS_CAP):
        raise LoginRefused(BUSY)


def google_resume(store: Store, state: str, now: float) -> tuple[str, str] | None:
    """(PKCE verifier, nonce) for a state this app handed out in the last GOOGLE_START_SECONDS; once."""
    return store.take_google_start(_token_hash(state), now - GOOGLE_START_SECONDS)


def _prune(store: Store, now: float) -> None:
    if 0 <= now - store.pruned_at < PRUNE_EVERY:  # the deletes scan whole tables under the store's lock
        return
    store.pruned_at = now
    store.prune(
        failures_before=now - 24 * 3600, sessions_before=now - MAX_SECONDS, notes_before=now - NOTES_SECONDS,
        starts_before=now - GOOGLE_START_SECONDS,
    )


def google_login(store: Store, identity: Identity, now: float) -> tuple[str, User]:
    """Returns (session token, user) or raises LoginRefused."""
    _prune(store, now)
    user = store.user_by_google_sub(identity.sub)
    if user is None and identity.authoritative:
        # First Google sign-in: the verified email finds the account, unless another Google account
        # already owns it. Only where Google is the authority for the address: elsewhere a Google
        # account can carry a verified address its holder no longer (or never fully) controls.
        by_email = store.user_by_email(identity.email)
        if by_email and by_email.active and store.link_google(by_email.id, identity.sub):
            user = store.user_by_id(by_email.id)
    if user is None or not user.active:
        raise LoginRefused(NO_GOOGLE_ACCOUNT)
    return _open_session(store, user, now)


def check_current_password(store: Store, user: User, password: str, client_ip: str, now: float) -> None:
    """Before a password change. Wrong guesses count toward the same lockout as logins, so a
    left-open session cannot be used to try passwords without limit."""
    email_key, ip_key = f"email:{user.email}", _ip_key(client_ip)
    with _hashing():
        attempt = _attempt(store, email_key, ip_key, now)
        ok = verify_password(password, user.pw_hash)
    if not ok:
        raise LoginRefused("The current password is wrong.")
    store.drop_attempts(attempt)


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
