"""Who handles which email, the activity on each email, and correcting the AI's labels."""

import pytest
from fastapi.testclient import TestClient
from test_web import ORIGIN, PASSWORD, SETTINGS, FakeEngine

from mailflow import auth
from mailflow.store import Store
from mailflow.web import create_app

H = {"X-MailFlow": "1"}


@pytest.fixture
def team():
    store = Store(":memory:")
    ids = {
        "boss": store.add_user("boss@example.com", "Boss", auth.hash_password(PASSWORD), is_admin=True),
        "staff": store.add_user("staff@example.com", "Staff", auth.hash_password(PASSWORD), is_admin=False),
        "thabo": store.add_user("thabo@example.com", "Thabo", auth.hash_password(PASSWORD), is_admin=False),
    }
    engine = FakeEngine()
    app = create_app(SETTINGS, engine, store)

    def client(who: str) -> TestClient:
        c = TestClient(app, base_url=ORIGIN)
        response = c.post("/api/login", json={"email": f"{who}@example.com", "password": PASSWORD}, headers=H)
        assert response.status_code == 200, response.text
        return c

    return client, engine, store, ids


def assign(c, row_id, user_id):
    return c.post(f"/api/emails/{row_id}/assign", json={"user_id": user_id}, headers=H)


def assignee_in_list(c, row_id):
    items = c.get("/api/inbox?view=all").json()["items"]
    return next(item["assignee"] for item in items if item["id"] == row_id)


# --- assigning ------------------------------------------------------------------


def test_staff_take_an_unassigned_email_and_let_it_go(team):
    client, _, _, ids = team
    staff = client("staff")
    assert assignee_in_list(staff, 1) is None
    assert assign(staff, 1, ids["staff"]).status_code == 200
    assert assignee_in_list(staff, 1) == ids["staff"]
    assert staff.get("/api/emails/1").json()["assignee"] == ids["staff"]
    assert assign(staff, 1, None).status_code == 200
    assert assignee_in_list(staff, 1) is None


def test_staff_cannot_give_an_email_away_or_take_one_someone_else_has(team):
    client, _, _, ids = team
    staff, thabo = client("staff"), client("thabo")
    refused = assign(staff, 1, ids["thabo"])
    assert refused.status_code == 403
    assert assignee_in_list(staff, 1) is None
    assert assign(thabo, 1, ids["thabo"]).status_code == 200
    assert assign(staff, 1, ids["staff"]).status_code == 403
    assert assign(staff, 1, None).status_code == 403
    assert assignee_in_list(staff, 1) == ids["thabo"]


def test_an_admin_gives_and_takes_any_email(team):
    client, _, store, ids = team
    boss, thabo = client("boss"), client("thabo")
    assert assign(thabo, 2, ids["thabo"]).status_code == 200
    assert assign(boss, 2, ids["staff"]).status_code == 200
    assert assignee_in_list(boss, 2) == ids["staff"]
    assert assign(boss, 2, None).status_code == 200
    assert assignee_in_list(boss, 2) is None
    store.set_active(ids["thabo"], False)
    assert assign(boss, 2, ids["thabo"]).status_code == 400  # a disabled account
    assert assign(boss, 2, 999).status_code == 400  # no such account
    assert assign(boss, 99, ids["staff"]).status_code == 404  # no such email


def test_mine_lists_only_my_emails_that_are_not_done(team):
    client, engine, _, ids = team
    staff = client("staff")
    assign(staff, 1, ids["staff"])
    inbox = staff.get("/api/inbox?view=mine").json()
    assert inbox["view"] == "mine"
    assert [item["id"] for item in inbox["items"]] == [1]
    assert inbox["counts"]["mine"] == 1
    assert client("thabo").get("/api/inbox?view=mine").json()["items"] == []
    engine.rows[0]["status"] = "done"
    assert staff.get("/api/inbox?view=mine").json()["items"] == []


def test_the_list_names_the_team(team):
    client, _, store, ids = team
    store.set_active(ids["thabo"], False)
    people = client("staff").get("/api/inbox").json()["people"]
    assert people == [{"id": ids["boss"], "name": "Boss"}, {"id": ids["staff"], "name": "Staff"}]


# --- activity --------------------------------------------------------------------


def test_each_email_keeps_who_did_what_newest_first(team):
    client, _, _, ids = team
    staff, boss = client("staff"), client("boss")
    assign(staff, 1, ids["staff"])
    staff.post("/api/emails/1/status", json={"to": "waiting"}, headers=H)
    staff.post("/api/emails/1/reply", json={"text": "Refund done"}, headers=H)
    boss.post("/api/emails/1/labels", json={"priority": "P2"}, headers=H)
    assign(boss, 1, ids["thabo"])
    staff.post("/api/emails/1/status", json={"to": "open"}, headers=H)
    log = [(entry["name"], entry["text"]) for entry in staff.get("/api/emails/1/activity").json()]
    assert log == [
        ("Staff", "reopened it"),
        ("Boss", "gave it to Thabo"),
        ("Boss", "changed the priority from P1 to P2"),
        ("Staff", "sent a reply"),
        ("Staff", "marked it Waiting on customer"),
        ("Staff", "took it"),
    ]
    assert staff.get("/api/emails/2/activity").json() == []


def test_activity_needs_a_login(team):
    client, _, _, _ = team
    assert TestClient(client("staff").app, base_url=ORIGIN).get("/api/emails/1/activity").status_code == 401


# --- correcting the AI -----------------------------------------------------------------


def test_correcting_labels_writes_them_to_n8n_and_marks_the_email_as_corrected(team):
    client, engine, _, _ = team
    staff = client("staff")
    response = staff.post("/api/emails/2/labels", json={"type": "Sponsorship", "priority": "P1", "needs_reply": False}, headers=H)
    assert response.status_code == 200, response.text
    assert engine.fields == [(2, {"type": "Sponsorship", "priority": "P1", "needs_reply": False, "sorted_by": "person"})]
    texts = [entry["text"] for entry in staff.get("/api/emails/2/activity").json()]
    assert texts == ["changed the priority from P2 to P1, the topic to Sponsorship, and marked it as needing no reply"]


@pytest.mark.parametrize("body", [
    {"type": "Not a topic"},
    {"priority": "P9"},
    {"needs_reply": "yes"},
    {},
    {"priority": "P1"},  # already P1: nothing to change
])
def test_labels_must_be_known_values_and_change_something(team, body):
    client, engine, _, _ = team
    assert client("staff").post("/api/emails/1/labels", json=body, headers=H).status_code in (400, 422)
    assert engine.fields == []
