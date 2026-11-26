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

if [ -f "$STAGED" ]; then
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
