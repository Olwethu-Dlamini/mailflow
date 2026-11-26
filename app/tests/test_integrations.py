"""The Integrations page's API: mailboxes, SMTP replies, the AI model and the Telegram alerts.

n8n, the providers, Telegram and the mail servers are the stand-ins in deck/demo_n8n.py, which
refuse what the real ones refuse where it matters (wrong fields, keys, passwords).
"""

import dataclasses
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_web import ORIGIN, PASSWORD, SETTINGS, FakeEngine

from mailflow import auth, integrations, mailer
from mailflow.integrations import N8nAdmin
from mailflow.store import Store
from mailflow.web import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deck"))
import demo_n8n
from demo_n8n import (
    ERRORS_ID,
    GOOD_KEY,
    GOOD_PASSWORD,
    GOOD_TOKEN,
    PROCESS_ID,
    FakeImap,
    FakeSmtp,
)

H = {"X-MailFlow": "1"}
IMAP = {"host": "imap.example.com", "port": 993, "user": "support@example.com"}
SMTP = {"host": "smtp.example.com", "port": 587, "security": "starttls", "user": "support@example.com",
        "from_address": "support@example.com", "from_name": "Example Support"}


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr(mailer, "IMAP", FakeImap)
    monkeypatch.setattr(mailer, "SMTP", FakeSmtp)
    monkeypatch.setattr(mailer, "SMTP_SSL", FakeSmtp)
    FakeSmtp.sent, FakeSmtp.recipients = [], []
    monkeypatch.setattr(integrations, "BUSY_WAIT", 0)
    store = Store(":memory:")
    store.add_user("boss@example.com", "Boss", auth.hash_password(PASSWORD), is_admin=True)
    store.add_user("staff@example.com", "Staff", auth.hash_password(PASSWORD), is_admin=False)
    n8n = demo_n8n.FakeN8n()
    # The test rows' second mailbox, collected by a hand-made workflow like the real 22112002 one.
    n8n.workflows["coll-221"] = demo_n8n._collector("coll-221", "22112002", {"id": "cred-221", "name": "MailFlow · 22112002 IMAP"})
    engine = FakeEngine()
    engine.rows[1].update(from_name="Ann Buyer", from_address="ann@buyer.example")
    settings = dataclasses.replace(SETTINGS, secret_key=Fernet.generate_key().decode())
    app = create_app(
        settings, engine, store,
        n8n_admin=N8nAdmin(settings, transport=httpx.MockTransport(n8n)),
        outside=httpx.AsyncClient(transport=httpx.MockTransport(demo_n8n.fake_outside)),
    )

    def client(who: str = "boss") -> TestClient:
        c = TestClient(app, base_url=ORIGIN)
        assert c.post("/api/login", json={"email": f"{who}@example.com", "password": PASSWORD}, headers=H).status_code == 200
        return c

    return client, n8n, engine, store


def mailbox(overview: dict, label: str) -> dict | None:
    return next((m for m in overview["mailboxes"] if m["label"] == label), None)


# --- who may ----------------------------------------------------------------------------------------


def test_only_admins_reach_integrations(world):
    client, n8n, _, _ = world
    staff = client("staff")
    assert staff.get("/api/integrations").status_code == 403
    assert staff.post("/api/integrations/mailboxes", json={**IMAP, "password": GOOD_PASSWORD, "label": "x"}, headers=H).status_code == 403
    assert staff.post("/api/integrations/ai", json={"provider": "openai", "model": "m", "api_key": GOOD_KEY}, headers=H).status_code == 403
    assert not [call for call in n8n.calls if call[0] != "GET"]


def test_the_overview_shows_what_n8n_runs(world):
    client, *_ = world
    overview = client().get("/api/integrations").json()
    assert overview["error"] is None
    assert [m["label"] for m in overview["mailboxes"]] == ["22112002", "hello@", "press@", "sponsors@"]
    hello = mailbox(overview, "hello@")
    assert hello["active"] is True and hello["managed"] is False and hello["last_run"].startswith("2026-11-26")
    assert mailbox(overview, "press@")["active"] is False
    assert overview["ai"] == {"provider": "ollama", "model": "mistral:latest", "credential": "Ollama (local)"}
    assert overview["alerts"] == {"chat_id": "100200300", "credential": "Team alerts bot"}
    assert overview["credentials"]["telegramApi"] == [{"id": "cred-tg", "name": "Team alerts bot"}]


def test_when_n8n_refuses_the_overview_says_why(world):
    client, n8n, *_ = world
    n8n.refuse.add(("GET", "/workflows"))
    overview = client().get("/api/integrations").json()
    assert "n8n answered 500" in overview["error"]
    assert overview["mailboxes"] == []


# --- mailboxes --------------------------------------------------------------------------------------


def test_a_wrong_imap_password_is_refused_before_anything_is_made_in_n8n(world):
    client, n8n, *_ = world
    response = client().post("/api/integrations/mailboxes", json={**IMAP, "password": "nope", "label": "support@"}, headers=H)
    assert response.status_code == 400
    assert "refused the sign-in" in response.json()["error"]
    assert not [call for call in n8n.calls if call[0] != "GET"]


def test_connecting_a_mailbox_makes_a_working_collector_in_n8n(world):
    client, n8n, *_ = world
    boss = client()
    body = {**IMAP, "password": GOOD_PASSWORD, "label": "Support@", "since_days": 0}
    response = boss.post("/api/integrations/mailboxes", json=body, headers=H)
    assert response.status_code == 200, response.text
    assert response.json()["label"] == "support@" and response.json()["managed"] is True
    credential = next(c for c in n8n.credentials.values() if c["name"] == "MailFlow · support@ IMAP")
    assert credential["type"] == "imap"
    assert credential["data"] == {**{k: IMAP[k] for k in ("host", "port", "user")}, "password": GOOD_PASSWORD,
                                  "secure": True, "allowUnauthorizedCerts": False}
    workflow = next(w for w in n8n.workflows.values() if w["name"] == "MailFlow · From support@ (IMAP)")
    assert workflow["active"] is True
    assert workflow["settings"]["errorWorkflow"] == ERRORS_ID
    trigger, shape, run = workflow["nodes"]
    assert trigger["credentials"]["imap"]["name"] == "MailFlow · support@ IMAP"
    today = datetime.now(UTC)
    assert f"{today.day:02d}-{today.strftime('%b')}-{today.year}" in trigger["parameters"]["options"]["customEmailConfig"]
    assert {"name": "mailbox", "value": "support@"} in [{k: f[k] for k in ("name", "value")} for f in shape["parameters"]["assignments"]["assignments"]]
    assert run["parameters"]["workflowId"] == PROCESS_ID
    assert mailbox(boss.get("/api/integrations").json(), "support@")["managed"] is True
    again = boss.post("/api/integrations/mailboxes", json=body, headers=H)
    assert again.status_code == 400 and "already" in again.json()["error"]


def test_a_collector_n8n_refuses_leaves_no_credential_behind(world):
    client, n8n, *_ = world
    n8n.refuse.add(("POST", "/workflows"))
    before = set(n8n.credentials)
    response = client().post("/api/integrations/mailboxes", json={**IMAP, "password": GOOD_PASSWORD, "label": "support@"}, headers=H)
    assert response.status_code == 502
    assert set(n8n.credentials) == before
    assert ("POST", "/credentials") in n8n.calls


def test_values_n8n_would_run_as_expressions_are_refused_before_anything_is_made(world):
    client, n8n, *_ = world
    boss = client()
    for field in ("password", "user"):
        body = {**IMAP, "password": GOOD_PASSWORD, "label": "support@", field: "={{ $env.N8N_ENCRYPTION_KEY }}"}
        response = boss.post("/api/integrations/mailboxes", json=body, headers=H)
        assert response.status_code == 400 and "starts with" in response.json()["error"]
    key = boss.post("/api/integrations/ai", json={"provider": "openai", "model": "gpt-4o-mini", "api_key": "={{ 1 }}"}, headers=H)
    assert key.status_code == 400
    assert not [call for call in n8n.calls if call[0] != "GET"]


def test_a_password_with_characters_mail_servers_cannot_take_is_a_message_not_a_crash(world):
    client, *_ = world
    response = client().post("/api/integrations/imap/check", json={**IMAP, "password": "pässword"}, headers=H)
    assert response.status_code == 400
    assert "plain ASCII" in response.json()["error"] and "ä" not in response.json()["error"]


def test_pause_resume_and_remove(world):
    client, n8n, *_ = world
    boss = client()
    assert boss.post("/api/integrations/mailboxes/hello@/pause", headers=H).json()["active"] is False
    assert n8n.workflows["coll-hello"]["active"] is False
    assert boss.post("/api/integrations/mailboxes/hello@/resume", headers=H).json()["active"] is True
    hand_made = boss.delete("/api/integrations/mailboxes/hello@", headers=H)
    assert hand_made.status_code == 400 and "by hand" in hand_made.json()["error"]
    assert "coll-hello" in n8n.workflows
    boss.post("/api/integrations/mailboxes", json={**IMAP, "password": GOOD_PASSWORD, "label": "support@"}, headers=H)
    assert boss.delete("/api/integrations/mailboxes/support@", headers=H).status_code == 200
    assert not [w for w in n8n.workflows.values() if "support@" in w["name"]]
    assert not [c for c in n8n.credentials.values() if "support@" in c["name"]]
    assert mailbox(boss.get("/api/integrations").json(), "support@") is None


# --- replies over SMTP ------------------------------------------------------------------------------


def test_smtp_replies_answer_in_the_thread_and_keep_the_password_sealed(world):
    client, _, engine, store = world
    boss = client()
    assert boss.post("/api/emails/2/reply", json={"text": "Hi"}, headers=H).status_code == 400  # not set up yet
    assert boss.put("/api/integrations/mailboxes/22112002/smtp", json={**SMTP, "password": "nope"}, headers=H).status_code == 400
    saved = boss.put("/api/integrations/mailboxes/22112002/smtp", json={**SMTP, "password": GOOD_PASSWORD}, headers=H)
    assert saved.status_code == 200, saved.text
    assert GOOD_PASSWORD.encode() not in store.mailbox("22112002")["smtp_secret"]
    assert GOOD_PASSWORD not in boss.get("/api/integrations").text
    assert "22112002" in boss.get("/api/inbox").json()["reply_mailboxes"]
    assert boss.get("/api/emails/2").json()["can_reply"] is True

    sent = boss.post("/api/emails/2/reply", json={"text": "Here is the quote."}, headers=H)
    assert sent.status_code == 200, sent.text
    message = FakeSmtp.sent[-1]
    assert message["To"] == "Ann Buyer <ann@buyer.example>"
    assert message["From"] == "Example Support <support@example.com>"
    assert message["Subject"] == "Re: Quote"
    assert message["In-Reply-To"] == message["References"] == "<b@x>"
    assert message.get_content().strip() == "Here is the quote."
    assert (2, "waiting") in engine.statuses
    assert engine.replies == []  # not through n8n's Gmail workflow

    # Saving again without a password keeps the one already saved.
    assert boss.put("/api/integrations/mailboxes/22112002/smtp", json={**SMTP, "from_name": "Sales"}, headers=H).status_code == 200
    assert boss.post("/api/emails/2/reply", json={"text": "Again"}, headers=H).status_code == 200
    assert FakeSmtp.sent[-1]["From"] == "Sales <support@example.com>"
    assert boss.delete("/api/integrations/mailboxes/22112002/smtp", headers=H).json()["replies"] is None
    assert boss.get("/api/emails/2").json()["can_reply"] is False
    assert FakeSmtp.recipients == [["ann@buyer.example"]] * 2  # only the checked address, each time


def test_a_saved_smtp_password_only_goes_to_the_server_it_was_saved_for(world):
    client, _, _, store = world
    boss = client()
    assert boss.put("/api/integrations/mailboxes/22112002/smtp", json={**SMTP, "password": GOOD_PASSWORD}, headers=H).status_code == 200
    moved = boss.put("/api/integrations/mailboxes/22112002/smtp", json={**SMTP, "host": "smtp.attacker.example"}, headers=H)
    assert moved.status_code == 400 and "enter the SMTP password again" in moved.json()["error"]
    assert json.loads(store.mailbox("22112002")["smtp"])["host"] == "smtp.example.com"


def test_smtp_replies_stay_listed_after_their_collector_is_gone_from_n8n(world):
    client, n8n, *_ = world
    boss = client()
    boss.put("/api/integrations/mailboxes/22112002/smtp", json={**SMTP, "password": GOOD_PASSWORD}, headers=H)
    del n8n.workflows["coll-221"]  # removed by hand in n8n
    row = mailbox(boss.get("/api/integrations").json(), "22112002")
    assert row["workflow_id"] is None and row["replies"] == "smtp"
    assert boss.delete("/api/integrations/mailboxes/22112002/smtp", headers=H).status_code == 200
    assert mailbox(boss.get("/api/integrations").json(), "22112002") is None


def test_a_refused_smtp_send_says_not_sent_and_keeps_the_email_open(world):
    client, _, engine, store = world
    boss = client()
    boss.put("/api/integrations/mailboxes/22112002/smtp", json={**SMTP, "password": GOOD_PASSWORD}, headers=H)
    saved = store.mailbox("22112002")
    store.save_smtp("22112002", json.dumps({**SMTP, "host": "unreachable.example"}), saved["smtp_secret"], 1, 0)
    response = boss.post("/api/emails/2/reply", json={"text": "Hi"}, headers=H)
    assert response.status_code == 400
    assert response.json()["error"].startswith("Not sent: Could not reach unreachable.example")
    assert (2, "waiting") not in engine.statuses


def test_a_reply_cannot_smuggle_headers_and_skips_threading_without_a_real_message_id():
    smtp = mailer.Smtp("smtp.example.com", 587, "starttls", "u", "support@example.com", "Support")
    message = mailer.reply_message(smtp, "Eve", "eve@example.com", "Hi\r\nBcc: victim@example.com", "<2026-11-01|Hi>", "text")
    assert message["Subject"] == "Re: Hi Bcc: victim@example.com"
    assert message["Bcc"] is None and message["In-Reply-To"] is None
    with pytest.raises(mailer.MailError):
        mailer.reply_message(smtp, "Eve", "not an address", "Hi", "<a@b>", "text")


def test_smtp_needs_the_secret_key(world, monkeypatch):
    store = Store(":memory:")
    store.add_user("boss@example.com", "Boss", auth.hash_password(PASSWORD), is_admin=True)
    n8n = demo_n8n.FakeN8n()
    app = create_app(SETTINGS, FakeEngine(), store, n8n_admin=N8nAdmin(SETTINGS, transport=httpx.MockTransport(n8n)))
    boss = TestClient(app, base_url=ORIGIN)
    boss.post("/api/login", json={"email": "boss@example.com", "password": PASSWORD}, headers=H)
    assert boss.get("/api/integrations").json()["secret_key"] is False
    response = boss.put("/api/integrations/mailboxes/hello@/smtp", json={**SMTP, "password": GOOD_PASSWORD}, headers=H)
    assert response.status_code == 400 and "MAILFLOW_SECRET_KEY" in response.json()["error"]


# --- the AI model -----------------------------------------------------------------------------------


def test_a_refused_ai_key_changes_nothing(world):
    client, n8n, *_ = world
    boss = client()
    assert boss.post("/api/integrations/ai/check", json={"provider": "openai", "api_key": "wrong"}, headers=H).status_code == 400
    response = boss.post("/api/integrations/ai", json={"provider": "openai", "model": "gpt-4o-mini", "api_key": "wrong"}, headers=H)
    assert response.status_code == 400 and "refused this key" in response.json()["error"]
    assert not [call for call in n8n.calls if call[0] != "GET"]


def test_switching_the_ai_to_a_cloud_provider_and_back(world):
    client, n8n, _, store = world
    boss = client()
    assert boss.post("/api/integrations/ai/check", json={"provider": "openai", "api_key": GOOD_KEY}, headers=H).json() == {
        "models": ["model-large", "model-small"]}
    switched = boss.post("/api/integrations/ai", json={"provider": "openai", "model": "gpt-4o-mini", "api_key": GOOD_KEY}, headers=H)
    assert switched.status_code == 200, switched.text
    process = n8n.workflows[PROCESS_ID]
    models = [n for n in process["nodes"] if "lmChat" in n["type"]]
    assert len(models) == 1
    assert models[0]["type"] == "@n8n/n8n-nodes-langchain.lmChatOpenAi"
    assert models[0]["parameters"]["model"] == "gpt-4o-mini"
    credential = n8n.credentials[models[0]["credentials"]["openAiApi"]["id"]]
    assert credential["data"] == {"apiKey": GOOD_KEY, "url": "https://api.openai.com/v1", "header": False}
    assert process["connections"] == {"AI model": {"ai_languageModel": [[{"node": "Sort with AI", "type": "ai_languageModel", "index": 0}]]}}
    assert any(n["name"] == "Telegram alert" for n in process["nodes"])  # the rest of the workflow is untouched
    backup = json.loads(store.backups(PROCESS_ID)[0]["body"])
    assert any(n["type"].endswith("lmChatOllama") for n in backup["nodes"])

    back = boss.post("/api/integrations/ai", json={"provider": "ollama", "model": "mistral:latest", "credential_id": "cred-ollama"}, headers=H)
    assert back.json() == {"provider": "ollama", "model": "mistral:latest", "credential": "Ollama (local)"}
    assert boss.get("/api/integrations").json()["ai"]["provider"] == "ollama"


def test_an_ai_change_n8n_refuses_removes_the_new_key(world):
    client, n8n, *_ = world
    n8n.refuse.add(("PUT", "/workflows"))
    before = set(n8n.credentials)
    response = client().post("/api/integrations/ai", json={"provider": "groq", "model": "llama-3.3-70b-versatile", "api_key": GOOD_KEY}, headers=H)
    assert response.status_code == 502
    assert set(n8n.credentials) == before
    assert n8n.workflows[PROCESS_ID]["nodes"][1]["type"].endswith("lmChatOllama")


def test_a_key_n8n_saved_before_answering_an_error_stays(world):
    client, n8n, *_ = world
    n8n.fail_after.add(("PUT", "/workflows"))  # saved, then the answer is lost
    response = client().post("/api/integrations/ai", json={"provider": "groq", "model": "llama-3.3-70b-versatile", "api_key": GOOD_KEY}, headers=H)
    assert response.status_code == 502
    model = next(n for n in n8n.workflows[PROCESS_ID]["nodes"] if "lmChat" in n["type"])
    assert model["type"].endswith("lmChatGroq")
    assert model["credentials"]["groqApi"]["id"] in n8n.credentials  # the live workflow's key was not deleted


# --- Telegram alerts --------------------------------------------------------------------------------


def test_alerts_move_to_a_new_bot_and_chat_after_a_test_message(world):
    client, n8n, *_ = world
    boss = client()
    bad = boss.post("/api/integrations/alerts/check", json={"token": GOOD_TOKEN, "chat_id": "not a chat"}, headers=H)
    assert bad.status_code == 400
    assert boss.post("/api/integrations/alerts/check", json={"token": GOOD_TOKEN, "chat_id": "-1001234"}, headers=H).json() == {
        "bot": "@mailflow_demo_bot"}
    refused = boss.post("/api/integrations/alerts", json={"token": "1:short", "chat_id": "-1001234"}, headers=H)
    assert refused.status_code == 400
    response = boss.post("/api/integrations/alerts", json={"token": GOOD_TOKEN, "chat_id": "-1001234"}, headers=H)
    assert response.status_code == 200, response.text
    for workflow_id in (PROCESS_ID, ERRORS_ID):
        node = next(n for n in n8n.workflows[workflow_id]["nodes"] if n["type"] == "n8n-nodes-base.telegram")
        assert node["parameters"]["chatId"] == "-1001234"
        assert n8n.credentials[node["credentials"]["telegramApi"]["id"]]["data"]["accessToken"] == GOOD_TOKEN
    assert response.json()["chat_id"] == "-1001234"


def test_alerts_changed_in_one_workflow_only_say_so(world):
    client, n8n, *_ = world
    n8n.refuse.add(("PUT", f"/workflows/{ERRORS_ID}"))
    response = client().post("/api/integrations/alerts", json={"token": GOOD_TOKEN, "chat_id": "-1001234"}, headers=H)
    assert response.status_code == 502
    assert response.json()["error"].startswith("MailFlow · Process email already alerts the new chat")
    node = next(n for n in n8n.workflows[PROCESS_ID]["nodes"] if n["type"] == "n8n-nodes-base.telegram")
    assert node["credentials"]["telegramApi"]["id"] in n8n.credentials  # the bot Process email now uses stays
