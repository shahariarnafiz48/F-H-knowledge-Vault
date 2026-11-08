# Delivery status (honest ledger)

| Area | State | Evidence |
|---|---|---|
| PostgreSQL schema (entries, documents, versions, users, roles, sessions, audit, search events, feedback, gaps) | **Implemented, applied** | `db/schema.sql` |
| Migration of 556 entries with verification | **Implemented, verified** | `scripts/migrate_kb.py`: field-by-field equality + content digest identical (54d1024e9808ff1f) |
| Server-enforced authentication (cookie sessions, argon2id, lockout, idle + absolute expiry, CSRF) | **Implemented, tested** | tests/test_platform.py |
| Role- and department-based access control (admin/editor/reviewer/viewer) enforced in SQL | **Implemented, tested** | tests |
| Permission applied *during retrieval* | **Implemented, tested** | `test_search_respects_department_permissions` |
| Approval workflow Draft→Review→Approved→Published→Superseded/Archived with separation of duties and versioning | **Implemented, tested** | tests |
| Tamper-evident append-only audit log | **Implemented, tested** | hash chain + DB triggers |
| Dashboard metrics from real data | **Implemented (subset)**, coverage % deliberately returns null | tests |
| Hybrid retrieval (full-text + trigram) with acronym expansion, citations, refusal when unsupported, verbatim extractive answers | **Implemented, tested** | tests |
| Microsoft Entra ID sign-in | **Token validation implemented and unit-tested** with real RS256 crypto; **not connected to a tenant** | needs tenant + app registration |
| Backups with restore verification | **Implemented, tested** | `scripts/backup.sh` |
| Semantic (vector) search | **Schema ready, not active**: pgvector is not installed in this environment, and no embedding provider is chosen | — |
| LLM-written answers (RAG generation) | **Not implemented.** Answers are quoted from entries; nothing is generated | needs an approved provider, keys, data-residency decision |
| Bangla support | **Not implemented** | needs a multilingual embedding model |
| Document upload, OCR, extraction (PDF/DOCX/XLSX/PPTX), duplicate detection, file versions | **Not implemented** (tables exist for versions) | next stage |
| Query rewriting, conversation context | **Not implemented** | next stage |
| React + TypeScript + Tailwind front end on this API | **Not implemented.** The existing HTML prototype still runs on browser storage and is not connected to this backend | next stage |
| User/role administration UI, audit viewer, system configuration UI | **Not implemented** (API exists for users, roles, audit) | next stage |
| Knowledge relationship map, roadmap/coverage model in DB | **Not implemented** in the new stack | next stage |
| Deployment (containers, TLS, secrets manager, monitoring), penetration test, WCAG audit of the new UI | **Not done** | needs target infrastructure |

Acceptance criteria met so far: entries preserved and verified; authentication and permissions enforced by the backend; data stored centrally; citations verifiable against stored rows; versioned approvals; metrics from data; backup/recovery documented and tested. Not yet met: AI grounded generation, document intelligence, new UI, multi-device validation, production security testing.
