"""The MailFlow web app: the login, the JSON API the page uses, and the static page itself.

Run: uvicorn --factory mailflow.web:main_app
"""

import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config, queue
from .n8n import STATUSES, Engine, EngineDown
from .store import Store, User

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
COOKIE = "mf_session"
REPLY_MAILBOXES = ["gmail"]  # MailFlow · Reply sends through the Gmail node only
MAX_REPLY = 20_000
MAX_BODY = 64 * 1024  # bytes; a reply is at most MAX_REPLY characters
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
)
CHANGE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


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
    password: str
    is_admin: bool = False


class Reset(BaseModel):
    password: str


def _user_json(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin, "active": user.active}


def create_app(settings: config.Settings, engine: Engine, store: Store, clock=time.time) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if hasattr(engine, "aclose"):
            await engine.aclose()

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
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
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

    @app.get("/")
    def index(request: Request):
        if auth.session_user(store, request.cookies.get(COOKIE, ""), clock()) is None:
            return RedirectResponse("/login", 303)
        return FileResponse(STATIC / "index.html")

    @app.get("/login")
    def login_page():
        return FileResponse(STATIC / "login.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # session

    @app.post("/api/login")
    def login(body: Login, request: Request):
        try:
            token, user = auth.login(store, body.email, body.password, client_ip(request), clock())
        except auth.LoginRefused as refused:
            raise ApiError(401, str(refused)) from None
        response = JSONResponse(_user_json(user))
        response.set_cookie(
            COOKIE, token, max_age=auth.MAX_SECONDS, httponly=True, secure=settings.cookie_secure, samesite="strict", path="/"
        )
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

    @app.get("/api/inbox")
    async def inbox(view: str = "reply", mailbox: str = "", type: str = "", mood: str = "", user: User = Depends(current_user)):
        rows = await engine.recent_rows()
        result = queue.build(rows, view, mailbox, type, mood, datetime.now(UTC))
        result["reply_mailboxes"] = REPLY_MAILBOXES
        return result

    async def _row(row_id: int) -> dict:
        row = await engine.get_row(row_id)
        if row is None:
            raise ApiError(404, "This email was not found. It may have been cleaned up after 90 days.")
        return row

    @app.get("/api/emails/{row_id}")
    async def email(row_id: int, user: User = Depends(current_user)):
        row = await _row(row_id)
        return {
            **{k: row.get(k) for k in (*queue.ITEM_FIELDS, "body")},
            "status": queue.status_of(row),
            "needs_reply": queue.needs_reply(row),
            "can_reply": row.get("mailbox") in REPLY_MAILBOXES,
        }

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
            auth.check_password_rule(body.password)
            user_id = store.add_user(body.email, body.name, auth.hash_password(body.password), body.is_admin)
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
    return create_app(settings, Engine(settings), Store(settings.db_path))
