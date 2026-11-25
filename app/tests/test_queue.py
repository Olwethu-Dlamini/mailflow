from datetime import UTC, datetime, timedelta

from mailflow.queue import build

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def row(id, priority="P2", hours_ago=1.0, status="open", needs_reply=True, **extra):
    return {
        "id": id,
        "message_id": f"<m{id}@x>",
        "mailbox": "gmail",
        "type": "Registration",
        "sender": "Participant",
        "priority": priority,
        "needs_reply": needs_reply,
        "status": status,
        "received_at": (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z"),
        "subject": f"subject {id}",
        "body": "secret body text",
        **extra,
    }


def ids(inbox):
    return [item["id"] for item in inbox["items"]]


def test_new_and_empty_status_read_as_open():
    inbox = build([row(1, status="new"), row(2, status="", hours_ago=2), row(3, status="done")], "reply", "", "", "", NOW)
    assert ids(inbox) == [2, 1]
    assert {item["status"] for item in inbox["items"]} == {"open"}
    assert inbox["counts"]["reply"] == 2


def test_p1_open_needs_reply_is_late_after_4_hours():
    inbox = build([row(1, "P1", hours_ago=5), row(2, "P1", hours_ago=3)], "reply", "", "", "", NOW)
    late = {item["id"]: item["late"] for item in inbox["items"]}
    assert late == {1: True, 2: False}
    assert inbox["items"][0]["waiting"] == "5 h"


def test_p2_is_not_late_before_24_hours():
    inbox = build([row(1, "P2", hours_ago=23), row(2, "P2", hours_ago=25)], "reply", "", "", "", NOW)
    assert {item["id"]: item["late"] for item in inbox["items"]} == {1: False, 2: True}


def test_waiting_and_done_are_never_late_and_show_no_waiting_label():
    inbox = build([row(1, "P1", hours_ago=50, status="waiting")], "all", "", "", "", NOW)
    assert inbox["items"][0]["late"] is False
    assert inbox["items"][0]["waiting"] == ""


def test_reply_view_sorts_p1_first_then_oldest_first():
    rows = [row(1, "P2", hours_ago=10), row(2, "P1", hours_ago=1), row(3, "P1", hours_ago=2), row(4, "P3", hours_ago=30)]
    assert ids(build(rows, "reply", "", "", "", NOW)) == [3, 2, 1, 4]


def test_all_view_sorts_newest_first():
    rows = [row(1, "P1", hours_ago=10), row(2, "P3", hours_ago=1), row(3, "P2", hours_ago=5)]
    assert ids(build(rows, "all", "", "", "", NOW)) == [2, 3, 1]


def test_views_select_the_right_rows():
    rows = [
        row(1, "P1", status="done"),
        row(2, "P1", status="waiting"),
        row(3, "P2", needs_reply=False),
        row(4, "P2"),
    ]
    assert ids(build(rows, "p1", "", "", "", NOW)) == [2]
    assert ids(build(rows, "waiting", "", "", "", NOW)) == [2]
    assert ids(build(rows, "done", "", "", "", NOW)) == [1]
    assert ids(build(rows, "reply", "", "", "", NOW)) == [4]
    assert build(rows, "reply", "", "", "", NOW)["counts"] == {"reply": 1, "mine": 0, "p1": 1, "waiting": 1, "done": 1, "all": 4}


def test_mine_is_my_assigned_emails_that_are_not_done_sorted_like_the_queue():
    rows = [row(1, "P2", hours_ago=5), row(2, "P1", hours_ago=1), row(3, status="done"), row(4)]
    assigned = {1: 7, 2: 7, 3: 7, 4: 8}
    inbox = build(rows, "mine", "", "", "", NOW, assigned, me=7)
    assert ids(inbox) == [2, 1]
    assert inbox["counts"]["mine"] == 2
    assert [item["assignee"] for item in inbox["items"]] == [7, 7]
    assert ids(build(rows, "mine", "", "", "", NOW, assigned, me=9)) == []


def test_unknown_view_falls_back_to_needs_reply():
    inbox = build([row(1), row(2, status="done")], "nonsense", "", "", "", NOW)
    assert inbox["view"] == "reply"
    assert ids(inbox) == [1]


def test_mailbox_topic_and_sender_filters_combine():
    rows = [
        row(1, mailbox="gmail", type="Sponsorship", sender="Sponsor"),
        row(2, mailbox="22112002", type="Sponsorship", sender="Sponsor"),
        row(3, mailbox="gmail", type="Logistics", sender="Sponsor"),
        row(4, mailbox="gmail", type="Sponsorship", sender="Organiser"),
    ]
    assert ids(build(rows, "all", "gmail", "Sponsorship", "Sponsor", NOW)) == [1]
    inbox = build(rows, "all", "gmail", "", "", NOW)
    assert dict(inbox["mailboxes"]) == {"22112002": 1, "gmail": 3}
    assert dict(inbox["topics"]) == {"Sponsorship": 3, "Logistics": 1}
    assert dict(inbox["senders"]) == {"Sponsor": 3, "Organiser": 1}


def test_items_never_carry_the_body():
    inbox = build([row(1)], "all", "", "", "", NOW)
    assert inbox["items"][0]["subject"] == "subject 1"
    assert "body" not in inbox["items"][0]
