#!/usr/bin/env bash
# Publish the MailFlow web app (ai, 10.0.0.31:3100) as https://mailflow.22112002.xyz through the
# Cloudflare tunnel and Caddy already on srv1. Run on srv1: sudo bash srv1-publish.sh
# Backs up both configs, validates before applying, and puts the backups back if validation fails.
# Restarting cloudflared drops every site on the tunnel for a few seconds.
set -euo pipefail

HOST=mailflow.22112002.xyz
APP=10.0.0.31:3100
CF=/etc/cloudflared/config.yml
CADDY=/etc/caddy/Caddyfile

[ "$(id -u)" = 0 ] || { echo "Run with sudo."; exit 1; }
USER_NAME=${SUDO_USER:?run through sudo from your own account}

echo "==> The app answers from srv1?"
curl -fsS "http://$APP/healthz" && echo

ts=$(date +%Y%m%d-%H%M%S)
cp -a "$CF" "$CF.bak-$ts"
cp -a "$CADDY" "$CADDY.bak-$ts"
restore() {
  echo "!! Validation failed: putting the backups back, nothing was reloaded."
  cp -a "$CF.bak-$ts" "$CF"
  cp -a "$CADDY.bak-$ts" "$CADDY"
  exit 1
}

if ! grep -q "hostname: $HOST" "$CF"; then
  # One ingress rule above the 404 catch-all, with the catch-all's own indent.
  new=$(awk -v h="$HOST" '
    /^[[:space:]]*- service: http_status:404/ && !done {
      match($0, /^[[:space:]]*/); ind = substr($0, 1, RLENGTH)
      print ind "- hostname: " h
      print ind "  service: http://127.0.0.1:80"
      done = 1
    }
    { print }
    END { if (!done) exit 3 }' "$CF") || { echo "No '- service: http_status:404' line in $CF"; restore; }
  printf '%s\n' "$new" > "$CF"
fi

if ! grep -q "^$HOST" "$CADDY"; then
  cat >> "$CADDY" <<EOF

# MailFlow web app on the ai VM. Logins are in the app itself (one account per person).
$HOST:80 {
	reverse_proxy $APP
}
EOF
fi

echo "==> Validating"
cloudflared tunnel --config "$CF" ingress validate || restore
cloudflared tunnel --config "$CF" ingress rule "https://$HOST/" || restore
caddy validate --config "$CADDY" --adapter caddyfile || restore

echo "==> DNS record (as $USER_NAME, who holds the Cloudflare login)"
T=$(awk '/^tunnel:/{print $2}' "$CF")
sudo -u "$USER_NAME" cloudflared tunnel route dns "$T" "$HOST" || echo "(route dns failed; if the record already exists that is fine)"

echo "==> Applying"
systemctl reload caddy
systemctl restart cloudflared
sleep 5
curl -fsS -o /dev/null -w "https://$HOST/login -> %{http_code}\n" "https://$HOST/login" || echo "(DNS may need a minute to appear)"
echo "Backups: $CF.bak-$ts  $CADDY.bak-$ts"
