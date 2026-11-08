#!/usr/bin/env python3
"""Migrate the prototype's knowledge entries into PostgreSQL and verify them field-by-field.
Usage: DATABASE_URL=postgresql://... python3 migrate_kb.py [kb_prototype.json]
Idempotent: re-running updates nothing that already matches. Exits non-zero on any mismatch."""
import hashlib, json, os, sys, pathlib
import psycopg
HERE = pathlib.Path(__file__).parent
DSN = os.environ.get("DATABASE_URL", "postgresql://pgu@127.0.0.1/fhl")
src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "kb_prototype.json"
kb = json.loads(src.read_text()); depts = json.loads((HERE / "departments.json").read_text())

def canon(e):  # canonical form used for the integrity comparison
    return json.dumps([e["id"], e["d"], e["c"], e["s"], e["k"], e["t"], e["b"], e["src"], e["r"]], ensure_ascii=False)
def digest(rows): return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()

assert len({e["id"] for e in kb}) == len(kb), "duplicate ids in source"
with psycopg.connect(DSN) as cx:
    cur = cx.cursor()
    for d in depts:
        cur.execute("INSERT INTO departments(id,name,poc) VALUES(%s,%s,%s) ON CONFLICT(id) DO UPDATE SET name=excluded.name,poc=excluded.poc", (d["id"], d["name"], d["poc"]))
    docs = {}
    for e in kb:  # one controlled document per (department, source)
        key = (e["d"], e["src"])
        if key not in docs:
            cur.execute("""INSERT INTO documents(title,source,dept_id,status) VALUES(%s,%s,%s,'published')
                           ON CONFLICT(title,source) DO UPDATE SET updated_at=documents.updated_at RETURNING id""", (e["src"], e["src"], e["d"]))
            did = cur.fetchone()[0]; docs[key] = did
            cur.execute("""INSERT INTO document_versions(document_id,version,status,published_at,note)
                           VALUES(%s,1,'published',now(),'Migrated from prototype') ON CONFLICT DO NOTHING""", (did,))
    for e in kb:
        cur.execute("""INSERT INTO entries(id,dept_id,document_id,category,subcategory,kind,title,body,reference,source,status)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'published')
                       ON CONFLICT(id) DO UPDATE SET dept_id=excluded.dept_id,category=excluded.category,subcategory=excluded.subcategory,
                         kind=excluded.kind,title=excluded.title,body=excluded.body,reference=excluded.reference,source=excluded.source""",
                    (e["id"], e["d"], docs[(e["d"], e["src"])], e["c"], e["s"], e["k"], e["t"], e["b"], e["r"], e["src"]))
    cx.commit()
    # ---- verification
    cur.execute("SELECT id,dept_id,category,subcategory,kind,title,body,source,reference,status FROM entries")
    db = {r[0]: r for r in cur.fetchall()}
    errs = []
    if len(db) < len(kb): errs.append(f"row count {len(db)} < {len(kb)}")
    for e in kb:
        r = db.get(e["id"])
        if not r: errs.append("missing " + e["id"]); continue
        if canon(e) != json.dumps([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]], ensure_ascii=False): errs.append("field mismatch " + e["id"])
        if r[9] != "published": errs.append("not published " + e["id"])
    src_by = {}; [src_by.__setitem__(e["d"], src_by.get(e["d"], 0) + 1) for e in kb]
    cur.execute("SELECT dept_id,count(*) FROM entries WHERE id = ANY(%s) GROUP BY 1", ([e["id"] for e in kb],))
    db_by = dict(cur.fetchall())
    if db_by != src_by: errs.append(f"dept counts differ {db_by} vs {src_by}")
    cur.execute("SELECT count(*) FROM entries e LEFT JOIN documents d ON d.id=e.document_id WHERE e.id=ANY(%s) AND d.id IS NULL", ([e["id"] for e in kb],))
    if cur.fetchone()[0]: errs.append("entries without a controlled document")
    print(f"source entries : {len(kb)}\ndb entries     : {len(db)}\nper department : {db_by}\ncontent digest : {digest([canon(e) for e in kb])[:16]} (source)")
    print(f"                 {digest([json.dumps([r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8]],ensure_ascii=False) for r in db.values() if r[0] in {e['id'] for e in kb}])[:16]} (database)")
    if errs: print("VERIFICATION FAILED:\n" + "\n".join(errs[:20])); sys.exit(1)
    print("VERIFICATION PASSED: all entries present, identical, published and linked to a controlled document")
