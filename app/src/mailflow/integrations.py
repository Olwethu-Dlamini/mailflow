"""What an admin connects from the page, carried out in n8n through its public API.

- A mailbox: an IMAP credential and a collector workflow built like the hand-made ones (IMAP trigger →
  "MailFlow shape" → Process email), switched on. Paused, resumed, and (if the app made it) removed.
- The AI model that sorts the emails: the language model attached to "Sort with AI" in Process email
  is swapped for another provider's, with its API key as a new n8n credential.
- The Telegram alerts: the bot and chat of the Telegram nodes in Process email and Errors.

Passwords and keys go straight into n8n credentials (encrypted there) and are never kept by the app;
n8n's API does not hand them back either. Before a workflow is changed it is saved in the app's
database (store.backup_workflow), so a bad change can be undone by hand.
"""

import asyncio
import copy
import re
import uuid
from dataclasses import dataclass
from datetime import date

import httpx

from .config import Settings

PROCESS_NAME = "MailFlow · Process email"
ERRORS_NAME = "MailFlow · Errors"
SORT_NODE = "Sort with AI"
MODEL_NODE = "AI model"
IMAP_TRIGGER = "n8n-nodes-base.emailReadImap"
RUN_WORKFLOW = "n8n-nodes-base.executeWorkflow"
SET = "n8n-nodes-base.set"
TELEGRAM = "n8n-nodes-base.telegram"
# A mailbox's name in the list: what the collector writes in the "mailbox" column.
LABEL = re.compile(r"[a-z0-9][a-z0-9._@-]{0,31}")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SCOPES_HINT = (
    "n8n refused the app's API key for this. In n8n, Settings → n8n API: give the app's key the "
    "workflow and credential scopes (or use a key without scopes), then put it in the app's .env."
)
BUSY_WAIT = 1.0  # seconds between tries while n8n answers 409 (busy)
BUSY_TRIES = 20


class IntegrationError(Exception):
    """n8n or a provider refused or could not be reached; the message is for people. 502 when it is
    n8n that failed (the app's engine), 400 when what the admin entered was refused."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Provider:
    label: str
    node_type: str
    credential_type: str
    model: str  # the default model
    models_url: str = ""  # "" for a provider without keys (Ollama on the server)
    base_url: str = ""  # written into the credential, so the node never guesses it

    def credential_data(self, key: str) -> dict:
        data = {"apiKey": key}
        if self.base_url:  # OpenAI and Anthropic credentials also name the address, and no extra header
            data.update(url=self.base_url, header=False)
        return data

    def node(self, model: str, credential: dict) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "name": MODEL_NODE,
            "type": self.node_type,
            "typeVersion": 1,
            "parameters": {"model": model, "options": {"temperature": 0}},
            "credentials": {self.credential_type: {"id": credential["id"], "name": credential["name"]}},
        }


LANGCHAIN = "@n8n/n8n-nodes-langchain."
PROVIDERS = {
    "ollama": Provider("Mistral on your own server (Ollama)", LANGCHAIN + "lmChatOllama", "ollamaApi", "mistral:latest"),
    "groq": Provider("Groq", LANGCHAIN + "lmChatGroq", "groqApi", "llama-3.3-70b-versatile", "https://api.groq.com/openai/v1/models"),
    "openai": Provider(
        "OpenAI", LANGCHAIN + "lmChatOpenAi", "openAiApi", "gpt-4o-mini", "https://api.openai.com/v1/models", "https://api.openai.com/v1"
    ),
    "mistral": Provider("Mistral (cloud)", LANGCHAIN + "lmChatMistralCloud", "mistralCloudApi", "mistral-small-latest", "https://api.mistral.ai/v1/models"),
    "anthropic": Provider(
        "Anthropic", LANGCHAIN + "lmChatAnthropic", "anthropicApi", "claude-haiku-4-5", "https://api.anthropic.com/v1/models", "https://api.anthropic.com"
    ),
}
CREDENTIAL_TYPES = (*(p.credential_type for p in PROVIDERS.values()), "telegramApi")


# --- n8n's public API --------------------------------------------------------------------------------


class N8nAdmin:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(20.0))
        self._api = f"{settings.n8n_url}/api/v1"
        self._headers = {"X-N8N-API-KEY": settings.n8n_api_key}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, path: str, busy_tries: int = 1, **kwargs) -> dict:
        """One API call; a 409 (n8n still busy, e.g. unpublishing a workflow) is tried again,
        BUSY_WAIT seconds apart, up to `busy_tries` times in all."""
        for attempt in range(1, busy_tries + 1):
            try:
                response = await self._client.request(method, self._api + path, headers=self._headers, **kwargs)
            except httpx.HTTPError as error:
                raise IntegrationError(f"n8n could not be reached ({error.__class__.__name__}).", 502) from error
            if response.status_code != 409 or attempt == busy_tries:
                break
            await asyncio.sleep(BUSY_WAIT)
        if response.status_code in (401, 403):
            raise IntegrationError(SCOPES_HINT, 502)
        if response.status_code >= 400:
            try:
                detail = str(response.json().get("message", ""))[:200]
            except ValueError:
                detail = ""
            raise IntegrationError(f"n8n answered {response.status_code} for {method} {path.split('?')[0]}. {detail}".strip(), 502)
        try:
            return response.json() if response.content else {}
        except ValueError as error:
            raise IntegrationError("n8n answered something unexpected.", 502) from error

    async def _all(self, path: str) -> list[dict]:
        items, cursor = [], None
        while True:
            params = {"limit": "250", **({"cursor": cursor} if cursor else {})}
            body = await self._call("GET", path, params=params)
            items.extend(body.get("data", []))
            cursor = body.get("nextCursor")
            if not cursor:
                return items

    async def workflows(self) -> list[dict]:
        return await self._all("/workflows")

    async def workflow(self, workflow_id: str) -> dict:
        return await self._call("GET", f"/workflows/{workflow_id}")

    async def create_workflow(self, body: dict) -> str:
        return (await self._call("POST", "/workflows", json=body))["id"]

    async def update_workflow(self, workflow: dict) -> None:
        """Save nodes and connections; on an active workflow n8n publishes the change at once."""
        body = {key: workflow[key] for key in ("name", "nodes", "connections", "settings")}
        await self._call("PUT", f"/workflows/{workflow['id']}", json=body)

    async def set_active(self, workflow_id: str, active: bool) -> None:
        await self._call("POST", f"/workflows/{workflow_id}/{'activate' if active else 'deactivate'}")

    async def delete_workflow(self, workflow_id: str) -> None:
        # Right after a deactivate, n8n 2.x answers 409 "still being unpublished" for a few seconds.
        await self._call("DELETE", f"/workflows/{workflow_id}", busy_tries=BUSY_TRIES)

    async def credentials(self) -> list[dict]:
        """Names and types only: n8n never hands back what is inside a credential."""
        return [{"id": c["id"], "name": c["name"], "type": c["type"]} for c in await self._all("/credentials")]

    async def create_credential(self, name: str, kind: str, data: dict) -> dict:
        created = await self._call("POST", "/credentials", json={"name": name, "type": kind, "data": data})
        return {"id": created["id"], "name": created.get("name", name)}

    async def delete_credential(self, credential_id: str) -> None:
        await self._call("DELETE", f"/credentials/{credential_id}")

    async def last_run(self, workflow_id: str) -> str | None:
        """When the workflow last ran (for a collector: last collected an email), or None."""
        body = await self._call("GET", "/executions", params={"workflowId": workflow_id, "limit": "1"})
        runs = body.get("data", [])
        return runs[0].get("startedAt") if runs else None

    async def by_name(self, name: str) -> dict:
        found = next((w for w in await self.workflows() if w.get("name") == name), None)
        if found is None:
            raise IntegrationError(f"The n8n workflow '{name}' was not found.", 502)
        return await self.workflow(found["id"])


# --- mailboxes ---------------------------------------------------------------------------------------


def _target(node: dict) -> str:
    value = node.get("parameters", {}).get("workflowId")
    return value.get("value", "") if isinstance(value, dict) else str(value or "")


def collector_label(workflow: dict, process_id: str) -> str | None:
    """The mailbox a workflow collects for, if it is a MailFlow collector (IMAP → Process email)."""
    nodes = workflow.get("nodes", [])
    if not any(n.get("type") == IMAP_TRIGGER for n in nodes):
        return None
    if not any(n.get("type") == RUN_WORKFLOW and _target(n) == process_id for n in nodes):
        return None
    for node in nodes:
        if node.get("type") == SET:
            for field in node.get("parameters", {}).get("assignments", {}).get("assignments", []):
                if field.get("name") == "mailbox":
                    return str(field.get("value", ""))
    return None


def _sent_since(day: date) -> str:
    return f'["ALL", ["SENTSINCE", "{day.day:02d}-{MONTHS[day.month - 1]}-{day.year}"]]'


def _field(name: str, value: str) -> dict:
    return {"id": str(uuid.uuid4()), "name": name, "value": value, "type": "string"}


def collector_workflow(label: str, credential: dict, process_id: str, errors_id: str, since: date) -> dict:
    """A collector like the hand-made ones: new mail in INBOX since `since`, shaped, then sorted."""
    trigger, shape, run = f"New {label} email", "MailFlow shape", "Process email"
    body = (
        "={{ ($json.text || String($json.html || '').replace(/<style[\\s\\S]*?<\\/style>/gi, ' ')"
        ".replace(/<[^>]+>/g, ' ').replace(/\\s+/g, ' ') || '').slice(0, 4000) }}"
    )
    first = "$json.from && $json.from.value && $json.from.value[0]"
    return {
        "name": f"MailFlow · From {label} (IMAP)",
        "settings": {"executionOrder": "v1", "errorWorkflow": errors_id},
        "nodes": [
            {
                "id": str(uuid.uuid4()),
                "name": trigger,
                "type": IMAP_TRIGGER,
                "typeVersion": 2.2,
                "position": [0, 0],
                "parameters": {
                    "mailbox": "INBOX",
                    "postProcessAction": "nothing",
                    "downloadAttachments": False,
                    "format": "resolved",
                    "options": {"customEmailConfig": _sent_since(since), "trackLastMessageId": True},
                },
                "credentials": {"imap": {"id": credential["id"], "name": credential["name"]}},
            },
            {
                "id": str(uuid.uuid4()),
                "name": shape,
                "type": SET,
                "typeVersion": 3.4,
                "position": [240, 0],
                "parameters": {
                    "assignments": {
                        "assignments": [
                            _field("message_id", "={{ $json.messageId || ('<' + $json.date + '|' + $json.subject + '>') }}"),
                            _field("mailbox", label),
                            _field("source", "imap"),
                            _field("from_name", f"={{{{ ({first} && $json.from.value[0].name) || '' }}}}"),
                            _field("from_address", f"={{{{ ({first} && $json.from.value[0].address) || '' }}}}"),
                            _field("subject", "={{ $json.subject || '(no subject)' }}"),
                            _field("received_at", "={{ $json.date ? new Date($json.date).toISOString() : $now.toISO() }}"),
                            _field("body", body),
                        ]
                    },
                    "options": {},
                },
            },
            {
                "id": str(uuid.uuid4()),
                "name": run,
                "type": RUN_WORKFLOW,
                "typeVersion": 1,
                "position": [480, 0],
                "parameters": {"source": "database", "workflowId": process_id, "options": {}},
            },
        ],
        "connections": {
            trigger: {"main": [[{"node": shape, "type": "main", "index": 0}]]},
            shape: {"main": [[{"node": run, "type": "main", "index": 0}]]},
        },
    }


# --- the AI model -------------------------------------------------------------------------------------


def _model_sources(workflow: dict) -> list[str]:
    """Names of the nodes attached to "Sort with AI" as its language model."""
    return [
        source
        for source, outputs in workflow.get("connections", {}).items()
        for group in outputs.get("ai_languageModel", [])
        for link in group or []
        if link.get("node") == SORT_NODE
    ]


def current_model(workflow: dict) -> dict:
    names = _model_sources(workflow)
    node = next((n for n in workflow.get("nodes", []) if names and n.get("name") == names[0]), None)
    if node is None:
        return {"provider": "", "model": "", "credential": ""}
    provider = next((key for key, p in PROVIDERS.items() if p.node_type == node.get("type")), "other")
    credential = next(iter((node.get("credentials") or {}).values()), {})
    model = node.get("parameters", {}).get("model", "")
    if isinstance(model, dict):  # newer node versions keep the model as {"value": ...}
        model = model.get("value", "")
    return {"provider": provider, "model": str(model), "credential": credential.get("name", "")}


def with_model(workflow: dict, provider: str, model: str, credential: dict) -> dict:
    """A copy of Process email whose "Sort with AI" uses the given model; the old model node goes."""
    names = _model_sources(workflow)
    if not names:
        raise IntegrationError(f"'{SORT_NODE}' in Process email has no AI model attached; fix it in n8n first.")
    changed = copy.deepcopy(workflow)
    old = next(n for n in changed["nodes"] if n.get("name") == names[0])
    new = PROVIDERS[provider].node(model, credential)
    new["position"] = old.get("position", [0, 0])
    changed["nodes"] = [n for n in changed["nodes"] if n.get("name") not in names] + [new]
    for name in names:
        changed["connections"].pop(name, None)
    changed["connections"][MODEL_NODE] = {"ai_languageModel": [[{"node": SORT_NODE, "type": "ai_languageModel", "index": 0}]]}
    return changed


async def check_ai_key(client: httpx.AsyncClient, provider: str, key: str) -> list[str]:
    """Ask the provider which models the key may use; IntegrationError when the key is refused."""
    spec = PROVIDERS[provider]
    if not spec.models_url:
        return []
    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    else:
        headers = {"Authorization": f"Bearer {key}"}
    try:
        response = await client.get(spec.models_url, headers=headers)
    except httpx.HTTPError as error:
        raise IntegrationError(f"{spec.label} could not be reached ({error.__class__.__name__}).") from error
    if response.status_code in (401, 403):
        raise IntegrationError(f"{spec.label} refused this key.")
    if response.status_code >= 400:
        raise IntegrationError(f"{spec.label} answered {response.status_code}.")
    try:
        return sorted(str(m["id"]) for m in response.json().get("data", []) if "id" in m)
    except (ValueError, TypeError, AttributeError):
        return []


# --- Telegram alerts ---------------------------------------------------------------------------------


def current_alerts(workflows: list[dict]) -> dict:
    for workflow in workflows:
        for node in workflow.get("nodes", []):
            if node.get("type") == TELEGRAM:
                credential = (node.get("credentials") or {}).get("telegramApi", {})
                return {"chat_id": str(node.get("parameters", {}).get("chatId", "")), "credential": credential.get("name", "")}
    return {"chat_id": "", "credential": ""}


def with_alerts(workflow: dict, chat_id: str, credential: dict) -> dict:
    """A copy whose Telegram nodes send to `chat_id` with the bot in `credential`."""
    changed = copy.deepcopy(workflow)
    for node in changed.get("nodes", []):
        if node.get("type") == TELEGRAM:
            node.setdefault("parameters", {})["chatId"] = chat_id
            node["credentials"] = {"telegramApi": {"id": credential["id"], "name": credential["name"]}}
    return changed


TELEGRAM_API = "https://api.telegram.org"
CHAT_ID = re.compile(r"-?\d{1,20}|@[A-Za-z0-9_]{5,32}")
TOKEN = re.compile(r"\d{3,15}:[A-Za-z0-9_-]{30,64}")


async def check_telegram(client: httpx.AsyncClient, token: str, chat_id: str) -> str:
    """Send a test message; the bot's @name. IntegrationError when Telegram refuses."""
    if not TOKEN.fullmatch(token):
        raise IntegrationError("That does not look like a bot token (it is like 123456:ABC…, from @BotFather).")
    try:
        me = await client.get(f"{TELEGRAM_API}/bot{token}/getMe")
        if me.status_code != 200:
            raise IntegrationError("Telegram refused this bot token.")
        sent = await client.post(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "MailFlow test alert: P1 emails and errors will arrive here."},
        )
    except httpx.HTTPError as error:
        raise IntegrationError(f"Telegram could not be reached ({error.__class__.__name__}).") from error
    if sent.status_code != 200:
        raise IntegrationError("The bot could not write to that chat. Send the bot a message first, then check the chat id.")
    return "@" + str(me.json().get("result", {}).get("username", "bot"))
