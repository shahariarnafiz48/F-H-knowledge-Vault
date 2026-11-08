# Stage 5: Security model

Reference: OWASP ASVS and OWASP Top 10. This table states what is **implemented and tested here**; nothing else is claimed.

| Control | Implementation | Tested |
|---|---|---|
| Authentication | Server-side sessions; random 256-bit token, only its SHA-256 stored; argon2id passwords; timing-equalised unknown-user path | yes |
| Brute force | Lock for 15 min after 5 failures; failures audited | yes |
| Session management | Idle 30 min, absolute 12 h, revoke on logout and on role change | yes |
| CSRF | Per-session token required on every state-changing request; SameSite=Strict cookie | yes |
| Authorization | Roles global or per department; checked in the API and applied in SQL; 404 (not 403) for objects outside scope | yes |
| Separation of duties | Author cannot approve or publish their own entry | yes |
| Injection | Parameterised SQL only; field names for updates come from a validated model; tsquery built from `[A-Za-z0-9]` tokens | yes |
| Output encoding / XSS | API returns JSON only with CSP `default-src 'none'`, nosniff, DENY framing; the React front end must render text, never HTML | headers tested |
| Audit | Append-only (DB triggers block UPDATE/DELETE), SHA-256 hash chain, `/api/audit/verify` | yes |
| SSO | Entra ID token validation (signature via JWKS, issuer, audience, expiry, tenant); new SSO users get **no roles** until an admin grants them | crypto tested locally |
| Secrets | Read from environment; none in code | review |

## Not yet done (required before production)
TLS termination and HSTS at the proxy, encryption at rest (disk/volume or managed database), secrets manager, rate limiting at the proxy, secure file upload pipeline (type sniffing, size limits, malware scan), SSO redirect flow with PKCE in the front end, security headers for the front end, dependency scanning in CI, independent penetration test, database role separation (application role without DDL), log shipping to central monitoring.

## Honest limits
The extractive assistant cannot hallucinate, but it can return a *relevant but incomplete* entry; users should follow the citation. Relevance thresholds (`RELEVANCE_THRESHOLD`, `MIN_TERM_COVERAGE`) are tuned on a small question set and must be re-tuned against real user questions.
