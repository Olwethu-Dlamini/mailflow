#!/usr/bin/env bash
# MailFlow web app on ai: first deploy or update. Run on ai: sudo bash ai-deploy.sh
# Settings: for a first deploy, stage them as ~/mailflow.env (mode 600, see ../.env.example);
# this moves them to /opt/mailflow/app/.env (root, 600) and shreds the staged copy.
set -euo pipefail

STAGED=/home/${SUDO_USER:-oll}/mailflow.env
DIR=/opt/mailflow
NET=automation_default

[ "$(id -u)" = 0 ] || { echo "Run with sudo."; exit 1; }
docker network inspect "$NET" >/dev/null 2>&1 || { echo "Docker network $NET not found:"; docker network ls; exit 1; }

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
  # A copy of this script kept elsewhere (like ~/mailflow-deploy.sh) hands over to the version just pulled.
  if [ "$(realpath "$0")" != "$DIR/app/deploy/ai-deploy.sh" ]; then exec bash "$DIR/app/deploy/ai-deploy.sh"; fi
else
  if ss -ltn | grep -q ':3100 '; then echo "Port 3100 is already in use."; exit 1; fi
  git clone https://github.com/Olwethu-Dlamini/mailflow.git "$DIR"
fi

if [ -L "$STAGED" ]; then echo "$STAGED is a symlink: refusing to read it as root."; exit 1; fi
if [ -f "$STAGED" ]; then
  # New settings without a key keep the key already in use: a new one would lock the saved SMTP passwords.
  if [ -f "$DIR/app/.env" ] && ! grep -q '^MAILFLOW_SECRET_KEY=..*' "$STAGED"; then
    (
      umask 077
      tmp=$(mktemp "$STAGED.XXXXXX")  # a fresh file: root never writes through a planted symlink
      { grep -v '^MAILFLOW_SECRET_KEY=' "$STAGED" || true; grep '^MAILFLOW_SECRET_KEY=..*' "$DIR/app/.env" || true; } > "$tmp"
      mv -f "$tmp" "$STAGED"
    )
  fi
  install -m 600 -o root -g root "$STAGED" "$DIR/app/.env"
  shred -u "$STAGED"
fi
[ -f "$DIR/app/.env" ] || { echo "No $DIR/app/.env: stage it as $STAGED first."; exit 1; }

# Seals the SMTP passwords the app keeps (Integrations): made once, then kept. Losing it means
# entering those passwords again.
if ! grep -q '^MAILFLOW_SECRET_KEY=..*' "$DIR/app/.env"; then
  (
    umask 077
    key=$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')
    { grep -v '^MAILFLOW_SECRET_KEY=' "$DIR/app/.env" || true; echo "MAILFLOW_SECRET_KEY=$key"; } > "$DIR/app/.env.new"
    mv "$DIR/app/.env.new" "$DIR/app/.env"
  )
  echo "==> Made MAILFLOW_SECRET_KEY in $DIR/app/.env"
fi

cd "$DIR/app"
docker compose up -d --build

echo "==> Waiting for the app to report healthy"
for _ in $(seq 1 30); do
  state=$(docker inspect -f '{{.State.Health.Status}}' mailflow 2>/dev/null || echo starting)
  [ "$state" = healthy ] && break
  sleep 2
done
docker compose ps
curl -fsS http://10.0.0.31:3100/healthz && echo
docker stats --no-stream --format 'memory: {{.MemUsage}}' mailflow

if [ -z "$(docker compose exec -T mailflow mailflow user list)" ]; then
  echo
  echo "==> No accounts yet: your admin account (the password is asked twice, at least 12 characters)"
  read -rp "Your email address: " email
  docker compose exec mailflow mailflow user add --email "$email" --name Olwethu --admin
fi

# Keep the copy in your home folder (sudo bash ~/mailflow-deploy.sh) the same as this one.
copy=$(mktemp "/home/${SUDO_USER:-oll}/.mailflow-deploy.XXXXXX")
install -m 755 -o "${SUDO_USER:-oll}" "$DIR/app/deploy/ai-deploy.sh" "$copy"
mv -f "$copy" "/home/${SUDO_USER:-oll}/mailflow-deploy.sh"  # rename replaces a symlink, never follows it

echo
echo "==> What the app's n8n API key may do (Integrations needs workflows and credentials)"
docker compose exec -T mailflow python - <<'PY' || true
import os
import httpx
base = os.environ.get("N8N_URL", "http://n8n:5678").rstrip("/") + "/api/v1"
headers = {"X-N8N-API-KEY": os.environ["N8N_API_KEY"]}
checks = (("the emails table", f"/data-tables/{os.environ['MAILFLOW_TABLE_ID']}/rows?limit=1"),
          ("workflows", "/workflows?limit=1"), ("credentials", "/credentials?limit=1"))
refused = False
for name, path in checks:
    try:
        code = httpx.get(base + path, headers=headers, timeout=15).status_code
    except httpx.HTTPError as error:
        code = error.__class__.__name__
    refused |= code != 200
    print(f"   {name}: {'ok' if code == 200 else f'refused ({code})'}")
if refused:
    print("   In n8n: Settings > n8n API > create a key with those scopes (or no scopes), put it in")
    print("   N8N_API_KEY in /opt/mailflow/app/.env, then run this script again.")
PY

echo
echo "==> Through Cloudflare"
curl -fsS -o /dev/null -w "   https://mailflow.22112002.xyz answers %{http_code}\n" https://mailflow.22112002.xyz/healthz || echo "   not reachable from here: check srv1 (deploy/srv1-publish.sh)"

echo
echo "==> Left for you, in a browser"
if grep -q '^GOOGLE_CLIENT_ID=..*' "$DIR/app/.env"; then
  echo "   - Continue with Google is on."
else
  echo "   - Continue with Google is off (optional): app/README.md, 'Continue with Google'."
fi
echo "   - Google Cloud console: publish the OAuth consent screen, or the Gmail login in n8n expires every 7 days."
echo "   - Sign in as an admin: account menu > Integrations, to connect mailboxes, SMTP replies, the AI and alerts."
