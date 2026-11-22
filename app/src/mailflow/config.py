"""Settings, read once from the environment (on the server: /opt/mailflow/.env)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    n8n_url: str  # n8n's base address, e.g. http://n8n:5678 inside the Docker network
    n8n_api_key: str  # sent as X-N8N-API-KEY; never reaches the browser
    table_id: str  # the "MailFlow emails" data table
    reply_url: str  # the MailFlow · Reply webhook
    reply_secret: str  # its Header Auth value, sent as X-MailFlow-Secret
    db_path: str  # SQLite file with accounts and sessions
    cookie_secure: bool  # False only for testing over plain http on the laptop
    trusted_proxy: str  # srv1's LAN address: only through it is Cloudflare's Cf-Connecting-IP believed
    site_origin: str  # e.g. https://mailflow.22112002.xyz; POSTs from any other origin are refused
    # "Continue with Google": on only when both are set (Google Cloud → Clients → Web application)
    google_client_id: str = ""
    google_client_secret: str = ""


def _need(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is not set")
    return value


def _google() -> tuple[str, str]:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if bool(client_id) != bool(secret):
        raise SystemExit("Set both GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, or neither")
    return client_id, secret


def from_env() -> Settings:
    n8n_url = os.environ.get("N8N_URL", "http://n8n:5678").rstrip("/")
    google_client_id, google_client_secret = _google()
    return Settings(
        n8n_url=n8n_url,
        n8n_api_key=_need("N8N_API_KEY"),
        table_id=_need("MAILFLOW_TABLE_ID"),
        reply_url=os.environ.get("N8N_REPLY_URL", f"{n8n_url}/webhook/mailflow/reply"),
        reply_secret=_need("N8N_REPLY_SECRET"),
        db_path=os.environ.get("DB_PATH", "/data/mailflow.db"),
        cookie_secure=os.environ.get("COOKIE_SECURE", "true").lower() != "false",
        # Required: unset, every visitor would share srv1's address and 20 bad logins would lock
        # everyone out. "none" (laptop testing, no proxy) uses each connection's own address.
        trusted_proxy="" if _need("TRUSTED_PROXY").lower() == "none" else _need("TRUSTED_PROXY"),
        site_origin=_need("SITE_ORIGIN").rstrip("/"),
        google_client_id=google_client_id,
        google_client_secret=google_client_secret,
    )
