# What MailFlow needs from you

Everything here is a decision or a login only you (or the company's admins) can give. Collect
it **outside this public repo**: in a private note, or straight into n8n credentials. Never put
passwords or mailbox addresses in a file here.

## 1. Decisions (before lesson 1)

| # | Decision | Suggested default | Used in |
|---|---|---|---|
| D1 | The categories | Billing, Support, Sales, Internal, Newsletter, Other | Lesson 2 (the AI schema) and lesson 5 (the filter list) |
| D2 | What "High urgency" means for the company | "Needs an answer today" | Lesson 2 |
| D3 | AI: local Mistral, or a cloud model with an API key | Local Mistral (mail stays on the server) | Lesson 2 |
| D4 | If cloud: the company agrees that email text goes to that provider | — | Before lesson 2 |
| D5 | Who may open the inbox page | One shared username and password for v1 | Lesson 5 |
| D6 | Pages reachable on the tailnet only, or also from the internet with the password | Tailnet only | Lesson 5 |
| D7 | How long to keep emails in MailFlow | 90 days | Lesson 9 |
| D8 | Who gets the Telegram alerts for urgent and negative emails | You | Lesson 2 |

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
| A Caddy rule on srv1 blocking `/webhook/mailflow*` from the internet (if D6 = tailnet only) | The pages show company email | Lesson 5 |
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
