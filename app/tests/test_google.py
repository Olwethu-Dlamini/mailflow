import base64
import hashlib
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from test_web import ORIGIN, PASSWORD, SETTINGS, FakeEngine

from mailflow import auth
from mailflow.google import TOKEN_URL, GoogleLogin, GoogleRefused
from mailflow.store import Store
from mailflow.web import create_app

GOOGLE = replace(SETTINGS, google_client_id="client-1.apps.googleusercontent.com", google_client_secret="shh")
NOW = 1_800_000_000.0


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def id_token(claims: dict) -> str:
    header = b64url(json.dumps({"alg": "RS256", "kid": "k"}).encode())
    return f"{header}.{b64url(json.dumps(claims).encode())}.c2lnbmF0dXJl"


class FakeGoogle:
    """Google's token endpoint: answers with an id_token made of `claims` (plus the nonce seen at start)."""

    def __init__(self):
        self.claims = {
            "iss": "https://accounts.google.com", "aud": GOOGLE.google_client_id, "sub": "1001",
            "email": "Staff@Example.com", "email_verified": True, "exp": NOW + 3600, "name": "Staff Member",
        }
        self.nonce = None
        self.status = 200
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert str(request.url) == TOKEN_URL
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "invalid_grant"})
        return httpx.Response(200, json={"id_token": id_token({**self.claims, "nonce": self.nonce}), "access_token": "at"})


def google_login(fake: FakeGoogle) -> GoogleLogin:
    return GoogleLogin(GOOGLE, transport=httpx.MockTransport(fake.handler))


# --- the OpenID Connect client ------------------------------------------------


def test_start_sends_the_browser_to_google_with_state_nonce_and_pkce():
    start = GoogleLogin(GOOGLE).start()
    url = urlsplit(start.url)
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert q["client_id"] == GOOGLE.google_client_id
    assert q["redirect_uri"] == ORIGIN + "/auth/google/callback"
    assert q["response_type"] == "code"
    assert q["scope"].split() == ["openid", "email", "profile"]
    assert q["state"] == start.state and q["nonce"] == start.nonce
    assert q["code_challenge_method"] == "S256"
    assert q["code_challenge"] == b64url(hashlib.sha256(start.verifier.encode()).digest())
    assert GoogleLogin(GOOGLE).start().state != start.state


async def test_finish_exchanges_the_code_and_returns_the_verified_identity():
    fake = FakeGoogle()
    fake.nonce = "n-1"
    identity = await google_login(fake).finish("the-code", "the-verifier", "n-1", NOW)
    assert (identity.sub, identity.email, identity.name) == ("1001", "staff@example.com", "Staff Member")
    form = parse_qs(fake.requests[0].content.decode())
    assert form["code"] == ["the-code"] and form["code_verifier"] == ["the-verifier"]
    assert form["client_secret"] == ["shh"] and form["grant_type"] == ["authorization_code"]
    assert form["redirect_uri"] == [ORIGIN + "/auth/google/callback"]


@pytest.mark.parametrize("change", [
    {"aud": "someone-else.apps.googleusercontent.com"},
    {"iss": "https://evil.example"},
    {"exp": NOW - 1},
    {"email_verified": False},
    {"email": ""},
])
async def test_finish_refuses_a_token_that_is_not_for_us(change):
    fake = FakeGoogle()
    fake.nonce = "n-1"
    fake.claims.update(change)
    with pytest.raises(GoogleRefused):
        await google_login(fake).finish("code", "verifier", "n-1", NOW)


async def test_finish_refuses_a_replayed_nonce_and_a_refused_code():
    fake = FakeGoogle()
    fake.nonce = "someone-elses-nonce"
    with pytest.raises(GoogleRefused):
        await google_login(fake).finish("code", "verifier", "n-1", NOW)
    fake.status = 400
    with pytest.raises(GoogleRefused):
        await google_login(fake).finish("code", "verifier", "n-1", NOW)


async def test_finish_says_so_when_google_cannot_be_reached():
    def down(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(GoogleRefused):
        await GoogleLogin(GOOGLE, transport=httpx.MockTransport(down)).finish("code", "verifier", "n", NOW)


# --- the login flow through the app ------------------------------------------


@pytest.fixture
def world():
    store = Store(":memory:")
    store.add_user("boss@example.com", "Boss", auth.hash_password(PASSWORD), is_admin=True)
    store.add_user("staff@example.com", "Staff", auth.hash_password(PASSWORD), is_admin=False)
    fake = FakeGoogle()
    app = create_app(GOOGLE, FakeEngine(), store, clock=lambda: NOW, google=google_login(fake))
    return TestClient(app, base_url=ORIGIN), fake, store


def start(client, fake) -> str:
    """Click 'Continue with Google'; returns the state Google would send back."""
    response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 303
    assert "SameSite=lax" in response.headers["set-cookie"] and "HttpOnly" in response.headers["set-cookie"]
    q = {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}
    fake.nonce = q["nonce"]
    return q["state"]


def callback(client, state, code="code-1"):
    return client.get(f"/auth/google/callback?code={code}&state={state}", follow_redirects=False)


def test_login_options_say_whether_google_is_on(world):
    client, _, _ = world
    assert client.get("/api/login-options").json() == {"google": True}
    plain = TestClient(create_app(SETTINGS, FakeEngine(), Store(":memory:")), base_url=ORIGIN)
    assert plain.get("/api/login-options").json() == {"google": False}
    assert plain.get("/auth/google", follow_redirects=False).status_code == 404


def test_google_login_opens_a_session_for_the_existing_account_and_links_it(world):
    client, fake, store = world
    response = callback(client, start(client, fake))
    assert response.status_code == 200
    # A same-site page continues to "/": the Strict session cookie would be dropped after a
    # redirect chain that began on accounts.google.com.
    assert 'http-equiv="refresh"' in response.text and "url=/" in response.text
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert client.get("/api/me").json()["email"] == "staff@example.com"
    assert store.user_by_email("staff@example.com").google_sub == "1001"


def test_a_linked_account_follows_the_google_sub_not_the_email(world):
    client, fake, _ = world
    callback(client, start(client, fake))
    client.post("/api/logout", headers={"X-MailFlow": "1"})
    fake.claims["email"] = "renamed@example.com"
    assert callback(client, start(client, fake)).status_code == 200
    assert client.get("/api/me").json()["email"] == "staff@example.com"


def test_another_google_account_cannot_take_over_a_linked_account(world):
    client, fake, _ = world
    callback(client, start(client, fake))
    client.post("/api/logout", headers={"X-MailFlow": "1"})
    fake.claims["sub"] = "2002"  # same email, different Google account
    response = callback(client, start(client, fake))
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=google_no_account"
    assert client.get("/api/me").status_code == 401


def test_no_account_and_disabled_account_are_refused(world):
    client, fake, store = world
    fake.claims["email"] = "stranger@example.com"
    response = callback(client, start(client, fake))
    assert response.headers["location"] == "/login?error=google_no_account"
    assert store.user_by_email("stranger@example.com") is None
    fake.claims["email"] = "staff@example.com"
    store.set_active(store.user_by_email("staff@example.com").id, False)
    assert callback(client, start(client, fake)).headers["location"] == "/login?error=google_no_account"
    assert client.get("/api/me").status_code == 401


def test_state_must_match_this_browser_and_works_once(world):
    client, fake, _ = world
    state = start(client, fake)
    other_browser = TestClient(client.app, base_url=ORIGIN)
    assert callback(other_browser, state).headers["location"] == "/login?error=google_state"
    assert other_browser.get("/api/me").status_code == 401
    # A callback whose state differs from this browser's cookie fails and ends that attempt.
    assert callback(client, "forged" + state).headers["location"] == "/login?error=google_state"
    state = start(client, fake)
    assert callback(client, state).status_code == 200
    client.post("/api/logout", headers={"X-MailFlow": "1"})
    client.cookies.set("mf_oauth", state, path="/auth/google")
    assert callback(client, state).headers["location"] == "/login?error=google_state"
    assert len(fake.requests) == 1  # the replay never reached Google


def test_a_state_with_non_ascii_characters_is_refused_not_a_crash(world):
    client, fake, _ = world
    start(client, fake)
    response = client.get("/auth/google/callback?code=c&state=%C3%A9t%C3%A9", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=google_state"


def test_google_errors_go_back_to_the_login_page(world):
    client, fake, _ = world
    start(client, fake)
    denied = client.get("/auth/google/callback?error=access_denied", follow_redirects=False)
    assert denied.headers["location"] == "/login?error=google_denied"
    fake.status = 400
    assert callback(client, start(client, fake)).headers["location"] == "/login?error=google_failed"
    assert client.get("/api/me").status_code == 401


def test_admin_can_add_a_google_only_user_who_has_no_password(world):
    client, fake, _ = world
    client.post("/api/login", json={"email": "boss@example.com", "password": PASSWORD}, headers={"X-MailFlow": "1"})
    added = client.post("/api/users", json={"email": "g@example.com", "name": "G", "password": "", "is_admin": False},
                        headers={"X-MailFlow": "1"})
    assert added.status_code == 200, added.text
    assert added.json()["google_only"] is True
    # No password can ever match the placeholder hash.
    refused = client.post("/api/login", json={"email": "g@example.com", "password": ""}, headers={"X-MailFlow": "1"})
    assert refused.status_code == 401
    client.post("/api/logout", headers={"X-MailFlow": "1"})
    fake.claims.update(email="g@example.com", sub="3003")
    assert callback(client, start(client, fake)).status_code == 200
    assert client.get("/api/me").json()["email"] == "g@example.com"


def test_without_google_a_new_user_needs_a_password():
    store = Store(":memory:")
    store.add_user("boss@example.com", "Boss", auth.hash_password(PASSWORD), is_admin=True)
    client = TestClient(create_app(SETTINGS, FakeEngine(), store), base_url=ORIGIN)
    client.post("/api/login", json={"email": "boss@example.com", "password": PASSWORD}, headers={"X-MailFlow": "1"})
    response = client.post("/api/users", json={"email": "g@example.com", "name": "G", "password": "", "is_admin": False},
                           headers={"X-MailFlow": "1"})
    assert response.status_code == 400
