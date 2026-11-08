#!/usr/bin/env python3
"""Create the break-glass local administrator. Password is read from the ADMIN_PASSWORD env var (never from argv/history)."""
import os, sys, psycopg
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app import security as sec, config
email, pw = sys.argv[1], os.environ.get("ADMIN_PASSWORD", "")
if (m := sec.validate_password_policy(pw)): sys.exit(m)
with psycopg.connect(config.DATABASE_URL) as cx:
    uid = cx.execute("INSERT INTO users(email,display_name,password_hash) VALUES(%s,'Administrator',%s) ON CONFLICT(email) DO UPDATE SET password_hash=excluded.password_hash RETURNING id", (email, sec.hash_password(pw))).fetchone()[0]
    cx.execute("INSERT INTO user_roles(user_id,dept_id,role) VALUES(%s,NULL,'admin') ON CONFLICT DO NOTHING", (uid,))
    cx.execute("INSERT INTO audit_log(actor_email,action,object_type,object_id) VALUES(%s,'admin.bootstrap','user',%s)", (email, str(uid)))
print("administrator ready:", email)
