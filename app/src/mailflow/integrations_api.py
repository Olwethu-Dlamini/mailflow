"""The Integrations API, for admins: mailboxes, replies over SMTP, the AI model and the Telegram alerts.

Each route checks what it can before it changes anything in n8n (the IMAP or SMTP sign-in, the AI
key, the bot can write to the chat) and removes what it already made when a later step fails.
Passwords and keys are never logged or sent back to the page.
"""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from . import integrations as ig
from . import mailer
from .integrations import IntegrationError, N8nAdmin
from .mailer import Smtp
from .store import Store, User
from .vault import Vault

log = logging.getLogger(__name__)

HOST = re.compile(r"[A-Za-z0-9.-]{1,253}")
MODEL = re.compile(r"[\w.:/@-]{1,100}")
MAX_SINCE_DAYS = 30


class ImapLogin(BaseModel):
    host: str
    port: int = 993
    user: str
    password: str


class NewMailbox(ImapLogin):
    label: str
    since_days: int = 0  # collect emails sent since this many days ago; 0 is today


class SmtpSettings(BaseModel):
    host: str
    port: int = 587
    security: str = "starttls"
    user: str
    password: str = ""  # empty keeps the password already saved
    from_address: str
    from_name: str = ""


class AiKey(BaseModel):
    provider: str
    api_key: str


class AiChoice(BaseModel):
    provider: str
    model: str
    credential_id: str = ""  # a key already in n8n …
    api_key: str = ""  # … or a new one


class AlertsTest(BaseModel):
    token: str
    chat_id: str


class AlertsChoice(BaseModel):
    chat_id: str
    credential_id: str = ""
    token: str = ""


def _host(host: str, port: int) -> str:
    host = host.strip()
    if not HOST.fullmatch(host) or not 0 < port < 65536:
        raise IntegrationError("Enter the server's name (like imap.example.com) and a port from 1 to 65535.")
    return host


def _plain(value: str, what: str) -> str:
    """A value that goes into an n8n credential: n8n runs a value that starts with "=" as an
    expression (it could read n8n's own settings), so such a value is refused."""
    if value.startswith("="):
        raise IntegrationError(f"n8n cannot keep a {what} that starts with “=”. Change it, then try again.")
    return value


def _smtp_public(saved: dict | None) -> dict | None:
    return json.loads(saved["smtp"]) if saved and saved.get("smtp") else None


def add_routes(
    app: FastAPI,
    *,
    admin_user: Callable,
    store: Store,
    n8n: N8nAdmin,
    outside: httpx.AsyncClient,
    vault: Vault,
    clock: Callable[[], float],
    reply_mailboxes: list[str],
) -> None:
    """Add the /api/integrations routes; `reply_mailboxes` are those n8n's Reply workflow answers."""

    async def _collectors() -> tuple[dict, dict[str, dict], list[dict]]:
        """Process email, the collectors by mailbox, and every workflow."""
        workflows = await n8n.workflows()
        process = next((w for w in workflows if w.get("name") == ig.PROCESS_NAME), None)
        if process is None:
            raise IntegrationError(f"The n8n workflow '{ig.PROCESS_NAME}' was not found.", 502)
        found = {}
        for workflow in workflows:
            label = ig.collector_label(workflow, process["id"])
            if label:
                found[label] = workflow
        return process, found, workflows

    def _mailbox_json(label: str, workflow: dict | None, last_run: str | None = None) -> dict:
        saved = store.mailbox(label)
        smtp = _smtp_public(saved)
        return {
            "label": label,
            "workflow_id": workflow["id"] if workflow else None,
            "name": workflow.get("name", "") if workflow else "",
            "active": bool(workflow and workflow.get("active")),
            # Only what the app made can be removed from here; hand-made ones are paused at most.
            "managed": bool(saved and workflow and saved.get("workflow_id") == workflow["id"]),
            "last_run": last_run,
            "smtp": smtp,
            "replies": "smtp" if smtp else ("gmail" if label in reply_mailboxes else None),
        }

    async def _collector(label: str) -> dict:
        _, found, _ = await _collectors()
        if label not in found:
            raise IntegrationError("No mailbox of that name collects into MailFlow.")
        return found[label]

    @app.get("/api/integrations")
    async def overview(admin: User = Depends(admin_user)):
        result = {
            "secret_key": vault.ready,
            "providers": {
                key: {"label": p.label, "model": p.model, "needs_key": bool(p.models_url), "credential_type": p.credential_type}
                for key, p in ig.PROVIDERS.items()
            },
            "mailboxes": [],
            "ai": None,
            "alerts": None,
            "credentials": {},
            "error": None,
        }
        try:
            process, found, workflows = await _collectors()
            labels = sorted(found)
            runs = await asyncio.gather(*(n8n.last_run(found[label]["id"]) for label in labels))
            result["mailboxes"] = [_mailbox_json(label, found[label], run) for label, run in zip(labels, runs, strict=True)]
            # SMTP saved for a mailbox whose collector is gone from n8n: still sending, so still shown.
            result["mailboxes"] += [_mailbox_json(label, None) for label in store.smtp_labels() if label not in found]
            result["ai"] = ig.current_model(process)
            errors = next((w for w in workflows if w.get("name") == ig.ERRORS_NAME), None)
            result["alerts"] = ig.current_alerts([process, *([errors] if errors else [])])
            credentials = await n8n.credentials()
            result["credentials"] = {
                kind: [{"id": c["id"], "name": c["name"]} for c in credentials if c["type"] == kind] for kind in ig.CREDENTIAL_TYPES
            }
        except IntegrationError as error:
            result["error"] = str(error)
            # What the app knows by itself, so SMTP replies can still be seen and switched off.
            result["mailboxes"] = [_mailbox_json(label, None) for label in sorted(store.mailboxes())]
        return result

    # mailboxes

    @app.post("/api/integrations/imap/check")
    async def check_imap(body: ImapLogin, admin: User = Depends(admin_user)):
        host = _host(body.host, body.port)
        user, password = _plain(body.user.strip(), "sign-in"), _plain(body.password, "password")
        await asyncio.to_thread(mailer.check_imap, host, body.port, user, password)
        return {"ok": True}

    @app.post("/api/integrations/mailboxes")
    async def add_mailbox(body: NewMailbox, admin: User = Depends(admin_user)):
        label = body.label.strip().lower()
        if not ig.LABEL.fullmatch(label):
            raise IntegrationError("A mailbox name is 1 to 32 lowercase letters, digits, or . _ - @ (like support@).")
        if not 0 <= body.since_days <= MAX_SINCE_DAYS:
            raise IntegrationError(f"Collect from today, or from up to {MAX_SINCE_DAYS} days back.")
        host = _host(body.host, body.port)
        user, password = _plain(body.user.strip(), "sign-in"), _plain(body.password, "password")
        process, found, workflows = await _collectors()
        if label in found:
            raise IntegrationError(f"There is already a mailbox called {label}.")
        await asyncio.to_thread(mailer.check_imap, host, body.port, user, password)
        errors = next((w for w in workflows if w.get("name") == ig.ERRORS_NAME), None)
        since = (datetime.now(UTC) - timedelta(days=body.since_days)).date()
        credential = await n8n.create_credential(
            f"MailFlow · {label} IMAP",
            "imap",
            {"user": user, "password": password, "host": host, "port": body.port, "secure": True, "allowUnauthorizedCerts": False},
        )
        workflow_id = None
        try:
            workflow = ig.collector_workflow(label, credential, process["id"], errors["id"] if errors else "", since)
            if not errors:
                del workflow["settings"]["errorWorkflow"]
            workflow_id = await n8n.create_workflow(workflow)
            await n8n.set_active(workflow_id, True)
            store.save_collector(label, workflow_id, credential["id"], admin.id, clock())
        except Exception:
            await _undo_mailbox(workflow_id, credential["id"])
            raise
        log.info("%s connected the mailbox %s (%s@%s)", admin.email, label, user, host)
        return _mailbox_json(label, {**workflow, "id": workflow_id, "active": True})

    async def _undo_mailbox(workflow_id: str | None, credential_id: str) -> None:
        """Remove what add_mailbox made, as far as n8n lets it; the credential only once no collector uses it."""
        if workflow_id:
            try:
                await n8n.set_active(workflow_id, False)
            except IntegrationError:
                pass  # it may never have been switched on
            try:
                await n8n.delete_workflow(workflow_id)
            except IntegrationError as error:
                log.warning("a collector the app could not finish setting up stayed in n8n (%s): %s", workflow_id, error)
                return
        try:
            await n8n.delete_credential(credential_id)
        except IntegrationError as error:
            log.warning("an unused IMAP credential stayed in n8n (%s): %s", credential_id, error)

    async def _switch(label: str, active: bool, admin: User) -> dict:
        workflow = await _collector(label)
        await n8n.set_active(workflow["id"], active)
        log.info("%s %s the mailbox %s", admin.email, "resumed" if active else "paused", label)
        return _mailbox_json(label, {**workflow, "active": active})

    @app.post("/api/integrations/mailboxes/{label}/pause")
    async def pause(label: str, admin: User = Depends(admin_user)):
        return await _switch(label, False, admin)

    @app.post("/api/integrations/mailboxes/{label}/resume")
    async def resume(label: str, admin: User = Depends(admin_user)):
        return await _switch(label, True, admin)

    @app.delete("/api/integrations/mailboxes/{label}")
    async def remove(label: str, admin: User = Depends(admin_user)):
        saved = store.mailbox(label)
        workflow = await _collector(label)
        if not saved or saved.get("workflow_id") != workflow["id"]:
            raise IntegrationError("This mailbox was set up in n8n by hand: pause it here, or remove it in n8n.")
        await n8n.set_active(workflow["id"], False)
        await n8n.delete_workflow(workflow["id"])
        if saved.get("credential_id"):
            try:
                await n8n.delete_credential(saved["credential_id"])
            except IntegrationError as error:  # the collector is gone, which is what matters
                log.warning("the IMAP credential of %s stayed in n8n: %s", label, error)
        store.drop_mailbox(label)
        log.info("%s removed the mailbox %s", admin.email, label)
        return {"ok": True}

    # replies over SMTP

    @app.put("/api/integrations/mailboxes/{label}/smtp")
    async def set_smtp(label: str, body: SmtpSettings, admin: User = Depends(admin_user)):
        if not vault.ready:
            raise IntegrationError("Set MAILFLOW_SECRET_KEY in the server's .env first (the deploy script makes one).")
        await _collector(label)
        smtp = Smtp(
            host=_host(body.host, body.port), port=body.port, security=body.security, user=body.user.strip(),
            from_address=body.from_address.strip(), from_name=body.from_name.strip()[:100],
        )
        if smtp.security not in mailer.SECURITY:
            raise IntegrationError("Choose SSL (usually port 465) or STARTTLS (usually port 587).")
        if not mailer.ADDRESS.fullmatch(smtp.from_address):
            raise IntegrationError("Enter the address replies come from, like support@example.com.")
        password = body.password  # stays in the app (sealed), never in n8n
        if not password:
            # The saved password goes only to the server and account it was saved for.
            saved = store.mailbox(label)
            before = _smtp_public(saved) or {}
            if not (saved and saved.get("smtp_secret")):
                raise IntegrationError("Enter the SMTP password.")
            if any(before.get(key) != getattr(smtp, key) for key in ("host", "port", "security", "user")):
                raise IntegrationError("The server or sign-in changed: enter the SMTP password again.")
            password = vault.open(saved["smtp_secret"])
        await asyncio.to_thread(mailer.check_smtp, smtp, password)
        store.save_smtp(label, json.dumps(smtp.as_dict()), vault.seal(password), admin.id, clock())
        log.info("%s set up SMTP replies for %s (%s@%s)", admin.email, label, smtp.user, smtp.host)
        return {"label": label, "smtp": smtp.as_dict(), "replies": "smtp"}

    @app.delete("/api/integrations/mailboxes/{label}/smtp")
    def drop_smtp(label: str, admin: User = Depends(admin_user)):
        store.drop_smtp(label)
        log.info("%s switched off SMTP replies for %s", admin.email, label)
        return {"label": label, "smtp": None, "replies": "gmail" if label in reply_mailboxes else None}

    # the AI model

    async def _credential(kind: str, credential_id: str, make: Callable) -> tuple[dict, bool]:
        """A saved credential of that type, or a new one from make(); and whether it is new."""
        if credential_id:
            saved = next((c for c in await n8n.credentials() if c["id"] == credential_id and c["type"] == kind), None)
            if saved is None:
                raise IntegrationError("That saved key was not found in n8n.")
            return {"id": saved["id"], "name": saved["name"]}, False
        return await make(), True

    async def _drop_if_unused(credential_id: str, workflow_ids: list[str]) -> None:
        """After a change that failed: delete the new credential, unless n8n saved the change after
        all (a timeout after the save) and a workflow now uses it."""
        try:
            for workflow_id in workflow_ids:
                workflow = await n8n.workflow(workflow_id)
                for node in workflow.get("nodes", []):
                    if any(c.get("id") == credential_id for c in (node.get("credentials") or {}).values()):
                        return
            await n8n.delete_credential(credential_id)
        except IntegrationError as error:
            log.warning("a new n8n credential may be left unused (%s): %s", credential_id, error)

    @app.post("/api/integrations/ai/check")
    async def check_ai(body: AiKey, admin: User = Depends(admin_user)):
        if body.provider not in ig.PROVIDERS or not ig.PROVIDERS[body.provider].models_url:
            raise IntegrationError("Choose a provider that takes a key.")
        return {"models": (await ig.check_ai_key(outside, body.provider, body.api_key.strip()))[:300]}

    @app.post("/api/integrations/ai")
    async def set_ai(body: AiChoice, admin: User = Depends(admin_user)):
        spec = ig.PROVIDERS.get(body.provider)
        if spec is None:
            raise IntegrationError("Unknown provider.")
        model = body.model.strip()
        if not MODEL.fullmatch(model):
            raise IntegrationError("Enter the model's name, like " + spec.model + ".")
        key = _plain(body.api_key.strip(), "key")
        if not body.credential_id and not (key and spec.models_url):
            raise IntegrationError("Choose a saved key, or enter a new one.")
        if key and not body.credential_id:
            await ig.check_ai_key(outside, body.provider, key)

        async def make() -> dict:
            stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
            return await n8n.create_credential(f"MailFlow · {spec.label} ({stamp})", spec.credential_type, spec.credential_data(key))

        credential, made = await _credential(spec.credential_type, body.credential_id, make)
        process = None
        try:
            process = await n8n.by_name(ig.PROCESS_NAME)
            changed = ig.with_model(process, body.provider, model, credential)
            store.backup_workflow(process["id"], json.dumps(process), admin.id, clock())
            await n8n.update_workflow(changed)
        except IntegrationError:
            if made:
                await _drop_if_unused(credential["id"], [process["id"]] if process else [])
            raise
        log.info("%s switched the AI to %s %s", admin.email, body.provider, model)
        return ig.current_model(changed)

    # Telegram alerts

    @app.post("/api/integrations/alerts/check")
    async def check_alerts(body: AlertsTest, admin: User = Depends(admin_user)):
        chat_id = body.chat_id.strip()
        if not ig.CHAT_ID.fullmatch(chat_id):
            raise IntegrationError("A chat id is a number (like 7769198902, or -100… for a group) or @channelname.")
        return {"bot": await ig.check_telegram(outside, body.token.strip(), chat_id)}

    @app.post("/api/integrations/alerts")
    async def set_alerts(body: AlertsChoice, admin: User = Depends(admin_user)):
        chat_id = body.chat_id.strip()
        if not ig.CHAT_ID.fullmatch(chat_id):
            raise IntegrationError("A chat id is a number (like 7769198902, or -100… for a group) or @channelname.")
        token = body.token.strip()
        if not body.credential_id and not token:
            raise IntegrationError("Choose a saved bot, or enter a bot token.")
        if token and not body.credential_id:
            await ig.check_telegram(outside, token, chat_id)

        async def make() -> dict:
            stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
            return await n8n.create_credential(
                f"MailFlow · Telegram ({stamp})", "telegramApi", {"accessToken": token, "baseUrl": ig.TELEGRAM_API}
            )

        credential, made = await _credential("telegramApi", body.credential_id, make)
        targets, updated = [], []
        try:
            targets.append(await n8n.by_name(ig.PROCESS_NAME))
            errors = next((w for w in await n8n.workflows() if w.get("name") == ig.ERRORS_NAME), None)
            if errors:
                targets.append(await n8n.workflow(errors["id"]))
            changed = []
            for workflow in targets:
                store.backup_workflow(workflow["id"], json.dumps(workflow), admin.id, clock())
                changed.append(ig.with_alerts(workflow, chat_id, credential))
            for workflow in changed:
                await n8n.update_workflow(workflow)
                updated.append(workflow["name"])
        except IntegrationError as error:
            if made:
                await _drop_if_unused(credential["id"], [w["id"] for w in targets])
            if updated:
                raise IntegrationError(
                    f"{', '.join(updated)} already alerts the new chat, but the rest still uses the old one ({error}). Save again to finish.",
                    error.status,
                ) from error
            raise
        log.info("%s sent the alerts to Telegram chat %s", admin.email, chat_id)
        return ig.current_alerts(changed)
