#!/usr/bin/env bash
# Nightly logical backup + restore verification. Usage: DATABASE_URL=... BACKUP_DIR=/secure/backups ./backup.sh
set -euo pipefail
DIR="${BACKUP_DIR:-./backups}"; mkdir -p "$DIR"; F="$DIR/fhl-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner "$DATABASE_URL" -f "$F"
sha256sum "$F" > "$F.sha256"
# restore into a scratch database and compare row counts (a backup that was never restored is not a backup)
SCRATCH="restore_check_$$"; BASE="${DATABASE_URL%/*}"
psql "$BASE/postgres" -qc "CREATE DATABASE $SCRATCH"
trap 'psql "$BASE/postgres" -qc "DROP DATABASE IF EXISTS $SCRATCH WITH (FORCE)"' EXIT
pg_restore --no-owner -d "$BASE/$SCRATCH" "$F"
a=$(psql "$DATABASE_URL" -Atc "SELECT count(*) FROM entries"); b=$(psql "$BASE/$SCRATCH" -Atc "SELECT count(*) FROM entries")
[ "$a" = "$b" ] && echo "OK: $F ($a entries restored and verified)" || { echo "RESTORE VERIFICATION FAILED ($a vs $b)"; exit 1; }
