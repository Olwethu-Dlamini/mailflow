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

# The app believes Cf-Connecting-IP from srv1 (TRUSTED_PROXY), so only cloudflared on this host may
# use the site: anyone reaching srv1:80 directly could otherwise choose the address the login lockout counts.
GUARD="# MailFlow: only the local Cloudflare tunnel may use this site"
if grep -q "^$HOST" "$CADDY" && ! grep -qF "$GUARD" "$CADDY"; then
  # A block from before that rule: take it out; the new one is added below.
  awk -v h="$HOST:80 {" '$0 == h {skip = 1} skip && /^}/ {skip = 0; next} !skip' "$CADDY" > "$CADDY.new"
  cat "$CADDY.new" > "$CADDY" && rm -f "$CADDY.new"
fi
if ! grep -q "^$HOST" "$CADDY"; then
  cat >> "$CADDY" <<EOF

$GUARD (logins are in the app itself)
$HOST:80 {
	@outside not remote_ip 127.0.0.1 ::1
	respond @outside 403
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
