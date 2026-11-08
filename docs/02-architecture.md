# Stage 3–4: Target architecture, schema, design system

## Components
```
Browser (React + TS + Tailwind)  ──HTTPS──▶  Reverse proxy (TLS, rate limit, WAF)
                                              │
                                   FastAPI service (stateless, 2+ replicas)
                                   ├─ auth/session, RBAC, audit
                                   ├─ retrieval (hybrid) ──▶ PostgreSQL 16 (+ pgvector when available)
                                   ├─ workflow (draft→review→approved→published)
                                   ├─ LLM adapter (interface; default = extractive, no generation)
                                   └─ ingestion worker (queue) ──▶ object storage (encrypted)
Microsoft Entra ID (OIDC)  ◀── sign-in
```
## Key decisions
- **PostgreSQL as the single system of record**: relational integrity, row-level logic in SQL, `tsvector` + `pg_trgm` today, `pgvector` later in the same database (one backup, one permission model).
- **Permissions inside the query**, not after it, so unauthorised text can never reach an LLM prompt.
- **Cookie sessions (HttpOnly, SameSite=Strict) + CSRF token** instead of tokens in JavaScript storage.
- **LLM behind an interface**; provider choice is a business decision (data residency, cost). Until chosen, answers are verbatim extracts with citations, so nothing can be fabricated.
- **Immutable published entries**: change = new version (`supersedes`), old becomes `superseded`; history is queryable.

## Schema
See `db/schema.sql` (13 tables, enums for roles and statuses, generated `tsvector`, audit hash-chain triggers).

## Design system (for the React build)
Foundation deep navy `#0B1220` / graphite `#161C2A`; primary electric blue `#2F6BFF`; accent cyan `#22D3EE` (data highlights only); status green/amber/red; 8-px spacing scale; radius 8/12; Inter + IBM Plex Mono; 3D only in the relationship map (information value), never decorative. Note: this replaces the current crimson/charcoal brand palette, which you asked for earlier. Please confirm which palette governs.

## Interface contract
All endpoints and schemas are in the live OpenAPI document (`/api/docs`, `/api/openapi.json`). Summary: `/api/auth/*`, `/api/ask`, `/api/feedback`, `/api/entries[/{id}][/submit|review|publish|archive|revise]`, `/api/gaps`, `/api/dashboard`, `/api/audit[/verify]`, `/api/admin/users[/{id}/roles]`, `/api/health`.
