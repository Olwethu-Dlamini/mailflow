#!/usr/bin/env python3
"""Export MailFlow's n8n workflows into n8n/ without anything tied to one installation.

Usage (from the repository root, with the n8n API reachable):
    N8N_URL=http://ai:5678 N8N_API_KEY=... MAILFLOW_TABLE_ID=... python3 tools/export_n8n.py

What is replaced, so the files can be imported into another n8n (n8n/README.md says how):
- the emails data table's id            -> MAILFLOW_TABLE_ID
- the Process email and Errors ids      -> PROCESS_EMAIL_WORKFLOW_ID, ERRORS_WORKFLOW_ID
- the Telegram chat id                   -> YOUR_TELEGRAM_CHAT_ID
- credential ids (names are kept, so n8n asks you to pick the matching credential)
Only the name, nodes, connections and settings are written: no owner, sharing, version or saved
state (staticData). Credentials themselves are never exported by this script.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "n8n"
WORKFLOWS = {  # file name -> workflow name in n8n
    "process-email.json": "MailFlow · Process email",
    "reply.json": "MailFlow · Reply",
    "errors.json": "MailFlow · Errors",
    "cleanup.json": "MailFlow · Cleanup",
    "collector-gmail-imap.json": "MailFlow · From Gmail (IMAP)",
}


def get(path: str, **params) -> dict:
    url = f"{os.environ['N8N_URL'].rstrip('/')}/api/v1{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"X-N8N-API-KEY": os.environ["N8N_API_KEY"]})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def scrub(value, replace: dict[str, str]):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "credentials" and isinstance(item, dict):
                out[key] = {kind: {"name": cred.get("name", "")} for kind, cred in item.items()}
            elif key == "chatId" and isinstance(item, str):
                out[key] = "YOUR_TELEGRAM_CHAT_ID"
            else:
                out[key] = scrub(item, replace)
        return out
    if isinstance(value, list):
        return [scrub(item, replace) for item in value]
    if isinstance(value, str):
        for old, new in replace.items():
            value = value.replace(old, new)
    return value


def main() -> int:
    table_id = os.environ["MAILFLOW_TABLE_ID"]
    listed = {w["name"]: w["id"] for w in get("/workflows", limit=250)["data"]}
    missing = [name for name in WORKFLOWS.values() if name not in listed]
    if missing:
        print("not found in n8n:", ", ".join(missing), file=sys.stderr)
        return 1
    replace = {
        table_id: "MAILFLOW_TABLE_ID",
        listed["MailFlow · Process email"]: "PROCESS_EMAIL_WORKFLOW_ID",
        listed["MailFlow · Errors"]: "ERRORS_WORKFLOW_ID",
    }
    OUT.mkdir(exist_ok=True)
    for file, name in WORKFLOWS.items():
        workflow = get(f"/workflows/{listed[name]}")
        kept = {key: workflow[key] for key in ("name", "nodes", "connections", "settings")}
        (OUT / file).write_text(json.dumps(scrub(kept, replace), indent=2, ensure_ascii=False) + "\n")
        print("wrote", OUT / file)
    table = next(t for t in get("/data-tables", limit=50)["data"] if t["id"] == table_id)
    columns = [{"name": c["name"], "type": c["type"]} for c in sorted(table["columns"], key=lambda c: c["index"])]
    (OUT / "data-table.json").write_text(json.dumps({"name": table["name"], "columns": columns}, indent=2) + "\n")
    print("wrote", OUT / "data-table.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
