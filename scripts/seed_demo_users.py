#!/usr/bin/env python3
"""DEMONSTRATION ONLY: creates four demo accounts with a shared, publicly known password. Never run against production."""
import os, sys, psycopg
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app import security as sec, config
pw = sec.hash_password("Demo-Passw0rd-1")
with psycopg.connect(config.DATABASE_URL, autocommit=True) as cx:
    for e, n, roles in [("admin@demo.fiberathome.net", "Demo Administrator", [(None, "admin")]), ("editor@demo.fiberathome.net", "Demo Editor", [(None, "editor"), (None, "viewer")]),
                        ("reviewer@demo.fiberathome.net", "Demo Reviewer", [(None, "reviewer"), (None, "viewer")]), ("viewer@demo.fiberathome.net", "Demo Viewer (HR only)", [("corp", "viewer")])]:
        u = cx.execute("INSERT INTO users(email,display_name,password_hash) VALUES(%s,%s,%s) ON CONFLICT(email) DO UPDATE SET password_hash=excluded.password_hash RETURNING id", (e, n, pw)).fetchone()[0]
        cx.execute("DELETE FROM user_roles WHERE user_id=%s", (u,))
        for d, r in roles: cx.execute("INSERT INTO user_roles(user_id,dept_id,role) VALUES(%s,%s,%s)", (u, d, r))
print("demo users ready (password Demo-Passw0rd-1)")
