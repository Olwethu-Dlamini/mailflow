# MailFlow and personal data

This page is for a company that runs MailFlow or has it run for them. It says what personal data
MailFlow keeps, where, for how long, who can see it and who else may receive it. It describes the
software as it is today. It is not legal advice: check your own duties under POPIA, GDPR or any
other law that applies to you.

MailFlow has two parts that hold data:

- **n8n**, the engine. It collects the mail, sorts it and keeps one row per email in a data table.
- **The MailFlow web app**, the page your team works in. It keeps accounts and the team's notes in
  its own SQLite file.

MailFlow reads your mailboxes. It does not move, delete or mark mail in them
([SYSTEM-DESIGN.md](SYSTEM-DESIGN.md) §1 and §7). Your mailboxes stay the original; MailFlow keeps
a working copy.

## What is kept, and where

### In n8n: the `MailFlow emails` data table

One row per email ([SYSTEM-DESIGN.md](SYSTEM-DESIGN.md) §4):

| Data | Personal data in it |
|---|---|
| `from_name`, `from_address` | The sender's name and email address |
| `subject` | Whatever the sender wrote |
| `body` | The first 4,000 characters of the email as plain text (HTML is turned into text). Attachments are not kept |
| `message_id`, `mailbox`, `source`, `received_at` | Which mailbox it came to, and when |
| `summary`, `next_step`, `type`, `sender`, `priority`, `needs_reply` | What the AI (or a rule) made of the email: a one-line summary, a next step and labels |
| `status`, `sorted_by` | Open, waiting or done; whether a rule, the AI or a person set the labels |

The 4,000-character cut is made by the collectors (the `slice(0, 4000)` in
`app/src/mailflow/integrations.py` and in lessons 2, 4 and 7).

The data table lives in n8n's own database, so the server's backup of n8n also holds it.

### In n8n: credentials

n8n keeps these in its credentials store, encrypted with n8n's own key:

- the IMAP password (or app password) of each mailbox, and the Gmail or Microsoft 365 sign-in;
- the API key of a cloud AI provider, if you use one;
- the Telegram bot token for alerts;
- the shared secret the app uses to call the Reply workflow.

The app hands these to n8n and does not keep them (`app/src/mailflow/vault.py`, `app/README.md`
"Integrations").

### In n8n: run history

n8n can keep the input and output of each workflow run, and that includes email text. How long
it keeps them is an n8n setting on your server, not a MailFlow one. Look at n8n's execution
settings (for example `EXECUTIONS_DATA_SAVE_ON_SUCCESS` and `EXECUTIONS_DATA_MAX_AGE`) and set
them to match your retention.

### In the app: the SQLite file

`/data/mailflow.db` in the app's Docker volume (`app/src/mailflow/store.py`):

| Table | What it holds |
|---|---|
| `users` | Each team member's email address, name, password hash (scrypt), admin yes/no, active yes/no, and the Google account id if they sign in with Google |
| `sessions` | A SHA-256 hash of each session token, the user, and when it started and was last used |
| `login_failures` | Failed sign-ins, keyed by the email typed and by the visitor's IP address |
| `google_starts` | A Google sign-in in progress (state, PKCE verifier, nonce) |
| `assignments` | Which team member has which email (by row id, not by content) |
| `activity` | Who did what to an email and when: took it, replied, changed its status, corrected a label. The reply text itself is not kept here |
| `mailboxes` | SMTP settings for replies, with the SMTP password sealed with `MAILFLOW_SECRET_KEY` (Fernet). A copy of the database alone does not reveal the password |
| `n8n_backups` | Copies of the n8n workflows the app changed (the last 50). These hold settings such as the Telegram chat id, not email text |

### In the app's memory

The app keeps the last 30 days of emails in memory so the page is fast (`app/src/mailflow/n8n.py`).
This copy goes away when the app stops.

### In the app's log

The app writes short lines to its container log: which team member changed an email's status or
replied (by email address and row id), and which admin connected a mailbox (sign-in name and
server). No email text. Docker keeps at most three log files of 10 MB each
(`app/docker-compose.yml`), so older lines drop off on their own.

### In the browser

The signed-in page is sent with `Cache-Control: no-store`, so the browser does not keep a copy of
the queue (`app/src/mailflow/web.py`). The session cookie is HttpOnly and ends when the session
does.

## How long it is kept

| Data | Kept for | Done by |
|---|---|---|
| Emails in the data table | 90 days from `received_at` | The `MailFlow · Cleanup` workflow in n8n, nightly at 02:00 ([AS-BUILT.md](AS-BUILT.md), [lesson 9](lessons/09-errors-and-cleanup.md)). The number of days can be changed in that workflow |
| Who has which email, and the activity log | 120 days | The app (`NOTES_SECONDS` in `store.py`) |
| Sessions | 7 days at most; also ended after 12 hours without use, at sign-out, at a password change and when an account is disabled | The app (`auth.py`) |
| Failed sign-ins | 24 hours | The app (`auth.py`, `_prune`) |
| Google sign-ins in progress | 10 minutes | The app (`auth.py`) |
| Team accounts | Until removed by hand. The page can disable an account but not delete it | — |
| SMTP settings | Until an admin switches SMTP off for that mailbox | — |
| n8n credentials | Until removed in n8n, or until an admin removes a mailbox the app made | — |
| Backups of the server | As long as your backup keeps them | Your backup setup |

The app removes its own old rows when someone signs in (at most once a minute, `_prune` in
`auth.py`). If nobody signs in for a while, old rows wait until the next sign-in; an expired
session still cannot be used. The 90 days only hold if `MailFlow · Cleanup` is active in n8n.

## Who sees what

- **Every signed-in team member sees every email** MailFlow has collected, from every connected
  mailbox. There are no per-mailbox or per-person limits on reading. The "Mine" view is a filter,
  not a restriction.
- Every team member can change an email's status, take it, correct its labels, reply to it and
  read its activity log. Staff can only take an email nobody has, or let theirs go.
- **Admins** also add, disable and reset accounts, give emails to people, and manage the
  integrations: mailboxes, SMTP replies, the AI provider and the Telegram alerts.
- **Whoever runs the server** (you, or the owner if they host it for you) can read the n8n data
  table, n8n's run history, the SQLite file and the logs.
- Nobody can sign up on their own. An admin adds each account
  ([app/README.md](../app/README.md#security)).

## Who else receives data

Which outside services see data depends on how MailFlow is set up.

| Service | When | What it receives |
|---|---|---|
| The AI provider you choose (Groq, OpenAI, Mistral cloud or Anthropic) | Only when you pick a cloud provider under Integrations → AI | For each email the rules do not catch: the sender's name and address, the subject and the first 4,000 characters of the body. With Mistral on your own server (Ollama) nothing leaves the server |
| Telegram | When alerts are set up | For each P1 email: the mailbox, the topic, the sender's name and address, the subject, the summary and the next step. For each workflow error: the workflow, the failing step and the error message |
| Google | When "Continue with Google" is on | The sign-in of team members who use it. Google sends back their name, email address and account id |
| Google, Microsoft or your mail host | Always, for the mailboxes you connect | They already hold the mail. MailFlow signs in to read it, and replies leave through Gmail or through the SMTP server you set up |
| Cloudflare | In the setup where the owner hosts MailFlow for you, the page is reached through a Cloudflare tunnel | Cloudflare carries all page traffic, including email text shown on the page and sign-in details, and sees it unencrypted between its edge and the tunnel |

If you install MailFlow yourself, you choose the hosting and whether a service like Cloudflare sits
in front of it.

## Security controls in short

Passwords are scrypt-hashed and at least 12 characters long. Failed sign-ins lock an email after 5
tries and an IP address after 20. Session cookies are HttpOnly, Secure and SameSite=Strict. Changes
must come from the site's own origin. The page runs under a strict Content Security Policy and
shows email text only as text. The container runs read-only, as a non-root user, without Linux
capabilities. The full list is in [app/README.md](../app/README.md#security).

## What you need to do

- **If the owner hosts MailFlow for you**, they process your mail on your behalf. Put a data
  processing agreement in place with them before you connect a mailbox.
- **Choose where the AI runs.** To keep email text on your own server, use "Mistral on your own
  server (Ollama)" under Integrations → AI. A cloud provider receives the text described above;
  check its terms first.
- **Decide on retention.** Change the 90 days in `MailFlow · Cleanup` if your policy needs another
  period, keep the workflow active, and set n8n's run history and your backups to match.
- **Answer requests from the people who email you** (a subject access request, or a request to
  delete). There is **no export or delete button in MailFlow yet**. The operator does it by hand
  in n8n:
  - *Access*: open the `MailFlow emails` data table in n8n and filter on `from_address`. The rows
    are everything MailFlow holds about that sender's emails.
  - *Deletion*: delete those rows in the same table. Also remove the person's mail from n8n's run
    history if it is kept, and note that server backups still hold it until they expire. The
    app's `assignments` and `activity` rows for a deleted email hold no email content and go after
    120 days.
  - The original mail stays in your mailboxes. MailFlow does not touch it; deal with it there.
- **Answer requests from your team members.** Their account is in the app's SQLite file. The page
  can disable an account but not delete it; deleting one means editing the SQLite file on the
  server.
- **Limit who gets an account.** Everyone with an account sees every email (above). Disable
  accounts when people leave.
- **Keep `MAILFLOW_SECRET_KEY` and the server's `.env` safe**, and keep the n8n database in your
  backup.
