# What MailFlow needs from you

Everything here is a decision or a login only you (or the company's admins) can give. Collect
it **outside this public repo**: in a private note, or straight into n8n credentials. Never put
passwords or mailbox addresses in a file here.

## 1. Decisions (before lesson 1)

| # | Decision | Suggested default | Used in |
|---|---|---|---|
| D1 | The email types | Complaint, Question, Request, Order, Payment, Technical, Cancellation, Feedback, Marketing, Notification, Other | Lesson 2 (the AI schema) and lesson 5 (the `TYPES` filter list) |
| D2 | What each priority means for the company | P1 answer today (angry customer, service down, money taken wrongly, threat to cancel or leave, legal); P2 answer this week; P3 no rush or no answer needed. Late after 4 h (P1) and 24 h (P2) | Lesson 2 (schema) and lesson 5 (`LATE_AFTER`) |
| D3 | AI: local Mistral, or a cloud model with an API key | Local Mistral (mail stays on the server) | Lesson 2 |
| D4 | If cloud: the company agrees that email text goes to that provider | — | Before lesson 2 |
| D5 | Who may open the inbox page | **Decided 2026-11-19:** one account per person in the MailFlow web app; you are admin and add people | Web app (M11) |
| D6 | Pages reachable on the tailnet only, or also from the internet with the password | **Decided 2026-11-19:** on the internet at `https://mailflow.22112002.xyz`, behind the per-person logins | Web app (M11) |
| D7 | How long to keep emails in MailFlow | 90 days | Lesson 9 |
| D8 | Who gets the Telegram alert for every P1 email | You | Lesson 2 |

## 2. The mailbox list (private)

One line per mailbox. Keep it private.

| Short label (shown on the page) | Address | Type | Login you have | Who owns it |
|---|---|---|---|---|
| e.g. `accounts@` | … | Gmail / Microsoft 365 / IMAP / POP3 | password, app password, admin | … |

How to tell the type: ask the IT person or the hosting company. If you only know the address,
the mail settings in Outlook or a phone usually show the server (imap.… or pop.…).

## 3. Logins per type

### IMAP mailboxes (lesson 4)

- Server name (e.g. `mail.example.co.sz`), port (usually **993**, SSL on).
- Username (usually the full address) and password, or an **app password** if the provider
  offers one (safer: it can be revoked without changing the real password).

### Old POP3 mailboxes (lesson 3)

- The work mailbox already reaches n8n through `mail-poll`; nothing new needed for it.
- Each **additional** POP3 mailbox needs its own `mail-poll` on the server: server name, user,
  password. Setting that up needs `sudo` on `ai`; we do it together.

### Gmail / Google Workspace (lesson 7)

- Whether it is a **Google Workspace** account (company domain) or a plain **@gmail.com**.
- Someone who can create a **Google Cloud project** with that account (for Workspace: an admin,
  or a user allowed to create projects).
- Before the lesson: a decision on the **HTTPS address** Google will send you back to after
  login (design, section 6). We settle it together; it needs a small server change.

### Microsoft 365 (lesson 8)

- A **Microsoft 365 / Entra administrator** who will:
  1. register an app ("MailFlow") in Microsoft Entra;
  2. give it the **Mail.Read** application permission and grant admin consent;
  3. restrict it to the MailFlow mailboxes only;
  4. give you the **tenant ID**, **client ID** and a **client secret** (with its expiry date:
     put a reminder in your calendar a month before).

## 4. Server changes (I prepare them, you run them with `sudo`)

| Change | Why | When |
|---|---|---|
| `OLLAMA_KEEP_ALIVE=30m` in `/opt/automation/.env`, then `sudo bash deploy.sh` | Mistral stays loaded between emails (saves ~70 s each after a quiet gap) | Before go-live |
| `N8N_DATA_TABLES_MAX_SIZE_BYTES=1073741824` (1 GiB) | Room for 90 days of mail at up to 1,000 a day | Once real volume is known |
| The MailFlow web app on `ai`: `/opt/mailflow`, `.env`, `docker compose up -d --build` ([app/README.md](../app/README.md)) | The page staff work in | 2026-11-19 |
| `mailflow.22112002.xyz` on srv1: DNS route, tunnel ingress line, Caddy block to `10.0.0.31:3100` | Publishes the web app through Cloudflare | 2026-11-19 |
| HTTPS address for Google sign-in | Google refuses `http://ai:5678` | Before lesson 7 |
| One `mail-poll` per extra POP3 mailbox | POP3 servers can't push | Lesson 3, if there are more |

## 5. Your time

| Phase | Lessons | Rough time |
|---|---|---|
| First mailbox working | 1-3 | 2-3 hours |
| IMAP mailboxes | 4 | 30 min, then 5 min per extra mailbox |
| Inbox page | 5-6 | 2 hours |
| Gmail + Microsoft | 7-8 | 1-2 hours each, mostly waiting on admins |
| Go live | 9-10 | 1 hour |

These are estimates for a first time through. Ask me at any step; each lesson ends with a check
that proves the step works before you move on.
