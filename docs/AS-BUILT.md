# MailFlow as built

What is actually running on `ai`, as of **19 November 2026**: the n8n workflows and, since that
day, the MailFlow web app. The design ([SYSTEM-DESIGN.md](SYSTEM-DESIGN.md)) also covers the parts
still planned; this page shows only what exists.

![MailFlow as built](images/as-built.png)

The workflow pictures below are drawn from each workflow's n8n export with
[`tools/draw_workflows.py`](../tools/draw_workflows.py), so they show the real nodes and
connections. Colours: green = trigger, cyan = data table, purple = AI, amber = decision,
grey = transform, blue = sends something out, light green = web page answer. "true"/"false"
mark the two outputs of an If node; the dashed purple line is the AI model plugged into its node.

## Collectors

One per mailbox. Each turns the provider's email into the common shape and hands it to Process
email. Both read only mail from 16 November on and leave emails unread.

![From Gmail](images/workflows/from-gmail-imap.png)

![From 22112002](images/workflows/from-22112002-imap.png)

## Process email

Skips empty runs and emails already saved, sorts newsletters and no-reply mail with rules, asks
Mistral for type, priority, mood, needs reply, summary and next step, saves the row and sends a
Telegram alert for every P1. Lesson 2.

![Process email](images/workflows/process-email.png)

## The web app

`https://mailflow.22112002.xyz`, code in [`app/`](../app/). One container (`mailflow`) on `ai`,
published to the internet through srv1 (Cloudflare tunnel and Caddy), one login per person. It
reads and updates the `MailFlow emails` table through n8n's API and sends Gmail replies through
`MailFlow · Reply`. Run, deploy and account commands: [app/README.md](../app/README.md).

![Reply](images/workflows/reply.png)

`MailFlow · Reply` takes the header `X-MailFlow-Secret` (credential `MailFlow app secret`) and
answers `{"result": "sent" | "cannot" | "not_found"}`.

## The first pages (n8n, switched off after the app went live)

Kept in n8n, inactive, for rollback. They used the `MailFlow page login` (browser login pop-up).
Lessons 5 and 6.

![Inbox page](images/workflows/inbox-page.png)

![Email page and status](images/workflows/email-page.png)

## Where the workflows are kept

| What | Where |
|---|---|
| Running workflows | n8n on `ai` (`http://ai:5678` or `https://ai.tail653118.ts.net`), tag `mailflow` |
| Workflow files (backup, re-import) | Private repo `n8n-chatbot`, folder `mailflow/`, via its `tools/n8n-sync.py pull` |
| Pictures and docs | This repo |

To redraw the pictures after a change: export the workflows (`tools/n8n-sync.py pull` in the
private repo), then run `python3 tools/draw_workflows.py <that repo>/mailflow docs/images/workflows`
here.
