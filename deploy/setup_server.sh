#!/usr/bin/env bash
# One-time server setup for Ubuntu 22.04/24.04. Run as root from inside the checked-out repository (default /srv/vault):
#     sudo bash deploy/setup_server.sh vault.fiberathome.net admin@fiberathome.net
# Safe to re-run: it skips what already exists and never overwrites /etc/fhl-vault.env.
set -euo pipefail
DOMAIN="${1:?usage: setup_server.sh <domain> <admin-email>}"; ADMIN="${2:?usage: setup_server.sh <domain> <admin-email>}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
[ "$REPO" = "/srv/vault" ] || { echo "Clone the repository to /srv/vault first (see DEPLOY.md). Found: $REPO"; exit 1; }
[ "$(id -u)" = 0 ] || { echo "Run as root (sudo)."; exit 1; }

echo "== 1/7 packages"; export DEBIAN_FRONTEND=noninteractive; apt-get update -y
apt-get install -y postgresql postgresql-contrib python3-venv python3-pip git ufw curl gpg debian-keyring debian-archive-keyring apt-transport-https
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

echo "== 2/7 firewall (SSH, HTTP, HTTPS only)"; ufw allow OpenSSH; ufw allow 80/tcp; ufw allow 443/tcp; ufw --force enable

echo "== 3/7 service user and folders"
id vault >/dev/null 2>&1 || useradd --system --home /srv/vault --shell /usr/sbin/nologin vault
mkdir -p /var/backups/fhl-vault; chown vault:vault /var/backups/fhl-vault; chmod 700 /var/backups/fhl-vault

echo "== 4/7 python environment"
python3 -m venv "$REPO/.venv"; "$REPO/.venv/bin/pip" install --quiet --upgrade pip; "$REPO/.venv/bin/pip" install --quiet -r "$REPO/backend/requirements.txt"
chown -R vault:vault "$REPO/.venv"

echo "== 5/7 database and settings"
if [ ! -f /etc/fhl-vault.env ]; then
  DBPW="$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')"; PEPPER="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
  sudo -u postgres psql -qc "CREATE ROLE fhl LOGIN CREATEDB PASSWORD '$DBPW'"
  sudo -u postgres createdb -O fhl fhl
  sed -e "s|postgresql://fhl:CHANGE_ME@|postgresql://fhl:$DBPW@|" -e "s|^OTP_PEPPER=.*|OTP_PEPPER=$PEPPER|" "$REPO/deploy/.env.example" > /etc/fhl-vault.env
  chown root:vault /etc/fhl-vault.env; chmod 640 /etc/fhl-vault.env
  echo "   -> /etc/fhl-vault.env created. EDIT IT NOW: set SMTP_USER, SMTP_PASSWORD (and SMTP_HOST if not Hostinger)."
fi
set -a; . /etc/fhl-vault.env; set +a
psql "$DATABASE_URL" -q -f "$REPO/db/schema.sql" >/dev/null
"$REPO/.venv/bin/python" -I "$REPO/scripts/migrate_kb.py"
ADMIN_PASSWORD="$(python3 -c 'import secrets;print(secrets.token_urlsafe(18)+"-Aa1")')"
ADMIN_PASSWORD="$ADMIN_PASSWORD" "$REPO/.venv/bin/python" "$REPO/scripts/create_admin.py" "$ADMIN"
echo "   (the administrator signs in with an emailed code like everyone else; the random local password above was not shown or stored)"
unset ADMIN_PASSWORD

echo "== 6/7 web server (HTTPS) and service"
sed "s/vault.example.com/$DOMAIN/" "$REPO/deploy/Caddyfile" > /etc/caddy/Caddyfile; systemctl reload caddy || systemctl restart caddy
cp "$REPO/deploy/fhl-vault.service" /etc/systemd/system/fhl-vault.service; systemctl daemon-reload; systemctl enable --now fhl-vault

echo "== 7/7 nightly backup (02:30)"
cat > /etc/cron.d/fhl-vault-backup <<CRON
30 2 * * * vault bash -c 'set -a; . /etc/fhl-vault.env; set +a; BACKUP_DIR=/var/backups/fhl-vault /srv/vault/scripts/backup.sh >> /var/backups/fhl-vault/backup.log 2>&1; find /var/backups/fhl-vault -name "fhl-*.dump*" -mtime +30 -delete'
CRON
chmod 644 /etc/cron.d/fhl-vault-backup
sleep 3; curl -fsS http://127.0.0.1:8000/api/health && echo && echo "DONE. Now: edit /etc/fhl-vault.env (SMTP), then 'systemctl restart fhl-vault', then open https://$DOMAIN"
