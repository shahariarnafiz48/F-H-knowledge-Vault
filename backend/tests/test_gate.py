import os, pathlib, pytest, psycopg
os.environ.update(OTP_PEPPER="test-pepper-0123456789", SMTP_HOST="memory", OTP_ALLOWED_DOMAINS="t.io", OTP_RESEND_SECONDS="0")
from app import config, mailer
for k in ("OTP_PEPPER", "SMTP_HOST"): setattr(config, k, os.environ[k])
config.OTP_ALLOWED_DOMAINS = ["t.io"]; config.OTP_RESEND_SECONDS = 0

WEB = pathlib.Path(__file__).resolve().parents[2] / "web"
SECRET = "BTRC"          # a term that exists only inside the knowledge base, never on the sign-in page

@pytest.fixture(autouse=True)
def clean():
    mailer.OUTBOX.clear(); config.OTP_RESEND_SECONDS = 0; config.OTP_MAX_PER_HOUR = 50
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True); cx.execute("DELETE FROM login_codes"); cx.execute("UPDATE users SET failed_logins=0, locked_until=NULL"); cx.close()

def sign_in(client, email="viewer_all@t.io"):
    client.post("/api/auth/otp/request", json={"email": email})
    code = [m for m in mailer.OUTBOX if m["to"] == email][-1]["code"]
    r = client.post("/api/auth/otp/verify", json={"email": email, "code": code}); assert r.status_code == 200; return r.json()

def test_built_pages_exist_and_login_page_holds_no_knowledge():
    assert (WEB / "vault.html").exists() and (WEB / "login.html").exists()
    login = (WEB / "login.html").read_text(); vault = (WEB / "vault.html").read_text()
    assert SECRET not in login and "const KB" not in login and len(login) < 400_000
    assert SECRET in vault and "const SERVER=true" in vault

def test_public_address_shows_only_the_sign_in_page(client):
    r = client.get("/"); assert r.status_code == 200
    assert "Send one-time code" in r.text and SECRET not in r.text and "const SERVER" not in r.text
    assert "no-store" in r.headers["cache-control"]

def test_vault_is_sent_only_after_a_verified_code(client):
    sign_in(client)
    r = client.get("/"); assert r.status_code == 200 and "const SERVER=true" in r.text and SECRET in r.text
    assert "no-store" in r.headers["cache-control"] and "frame-ancestors 'none'" in r.headers["content-security-policy"]

def test_wrong_code_never_unlocks_the_vault(client):
    client.post("/api/auth/otp/request", json={"email": "viewer_all@t.io"})
    assert client.post("/api/auth/otp/verify", json={"email": "viewer_all@t.io", "code": "000000"}).status_code == 401
    r = client.get("/"); assert "const SERVER=true" not in r.text and SECRET not in r.text

def test_expired_or_revoked_session_goes_back_to_sign_in(client):
    sign_in(client); assert "const SERVER=true" in client.get("/").text
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True); cx.execute("UPDATE sessions SET revoked=true"); cx.close()
    assert "const SERVER=true" not in client.get("/").text and client.get("/api/auth/me").status_code == 401

def test_logout_works_from_any_tab_without_csrf_and_locks_the_vault_again(client):
    sign_in(client); assert client.post("/api/auth/logout").status_code == 200
    assert "const SERVER=true" not in client.get("/").text

def test_csrf_still_enforced_and_cannot_be_switched_off_by_query_string(client):
    tok = sign_in(client)["csrf_token"]
    body = {"query": "BTRC licence"}
    assert client.post("/api/ask", json=body).status_code == 403
    assert client.post("/api/ask?check_csrf=false", json=body).status_code == 403
    assert client.post("/api/ask", json=body, headers={"X-CSRF-Token": tok}).status_code == 200

def test_data_endpoints_need_a_session(client):
    for path in ("/api/entries", "/api/dashboard", "/api/gaps", "/api/auth/me"):
        assert client.get(path).status_code == 401, path
