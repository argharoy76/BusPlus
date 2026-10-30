#!/usr/bin/env bash
# =============================================================================
# Update the live server to the newest code on GitHub and restart BusPlus.
#
# GitHub runs this automatically after every push to main (.github/workflows/ci.yml).
# By hand, on the server:   sudo -u busplus bash /opt/busplus/deploy/update.sh
#
# Your data is safe: .env, instance/ (the database) and backups/ are not in Git,
# so updating the code never touches them.
# =============================================================================
set -euo pipefail

APP_DIR=/opt/busplus
BRANCH="${BRANCH:-main}"
cd "$APP_DIR"

echo "==> Getting the newest code ($BRANCH)"
git fetch --quiet origin "$BRANCH"
git reset --hard --quiet "origin/$BRANCH"

echo "==> Installing Python libraries"
.venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt

echo "==> Restarting BusPlus"
sudo /usr/bin/systemctl restart busplus

for _ in $(seq 20); do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "==> BusPlus is running version $(git rev-parse --short HEAD)"
        exit 0
    fi
    sleep 1
done

echo "!! BusPlus did not start. Last log lines:"
journalctl -u busplus -n 40 --no-pager || true
exit 1
