# Stage 10: Deployment, backup and recovery

## Deploy
1. Provision PostgreSQL 16 (managed or private VM) with encrypted storage; create a non-superuser application role; install `pgvector` if semantic search is wanted.
2. `psql -f db/schema.sql`; run `scripts/migrate_kb.py`; run `scripts/create_admin.py` once.
3. Run the API (`uvicorn app.main:app`, 2+ workers) behind TLS. Set `DATABASE_URL`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`; leave `COOKIE_SECURE=true`.
4. Monitor `/api/health`; ship logs and the `audit_log` table to central monitoring.
5. CI gate: `python3 -m pytest -q backend/tests` must pass.

## Backup and recovery
- `scripts/backup.sh` (cron nightly): custom-format dump, checksum, **restore into a scratch database and compare row counts**; fails loudly otherwise. Tested here: 556 entries restored and verified.
- Keep 30 daily and 12 monthly copies in encrypted off-site storage; enable PostgreSQL WAL archiving for point-in-time recovery in production.
- Restore drill (quarterly): `createdb fhl_new && pg_restore -d fhl_new <dump>`, run `scripts/migrate_kb.py` verification (it is idempotent), run the test suite against it, then switch `DATABASE_URL`.
- After any restore run `GET /api/audit/verify`.

## Handover
Everything is plain Python, SQL and shell, with an OpenAPI description and tests, so another team can extend it. Modules still to build are listed in `00-status.md`.
