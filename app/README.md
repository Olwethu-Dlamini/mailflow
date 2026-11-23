# MailFlow web app

The page staff work in, at `https://mailflow.22112002.xyz`. n8n stays the engine: it collects the
mail, sorts it with Mistral and sends Gmail replies. This app only shows the `MailFlow emails`
data table, changes an email's status, and asks `MailFlow · Reply` to send a reply.

```
browser ──https──▶ Cloudflare ──tunnel──▶ srv1 Caddy ──▶ ai:3100 MailFlow app ──▶ n8n (API + Reply webhook)
```

| Piece | Where |
|---|---|
| Accounts and sessions | SQLite in the `mailflow_data` volume (`/data/mailflow.db`) |
| Emails | n8n data table, read and updated through n8n's API (key in `.env`, never sent to the browser) |
| Replies | `POST http://n8n:5678/webhook/mailflow/reply` with header `X-MailFlow-Secret` (n8n credential `MailFlow app secret`) |

## The page

![The MailFlow page](../docs/images/app/queue.png)

Three panes, after Front, Help Scout and Superhuman: the sidebar (search, views with counts,
mailboxes, refresh state, the account menu; it collapses to icons with `[`), the queue, and the
open email (action bar, AI card, the message, the reply box). Light and dark follow the system.
On a phone the sidebar is a drawer and one pane shows at a time.

| Key | Does | Key | Does |
|---|---|---|---|
| `J` / `K` | next / previous email | `E` | Done |
| `/` | search the list | `W` | replied, waiting on the customer |
| `1`–`5` | Needs reply, P1, Waiting, Done, Everything | `U` | reopen |
| `Esc` | close the email | `R` | write a reply (`Ctrl`+`Enter` sends) |
| `?` | all shortcuts | `Z` | undo the last status change |

Marking an email Done or Waiting opens the next one in the list, with Undo in the toast.

## Speed

Every request to the live site crosses Cloudflare, srv1 and ai (about 450 ms there and back), and
a read of the list from n8n takes a second or more. So:

- **The server keeps the 30-day list in memory** (`n8n.py`): read when the app starts, served as is
  for 15 s, then served at once while a fresh copy is read in the background (up to 6 h old; the
  sidebar says *Updating from n8n…* and the page asks again after 2 s). Opening an email and
  status changes use the rows in memory; a change updates them in place.
- **The page arrives with what it needs**: the account, the list and the open email are embedded
  in `GET /` as JSON, so the list shows after one round trip. CSS and JS are stamped with a hash
  of their contents and kept by the browser (and Cloudflare) for a year; a deploy changes the hash.
- **The page does not wait for the server**: an email shows the moment it is picked (the list
  holds all but its text, which follows), the next ones are fetched ahead, status changes and
  Undo apply at once and are saved in the background, the working views are loaded ahead, and
  long lists render 80 rows at a time.

Measured on the laptop with `DEMO_N8N_MS=800 uv run python ../deck/demo_server.py` and a 450 ms
round trip emulated in Chrome (23 Nov 2026):

| Step | Before | After |
|---|---|---|
| Open the page: list shown | 1931 ms | 550 ms |
| Open an email (text follows one round trip later) | 867 ms | 20–50 ms |
| J to the next email | 880 ms | 20–40 ms |
| E: Done, next email open | 2485 ms | 40–80 ms |
| Z: Undo | 3314 ms | 15–40 ms |
| Switch to P1 | 495 ms | 30–50 ms |
| Draw a 3,000-email list | 2.7 s | 74 ms |

Lighthouse (desktop, same 450 ms round trip): sign-in page and queue both 96 performance,
100 accessibility, 100 best practices, 100 SEO (before: 96/91, 95, 96, 90). The rest of the
performance score is the two round trips (page, then CSS) a first visit cannot avoid.

## Security

- One account per person; an admin adds people under **Users**. Passwords are scrypt-hashed and
  need at least 12 characters.
- **Continue with Google** (optional, below) opens a session only for an account an admin already
  added: never a new account. The first Google sign-in links the account by its verified email;
  after that Google's account id (`sub`) must match, so another Google account with that address
  cannot take it over. A disabled account is refused either way.
- 5 failed logins on one email lock it for 15 minutes; 20 from one address block that address.
  Behind srv1 the visitor's address comes from Cloudflare's `Cf-Connecting-IP`, believed only on
  requests from `TRUSTED_PROXY`.
- Sessions: HttpOnly, Secure, SameSite=Strict cookie; end after 12 h idle, 7 days, logout, a
  password change or when the user is disabled.
- Every change must carry `X-MailFlow: 1` and come from `SITE_ORIGIN`; strict Content Security
  Policy, no inline script. Email text is always shown as text.

## Continue with Google (optional)

Off until both settings are in `.env`. To turn it on:

1. Google Cloud console → **APIs & Services → Credentials → Create credentials → OAuth client ID**,
   type **Web application** (the n8n Gmail client can stay as it is; this is a second client).
2. **Authorised redirect URI**: `https://mailflow.22112002.xyz/auth/google/callback`
   (`SITE_ORIGIN` + `/auth/google/callback`; for the laptop also `http://127.0.0.1:8770/auth/google/callback`).
3. The OAuth consent screen asks only for `openid email profile`. Publish it, or while it is in
   *Testing* add each person as a test user.
4. Put `GOOGLE_CLIENT_ID=…` and `GOOGLE_CLIENT_SECRET=…` in `/opt/mailflow/app/.env` and run the
   deploy script again. The sign-in page then shows the button.

People still need an account: an admin adds them under **Users** with the email address of their
Google account. With Google on, the first password may be left empty: that person can only sign
in with Google (an admin can set a password later).

How it works: `GET /auth/google` stores a one-time state (PKCE verifier and nonce, 10 minutes) and
sends the browser to Google with the state in a SameSite=Lax cookie; `/auth/google/callback`
checks the state against that cookie, swaps the code for the ID token directly with Google, checks
issuer, audience, expiry, nonce and a verified email, and opens the normal session.

## Run on the laptop (against n8n on `ai`)

```bash
cd app
uv sync
export N8N_URL=http://ai:5678 N8N_API_KEY=… MAILFLOW_TABLE_ID=HwHXJgR6FLgD8aeS N8N_REPLY_SECRET=… \
       DB_PATH=/tmp/mailflow.db COOKIE_SECURE=false TRUSTED_PROXY=none SITE_ORIGIN=http://127.0.0.1:8770
uv run mailflow user add --email you@example.com --name You --admin
uv run uvicorn --factory mailflow.web:main_app --port 8770
uv run pytest
```

## Deploy on `ai`

First stage the settings as `~/mailflow.env` on `ai` (mode 600, values as in `.env.example`;
`TRUSTED_PROXY=10.0.0.10`, srv1's LAN address). Then, on `ai`:

```bash
wget -qO /tmp/ai-deploy.sh https://raw.githubusercontent.com/Olwethu-Dlamini/mailflow/main/app/deploy/ai-deploy.sh
sudo bash /tmp/ai-deploy.sh
```

[`deploy/ai-deploy.sh`](deploy/ai-deploy.sh) clones (or pulls) the repo into `/opt/mailflow`,
moves the settings to `/opt/mailflow/app/.env` (root, 600), builds and starts the container, waits
for it to be healthy and, when there are no accounts yet, asks for your admin account.

The port is published on ai's LAN address only (`10.0.0.31:3100`, change with `MAILFLOW_BIND`),
so the app is reached through srv1 and Cloudflare, not around them. The container runs read-only,
without Linux capabilities, as a non-root user, in 128 MB.

Update later: run the same script again.

Accounts from the server: `sudo docker compose exec mailflow mailflow user list|reset|disable|enable --email …`.

## Publish through srv1

Same path as `n8n.22112002.xyz` (Homelab repo, `n8n-public-webhooks.md`). On srv1:

```bash
wget -qO /tmp/srv1-publish.sh https://raw.githubusercontent.com/Olwethu-Dlamini/mailflow/main/app/deploy/srv1-publish.sh
sudo bash /tmp/srv1-publish.sh
```

[`deploy/srv1-publish.sh`](deploy/srv1-publish.sh) backs up both configs, adds the tunnel ingress
line above the 404 catch-all and this Caddy block, validates both (and restores the backups if
either fails), adds the DNS record, then reloads Caddy and restarts the tunnel:

```caddyfile
mailflow.22112002.xyz:80 {
	reverse_proxy 10.0.0.31:3100
}
```
