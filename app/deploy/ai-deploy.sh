#!/usr/bin/env bash
# MailFlow web app: first deploy or update, on the host that runs n8n's Docker stack (ai, for the
# owner's own copy). Run from your own account: sudo bash ai-deploy.sh
# Settings: for a first deploy, stage them as ~/mailflow.env (mode 600, see ../.env.example);
# this moves them to $MAILFLOW_DIR/app/.env (root, 600) and shreds the staged copy.
#
# Optional, on the command line (sudo MAILFLOW_DIR=/srv/mailflow bash ai-deploy.sh):
#   MAILFLOW_REPO  the repository to clone on a first deploy (default: the owner's GitHub repo)
#   MAILFLOW_DIR   where it is cloned (default /opt/mailflow)
#   MAILFLOW_SITE  the public address checked at the end (default: SITE_ORIGIN in the settings)
# MAILFLOW_BIND, MAILFLOW_PORT and AUTOMATION_NETWORK are read like docker compose reads them: from
# the command line, else from the settings, else 10.0.0.31, 3100 and automation_default.
set -euo pipefail

STAGED=/home/${SUDO_USER:-oll}/mailflow.env
DIR=${MAILFLOW_DIR:-/opt/mailflow}
DIR=${DIR%/}
REPO=${MAILFLOW_REPO:-https://github.com/Olwethu-Dlamini/mailflow.git}

[ "$(id -u)" = 0 ] || { echo "Run with sudo."; exit 1; }
if [ -L "$STAGED" ]; then echo "$STAGED is a symlink: refusing to read it as root."; exit 1; fi

# NAME's value in the staged settings, else in the installed .env, else $2. Read as text, never run.
file_setting() {
  local file value=""
  for file in "$STAGED" "$DIR/app/.env"; do
    if [ -z "$value" ] && [ -f "$file" ]; then value=$(sed -n "s/^$1=//p" "$file" | tail -n 1); fi
  done
  value=${value%$'\r'}
  case $value in \"*\" | \'*\') value=${value:1:${#value}-2} ;; esac
  printf '%s\n' "${value:-$2}"
}

NET=${AUTOMATION_NETWORK:-$(file_setting AUTOMATION_NETWORK automation_default)}
BIND=${MAILFLOW_BIND:-$(file_setting MAILFLOW_BIND 10.0.0.31)}
PORT=${MAILFLOW_PORT:-$(file_setting MAILFLOW_PORT 3100)}
SITE=${MAILFLOW_SITE:-$(file_setting SITE_ORIGIN "")}
# docker compose gets the same values the checks below use.
export AUTOMATION_NETWORK=$NET MAILFLOW_BIND=$BIND MAILFLOW_PORT=$PORT

docker network inspect "$NET" >/dev/null 2>&1 || { echo "Docker network $NET not found:"; docker network ls; exit 1; }

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
  # A copy of this script kept elsewhere (like ~/mailflow-deploy.sh) hands over to the version just pulled.
  if [ "$(realpath "$0")" != "$(realpath "$DIR/app/deploy/ai-deploy.sh")" ]; then exec bash "$DIR/app/deploy/ai-deploy.sh"; fi
else
  if ss -ltn | grep -q ":$PORT "; then echo "Port $PORT is already in use."; exit 1; fi
  git clone "$REPO" "$DIR"
fi

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
curl -fsS "http://$BIND:$PORT/healthz" && echo
docker stats --no-stream --format 'memory: {{.MemUsage}}' mailflow

if [ -z "$(docker compose exec -T mailflow mailflow user list)" ]; then
  echo
  echo "==> No accounts yet: your admin account (the password is asked twice, at least 12 characters)"
  read -rp "Your name: " name
  read -rp "Your email address: " email
  docker compose exec mailflow mailflow user add --email "$email" --name "$name" --admin
fi

# Keep the copy in your home folder (sudo bash ~/mailflow-deploy.sh) the same as this one; only when
# run through sudo from your own account (run directly as root there is no such folder to update).
if [ -n "${SUDO_USER:-}" ] && [ -d "/home/$SUDO_USER" ]; then
  copy=$(mktemp "/home/$SUDO_USER/.mailflow-deploy.XXXXXX")
  install -m 755 -o "$SUDO_USER" "$DIR/app/deploy/ai-deploy.sh" "$copy"
  mv -f "$copy" "/home/$SUDO_USER/mailflow-deploy.sh"  # rename replaces a symlink, never follows it
fi

echo
echo "==> What the app's n8n API key may do (Integrations needs workflows and credentials)"
checked=0
docker compose exec -T mailflow python - <<'PY' || checked=$?
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
raise SystemExit(3 if refused else 0)
PY
if [ "$checked" = 3 ]; then
  echo "   In n8n: Settings > n8n API > create a key with those scopes (or no scopes), put it in"
  echo "   N8N_API_KEY in $DIR/app/.env, then run this script again."
fi

echo
echo "==> Through the public address"
if [ -z "$SITE" ]; then
  read -rp "The site's public address (like https://mail.example.com; empty skips this check): " SITE || true
fi
SITE=${SITE%/}
if [ -n "$SITE" ]; then
  curl -fsS -o /dev/null -w "   $SITE answers %{http_code}\n" "$SITE/healthz" || echo "   not reachable from here: check the proxy in front (deploy/srv1-publish.sh)"
fi

echo
echo "==> Left for you, in a browser"
if grep -q '^GOOGLE_CLIENT_ID=..*' "$DIR/app/.env"; then
  echo "   - Continue with Google is on."
else
  echo "   - Continue with Google is off (optional): app/README.md, 'Continue with Google'."
fi
echo "   - Google Cloud console: publish the OAuth consent screen, or the Gmail login in n8n expires every 7 days."
echo "   - Sign in as an admin: account menu > Integrations, to connect mailboxes, SMTP replies, the AI and alerts."
