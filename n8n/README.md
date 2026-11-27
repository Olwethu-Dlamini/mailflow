# The n8n side of MailFlow

These are the n8n workflows a MailFlow installation needs, exported from the running system with
[`tools/export_n8n.py`](../tools/export_n8n.py). Nothing tied to one installation is in them:
credential ids, the data table's id, workflow ids and the Telegram chat are placeholders, and no
credential (password, key, token) is ever exported.

| File | Workflow | What it does |
|---|---|---|
| `data-table.json` | (data table) `MailFlow emails` | The columns every email row has; the app reads and updates this table |
| `process-email.json` | MailFlow · Process email | Skips emails already saved, sorts obvious mail by rules and the rest with the AI, saves the row, sends a Telegram alert for P1 |
| `reply.json` | MailFlow · Reply | Webhook the app calls to answer a Gmail email in its own conversation |
| `errors.json` | MailFlow · Errors | Telegram message when any MailFlow workflow fails |
| `cleanup.json` | MailFlow · Cleanup | Every night at 02:00, deletes rows older than 90 days |
| `collector-gmail-imap.json` | MailFlow · From Gmail (IMAP) | An example collector; usually you add mailboxes from the app instead (Integrations) |

## Setting up a new n8n (version 2.x)

1. **Data table.** In n8n, create a data table named `MailFlow emails` with the columns in
   `data-table.json`, in that order and with those types (`received_at` is a date, `needs_reply` a
   boolean, the rest strings). Note its id (in the address bar): it is `MAILFLOW_TABLE_ID` in the
   app's `.env`.
2. **Credentials** (n8n → Credentials), names as you like:
   - *Header Auth* with header name `X-MailFlow-Secret` and a long random value: the app's
     `N8N_REPLY_SECRET`.
   - *Telegram* (a bot from @BotFather) for alerts; optional.
   - *Ollama* pointing at your Ollama server, or skip it and pick a cloud AI later in the app.
   - *Gmail OAuth2*, only if a Gmail mailbox should reply through n8n (otherwise the app sends
     replies over SMTP, set up under Integrations).
3. **Import in this order** (n8n → Workflows → Import from file): `errors.json`, `process-email.json`,
   `reply.json`, `cleanup.json`. After each import, open every node that shows a credential warning
   and choose your credential, and replace the placeholders:
   - `MAILFLOW_TABLE_ID` in every data-table node (choose the table from the list),
   - `ERRORS_WORKFLOW_ID` in each workflow's settings (Error workflow: *MailFlow · Errors*),
   - `PROCESS_EMAIL_WORKFLOW_ID` in collectors (the *Process email* node: choose the workflow),
   - `YOUR_TELEGRAM_CHAT_ID` in the two Telegram nodes.
4. **Switch on** Errors, Reply and Cleanup (Process email runs when a collector calls it).
5. **API key** for the app: n8n → Settings → n8n API → create a key (with workflow, credential and
   data-table scopes, or none). It is `N8N_API_KEY` in the app's `.env`; the deploy script checks
   what it may do.
6. **Mailboxes**: sign in to MailFlow as an admin and add them under Integrations. The app builds
   each collector the same way as `collector-gmail-imap.json`.

## Updating these files

Run the export again after changing a workflow in n8n, check the diff for anything that should not
be public, and commit:

```bash
N8N_URL=http://ai:5678 N8N_API_KEY=… MAILFLOW_TABLE_ID=… python3 tools/export_n8n.py
```
