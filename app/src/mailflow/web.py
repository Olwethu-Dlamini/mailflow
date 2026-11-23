"""The MailFlow web app: the login, the JSON API the page uses, and the static page itself.

Run: uvicorn --factory mailflow.web:main_app
"""

import hashlib
import json
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config, queue
from .google import CALLBACK_PATH, GoogleLogin, GoogleRefused
from .n8n import STATUSES, Engine, EngineDown
from .store import NO_PASSWORD, Store, User

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
COOKIE = "mf_session"
GOOGLE_COOKIE = "mf_oauth"  # the state of a Google sign-in in progress, for this browser only
REPLY_MAILBOXES = ["gmail"]  # MailFlow · Reply sends through the Gmail node only
MAX_REPLY = 20_000
MAX_BODY = 64 * 1024  # bytes; a reply is at most MAX_REPLY characters
YEAR = "public, max-age=31536000, immutable"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
)
CHANGE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# After Google, the session cookie is set on a page that then moves on by itself: the SameSite=Strict
# cookie would not be sent on a redirect chain that started on accounts.google.com.
SIGNED_IN_PAGE = (
    '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    '<meta http-equiv="refresh" content="0;url=/"><title>MailFlow</title></head>'
    '<body><a href="/">Continue to MailFlow</a></body></html>'
)


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


class Login(BaseModel):
    email: str
    password: str


class NewPassword(BaseModel):
    current: str
    new: str


class StatusChange(BaseModel):
    to: str


class Reply(BaseModel):
    text: str


class NewUser(BaseModel):
    email: str
    name: str
    password: str = ""  # empty: a Google-only account (allowed when Google sign-in is on)
    is_admin: bool = False


class Reset(BaseModel):
    password: str


def _user_json(user: User) -> dict:
    return {
        "id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin, "active": user.active,
        "google_linked": user.google_sub is not None, "google_only": user.google_only,
    }


def _pages() -> dict[str, str]:
    """The two HTML pages with every /static/ link stamped with a hash of the static files.

    A stamped file never changes under its address, so browsers (and Cloudflare) keep it for a year
    and a repeat visit loads no CSS or JS at all; a deploy changes the hash, so nobody runs old code.
    """
    files = sorted(p for p in STATIC.iterdir() if p.is_file() and p.suffix != ".html")
    version = hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in files)).hexdigest()[:12]
    return {
        name: re.sub(r'((?:href|src)="/static/[^"?]+)"', rf'\1?v={version}"', (STATIC / name).read_text())
        for name in ("index.html", "login.html")
    }


def create_app(
    settings: config.Settings, engine: Engine, store: Store, clock=time.time, google: GoogleLogin | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine.warm()  # read the list now, so the first visitor does not wait for n8n
        yield
        for client in (engine, google):
            if hasattr(client, "aclose"):
                await client.aclose()

    app = FastAPI(title="MailFlow", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def client_ip(request: Request) -> str:
        peer = request.client.host if request.client else ""
        # Cloudflare sets Cf-Connecting-IP to the real visitor and overwrites any copy a visitor sends;
        # believe it only when the request came through srv1, the one proxy in front of the app.
        if settings.trusted_proxy and peer == settings.trusted_proxy:
            return request.headers.get("cf-connecting-ip", peer)
        return peer

    def _plain_http(request: Request) -> RedirectResponse | None:
        # Cloudflare also serves http://; the session cookie is https-only, so a login there would
        # silently fail. Cf-Visitor (set by Cloudflare) says which scheme the visitor used.
        peer = request.client.host if request.client else ""
        if not (settings.trusted_proxy and peer == settings.trusted_proxy):
            return None
        if '"scheme":"http"' not in request.headers.get("cf-visitor", "").replace(" ", ""):
            return None
        target = settings.site_origin + request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(target, 308)

    def _refusal(request: Request) -> JSONResponse | None:
        if request.method not in CHANGE_METHODS:
            return None
        origin = request.headers.get("origin")
        if request.headers.get("x-mailflow") != "1" or (origin and origin != settings.site_origin):
            return JSONResponse({"error": "Refused: this change did not come from the MailFlow page."}, 403)
        # The whole body is read into memory before it is checked, so cap it up front
        # (the container has 128 MB). A browser always sends Content-Length for these requests.
        if "chunked" in request.headers.get("transfer-encoding", "").lower():
            return JSONResponse({"error": "Content-Length required."}, 411)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            length = MAX_BODY + 1
        if length > MAX_BODY:
            return JSONResponse({"error": "Request too large."}, 413)
        return None

    @app.middleware("http")
    async def guard(request: Request, call_next):
        response = _plain_http(request) or _refusal(request) or await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path.startswith(("/api/", "/auth/")):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/static/") and "v" in request.query_params:
            response.headers["Cache-Control"] = YEAR
        elif request.url.path.startswith("/static/") or request.url.path in ("/", "/login"):
            # The pages and unstamped files: re-check with the server on every load.
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError):
        return JSONResponse({"error": error.message}, error.status)

    @app.exception_handler(EngineDown)
    async def engine_down(request: Request, error: EngineDown):
        log.warning("engine down: %s", error)
        return JSONResponse({"error": "MailFlow engine unreachable"}, 502)

    def current_user(request: Request) -> User:
        user = auth.session_user(store, request.cookies.get(COOKIE, ""), clock())
        if user is None:
            raise ApiError(401, "Please log in.")
        return user

    def admin_user(user: User = Depends(current_user)) -> User:
        if not user.is_admin:
            raise ApiError(403, "Only an admin can manage accounts.")
        return user

    # pages

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    pages = _pages()

    @app.get("/")
    async def index(request: Request):
        user = auth.session_user(store, request.cookies.get(COOKIE, ""), clock())
        if user is None:
            return RedirectResponse("/login", 303)
        # The account, the list and the open email ride along with the page, so it shows them
        # without three more round trips. Only what is in memory: the page never waits for n8n.
        q = request.query_params
        boot = {"me": _user_json(user)}
        if engine.ready:
            boot["inbox"] = await _inbox_json(q.get("view", "reply"), q.get("mailbox", ""), q.get("topic", ""), q.get("sender", ""))
            row = engine.cached_row(int(q["id"])) if q.get("id", "").isdigit() else None
            if row is not None:
                boot["email"] = _email_json(row)
        # As data, not script (the CSP runs none inline); "<" escaped so no text can close the tag.
        data = json.dumps(boot).replace("<", "\\u003c")
        return HTMLResponse(pages["index.html"].replace("</body>", f'<script type="application/json" id="boot">{data}</script>\n</body>'))

    @app.get("/login")
    def login_page():
        return HTMLResponse(pages["login.html"])

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # session

    def _with_session(response, token: str):
        response.set_cookie(
            COOKIE, token, max_age=auth.MAX_SECONDS, httponly=True, secure=settings.cookie_secure, samesite="strict", path="/"
        )
        return response

    @app.get("/api/login-options")
    def login_options():
        return {"google": google is not None}

    @app.post("/api/login")
    def login(body: Login, request: Request):
        try:
            token, user = auth.login(store, body.email, body.password, client_ip(request), clock())
        except auth.LoginRefused as refused:
            raise ApiError(401, str(refused)) from None
        return _with_session(JSONResponse(_user_json(user)), token)

    # Continue with Google. Failures go back to the login page with a short code it explains.

    def _google_failed(code: str) -> RedirectResponse:
        response = RedirectResponse(f"/login?error={code}", 303)
        response.delete_cookie(GOOGLE_COOKIE, path="/auth/google")
        return response

    @app.get("/auth/google")
    def google_start():
        if google is None:
            raise ApiError(404, "Google sign-in is not set up.")
        start = google.start()
        auth.google_begin(store, start.state, start.verifier, start.nonce, clock())
        response = RedirectResponse(start.url, 303)
        # Lax, not Strict: the browser must send it on Google's redirect back to the callback.
        response.set_cookie(
            GOOGLE_COOKIE, start.state, max_age=auth.GOOGLE_START_SECONDS, httponly=True,
            secure=settings.cookie_secure, samesite="lax", path="/auth/google",
        )
        return response

    @app.get(CALLBACK_PATH)
    async def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        if google is None:
            raise ApiError(404, "Google sign-in is not set up.")
        if error:
            return _google_failed("google_denied")
        mine = request.cookies.get(GOOGLE_COOKIE, "")
        # as bytes: compare_digest refuses str with non-ASCII characters, and ?state= is anyone's
        if not (state and mine and secrets.compare_digest(state.encode(), mine.encode())):
            return _google_failed("google_state")
        started = auth.google_resume(store, state, clock())
        if started is None or not code:
            return _google_failed("google_state")
        try:
            identity = await google.finish(code, *started, clock())
        except GoogleRefused as refused:
            log.warning("Google sign-in failed: %s", refused)
            return _google_failed("google_failed")
        try:
            token, user = auth.google_login(store, identity, clock())
        except auth.LoginRefused:
            log.info("Google sign-in refused for %s: no active MailFlow account", identity.email)
            return _google_failed("google_no_account")
        log.info("%s signed in with Google", user.email)
        response = _with_session(HTMLResponse(SIGNED_IN_PAGE), token)
        response.delete_cookie(GOOGLE_COOKIE, path="/auth/google")
        return response

    @app.post("/api/logout")
    def logout(request: Request):
        auth.logout(store, request.cookies.get(COOKIE, ""))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.get("/api/me")
    def me(user: User = Depends(current_user)):
        return _user_json(user)

    @app.post("/api/me/password")
    def change_password(body: NewPassword, request: Request, user: User = Depends(current_user)):
        try:
            auth.check_current_password(store, user, body.current, client_ip(request), clock())
        except auth.LoginRefused as refused:
            raise ApiError(400, str(refused)) from None
        try:
            auth.check_password_rule(body.new)
        except ValueError as error:
            raise ApiError(400, str(error)) from None
        store.set_password(user.id, auth.hash_password(body.new))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/")
        return response

    # email

    async def _inbox_json(view: str, mailbox: str, topic: str, sender: str) -> dict:
        rows = await engine.recent_rows()
        result = queue.build(rows, view, mailbox, topic, sender, datetime.now(UTC))
        result["reply_mailboxes"] = REPLY_MAILBOXES
        # An older list served while a fresh one is read: the page asks again in a moment.
        result["stale"] = engine.stale
        return result

    def _email_json(row: dict) -> dict:
        return {
            **{k: row.get(k) for k in (*queue.ITEM_FIELDS, "body")},
            "status": queue.status_of(row),
            "needs_reply": queue.needs_reply(row),
            "can_reply": row.get("mailbox") in REPLY_MAILBOXES,
        }

    @app.get("/api/inbox")
    async def inbox(view: str = "reply", mailbox: str = "", topic: str = "", sender: str = "", user: User = Depends(current_user)):
        return await _inbox_json(view, mailbox, topic, sender)

    async def _row(row_id: int) -> dict:
        row = await engine.get_row(row_id)
        if row is None:
            raise ApiError(404, "This email was not found. It may have been cleaned up after 90 days.")
        return row

    @app.get("/api/emails/{row_id}")
    async def email(row_id: int, user: User = Depends(current_user)):
        return _email_json(await _row(row_id))

    @app.post("/api/emails/{row_id}/status")
    async def set_status(row_id: int, body: StatusChange, user: User = Depends(current_user)):
        if body.to not in STATUSES:
            raise ApiError(400, "Unknown status.")
        await _row(row_id)
        await engine.set_status(row_id, body.to)
        log.info("%s set email %d to %s", user.email, row_id, body.to)
        return {"status": body.to}

    @app.post("/api/emails/{row_id}/reply")
    async def reply(row_id: int, body: Reply, user: User = Depends(current_user)):
        text = body.text.strip()
        if not text or len(text) > MAX_REPLY:
            raise ApiError(400, "Write a reply first (at most 20,000 characters).")
        row = await _row(row_id)
        if row.get("mailbox") not in REPLY_MAILBOXES:
            raise ApiError(400, f"Replies from this page work for the {', '.join(REPLY_MAILBOXES)} mailbox only.")
        result = await engine.send_reply(row["message_id"], text)
        if result == "not_found":
            raise ApiError(404, "Not sent: this email could not be found in Gmail.")
        if result == "cannot":
            raise ApiError(400, "Not sent: n8n refused this reply.")
        log.info("%s replied to email %d", user.email, row_id)
        return {"result": "sent"}

    # accounts (admins)

    @app.get("/api/users")
    def users(admin: User = Depends(admin_user)):
        return [_user_json(u) for u in store.list_users()]

    @app.post("/api/users")
    def add_user(body: NewUser, admin: User = Depends(admin_user)):
        if "@" not in body.email or not body.name.strip():
            raise ApiError(400, "An email address and a name are needed.")
        try:
            if body.password:
                auth.check_password_rule(body.password)
                pw_hash = auth.hash_password(body.password)
            elif google is not None:
                pw_hash = NO_PASSWORD
            else:
                raise ValueError(f"The password needs at least {auth.MIN_PASSWORD} characters.")
            user_id = store.add_user(body.email, body.name, pw_hash, body.is_admin)
        except ValueError as error:
            raise ApiError(400, str(error)) from None
        return _user_json(store.user_by_id(user_id))

    def _other_user(user_id: int, admin: User) -> User:
        user = store.user_by_id(user_id)
        if user is None:
            raise ApiError(404, "No such account.")
        if user.id == admin.id:
            raise ApiError(400, "Use Change password for your own account; you cannot disable yourself.")
        return user

    @app.post("/api/users/{user_id}/disable")
    def disable(user_id: int, admin: User = Depends(admin_user)):
        store.set_active(_other_user(user_id, admin).id, False)
        return {"ok": True}

    @app.post("/api/users/{user_id}/enable")
    def enable(user_id: int, admin: User = Depends(admin_user)):
        store.set_active(_other_user(user_id, admin).id, True)
        return {"ok": True}

    @app.post("/api/users/{user_id}/reset")
    def reset(user_id: int, body: Reset, admin: User = Depends(admin_user)):
        user = _other_user(user_id, admin)
        try:
            auth.check_password_rule(body.password)
        except ValueError as error:
            raise ApiError(400, str(error)) from None
        store.set_password(user.id, auth.hash_password(body.password))
        return {"ok": True}

    return app


def main_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = config.from_env()
    google = GoogleLogin(settings) if settings.google_client_id else None
    return create_app(settings, Engine(settings), Store(settings.db_path), google=google)
