"""Regression tests for the fixes made after the 2026-11-27 security audit (sign-in under load, the
static cache, request edge cases, Gmail replies, sender headers in the collector)."""

import dataclasses
import json
import re
import shutil
import subprocess
import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_web import ORIGIN, PASSWORD, SETTINGS, FakeEngine

from mailflow import auth, integrations, mailer
from mailflow.store import Store
from mailflow.web import create_app

H = {"X-MailFlow": "1"}


@pytest.fixture
def world():
    store = Store(":memory:")
    store.add_user("staff@example.com", "Staff", auth.hash_password(PASSWORD), is_admin=False)
    engine = FakeEngine()
    return TestClient(create_app(SETTINGS, engine, store), base_url=ORIGIN), engine, store


def sign_in(client):
    response = client.post("/api/login", json={"email": "staff@example.com", "password": PASSWORD}, headers=H)
    assert response.status_code == 200, response.text
    return response


# --- sign-in under load ----------------------------------------------------------------------------


def test_attempts_sent_at_once_cannot_get_past_the_lockout():
    store = Store(":memory:")
    store.add_user("staff@example.com", "Staff", auth.hash_password(PASSWORD), is_admin=False)
    answers = []

    def guess(i):
        try:
            auth.login(store, "staff@example.com", f"wrong guess {i}", f"198.51.100.{i}", 1000.0)
        except auth.LoginRefused as refused:
            answers.append(str(refused))

    threads = [threading.Thread(target=guess, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(answers) == 12
    # Only LOCK_AFTER passwords were checked; the rest were refused before any hashing.
    assert answers.count(auth.REFUSED) == auth.LOCK_AFTER
    assert answers.count(auth.LOCKED) == 12 - auth.LOCK_AFTER


def test_a_right_password_leaves_no_failure_behind():
    store = Store(":memory:")
    store.add_user("staff@example.com", "Staff", auth.hash_password(PASSWORD), is_admin=False)
    for _ in range(25):  # more than IP_LIMIT good sign-ins from one office address
        auth.login(store, "staff@example.com", PASSWORD, "203.0.113.9", 1000.0)
    assert store.failures_since("ip:203.0.113.9", 0) == 0


def test_when_every_hashing_slot_is_busy_the_answer_is_try_again(world, monkeypatch):
    client, _, _ = world
    monkeypatch.setattr(auth, "_hash_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(auth, "HASH_WAIT", 0.05)
    auth._hash_slots.acquire()
    try:
        response = client.post("/api/login", json={"email": "staff@example.com", "password": PASSWORD}, headers=H)
    finally:
        auth._hash_slots.release()
    assert response.status_code == 429
    assert response.json()["error"] == auth.BUSY
    assert sign_in(client).status_code == 200  # free again


@pytest.mark.parametrize(("address", "key"), [
    ("2001:db8:1:2:aaaa::1", "ip:2001:db8:1:2::/64"),
    ("2001:db8:1:2:bbbb::7", "ip:2001:db8:1:2::/64"),
    ("::ffff:198.51.100.4", "ip:198.51.100.4"),
    ("198.51.100.4", "ip:198.51.100.4"),
])
def test_ipv6_visitors_are_counted_per_64(address, key):
    assert auth._ip_key(address) == key


def test_signing_in_again_ends_the_session_the_browser_had(world):
    client, _, store = world
    sign_in(client)
    before = {row[0] for row in store.dump_sessions()}
    sign_in(client)
    after = {row[0] for row in store.dump_sessions()}
    assert len(before) == 1 and len(after) == 1 and before != after


def test_over_https_the_session_cookie_is_host_only():
    store = Store(":memory:")
    store.add_user("staff@example.com", "Staff", auth.hash_password(PASSWORD), is_admin=False)
    app = create_app(dataclasses.replace(SETTINGS, cookie_secure=True), FakeEngine(), store)
    client = TestClient(app, base_url=ORIGIN)
    cookie = client.post("/api/login", json={"email": "staff@example.com", "password": PASSWORD}, headers=H).headers["set-cookie"]
    assert cookie.startswith("__Host-mf_session=")
    assert "Secure" in cookie and "Path=/" in cookie and "Domain" not in cookie


# --- the static cache ------------------------------------------------------------------------------


def test_only_this_versions_files_are_cached_for_a_year(world):
    client, _, _ = world
    version = re.search(r'/static/app\.css\?v=([0-9a-f]+)"', client.get("/login").text).group(1)
    current = client.get(f"/static/login.js?v={version}")
    assert current.status_code == 200 and "immutable" in current.headers["cache-control"]
    other = client.get("/static/login.js?v=000000000000")
    assert other.status_code == 200 and other.text == current.text
    assert "immutable" not in other.headers["cache-control"]
    missing = client.get(f"/static/nope.js?v={version}")
    assert missing.status_code == 404
    assert "immutable" not in missing.headers.get("cache-control", "")


# --- request edge cases ----------------------------------------------------------------------------


def test_odd_email_ids_are_refused_cleanly(world):
    client, _, _ = world
    sign_in(client)
    page = client.get("/?id=²")  # a Unicode digit: isdigit() says yes, int() says no
    assert page.status_code == 200 and 'id="boot"' in page.text
    for path in ("/api/emails/100000000000000000000/activity", "/api/emails/0"):
        assert client.get(path).status_code == 422
    assert client.post("/api/emails/100000000000000000000/assign", json={"user_id": None}, headers=H).status_code == 422
    assert client.get("/api/emails/1/activity").status_code == 200


# --- Gmail replies ---------------------------------------------------------------------------------


def test_a_gmail_reply_needs_a_well_formed_message_id(world):
    client, engine, _ = world
    sign_in(client)
    engine.rows[0]["message_id"] = "<x@sender.example> OR from:victim@third.example>"
    refused = client.post("/api/emails/1/reply", json={"text": "Hello"}, headers=H)
    assert refused.status_code == 400 and "Message-ID" in refused.json()["error"]
    assert engine.replies == []
    engine.rows[0]["message_id"] = "<x@sender.example>"
    assert client.post("/api/emails/1/reply", json={"text": "Hello"}, headers=H).status_code == 200
    assert len(engine.replies) == 1


def test_a_name_that_decodes_to_a_line_break_is_not_sent():
    smtp = mailer.Smtp("smtp.example.com", 587, "starttls", "u", "support@example.com", "Support")
    with pytest.raises(mailer.MailError):
        mailer.reply_message(smtp, "=?utf-8?q?Eve=0D=0ABcc=3A_x=40y.example?=", "eve@example.com", "Hi", "<a@b>", "text")


# --- sender headers in the collector ---------------------------------------------------------------


@pytest.mark.skipif(shutil.which("node") is None, reason="node evaluates the n8n expressions")
def test_the_collector_cuts_sender_headers_and_keeps_future_dates_out():
    workflow = integrations.collector_workflow("support@", {"id": "c", "name": "c"}, "p", "e", date(2026, 11, 27))
    fields = {f["name"]: f["value"] for f in workflow["nodes"][1]["parameters"]["assignments"]["assignments"]}
    expressions = {k: v[3:-2].strip() for k, v in fields.items() if v.startswith("={{")}
    script = """
const $json = {subject: 'S'.repeat(100000), messageId: '<' + 'm'.repeat(100000) + '@x>', date: 'Fri, 01 Jan 2099 00:00:00 +0000',
  from: {value: [{name: 'N'.repeat(100000), address: 'a'.repeat(100000) + '@x.example'}]}, text: 'b'.repeat(100000)};
const $now = {toISO: () => new Date().toISOString()};
const out = {};
for (const [k, e] of Object.entries(JSON.parse(process.argv[1]))) out[k] = eval(e);
console.log(JSON.stringify(out));
"""
    result = json.loads(subprocess.run(["node", "-e", script, json.dumps(expressions)], capture_output=True, text=True, check=True).stdout)
    lengths = {k: len(v) for k, v in result.items() if k != "received_at"}
    assert lengths == {"message_id": 998, "from_name": 200, "from_address": 320, "subject": 500, "body": 4000}
    assert result["received_at"] < "2027"  # the sender's 2099 became the time it arrived
