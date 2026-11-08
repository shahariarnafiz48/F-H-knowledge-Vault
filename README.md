# Fiber@Home Knowledge Vault

An internal knowledge platform for Fiber@Home Limited. Staff sign in with their company email and a one-time code, then search department knowledge and ask questions that are answered only from the company's own documents, with the source shown.

- **Sign-in:** email one-time code (6 digits, 10 minutes, single use, 5 attempts). The public address shows only the sign-in page; the vault itself is sent only after the code is verified.
- **Vault:** Ask the Vault, department knowledge, 3D knowledge map, coverage roadmap, insights, Update Center.
- **Back end:** Python FastAPI + PostgreSQL; secure cookies, CSRF protection, role-based access, tamper-evident audit log.
- **Go live:** see **[DEPLOY.md](DEPLOY.md)** (Hostinger VPS, staff only).
- **Private repository.** It holds internal company content. Never make it public. Secrets live only on the server in `/etc/fhl-vault.env`.

```
frontend-src/   sign-in page + vault source, and build_frontend.py (writes web/login.html and web/vault.html)
web/            the two built pages the server hands out (legacy/ = earlier prototype interface, not served)
backend/        FastAPI service + automated tests (python3 -m pytest -q backend/tests)
db/ scripts/    schema, knowledge loader, staff import, backup
deploy/         server setup, HTTPS config, service file, update script
docs/           audit, architecture, security model, status
```
Developed by the Strategy and Automation Team | Technology and Operations.

---

# Fiber@Home Knowledge Intelligence Platform — foundation (v1)

Status of this delivery is in `docs/00-status.md`. Read it first: it separates what is implemented and tested from what is not yet built.

```
docs/      audit, gap analysis, architecture, security model, API, deployment & recovery
db/        schema.sql (PostgreSQL 16)
backend/   FastAPI service + 23 automated tests
scripts/   migrate_kb.py (+ verification), backup.sh (+ restore check), create_admin.py
```

## Run locally
```bash
createdb fhl && psql fhl -f db/schema.sql
DATABASE_URL=postgresql:///fhl python3 -I scripts/migrate_kb.py          # loads + verifies the 556 entries
ADMIN_PASSWORD='Choose-A-Long-Pass-1' DATABASE_URL=postgresql:///fhl python3 scripts/create_admin.py you@fiberathome.net
cd backend && COOKIE_SECURE=false DATABASE_URL=postgresql:///fhl uvicorn app.main:app   # interactive API docs: /api/docs
cd backend && python3 -m pytest -q tests                                  # creates its own throw-away database
```
Production: serve only behind TLS (COOKIE_SECURE=true, the default), set `ENTRA_TENANT_ID` / `ENTRA_CLIENT_ID`.

## Run the full application (API + web interface on one port)
```bash
cd backend && COOKIE_SECURE=false DATABASE_URL=postgresql:///fhl uvicorn app.main:app --port 8010
# open http://localhost:8010   (demo accounts: python3 scripts/seed_demo_users.py — NOT for production)
```
Web interface (`web/`): sign-in, executive overview, assistant with sources and feedback, vault with filters, approvals workflow, audit log. It is plain JavaScript with no build step (not React/TypeScript; see docs/00-status.md).
