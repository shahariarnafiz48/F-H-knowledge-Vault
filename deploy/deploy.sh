#!/usr/bin/env bash
# Update the live server to the latest code on GitHub. Run on the VPS:  cd /srv/vault && sudo bash deploy/deploy.sh
set -euo pipefail
cd /srv/vault; git config --global --add safe.directory /srv/vault
git fetch --quiet origin && git merge --ff-only origin/main
.venv/bin/pip install --quiet -r backend/requirements.txt
set -a; . /etc/fhl-vault.env; set +a
psql "$DATABASE_URL" -q -f db/schema.sql >/dev/null          # schema is idempotent (CREATE ... IF NOT EXISTS)
systemctl restart fhl-vault; sleep 3
curl -fsS http://127.0.0.1:8000/api/health && echo " <- healthy. Deployed $(git rev-parse --short HEAD)"
