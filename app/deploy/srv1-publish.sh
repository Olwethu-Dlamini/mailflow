#!/usr/bin/env bash
# Publish the MailFlow web app through a Cloudflare tunnel and Caddy that already run on this host
# (srv1, for the owner's own copy). Run here: sudo bash srv1-publish.sh [HOST] [APP]
#   HOST  the public name (or MAILFLOW_HOST; default mailflow.22112002.xyz)
#   APP   the app's address as seen from here (or MAILFLOW_APP; default 10.0.0.31:3100)
# Backs up both configs, validates before applying, and puts the backups back if validation fails.
# Restarting cloudflared drops every site on the tunnel for a few seconds.
set -euo pipefail

HOST=${1:-${MAILFLOW_HOST:-mailflow.22112002.xyz}}
APP=${2:-${MAILFLOW_APP:-10.0.0.31:3100}}
CF=/etc/cloudflared/config.yml
CADDY=/etc/caddy/Caddyfile

# Both go into config files and patterns below: plain names and addresses only.
[[ $HOST =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || { echo "HOST '$HOST' is not a plain host name."; exit 1; }
[[ $APP =~ ^[A-Za-z0-9.-]+:[0-9]{1,5}$ ]] || { echo "APP '$APP' is not host:port."; exit 1; }

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
BLOCK="$HOST:80 {"
has_block() { grep -qxF "$BLOCK" "$CADDY"; }
# This host's block is guarded when the guard comment is the line right above it.
guarded() { awk -v h="$BLOCK" -v g="$GUARD" 'index(prev, g) == 1 && $0 == h {found = 1} {prev = $0} END {exit !found}' "$CADDY"; }
if has_block && ! guarded; then
  # A block from before that rule: take it out; the new one is added below.
  old="# MailFlow web app on the ai VM. Logins are in the app itself (one account per person)."
  awk -v h="$BLOCK" -v c="$old" '$0 == c {next} $0 == h {skip = 1} skip && /^}/ {skip = 0; next} !skip' "$CADDY" > "$CADDY.new"
  cat "$CADDY.new" > "$CADDY" && rm -f "$CADDY.new"
  # Stop rather than report success over an unguarded block this could not recognise.
  if has_block; then echo "An unguarded $HOST block in $CADDY was not removed: edit it by hand."; restore; fi
fi
# (A block for this host written in another form makes the validation below fail on the duplicate
# site, and the backups are put back.)
if ! has_block; then
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
