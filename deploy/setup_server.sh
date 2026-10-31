#!/usr/bin/env bash
# =============================================================================
# One-time setup of BusPlus on a fresh Hostinger VPS (Ubuntu 24.04).
#
# Run it on the server as root:
#   curl -fsSLO https://raw.githubusercontent.com/<you>/<repo>/main/deploy/setup_server.sh
#   sudo bash setup_server.sh <git-repo-url> <your-domain> <your-email>
#
# Example:
#   sudo bash setup_server.sh git@github.com:rahim/busplus.git bus.example.com rahim@example.com
#
# What it does (safe to run again):
#   1. installs Python, nginx, git, certbot and the firewall
#   2. creates a "busplus" user and puts the app in /opt/busplus
#   3. creates /opt/busplus/.env with a random SECRET_KEY and admin password
#   4. runs the app as a systemd service behind nginx with free HTTPS (Let's Encrypt)
#   5. makes a key so GitHub can redeploy the app on every push (see DEPLOYMENT.md)
#   6. backs up the database every night (kept 14 days)
# =============================================================================
set -euo pipefail

REPO_URL="${1:?Usage: sudo bash setup_server.sh <git-repo-url> <domain> <email>}"
DOMAIN="${2:?Give your domain, e.g. bus.example.com}"
EMAIL="${3:?Give an email for HTTPS certificate notices}"
BRANCH="${BRANCH:-main}"
APP_DIR=/opt/busplus
APP_USER=busplus
APP_HOME=/home/$APP_USER

[[ $EUID -eq 0 ]] || { echo "Please run with sudo."; exit 1; }
say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
as_app() { sudo -u "$APP_USER" -H "$@"; }

say "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx ufw sqlite3 curl
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Python 3.11+ is needed (use Ubuntu 24.04)."; exit 1; }

say "Creating the '$APP_USER' user"
id "$APP_USER" &>/dev/null || useradd --create-home --shell /bin/bash "$APP_USER"
usermod -aG systemd-journal "$APP_USER"          # lets the update script show the app's logs
install -d -m 700 -o "$APP_USER" -g "$APP_USER" "$APP_HOME/.ssh"
as_app touch "$APP_HOME/.ssh/known_hosts"
grep -q github.com "$APP_HOME/.ssh/known_hosts" || ssh-keyscan -t ed25519 github.com 2>/dev/null >> "$APP_HOME/.ssh/known_hosts"

# Private GitHub repo over SSH: the server needs a read-only "deploy key".
if [[ "$REPO_URL" == git@* && ! -f "$APP_HOME/.ssh/id_ed25519" ]]; then
    as_app ssh-keygen -q -t ed25519 -N "" -C "busplus-server" -f "$APP_HOME/.ssh/id_ed25519"
    say "Add this key to GitHub: your repo > Settings > Deploy keys > Add deploy key (read-only)"
    cat "$APP_HOME/.ssh/id_ed25519.pub"
    read -r -p "Press Enter after adding it on GitHub... "
fi

say "Getting the code into $APP_DIR"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
if [[ -d "$APP_DIR/.git" ]]; then
    as_app git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
    as_app git -C "$APP_DIR" reset --hard --quiet "origin/$BRANCH"
else
    as_app git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
install -d -m 700 -o "$APP_USER" -g "$APP_USER" "$APP_DIR/instance" "$APP_DIR/backups"

say "Installing Python libraries"
[[ -d "$APP_DIR/.venv" ]] || as_app python3 -m venv "$APP_DIR/.venv"
as_app "$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
as_app "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

ADMIN_PASSWORD=""
if [[ ! -f "$APP_DIR/.env" ]]; then
    say "Creating $APP_DIR/.env with new secrets"
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
    ADMIN_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
    cat > "$APP_DIR/.env" <<EOF
BUSPLUS_ENV=production
SECRET_KEY=$SECRET_KEY
BUSPLUS_ADMIN_USERNAME=admin
BUSPLUS_ADMIN_PASSWORD=$ADMIN_PASSWORD
BUSPLUS_DEMO_DRIVERS=false
TRUSTED_PROXIES=1
EOF
    chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
fi

say "Starting the BusPlus service"
install -m 644 "$APP_DIR/deploy/busplus.service" /etc/systemd/system/busplus.service
systemctl daemon-reload
systemctl enable --quiet busplus
systemctl restart busplus

# The update script (run by GitHub) may restart the service, and nothing else.
cat > /etc/sudoers.d/busplus <<EOF
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart busplus
EOF
chmod 440 /etc/sudoers.d/busplus
visudo -cf /etc/sudoers.d/busplus >/dev/null

say "Setting up nginx for $DOMAIN"
# Also serve www.<domain> when its DNS record points here.
SERVER_NAMES="$DOMAIN"
CERT_DOMAINS=(-d "$DOMAIN")
if getent hosts "www.$DOMAIN" >/dev/null; then
    SERVER_NAMES="$DOMAIN www.$DOMAIN"
    CERT_DOMAINS+=(-d "www.$DOMAIN")
fi
sed "s/YOUR_DOMAIN/$SERVER_NAMES/g" "$APP_DIR/deploy/nginx-busplus.conf" > /etc/nginx/sites-available/busplus
ln -sf /etc/nginx/sites-available/busplus /etc/nginx/sites-enabled/busplus
rm -f /etc/nginx/sites-enabled/default
chmod o+x /opt "$APP_DIR"                         # nginx serves /opt/busplus/static directly
nginx -t
systemctl reload nginx

say "Firewall: only SSH and web traffic"
ufw allow OpenSSH >/dev/null
ufw allow 'Nginx Full' >/dev/null
ufw --force enable >/dev/null

say "Free HTTPS certificate from Let's Encrypt"
certbot --nginx --non-interactive --agree-tos --redirect -m "$EMAIL" "${CERT_DOMAINS[@]}" \
    || echo "!! HTTPS failed. Check that $DOMAIN points to this server's IP, then run: sudo certbot --nginx -d $DOMAIN"

say "Nightly database backup (03:15, kept 14 days)"
cat > /etc/cron.d/busplus-backup <<EOF
15 3 * * * $APP_USER bash $APP_DIR/deploy/backup_db.sh
EOF

if [[ ! -f "$APP_HOME/.ssh/github_actions" ]]; then
    say "Key for automatic deploys from GitHub"
    as_app ssh-keygen -q -t ed25519 -N "" -C "github-actions-deploy" -f "$APP_HOME/.ssh/github_actions"
    # This key can ONLY run the update script - nothing else on the server.
    echo "command=\"bash $APP_DIR/deploy/update.sh\",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty $(cat "$APP_HOME/.ssh/github_actions.pub")" \
        >> "$APP_HOME/.ssh/authorized_keys"
    chown "$APP_USER:$APP_USER" "$APP_HOME/.ssh/authorized_keys"
    chmod 600 "$APP_HOME/.ssh/authorized_keys"
fi

sleep 2
if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
    say "BusPlus is running at https://$DOMAIN"
else
    echo "!! BusPlus did not start. See: sudo journalctl -u busplus -n 50"
    exit 1
fi

cat <<EOF

-----------------------------------------------------------------------
 Backend:   https://$DOMAIN/backend
 Username:  admin
 Password:  ${ADMIN_PASSWORD:-"(unchanged - see BUSPLUS_ADMIN_PASSWORD in $APP_DIR/.env)"}

 For automatic deploys, add these GitHub secrets (repo > Settings >
 Secrets and variables > Actions > New repository secret):
   VPS_HOST     $(curl -fsS -4 https://ifconfig.me 2>/dev/null || echo "<this server's IP>")
   VPS_USER     $APP_USER
   VPS_SSH_KEY  the private key printed below (all lines)
-----------------------------------------------------------------------
EOF
cat "$APP_HOME/.ssh/github_actions"
echo "-----------------------------------------------------------------------"
echo " After copying it to GitHub you can delete it here:  sudo rm $APP_HOME/.ssh/github_actions"
