#!/usr/bin/env bash
# Nightly copy of the BusPlus database (run by cron, see setup_server.sh). Keeps 14 days.
# Restore: stop the app, copy a backup over instance/busplus.db, start the app.
set -euo pipefail

APP_DIR=/opt/busplus
DB="$APP_DIR/instance/busplus.db"
[[ -f "$DB" ]] || exit 0

sqlite3 "$DB" ".backup '$APP_DIR/backups/busplus-$(date +%F).db'"   # safe while the app is running
find "$APP_DIR/backups" -name 'busplus-*.db' -mtime +14 -delete
