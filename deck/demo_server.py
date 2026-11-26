"""The real MailFlow web app with made-up hackathon emails, for the deck screenshots and speed tests.

No n8n, no real mail: the app's own Engine talks to a stand-in for n8n's data-table API and the
Reply webhook, so caching and every request path are the ones that run in production. Replies and
status changes work in memory only.

Run:   cd app && uv run python ../deck/demo_server.py      (then open http://127.0.0.1:8780)
       DEMO_N8N_MS=800 …   makes each call to the stand-in n8n take 800 ms, like the real one
Login: demo@mailflow.example / demo-password-123
(The Google button shows, but leads to Google's error page: the demo has no real Google client.)
Integrations (admin menu) run against stand-ins (demo_n8n.py): any mail server with the password
demo-password, AI key demo-key, and the Telegram token in demo_n8n.GOOD_TOKEN.
"""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import demo_n8n
import httpx
import uvicorn
from cryptography.fernet import Fernet

from mailflow import auth, mailer, web
from mailflow.config import Settings
from mailflow.google import GoogleLogin
from mailflow.integrations import N8nAdmin
from mailflow.n8n import Engine
from mailflow.store import Store
from mailflow.web import create_app

NOW = datetime.now(UTC)


def ago(hours: float) -> str:
    return (NOW - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# (mailbox, from name, from address, subject, body, topic, sender, priority, needs reply, summary,
#  next step, hours ago, status, sorted by)
EMAILS = [
    ("hello@", "Anonymous participant", "concerned.hacker@example.org", "Report about a participant",
     "Hi,\n\nI want to report that a participant at table 14 has been making sexist comments to me and other women in the room, and followed me outside during the break. I don't feel safe.\n\nPlease do something.",
     "Code of conduct", "Participant", "P1", True, "Participant reports harassment and feels unsafe at table 14",
     "Speak to the reporter and the participant today", 1.2, "open", "ai"),
    ("hello@", "Team Byte Me", "bytemeteam@example.com", "URGENT: Devpost won't accept our video",
     "Submission closes in 40 minutes and Devpost keeps rejecting our demo video upload (error 413). Can we send the video link by email instead?\n\nPlease answer asap!",
     "Submission", "Participant", "P1", True, "Demo video upload fails 40 minutes before the deadline",
     "Accept the video link by email and confirm", 0.4, "open", "ai"),
    ("sponsors@", "Lindiwe Khoza", "lindiwe.khoza@acme.example", "Gold sponsorship: contract and invoice",
     "Good day,\n\nWe're ready to confirm the Gold sponsorship package. Please send the contract and the invoice so we can process payment before Friday. Also let us know where to send our logo files.\n\nKind regards,\nLindiwe",
     "Sponsorship", "Sponsor", "P1", True, "Acme confirms Gold sponsorship, needs contract and invoice",
     "Send the contract and invoice today", 5.5, "open", "ai"),
    ("hello@", "Bongi, venue manager", "events@innovationhub.example", "Power outage in hall B",
     "Morning,\n\nWe have a power outage in hall B since 08:30. Technicians are on it but it may take 2 hours. Please advise if you want to move teams to hall C.",
     "Logistics", "Vendor/Venue", "P1", True, "Hall B has no power for about two hours",
     "Decide on moving teams to hall C", 2.0, "waiting", "ai"),
    ("hello@", "Ayanda Zulu", "ayanda.zulu@student.example", "Can I still register?",
     "Hi, registration closed yesterday but I only saw the post now. Is there any way I can still sign up? I'm a third-year computer science student.\n\nThanks, Ayanda",
     "Registration", "Participant", "P2", True, "Student asks to register after registration closed",
     "Check the waiting list and reply", 30, "open", "ai"),
    ("hello@", "Kabelo M", "kabelo.m@example.com", "Looking for a team",
     "Hey organisers, I signed up solo and I'm a backend developer (Python, Go). Is there a team matching channel, or can you connect me with a team that needs backend help?",
     "Team", "Participant", "P2", True, "Solo backend developer looking for a team",
     "Introduce them to teams needing a backend developer", 20, "open", "ai"),
    ("hello@", "Nomsa Dube", "nomsa.dube@example.com", "Can we use code we wrote before?",
     "Quick rules question: we have a small library we wrote last month. Are we allowed to use it in our project, or does everything need to be written during the event?",
     "Rules & judging", "Participant", "P2", True, "Asks whether existing code may be used",
     "Answer with the rule on prior work", 9, "open", "ai"),
    ("hello@", "Ahmed Hassan", "ahmed.hassan@example.com", "Visa invitation letter",
     "Dear organisers, I am travelling from Egypt and need an official invitation letter for my visa application. Could you please send one?",
     "Logistics", "Participant", "P2", True, "Needs an invitation letter for a visa",
     "Send the official invitation letter", 26, "open", "ai"),
    ("hello@", "Dr. Peter van Wyk", "pvanwyk@university.example", "Judging availability",
     "Thanks for the invitation to judge. I can be there on Sunday from 10:00 to 15:00 but not on Saturday. Will that work for your judging schedule?",
     "Mentor/Judge", "Mentor/Judge", "P2", True, "Judge available Sunday 10:00 to 15:00 only",
     "Confirm the Sunday judging slot", 14, "waiting", "ai"),
    ("press@", "Karen Smith", "karen.smith@technews.example", "Interview request",
     "Hi, I write for TechNews and would like to interview one of the organisers and a winning team for a feature next week.",
     "Media/press", "Press", "P2", True, "Journalist wants interviews for a feature",
     "Agree a time and a spokesperson", 40, "open", "ai"),
    ("hello@", "Thando", "thando.helps@example.com", "I'd like to volunteer",
     "Hi! I can't compete this year but I'd love to volunteer at registration or help with food. When are the volunteer shifts?",
     "Volunteer", "Volunteer", "P2", True, "Offers to volunteer at registration or food",
     "Send the volunteer shift schedule", 50, "done", "ai"),
    ("hello@", "Devpost", "support@devpost.com", "New submission: Smart Water Meter",
     "A new project was submitted to HackDay 2026: Smart Water Meter by Team Aqua.",
     "Platform notification", "Automated", "P3", False, "New submission: Smart Water Meter",
     "No reply needed", 3, "open", "rule"),
    ("sponsors@", "SwagWorld", "sales@swagworld.example", "20% off custom hoodies for your event",
     "Planning an event? Get 20% off custom printed hoodies, stickers and lanyards this month.",
     "Marketing", "Vendor/Venue", "P3", False, "Swag supplier offers a discount",
     "No reply needed", 60, "open", "ai"),
]

ROWS = [
    {
        "id": i + 1, "message_id": f"<demo-{i + 1}@mailflow.example>", "mailbox": m, "source": "imap",
        "from_name": fn, "from_address": fa, "subject": subj, "body": body, "type": topic, "sender": snd,
        "priority": prio, "needs_reply": nr, "summary": summ, "next_step": nxt, "received_at": ago(h),
        "status": st, "sorted_by": by,
    }
    for i, (m, fn, fa, subj, body, topic, snd, prio, nr, summ, nxt, h, st, by) in enumerate(EMAILS)
]


def _matches(row: dict, filter_json: str | None) -> bool:
    for f in json.loads(filter_json)["filters"] if filter_json else []:
        value = row.get(f["columnName"])
        if f["condition"] == "eq" and value != f["value"]:
            return False
        if f["condition"] == "gte" and str(value) < str(f["value"]):
            return False
    return True


async def fake_n8n(request: httpx.Request) -> httpx.Response:
    """Just enough of n8n's data-table API and the Reply webhook for the app, with n8n's slowness."""
    await asyncio.sleep(int(os.environ.get("DEMO_N8N_MS", "0")) / 1000)
    if request.url.path.endswith("/webhook/mailflow/reply"):
        message_id = json.loads(request.content)["id"]
        next(r for r in ROWS if r["message_id"] == message_id)["status"] = "waiting"
        return httpx.Response(200, json={"result": "sent"})
    if request.method == "PATCH":
        body = json.loads(request.content)
        for row in ROWS:
            if _matches(row, json.dumps(body["filter"])):
                row.update(body["data"])
        return httpx.Response(200, json=True)
    found = [r for r in ROWS if _matches(r, request.url.params.get("filter"))]
    found.sort(key=lambda r: r["received_at"], reverse=True)
    return httpx.Response(200, json={"data": found[: int(request.url.params.get("limit", "250"))], "nextCursor": None})


def build_app(port: int):
    """The real app on made-up data, as served on 127.0.0.1:`port` (the browser tests use it too)."""
    web.REPLY_MAILBOXES[:] = ["hello@"]  # the demo's main mailbox gets the reply box, as gmail does for real
    db = Path(tempfile.mkdtemp()) / "demo.db"
    store = Store(str(db))
    store.add_user("demo@mailflow.example", "Olwethu Dlamini", auth.hash_password("demo-password-123"), is_admin=True)
    store.add_user("thabo@mailflow.example", "Thabo Nkosi", auth.hash_password("demo-password-123"), is_admin=False)
    settings = Settings(
        n8n_url="http://demo", n8n_api_key="demo", table_id="demo", reply_url="http://demo/webhook/mailflow/reply",
        reply_secret="demo", db_path=str(db), cookie_secure=False, trusted_proxy="", site_origin=f"http://127.0.0.1:{port}",
        google_client_id="demo.apps.googleusercontent.com", google_client_secret="demo",
        secret_key=Fernet.generate_key().decode(),
    )
    engine = Engine(settings, transport=httpx.MockTransport(fake_n8n))
    # Integrations: a stand-in n8n API, providers and mail servers (password demo-password, key demo-key).
    mailer.IMAP, mailer.SMTP, mailer.SMTP_SSL = demo_n8n.FakeImap, demo_n8n.FakeSmtp, demo_n8n.FakeSmtp
    n8n_admin = N8nAdmin(settings, transport=httpx.MockTransport(demo_n8n.FakeN8n()))
    outside = httpx.AsyncClient(transport=httpx.MockTransport(demo_n8n.fake_outside))
    return create_app(settings, engine, store, google=GoogleLogin(settings), n8n_admin=n8n_admin, outside=outside)


def main() -> None:
    uvicorn.run(build_app(8780), host="127.0.0.1", port=8780, log_level="warning")


if __name__ == "__main__":
    main()
