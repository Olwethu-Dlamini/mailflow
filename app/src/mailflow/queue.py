"""The work queue: views, filters, sorting and the late rule (design §2.4).

Same rules as the n8n Inbox page it replaced. TOPICS and SENDERS must equal the enums in
MailFlow · Process email (the topic is stored in the `type` column).
"""

from datetime import datetime

TOPICS = [
    "Registration", "Team", "Rules & judging", "Submission", "Sponsorship", "Mentor/Judge", "Volunteer",
    "Logistics", "Prizes & payouts", "Media/press", "Withdrawal", "Code of conduct",
    "Platform notification", "Marketing", "Other",
]
SENDERS = ["Participant", "Sponsor", "Mentor/Judge", "Volunteer", "Vendor/Venue", "Press", "Organiser", "Automated", "Other"]
VIEWS = ["reply", "mine", "p1", "waiting", "done", "all"]
LATE_AFTER_HOURS = {"P1": 4, "P2": 24}
PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2}
ITEM_FIELDS = (
    "id", "message_id", "mailbox", "from_name", "from_address", "subject", "summary",
    "next_step", "type", "priority", "sender", "received_at", "sorted_by",
)


def status_of(row: dict) -> str:
    status = row.get("status")
    return "open" if not status or status == "new" else status


def needs_reply(row: dict) -> bool:
    return row.get("needs_reply") in (True, "true")


def _received(row: dict) -> float:
    value = row.get("received_at")
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return 0.0


IN_VIEW = {
    "reply": lambda r: needs_reply(r) and status_of(r) == "open",
    "p1": lambda r: r.get("priority") == "P1" and status_of(r) != "done",
    "waiting": lambda r: status_of(r) == "waiting",
    "done": lambda r: status_of(r) == "done",
    "all": lambda r: True,
}


def _age_text(hours: float) -> str:
    if hours < 1:
        return f"{max(1, round(hours * 60))} min"
    if hours < 48:
        return f"{round(hours)} h"
    return f"{round(hours / 24)} days"


def _item(row: dict, now: float, assigned: dict[int, int]) -> dict:
    item = {field: row.get(field) for field in ITEM_FIELDS}
    item["assignee"] = assigned.get(row.get("id"))
    status = status_of(row)
    received = _received(row)
    hours = (now - received) / 3600 if received else -1
    waiting = status == "open" and needs_reply(row) and hours >= 0
    limit = LATE_AFTER_HOURS.get(row.get("priority"))
    item.update(
        status=status,
        needs_reply=needs_reply(row),
        waiting=_age_text(hours) if waiting else "",
        late=bool(waiting and limit and hours > limit),
    )
    return item


def _counted(rows: list[dict], key: str, values: list[str]) -> list[list]:
    return [[value, sum(1 for r in rows if r.get(key) == value)] for value in values]


def build(
    rows: list[dict], view: str, mailbox: str, topic: str, sender: str, now: datetime,
    assigned: dict[int, int] | None = None, me: int | None = None,
) -> dict:
    """The list for one view and filters. `assigned` maps row id → user id; `me` is who is asking,
    for the Mine view (my emails that are not done)."""
    assigned = assigned or {}
    in_view = {**IN_VIEW, "mine": lambda r: me is not None and assigned.get(r.get("id")) == me and status_of(r) != "done"}
    view = view if view in in_view else "reply"
    chosen = [
        r for r in rows
        if in_view[view](r)
        and (not mailbox or r.get("mailbox") == mailbox)
        and (not topic or r.get("type") == topic)
        and (not sender or r.get("sender") == sender)
    ]
    if view in ("done", "all"):
        chosen.sort(key=_received, reverse=True)
    else:
        chosen.sort(key=lambda r: (PRIORITY_RANK.get(r.get("priority"), 3), _received(r)))
    stamp = now.timestamp()
    mailboxes = sorted({r.get("mailbox") for r in rows if r.get("mailbox")})
    return {
        "view": view,
        "counts": {name: sum(1 for r in rows if in_view[name](r)) for name in VIEWS},
        "total": len(rows),
        "mailboxes": _counted(rows, "mailbox", mailboxes),
        "topics": _counted(rows, "type", [t for t in TOPICS if any(r.get("type") == t for r in rows)]),
        "senders": _counted(rows, "sender", [s for s in SENDERS if any(r.get("sender") == s for r in rows)]),
        "items": [_item(r, stamp, assigned) for r in chosen],
    }
