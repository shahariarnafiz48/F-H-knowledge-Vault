import psycopg, pytest, os, time
from fastapi.testclient import TestClient
from conftest import login
from app.main import app
DSN = lambda: os.environ["DATABASE_URL"]
def C(email):
    c = TestClient(app); assert login(c, email).status_code == 200; return c

def test_all_556_entries_migrated():
    assert psycopg.connect(DSN()).execute("SELECT count(*) FROM entries WHERE status='published' AND id ~ '^S[0-9]{3}$'").fetchone()[0] == 556

def test_unauthenticated_requests_rejected(client):
    for path in ["/api/auth/me", "/api/dashboard", "/api/entries", "/api/audit"]: assert client.get(path).status_code == 401
    assert client.post("/api/ask", json={"query": "mission"}).status_code == 401
def test_bad_login_message_and_lockout(client):
    for _ in range(5): r = client.post("/api/auth/login", json={"email": "norole@t.io", "password": "wrong"})
    assert r.status_code == 401 and "incorrect" in r.json()["detail"]
    r = client.post("/api/auth/login", json={"email": "norole@t.io", "password": "Correct-Horse-9"})
    assert r.status_code == 429 and "Too many" in r.json()["detail"]
    psycopg.connect(DSN(), autocommit=True).execute("UPDATE users SET failed_logins=0,locked_until=NULL WHERE email='norole@t.io'")
def test_csrf_required_on_writes():
    c = C("editor_corp@t.io"); del c.headers["X-CSRF-Token"]
    assert c.post("/api/entries", json={"dept_id": "corp", "category": "x", "title": "abc", "body": "abc", "source": "src"}).status_code == 403
def test_logout_revokes_session():
    c = C("viewer_all@t.io"); assert c.get("/api/auth/me").status_code == 200
    c.post("/api/auth/logout"); assert c.get("/api/auth/me").status_code == 401
def test_idle_session_expires():
    c = C("viewer_all@t.io")
    psycopg.connect(DSN(), autocommit=True).execute("UPDATE sessions SET last_seen=now()-interval '2 hours' WHERE user_id=(SELECT id FROM users WHERE email='viewer_all@t.io')")
    assert c.get("/api/auth/me").status_code == 401
def test_security_headers_and_cookie_flags(client):
    r = client.post("/api/auth/login", json={"email": "viewer_all@t.io", "password": "Correct-Horse-9"})
    sc = r.headers["set-cookie"].lower(); assert "httponly" in sc and "samesite=strict" in sc
    assert r.headers["x-frame-options"] == "DENY" and "default-src 'none'" in r.headers["content-security-policy"]

def test_search_respects_department_permissions():
    q = {"query": "What does the BTRC licence rule say about NTTN?"}
    all_ = C("viewer_all@t.io").post("/api/ask", json=q).json(); corp = C("viewer_corp@t.io").post("/api/ask", json=q).json()
    assert all_["answered"] and any(c["department"] in ("reg", "net") for c in all_["citations"])
    assert all(c["department"] == "corp" for c in corp["citations"])
def test_no_role_user_sees_nothing():
    c = C("norole@t.io"); assert c.get("/api/entries").json() == []
    assert c.post("/api/ask", json={"query": "mission of Fiber@Home"}).json()["answered"] is False
    assert c.get("/api/entries/S301").status_code == 404
def test_answer_is_grounded_and_cited():
    r = C("viewer_all@t.io").post("/api/ask", json={"query": "what is the mission of Fiber@Home"}).json()
    assert r["answered"] and r["citations"][0]["source"]
    assert psycopg.connect(DSN()).execute("SELECT 1 FROM entries WHERE id=%s AND body=%s", (r["citations"][0]["entry_id"], r["answer"])).fetchone()
def test_unanswerable_question_is_not_fabricated_and_creates_gap():
    r = C("viewer_all@t.io").post("/api/ask", json={"query": "zxqv blorptastic quantum payroll sandwich"}).json()
    assert r["answered"] is False and r["answer"] is None and "could not find" in r["message"]
    assert any("blorptastic" in g["query"] for g in C("admin@t.io").get("/api/gaps").json())
def test_sql_injection_is_inert():
    c = C("viewer_all@t.io")
    assert c.post("/api/ask", json={"query": "'; DROP TABLE entries; --"}).status_code == 200
    assert c.get("/api/entries", params={"q": "' OR 1=1 --"}).status_code == 200
    assert psycopg.connect(DSN()).execute("SELECT count(*) FROM entries").fetchone()[0] >= 556

NEW = {"dept_id": "corp", "category": "Policies", "title": "Leave policy summary", "body": "Employees receive twenty days of annual leave.", "source": "HR Policy 2026"}
def test_viewer_cannot_write_and_editor_cannot_write_other_dept():
    assert C("viewer_corp@t.io").post("/api/entries", json=NEW).status_code == 403
    assert C("editor_corp@t.io").post("/api/entries", json={**NEW, "dept_id": "net"}).status_code == 403
def test_full_workflow_publish_and_supersede():
    ed, rv, vw = C("editor_corp@t.io"), C("reviewer_corp@t.io"), C("viewer_corp@t.io")
    eid = ed.post("/api/entries", json=NEW).json()["id"]
    assert vw.get(f"/api/entries/{eid}").status_code == 404
    assert "Leave policy" not in str(vw.post("/api/ask", json={"query": "annual leave policy"}).json())
    assert ed.post(f"/api/entries/{eid}/publish").status_code in (403, 404, 409)
    assert ed.post(f"/api/entries/{eid}/submit").json()["status"] == "review"
    assert ed.post(f"/api/entries/{eid}/review", json={"approve": True}).status_code in (403, 404)
    assert rv.post(f"/api/entries/{eid}/review", json={"approve": True}).json()["status"] == "approved"
    assert rv.post(f"/api/entries/{eid}/publish").json()["status"] == "published"
    assert "annual leave" in str(vw.post("/api/ask", json={"query": "annual leave policy"}).json()).lower()
    nid = ed.post(f"/api/entries/{eid}/revise").json()["id"]
    ed.patch(f"/api/entries/{nid}", json={"body": "Employees receive twenty-two days of annual leave."}); ed.post(f"/api/entries/{nid}/submit")
    rv.post(f"/api/entries/{nid}/review", json={"approve": True}); rv.post(f"/api/entries/{nid}/publish")
    cx = psycopg.connect(DSN())
    assert cx.execute("SELECT status::text FROM entries WHERE id=%s", (eid,)).fetchone()[0] == "superseded"
    assert cx.execute("SELECT version FROM entries WHERE id=%s", (nid,)).fetchone()[0] == 2
    assert "twenty-two" in vw.post("/api/ask", json={"query": "annual leave policy"}).json()["answer"]
def test_author_cannot_approve_own_entry():
    ad = C("admin@t.io"); eid = ad.post("/api/entries", json=NEW).json()["id"]; ad.post(f"/api/entries/{eid}/submit")
    r = ad.post(f"/api/entries/{eid}/review", json={"approve": True}); assert r.status_code == 403 and "Separation of duties" in r.json()["detail"]
def test_published_entries_are_not_directly_editable():
    assert C("editor_corp@t.io").patch("/api/entries/S001", json={"title": "tampered title"}).status_code == 409

def test_admin_endpoints_forbidden_to_non_admins():
    for e in ["editor_corp@t.io", "viewer_all@t.io", "reviewer_corp@t.io"]:
        c = C(e); assert c.get("/api/audit").status_code == 403; assert c.post("/api/admin/users", json={"email": "x@y.io", "display_name": "x"}).status_code == 403
def test_audit_log_records_actions_and_is_tamper_evident():
    a = C("admin@t.io"); actions = {r["action"] for r in a.get("/api/audit", params={"limit": 500}).json()}
    assert {"login.success", "entry.create", "entry.publish", "login.failed"} <= actions
    assert a.get("/api/audit/verify").json()["intact"] is True
    cx = psycopg.connect(DSN(), autocommit=True)
    with pytest.raises(psycopg.errors.RaiseException): cx.execute("DELETE FROM audit_log")
    with pytest.raises(psycopg.errors.RaiseException): cx.execute("UPDATE audit_log SET action='x'")
def test_role_change_revokes_other_sessions_and_takes_effect():
    a = C("admin@t.io"); uid = psycopg.connect(DSN()).execute("SELECT id FROM users WHERE email='norole@t.io'").fetchone()[0]
    u = C("norole@t.io"); assert u.get("/api/entries").json() == []
    a.put(f"/api/admin/users/{uid}/roles", json={"roles": [{"dept_id": "corp", "role": "viewer"}]})
    assert u.get("/api/auth/me").status_code == 401
    u = C("norole@t.io"); assert len(u.get("/api/entries").json()) >= 27
    a.put(f"/api/admin/users/{uid}/roles", json={"roles": []})
def test_weak_password_rejected_for_new_user():
    assert C("admin@t.io").post("/api/admin/users", json={"email": "n@t.io", "display_name": "n", "password": "short"}).status_code == 422

def test_dashboard_matches_database():
    d = C("admin@t.io").get("/api/dashboard").json(); cx = psycopg.connect(DSN())
    assert d["approved_entries"] == cx.execute("SELECT count(*) FROM entries WHERE status='published'").fetchone()[0]
    assert sum(x["entries"] for x in d["by_department"]) == d["approved_entries"]
    assert d["coverage_percent"] is None
    assert all(x["id"] == "corp" for x in C("viewer_corp@t.io").get("/api/dashboard").json()["by_department"])

def test_entra_token_validation():
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from app import security as sec
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    class J:
        def get_signing_key_from_jwt(self, t): return type("K", (), {"key": k.public_key()})
    base = {"iss": "https://login.microsoftonline.com/T1/v2.0", "aud": "CID", "sub": "s", "tid": "T1", "exp": int(time.time()) + 600}
    assert sec.verify_entra_id_token(jwt.encode(base, k, algorithm="RS256"), J(), "T1", "CID")["sub"] == "s"
    for bad in [{**base, "aud": "other"}, {**base, "iss": "https://evil/v2.0"}, {**base, "exp": int(time.time()) - 5}, {**base, "tid": "T2"}]:
        with pytest.raises(Exception): sec.verify_entra_id_token(jwt.encode(bad, k, algorithm="RS256"), J(), "T1", "CID")
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(Exception): sec.verify_entra_id_token(jwt.encode(base, other, algorithm="RS256"), J(), "T1", "CID")

def test_off_topic_questions_are_refused():
    c = C("viewer_all@t.io")
    for q in ["who is the CEO of Google", "what is the price of bitcoin today"]: assert c.post("/api/ask", json={"query": q}).json()["answered"] is False
    for q in ["what is the mission of Fiber@Home", "What is NTTN?", "what certifications does Fiber@Home hold", "Which licences were phased out under the 2025 policy?"]:
        assert c.post("/api/ask", json={"query": q}).json()["answered"] is True, q

def test_reviewer_and_editor_can_list_unpublished_but_viewer_cannot():
    assert C("reviewer_corp@t.io").get("/api/entries", params={"status": "review"}).status_code == 200
    assert C("editor_corp@t.io").get("/api/entries", params={"status": "draft"}).status_code == 200
    assert C("viewer_corp@t.io").get("/api/entries", params={"status": "draft"}).status_code == 403
    rows = C("reviewer_corp@t.io").get("/api/entries", params={"status": "draft"}).json()
    assert all(r["dept_id"] == "corp" for r in rows)
