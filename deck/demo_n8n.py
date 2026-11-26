"""Stand-ins for what the Integrations page talks to, for the demo, the screenshots and the tests:
n8n's workflow and credential API, the AI providers and Telegram, and IMAP/SMTP servers.

They check what the real ones check where it matters to the app: n8n refuses a workflow body with
fields its API does not take and a credential that misses a required field or has an unknown one
(the schemas below are n8n 2.47's), providers refuse any key but GOOD_KEY, and the mail servers
any password but GOOD_PASSWORD.
"""

import copy
import imaplib
import itertools
import json
import smtplib
from typing import ClassVar

import httpx

GOOD_KEY = "demo-key"
GOOD_PASSWORD = "demo-password"
GOOD_TOKEN = "123456789:demo-token-demo-token-demo-token-0000"
WORKFLOW_FIELDS = {"name", "nodes", "connections", "settings"}
# credential type → (required fields, allowed fields), from GET /api/v1/credentials/schema/{type}
SCHEMAS = {
    "imap": (set(), {"user", "password", "host", "port", "secure", "allowUnauthorizedCerts"}),
    "telegramApi": ({"accessToken"}, {"accessToken", "baseUrl"}),
    "ollamaApi": (set(), {"baseUrl", "apiKey"}),
    "groqApi": ({"apiKey"}, {"apiKey"}),
    "mistralCloudApi": ({"apiKey"}, {"apiKey"}),
    "openAiApi": ({"apiKey"}, {"apiKey", "organizationId", "url", "header", "headerName", "headerValue"}),
    "anthropicApi": ({"apiKey"}, {"apiKey", "url", "header", "headerName", "headerValue"}),
}
PROCESS_ID, ERRORS_ID = "proc0000000000001", "errs0000000000001"


def _collector(workflow_id: str, label: str, credential: dict) -> dict:
    trigger = f"New {label} email"
    return {
        "id": workflow_id,
        "name": f"MailFlow · From {label} (IMAP)",
        "active": True,
        "settings": {"executionOrder": "v1", "errorWorkflow": ERRORS_ID},
        "nodes": [
            {"name": trigger, "type": "n8n-nodes-base.emailReadImap", "typeVersion": 2.2, "parameters": {},
             "credentials": {"imap": credential}},
            {"name": "MailFlow shape", "type": "n8n-nodes-base.set", "typeVersion": 3.4,
             "parameters": {"assignments": {"assignments": [{"name": "mailbox", "value": label, "type": "string"}]}}},
            {"name": "Process email", "type": "n8n-nodes-base.executeWorkflow", "typeVersion": 1,
             "parameters": {"source": "database", "workflowId": PROCESS_ID}},
        ],
        "connections": {trigger: {"main": [[{"node": "MailFlow shape", "type": "main", "index": 0}]]},
                        "MailFlow shape": {"main": [[{"node": "Process email", "type": "main", "index": 0}]]}},
    }


def _telegram(name: str) -> dict:
    return {"name": name, "type": "n8n-nodes-base.telegram", "typeVersion": 1.2,
            "parameters": {"chatId": "100200300", "text": "alert"},
            "credentials": {"telegramApi": {"id": "cred-tg", "name": "Team alerts bot"}}}


class FakeN8n:
    """Call it with an httpx.Request (it is an httpx.MockTransport handler)."""

    def __init__(self):
        self._ids = (f"new{n:013d}" for n in itertools.count(1))
        self.credentials = {
            "cred-ollama": {"name": "Ollama (local)", "type": "ollamaApi", "data": {}},
            "cred-tg": {"name": "Team alerts bot", "type": "telegramApi", "data": {"accessToken": GOOD_TOKEN}},
            "cred-hello": {"name": "MailFlow · hello@ IMAP", "type": "imap", "data": {}},
            "cred-sponsors": {"name": "MailFlow · sponsors@ IMAP", "type": "imap", "data": {}},
            "cred-press": {"name": "MailFlow · press@ IMAP", "type": "imap", "data": {}},
        }
        model = {"name": "Ollama Chat Model", "type": "@n8n/n8n-nodes-langchain.lmChatOllama", "typeVersion": 1,
                 "position": [300, 200], "parameters": {"model": "mistral:latest", "options": {"temperature": 0}},
                 "credentials": {"ollamaApi": {"id": "cred-ollama", "name": "Ollama (local)"}}}
        self.workflows = {
            PROCESS_ID: {
                "id": PROCESS_ID, "name": "MailFlow · Process email", "active": True,
                "settings": {"executionOrder": "v1", "errorWorkflow": ERRORS_ID},
                "nodes": [{"name": "Sort with AI", "type": "@n8n/n8n-nodes-langchain.informationExtractor",
                           "typeVersion": 1, "parameters": {}}, model, _telegram("Telegram alert")],
                "connections": {"Ollama Chat Model": {"ai_languageModel": [[
                    {"node": "Sort with AI", "type": "ai_languageModel", "index": 0}]]}},
            },
            ERRORS_ID: {"id": ERRORS_ID, "name": "MailFlow · Errors", "active": True, "settings": {"executionOrder": "v1"},
                        "nodes": [_telegram("Telegram error alert")], "connections": {}},
            "coll-hello": _collector("coll-hello", "hello@", {"id": "cred-hello", "name": "MailFlow · hello@ IMAP"}),
            "coll-sponsors": _collector("coll-sponsors", "sponsors@", {"id": "cred-sponsors", "name": "MailFlow · sponsors@ IMAP"}),
            "coll-press": _collector("coll-press", "press@", {"id": "cred-press", "name": "MailFlow · press@ IMAP"}),
        }
        self.workflows["coll-press"]["active"] = False
        self.runs = {"coll-hello": "2026-11-26T09:41:00.000Z", "coll-sponsors": "2026-11-25T16:02:00.000Z"}
        self.calls: list[tuple[str, str]] = []
        self.refuse = set()  # (method, path start) answered 500, to test what happens when n8n fails midway
        self.unpublishing: dict[str, int] = {}  # workflow id → DELETEs still answered 409
        self.fail_after = set()  # (method, path start) carried out, then answered 500 (a timeout after the save)

    @staticmethod
    def _answer(status: int, body) -> httpx.Response:
        return httpx.Response(status, json=body)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path.removeprefix("/api/v1")
        self.calls.append((method, path))
        if any(method == m and path.startswith(p) for m, p in self.refuse):
            return self._answer(500, {"message": "refused for the test"})
        body = json.loads(request.content) if request.content else None
        parts = path.strip("/").split("/")
        if parts[0] == "workflows":
            answer = self._workflows(method, parts[1:], body)
            if any(method == m and path.startswith(p) for m, p in self.fail_after):
                return self._answer(500, {"message": "saved, then failed for the test"})
            return answer
        if parts[0] == "credentials":
            return self._credentials(method, parts[1:], body)
        if parts[0] == "executions":
            started = self.runs.get(request.url.params.get("workflowId", ""))
            return self._answer(200, {"data": [{"startedAt": started}] if started else [], "nextCursor": None})
        return self._answer(404, {"message": "not found"})

    def _workflows(self, method: str, rest: list[str], body) -> httpx.Response:
        if method == "GET" and not rest:
            return self._answer(200, {"data": copy.deepcopy(list(self.workflows.values())), "nextCursor": None})
        if method == "POST" and not rest:
            if set(body) - WORKFLOW_FIELDS:
                return self._answer(400, {"message": "request/body must NOT have additional properties"})
            workflow_id = next(self._ids)
            self.workflows[workflow_id] = {**copy.deepcopy(body), "id": workflow_id, "active": False}
            return self._answer(200, self.workflows[workflow_id])
        workflow = self.workflows.get(rest[0])
        if workflow is None:
            return self._answer(404, {"message": "Not Found"})
        if method == "GET":
            return self._answer(200, copy.deepcopy(workflow))
        if method == "PUT":
            if set(body) - WORKFLOW_FIELDS:
                return self._answer(400, {"message": "request/body must NOT have additional properties"})
            workflow.update(copy.deepcopy(body))
            return self._answer(200, copy.deepcopy(workflow))
        if method == "POST" and rest[1:] in (["activate"], ["deactivate"]):
            workflow["active"] = rest[1] == "activate"
            # n8n 2.47 answers 409 "still being unpublished" to a DELETE for a few seconds after this.
            self.unpublishing[rest[0]] = 2 if rest[1] == "deactivate" else 0
            return self._answer(200, copy.deepcopy(workflow))
        if method == "DELETE":
            if self.unpublishing.get(rest[0], 0) > 0:
                self.unpublishing[rest[0]] -= 1
                return self._answer(409, {"message": "Workflow is still being unpublished. Please try again in a few moments."})
            del self.workflows[rest[0]]
            return self._answer(200, workflow)
        return self._answer(405, {"message": "method not allowed"})

    def _credentials(self, method: str, rest: list[str], body) -> httpx.Response:
        if method == "GET" and not rest:
            items = [{"id": key, "name": c["name"], "type": c["type"]} for key, c in self.credentials.items()]
            return self._answer(200, {"data": items, "nextCursor": None})
        if method == "POST" and not rest:
            required, allowed = SCHEMAS.get(body.get("type"), (None, None))
            data = body.get("data", {})
            if required is None or not required <= set(data) or set(data) - allowed:
                return self._answer(400, {"message": "request.body.data does not match the credential's schema"})
            credential_id = next(self._ids)
            self.credentials[credential_id] = {"name": body["name"], "type": body["type"], "data": data}
            return self._answer(200, {"id": credential_id, "name": body["name"], "type": body["type"]})
        if method == "DELETE" and rest and rest[0] in self.credentials:
            return self._answer(200, self.credentials.pop(rest[0]))
        return self._answer(404, {"message": "Not Found"})


def fake_outside(request: httpx.Request) -> httpx.Response:
    """AI providers' model lists and the Telegram Bot API."""
    host, path = request.url.host, request.url.path
    if host == "api.telegram.org":
        if f"/bot{GOOD_TOKEN}/" not in path:
            return httpx.Response(401, json={"ok": False})
        if path.endswith("/getMe"):
            return httpx.Response(200, json={"ok": True, "result": {"username": "mailflow_demo_bot"}})
        return httpx.Response(200, json={"ok": True})
    key = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ")
    if key != GOOD_KEY:
        return httpx.Response(401, json={"error": "invalid key"})
    return httpx.Response(200, json={"data": [{"id": "model-small"}, {"id": "model-large"}]})


class FakeImap:
    """imaplib.IMAP4_SSL as the app uses it."""

    def __init__(self, host, port, ssl_context=None, timeout=None):
        if host.startswith("unreachable"):
            raise OSError("Name or service not known")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        f"{user}{password}".encode("ascii")  # imaplib sends both as ASCII, and fails before the server sees them
        if password != GOOD_PASSWORD:
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Invalid credentials (Failure)")

    def select(self, mailbox, readonly=False):
        return "OK", [b"3"]


class FakeSmtp:
    """smtplib.SMTP / SMTP_SSL as the app uses it; what was sent, and to whom, is in FakeSmtp.sent
    and FakeSmtp.recipients."""

    sent: ClassVar[list] = []
    recipients: ClassVar[list] = []

    def __init__(self, host, port, timeout=None, context=None):
        if host.startswith("unreachable"):
            raise OSError("Name or service not known")

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        f"{user}{password}".encode("ascii")  # as smtplib does
        if password != GOOD_PASSWORD:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    def send_message(self, message, from_addr=None, to_addrs=None):
        FakeSmtp.sent.append(message)
        FakeSmtp.recipients.append(to_addrs)

    def quit(self):
        pass

    def close(self):
        pass
