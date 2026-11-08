# Stage 1–2: Audit and gap analysis of the prototype

## What the prototype is
One self-contained HTML file (~580 KB). Vanilla JS, Three.js for 3D. 556 entries embedded as JSON (reg 319, net 197, corp 27, biz 13; sources: Q&A Regulatory Framework 200, NTTN Network Architecture PDF 194, BTRC Licence Guide 119, Company Profile 22, official website 20, curated 1). Retrieval is client-side BM25 with stemming, acronym and synonym tables. Features: assistant, department vault, 3D map, coverage roadmap, insights, update centre, command palette, login screen, light/dark theme.

## Retain
Entry content and ids (S001–S556), department model, source and reference strings, acronym/synonym knowledge, the "answer with source or say nothing" behaviour, UX patterns (command palette, department browsing, gaps), brand and logo.

## Weaknesses (each is a defect for an enterprise deployment)
| # | Weakness | Consequence |
|---|---|---|
| 1 | Access code is checked in the browser | Not authentication. Anyone can read the page source, which also contains every entry |
| 2 | All 556 entries are shipped to every visitor | No department confidentiality is possible |
| 3 | Updates, gaps, feedback live in browser storage | Not shared, not durable, not auditable |
| 4 | No roles, no approval, no versioning | Anyone with the file can alter what the assistant "knows" |
| 5 | No audit trail | Cannot answer "who changed or asked what" |
| 6 | Retrieval is keyword only | Misses paraphrases; no semantics, no Bangla |
| 7 | Coverage/roadmap status is stored per browser | Different users see different truth |
| 8 | Single 580 KB file mixing data, logic and styling | Hard to maintain, test or hand over |
| 9 | Hardcoded content in the build (gen.py) | No document ingestion pipeline |

## Gap analysis against the brief
Delivered in the new stack: items 1–5 above are addressed by the backend (see 00-status.md). Remaining gaps: semantic and multilingual retrieval, document intelligence, React front end, administration UIs, roadmap/coverage model, deployment and monitoring, security and accessibility testing of the new UI.

## Migration plan
1. Schema → 2. `migrate_kb.py` loads departments, one controlled document per (department, source), 556 published entries (ids preserved) → 3. Verification (count, per-department counts, field equality, digest) → 4. Create admin, then SSO users, grant roles → 5. Point the new front end at the API; retire the prototype's embedded data → 6. Keep `kb_prototype.json` as the archived baseline.
