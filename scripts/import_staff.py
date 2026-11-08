#!/usr/bin/env python3
"""Add or update staff accounts from a CSV so they can sign in with an emailed one-time code.
CSV columns (header row required):  email,name,role,department
  role        viewer | editor | reviewer | admin     (blank = viewer)
  department  a department id from db (e.g. corp, net, reg, biz), or blank = every department
Usage:  DATABASE_URL=postgresql:///fhl python3 scripts/import_staff.py staff.csv [--dry-run]
Only addresses on the allowed domain(s) (OTP_ALLOWED_DOMAINS) can ever receive a code, so a wrong-domain row is rejected here too."""
import csv, os, re, sys, psycopg
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app import config
ROLES = {"viewer", "editor", "reviewer", "admin"}; EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
def main(path, dry):
    rows, errs = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for n, r in enumerate(csv.DictReader(f), start=2):
            e = (r.get("email") or "").strip().lower(); name = (r.get("name") or "").strip() or e.split("@")[0].replace(".", " ").title()
            role = (r.get("role") or "viewer").strip().lower() or "viewer"; dept = (r.get("department") or "").strip() or None
            dom = e.rsplit("@", 1)[-1]
            if not EMAIL.match(e): errs.append(f"line {n}: '{e}' is not a valid email"); continue
            if "*" not in config.OTP_ALLOWED_DOMAINS and dom not in config.OTP_ALLOWED_DOMAINS: errs.append(f"line {n}: {e} is not on an allowed domain {config.OTP_ALLOWED_DOMAINS}"); continue
            if role not in ROLES: errs.append(f"line {n}: role '{role}' must be one of {sorted(ROLES)}"); continue
            rows.append((e, name, role, dept))
    if errs: print("\n".join(errs)); sys.exit(f"{len(errs)} problem(s). Nothing was imported.")
    with psycopg.connect(config.DATABASE_URL) as cx:
        depts = {d[0] for d in cx.execute("SELECT id FROM departments")}
        bad = [f"{e}: unknown department '{d}' (known: {sorted(depts)})" for e, _, _, d in rows if d and d not in depts]
        if bad: print("\n".join(bad)); sys.exit("Nothing was imported.")
        for e, name, role, dept in rows:
            u = cx.execute("INSERT INTO users(email,display_name) VALUES(%s,%s) ON CONFLICT(email) DO UPDATE SET display_name=excluded.display_name, is_active=true RETURNING id", (e, name)).fetchone()[0]
            cx.execute("INSERT INTO user_roles(user_id,dept_id,role) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING", (u, dept, role))
            if role != "viewer": cx.execute("INSERT INTO user_roles(user_id,dept_id,role) VALUES(%s,%s,'viewer') ON CONFLICT DO NOTHING", (u, dept))
        cx.execute("INSERT INTO audit_log(actor_email,action,object_type,detail) VALUES('import_staff','staff.import','user',%s::jsonb)", ('{"count": %d}' % len(rows),))
        if dry: cx.rollback(); print(f"dry run: {len(rows)} account(s) would be added or updated. Nothing saved.")
        else: cx.commit(); print(f"{len(rows)} account(s) added or updated.")
if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(__doc__)
    main(sys.argv[1], "--dry-run" in sys.argv)
