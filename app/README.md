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

## Security

- One account per person; an admin adds people under **Users**. Passwords are scrypt-hashed and
  need at least 12 characters.
- 5 failed logins on one email lock it for 15 minutes; 20 from one address block that address.
  Behind srv1 the visitor's address comes from Cloudflare's `Cf-Connecting-IP`, believed only on
  requests from `TRUSTED_PROXY`.
- Sessions: HttpOnly, Secure, SameSite=Strict cookie; end after 12 h idle, 7 days, logout, a
  password change or when the user is disabled.
- Every change must carry `X-MailFlow: 1` and come from `SITE_ORIGIN`; strict Content Security
  Policy, no inline script. Email text is always shown as text.

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
