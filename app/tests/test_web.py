import re

import pytest
from fastapi.testclient import TestClient

from mailflow import auth
from mailflow.config import Settings
from mailflow.n8n import EngineDown
from mailflow.store import Store
from mailflow.web import create_app

ORIGIN = "https://mailflow.example"
PASSWORD = "correct horse battery"
SETTINGS = Settings(
    n8n_url="http://n8n:5678",
    n8n_api_key="key",
    table_id="HwHXJgR6FLgD8aeS",
    reply_url="http://n8n:5678/webhook/mailflow/reply",
    reply_secret="secret",
    db_path=":memory:",
    cookie_secure=False,
    trusted_proxy="10.0.0.20",
    site_origin=ORIGIN,
)
ROWS = [
    {"id": 1, "message_id": "<a@x>", "mailbox": "gmail", "priority": "P1", "status": "open", "needs_reply": True,
     "received_at": "2026-11-19T08:00:00Z", "subject": "Charged twice", "body": "<script>alert(1)</script>"},
    {"id": 2, "message_id": "<b@x>", "mailbox": "22112002", "priority": "P2", "status": "open", "needs_reply": True,
     "received_at": "2026-11-19T09:00:00Z", "subject": "Quote", "body": "hello"},
]


class FakeEngine:
    def __init__(self):
        self.down = False
        self.statuses = []
        self.replies = []
        self.reply_result = "sent"
        self.stale = False

    def warm(self):
        pass

    def _check(self):
        if self.down:
            raise EngineDown("n8n unreachable")

    async def recent_rows(self):
        self._check()
        return ROWS

    async def get_row(self, row_id):
        self._check()
        return next((r for r in ROWS if r["id"] == row_id), None)

    async def set_status(self, row_id, to):
        self._check()
        self.statuses.append((row_id, to))

    async def send_reply(self, message_id, text):
        self._check()
        self.replies.append((message_id, text))
        return self.reply_result


@pytest.fixture
def world():
    store = Store(":memory:")
    store.add_user("boss@example.com", "Boss", auth.hash_password(PASSWORD), is_admin=True)
    store.add_user("staff@example.com", "Staff", auth.hash_password(PASSWORD), is_admin=False)
    engine = FakeEngine()
    client = TestClient(create_app(SETTINGS, engine, store), base_url=ORIGIN)
    return client, engine, store


H = {"X-MailFlow": "1"}


def login(client, email="staff@example.com"):
    response = client.post("/api/login", json={"email": email, "password": PASSWORD}, headers=H)
    assert response.status_code == 200, response.text
    return response


def test_inbox_needs_a_login(world):
    client, _, _ = world
    assert client.get("/api/inbox").status_code == 401
    assert client.get("/api/emails/1").status_code == 401


def test_page_redirects_to_login_without_a_session(world):
    client, _, _ = world
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    login(client)
    assert client.get("/", follow_redirects=False).status_code == 200


def test_login_sets_an_httponly_strict_cookie_and_inbox_works(world):
    client, _, _ = world
    cookie = login(client).headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    inbox = client.get("/api/inbox?view=all").json()
    assert [item["id"] for item in inbox["items"]] == [2, 1]
    assert all("body" not in item for item in inbox["items"])
    assert inbox["reply_mailboxes"] == ["gmail"]
    assert inbox["stale"] is False


def test_wrong_password_is_401_with_the_generic_message(world):
    client, _, _ = world
    response = client.post("/api/login", json={"email": "staff@example.com", "password": "nope nope nope"}, headers=H)
    assert response.status_code == 401
    assert response.json() == {"error": "Wrong email or password."}


def test_post_without_the_header_or_from_another_origin_is_refused(world):
    client, engine, _ = world
    login(client)
    assert client.post("/api/emails/1/status", json={"to": "done"}).status_code == 403
    foreign = {**H, "Origin": "https://evil.example"}
    assert client.post("/api/emails/1/status", json={"to": "done"}, headers=foreign).status_code == 403
    assert engine.statuses == []
    same = {**H, "Origin": ORIGIN}
    assert client.post("/api/emails/1/status", json={"to": "done"}, headers=same).status_code == 200
    assert engine.statuses == [(1, "done")]


def test_unknown_status_is_400(world):
    client, engine, _ = world
    login(client)
    assert client.post("/api/emails/1/status", json={"to": "archived"}, headers=H).status_code == 400
    assert engine.statuses == []


def test_email_page_returns_the_body_as_data(world):
    client, _, _ = world
    login(client)
    email = client.get("/api/emails/1").json()
    assert email["body"] == "<script>alert(1)</script>"
    assert email["can_reply"] is True
    assert client.get("/api/emails/2").json()["can_reply"] is False
    assert client.get("/api/emails/99").status_code == 404


def test_reply_refuses_a_non_gmail_mailbox_before_calling_n8n(world):
    client, engine, _ = world
    login(client)
    response = client.post("/api/emails/2/reply", json={"text": "Hi"}, headers=H)
    assert response.status_code == 400
    assert engine.replies == []


def test_reply_refuses_empty_text_and_passes_the_message_id(world):
    client, engine, _ = world
    login(client)
    assert client.post("/api/emails/1/reply", json={"text": "   "}, headers=H).status_code == 400
    assert client.post("/api/emails/1/reply", json={"text": "Refund done"}, headers=H).json() == {"result": "sent"}
    assert engine.replies == [("<a@x>", "Refund done")]
    engine.reply_result = "not_found"
    assert client.post("/api/emails/1/reply", json={"text": "again"}, headers=H).status_code == 404


def test_engine_down_is_502_and_login_still_works(world):
    client, engine, _ = world
    engine.down = True
    login(client)
    response = client.get("/api/inbox")
    assert response.status_code == 502
    assert response.json() == {"error": "MailFlow engine unreachable"}


def test_user_admin_is_for_admins_only(world):
    client, _, store = world
    login(client)
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/users", json={"email": "x@example.com", "name": "X", "password": PASSWORD, "is_admin": False}, headers=H).status_code == 403
    client.post("/api/logout", headers=H)
    login(client, "boss@example.com")
    created = client.post("/api/users", json={"email": "New@Example.com", "name": "New", "password": PASSWORD, "is_admin": False}, headers=H)
    assert created.status_code == 200
    assert store.user_by_email("new@example.com").name == "New"
    assert client.post("/api/users", json={"email": "y@example.com", "name": "Y", "password": "short", "is_admin": False}, headers=H).status_code == 400
    emails = [u["email"] for u in client.get("/api/users").json()]
    assert emails == ["boss@example.com", "new@example.com", "staff@example.com"]


def test_admin_cannot_disable_themselves_and_disabling_ends_sessions(world):
    client, _, store = world
    staff = TestClient(client.app, base_url=ORIGIN)
    login(staff)
    login(client, "boss@example.com")
    boss_id = store.user_by_email("boss@example.com").id
    staff_id = store.user_by_email("staff@example.com").id
    assert client.post(f"/api/users/{boss_id}/disable", headers=H).status_code == 400
    assert client.post(f"/api/users/{staff_id}/disable", headers=H).status_code == 200
    assert staff.get("/api/inbox").status_code == 401


def test_change_password_needs_the_current_one_and_logs_out(world):
    client, _, store = world
    login(client)
    wrong = client.post("/api/me/password", json={"current": "not it at all", "new": "another long password"}, headers=H)
    assert wrong.status_code == 400
    ok = client.post("/api/me/password", json={"current": PASSWORD, "new": "another long password"}, headers=H)
    assert ok.status_code == 200
    assert client.get("/api/inbox").status_code == 401
    assert auth.verify_password("another long password", store.user_by_email("staff@example.com").pw_hash)


def test_client_ip_comes_from_cloudflare_only_through_the_trusted_proxy(world):
    client, _, store = world
    # TestClient's peer is "testclient", not the trusted proxy: the header is ignored,
    # so 20 failures with different spoofed addresses still block that one client.
    for i in range(20):
        client.post("/api/login", json={"email": f"g{i}@example.com", "password": "wrong password!"},
                    headers={**H, "Cf-Connecting-IP": f"9.9.9.{i}"})
    response = client.post("/api/login", json={"email": "staff@example.com", "password": PASSWORD}, headers=H)
    assert response.status_code == 401


def test_behind_the_trusted_proxy_each_visitor_counts_on_their_own(world):
    client, _, _ = world
    proxied = TestClient(client.app, base_url=ORIGIN, client=("10.0.0.20", 443))
    for i in range(20):
        proxied.post("/api/login", json={"email": f"g{i}@example.com", "password": "wrong password!"},
                     headers={**H, "Cf-Connecting-IP": "6.6.6.6"})
    blocked = proxied.post("/api/login", json={"email": "staff@example.com", "password": PASSWORD},
                           headers={**H, "Cf-Connecting-IP": "6.6.6.6"})
    assert blocked.status_code == 401
    other = proxied.post("/api/login", json={"email": "staff@example.com", "password": PASSWORD},
                         headers={**H, "Cf-Connecting-IP": "7.7.7.7"})
    assert other.status_code == 200


def test_wrong_current_passwords_count_toward_the_lockout(world):
    client, _, _ = world
    login(client)
    for i in range(5):
        response = client.post("/api/me/password", json={"current": f"guess number {i}", "new": "another long password"}, headers=H)
        assert response.status_code == 400
    sixth = client.post("/api/me/password", json={"current": PASSWORD, "new": "another long password"}, headers=H)
    assert sixth.status_code == 400
    assert "15 minutes" in sixth.json()["error"]
    client.post("/api/logout", headers=H)
    assert client.post("/api/login", json={"email": "staff@example.com", "password": PASSWORD}, headers=H).status_code == 401


def test_large_or_chunked_bodies_are_refused_before_reading(world):
    client, engine, _ = world
    login(client)
    big = "x" * (64 * 1024 + 1)
    assert client.post("/api/login", content=big, headers={**H, "Content-Type": "application/json"}).status_code == 413
    chunked = client.post("/api/emails/1/reply", content=iter([b'{"text": "hi"}']), headers={**H, "Content-Type": "application/json"})
    assert chunked.status_code == 411
    assert engine.replies == []
    assert client.post("/api/emails/1/reply", json={"text": "fine size"}, headers=H).status_code == 200


def test_trusted_proxy_must_be_set_and_none_opts_out(monkeypatch):
    from mailflow import config

    for name, value in {"N8N_API_KEY": "k", "MAILFLOW_TABLE_ID": "t", "N8N_REPLY_SECRET": "s", "SITE_ORIGIN": ORIGIN}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("TRUSTED_PROXY", raising=False)
    with pytest.raises(SystemExit):
        config.from_env()
    monkeypatch.setenv("TRUSTED_PROXY", "none")
    assert config.from_env().trusted_proxy == ""
    monkeypatch.setenv("TRUSTED_PROXY", "10.0.0.20")
    assert config.from_env().trusted_proxy == "10.0.0.20"


def test_plain_http_through_cloudflare_redirects_to_https(world):
    client, _, _ = world
    proxied = TestClient(client.app, base_url=ORIGIN, client=("10.0.0.20", 443))
    response = proxied.get("/login?x=1", headers={"Cf-Visitor": '{"scheme":"http"}'}, follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == ORIGIN + "/login?x=1"
    assert proxied.get("/login", headers={"Cf-Visitor": '{"scheme":"https"}'}).status_code == 200
    # Only srv1 is believed: the same header from anywhere else changes nothing.
    assert client.get("/login", headers={"Cf-Visitor": '{"scheme":"http"}'}, follow_redirects=False).status_code == 200


def test_security_headers_on_every_response(world):
    client, _, _ = world
    for path in ("/login", "/api/inbox"):
        headers = client.get(path).headers
        assert "default-src 'self'" in headers["content-security-policy"]
        assert "frame-ancestors 'none'" in headers["content-security-policy"]
        assert headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/inbox").headers["cache-control"] == "no-store"


def test_pages_link_stamped_static_files_that_are_kept_for_a_year(world):
    client, _, _ = world
    page = client.get("/login")
    assert page.headers["cache-control"] == "no-cache"
    stamped = re.findall(r'(?:href|src)="(/static/[^"]+)"', page.text)
    assert stamped and all("?v=" in url for url in stamped)
    for url in stamped:
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/static/app.css").headers["cache-control"] == "no-cache"
