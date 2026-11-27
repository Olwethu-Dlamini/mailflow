#!/usr/bin/env bash
# Back up the MailFlow app's own data, on the host that runs it: sudo bash backup.sh
# Keeps, in /var/backups/mailflow (root only, files mode 600):
#   mailflow-<time>.db  a consistent copy of the app's SQLite file (accounts, sessions, who has
#                       which email, activity, the sealed SMTP passwords), taken while the app runs
#   env-<time>          the app's .env: it holds MAILFLOW_SECRET_KEY, without which the saved SMTP
#                       passwords in the copy cannot be opened
# and removes all but the newest MAILFLOW_BACKUP_KEEP of each (default 14).
#
# Every night at 02:30, as /etc/cron.d/mailflow-backup:
#   30 2 * * * root bash /opt/mailflow/app/deploy/backup.sh >/var/log/mailflow-backup.log 2>&1
#
# n8n's own data (workflows, credentials, the "MailFlow emails" table) is not in here: back it up
# with n8n's tools (app/README.md, "Backups").
#
# Optional: MAILFLOW_DIR (default /opt/mailflow), MAILFLOW_BACKUP_DIR (default /var/backups/mailflow),
# MAILFLOW_BACKUP_KEEP (default 14).
set -euo pipefail
shopt -s nullglob

DIR=${MAILFLOW_DIR:-/opt/mailflow}
DEST=${MAILFLOW_BACKUP_DIR:-/var/backups/mailflow}
KEEP=${MAILFLOW_BACKUP_KEEP:-14}

[ "$(id -u)" = 0 ] || { echo "Run as root (sudo)."; exit 1; }
[[ $KEEP =~ ^[1-9][0-9]{0,3}$ ]] || { echo "MAILFLOW_BACKUP_KEEP must be a whole number from 1."; exit 1; }
[ -f "$DIR/app/.env" ] || { echo "No $DIR/app/.env: is MailFlow installed in $DIR?"; exit 1; }
if [ -L "$DEST" ]; then echo "$DEST is a symlink: refusing to write through it."; exit 1; fi
cd "$DIR/app"

umask 077
install -d -m 700 -o root -g root "$DEST"
ts=$(date +%Y%m%d-%H%M%S)

# The container is read-only apart from /data and /tmp: the copy is made in /data (the app's volume),
# copied out, then removed there, also when a step fails.
inside=/data/.backup-$ts.db
trap 'docker compose exec -T mailflow rm -f "$inside" >/dev/null 2>&1 || true' EXIT

echo "==> Copying the database"
# SQLite's backup API gives a consistent copy even while the app writes.
docker compose exec -T mailflow python - "$inside" <<'PY'
import os
import sqlite3
import sys

source = sqlite3.connect(os.environ.get("DB_PATH", "/data/mailflow.db"))
copy = sqlite3.connect(sys.argv[1])
with copy:
    source.backup(copy)
check = copy.execute("PRAGMA quick_check").fetchone()[0]
copy.close()
source.close()
if check != "ok":
    raise SystemExit(f"the copy failed its check: {check}")
PY
# -L: copy the file, never a symlink the container may have put in its place; then refuse
# anything that is not a plain file before root changes its owner and mode.
docker cp -L "mailflow:$inside" "$DEST/.mailflow-$ts.db.part"
if [ -L "$DEST/.mailflow-$ts.db.part" ] || [ ! -f "$DEST/.mailflow-$ts.db.part" ]; then
  echo "The copy out of the container is not a plain file: not keeping it."
  rm -f "$DEST/.mailflow-$ts.db.part"
  exit 1
fi
chown root:root "$DEST/.mailflow-$ts.db.part"
chmod 600 "$DEST/.mailflow-$ts.db.part"
mv -f "$DEST/.mailflow-$ts.db.part" "$DEST/mailflow-$ts.db"

echo "==> Copying the settings (.env)"
install -m 600 -o root -g root "$DIR/app/.env" "$DEST/env-$ts"

# Names sort by time: drop all but the newest $KEEP of each kind.
prune() {
  local files=("$DEST"/"$1"*)
  local extra=$((${#files[@]} - KEEP))
  if [ "$extra" -gt 0 ]; then rm -f -- "${files[@]:0:extra}"; fi
}
prune mailflow-
prune env-

echo "==> Kept in $DEST (newest $KEEP of each)"
ls -l "$DEST"
echo "Copy this folder off the host too (it holds the key to the SMTP passwords: keep it as safe as the server)."
