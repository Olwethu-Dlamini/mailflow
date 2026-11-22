"""Sign in with Google: the OpenID Connect authorization-code flow, with PKCE.

Google's ID token is taken straight from Google's token endpoint over HTTPS with the client secret,
so its signature need not be checked again (Google's OpenID Connect guide, "Obtain user information
from the ID token"); its claims are: issuer, audience, expiry, nonce and a verified email.

Who may sign in is decided elsewhere (auth.google_login): only an existing, active MailFlow account.
"""

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from .config import Settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
CALLBACK_PATH = "/auth/google/callback"


class GoogleRefused(Exception):
    """Google said no, could not be reached, or sent a token that is not for this app."""


@dataclass(frozen=True)
class Start:
    url: str  # where to send the browser
    state: str  # ties Google's answer to this browser (kept in a cookie)
    verifier: str  # PKCE: proves the code is redeemed by whoever started the login
    nonce: str  # must come back inside the ID token


@dataclass(frozen=True)
class Identity:
    sub: str  # Google's stable account id; the email can change
    email: str
    name: str


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _claims(id_token: str) -> dict:
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as error:
        raise GoogleRefused("unreadable ID token") from error


class GoogleLogin:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._client_id = settings.google_client_id
        self._secret = settings.google_client_secret
        self._redirect_uri = settings.site_origin + CALLBACK_PATH
        self._http = httpx.AsyncClient(transport=transport, timeout=10.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    def start(self) -> Start:
        state, verifier, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(48), secrets.token_urlsafe(24)
        query = urlencode({
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        })
        return Start(f"{AUTH_URL}?{query}", state, verifier, nonce)

    async def finish(self, code: str, verifier: str, nonce: str, now: float) -> Identity:
        try:
            response = await self._http.post(TOKEN_URL, data={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            })
        except httpx.HTTPError as error:
            raise GoogleRefused(f"Google unreachable: {error.__class__.__name__}") from error
        if response.status_code != 200:
            raise GoogleRefused(f"Google refused the code ({response.status_code})")
        try:
            claims = _claims(response.json()["id_token"])
        except (ValueError, KeyError, TypeError) as error:
            raise GoogleRefused("no ID token in Google's answer") from error

        email = str(claims.get("email") or "").strip().lower()
        checks = {
            "issuer": claims.get("iss") in ISSUERS,
            "audience": claims.get("aud") == self._client_id,
            "expiry": isinstance(claims.get("exp"), int | float) and claims["exp"] > now,
            "nonce": secrets.compare_digest(str(claims.get("nonce") or ""), nonce),
            "verified email": claims.get("email_verified") in (True, "true") and "@" in email,
            "subject": bool(claims.get("sub")),
        }
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            raise GoogleRefused(f"ID token failed: {', '.join(failed)}")
        return Identity(str(claims["sub"]), email, str(claims.get("name") or ""))
