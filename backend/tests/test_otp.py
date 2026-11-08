import datetime as dt, os, pytest, psycopg
os.environ.update(OTP_PEPPER="test-pepper-0123456789", SMTP_HOST="memory", OTP_ALLOWED_DOMAINS="t.io", OTP_RESEND_SECONDS="0")
from app import config, mailer
for k in ("OTP_PEPPER", "SMTP_HOST"): setattr(config, k, os.environ[k])
config.OTP_ALLOWED_DOMAINS = ["t.io"]; config.OTP_RESEND_SECONDS = 0

@pytest.fixture(autouse=True)
def clean():
    mailer.OUTBOX.clear(); config.OTP_RESEND_SECONDS = 0; config.OTP_MAX_PER_HOUR = 5
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True); cx.execute("DELETE FROM login_codes"); cx.execute("UPDATE users SET failed_logins=0, locked_until=NULL"); cx.close()

def code_for(email): return [m for m in mailer.OUTBOX if m["to"] == email][-1]["code"]

def test_methods_reports_otp_available(client):
    assert client.get("/api/auth/methods").json()["otp"] is True

def test_request_then_verify_signs_in_and_code_is_single_use(client):
    r = client.post("/api/auth/otp/request", json={"email": "viewer_all@t.io"}); assert r.status_code == 200 and r.json()["sent"] is True
    code = code_for("viewer_all@t.io"); assert len(code) == 6 and code.isdigit()
    r = client.post("/api/auth/otp/verify", json={"email": "VIEWER_all@t.io", "code": code}); assert r.status_code == 200 and r.json()["csrf_token"]
    assert client.get("/api/auth/me").json()["email"] == "viewer_all@t.io"
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]; client.post("/api/auth/logout")
    assert client.post("/api/auth/otp/verify", json={"email": "viewer_all@t.io", "code": code}).status_code == 401   # already used

def test_unknown_inactive_and_other_domain_look_identical_and_send_nothing(client):
    a = client.post("/api/auth/otp/request", json={"email": "viewer_all@t.io"}).json()
    for e in ["nobody@t.io", "stranger@elsewhere.com"]:
        r = client.post("/api/auth/otp/request", json={"email": e}); assert r.status_code == 200 and r.json() == a
    assert [m["to"] for m in mailer.OUTBOX] == ["viewer_all@t.io"]

def test_wrong_code_is_rejected_and_attempts_are_limited(client):
    client.post("/api/auth/otp/request", json={"email": "viewer_corp@t.io"}); good = code_for("viewer_corp@t.io")
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(5): assert client.post("/api/auth/otp/verify", json={"email": "viewer_corp@t.io", "code": wrong}).status_code == 401
    r = client.post("/api/auth/otp/verify", json={"email": "viewer_corp@t.io", "code": good}); assert r.status_code == 429   # exhausted: even the right code is refused
    client.post("/api/auth/otp/request", json={"email": "viewer_corp@t.io"})
    assert client.post("/api/auth/otp/verify", json={"email": "viewer_corp@t.io", "code": code_for("viewer_corp@t.io")}).status_code == 200

def test_new_code_invalidates_the_old_one(client):
    client.post("/api/auth/otp/request", json={"email": "editor_corp@t.io"}); old = code_for("editor_corp@t.io")
    client.post("/api/auth/otp/request", json={"email": "editor_corp@t.io"}); new = code_for("editor_corp@t.io")
    if old != new: assert client.post("/api/auth/otp/verify", json={"email": "editor_corp@t.io", "code": old}).status_code == 401
    assert client.post("/api/auth/otp/verify", json={"email": "editor_corp@t.io", "code": new}).status_code == 200

def test_expired_code_is_rejected(client):
    client.post("/api/auth/otp/request", json={"email": "reviewer_corp@t.io"}); code = code_for("reviewer_corp@t.io")
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True); cx.execute("UPDATE login_codes SET expires_at = now() - interval '1 minute'"); cx.close()
    assert client.post("/api/auth/otp/verify", json={"email": "reviewer_corp@t.io", "code": code}).status_code == 401

def test_resend_throttle_and_hourly_cap(client):
    config.OTP_RESEND_SECONDS = 60
    client.post("/api/auth/otp/request", json={"email": "admin@t.io"}); client.post("/api/auth/otp/request", json={"email": "admin@t.io"})
    assert len([m for m in mailer.OUTBOX if m["to"] == "admin@t.io"]) == 1
    config.OTP_RESEND_SECONDS = 0; config.OTP_MAX_PER_HOUR = 3
    for _ in range(6): client.post("/api/auth/otp/request", json={"email": "admin@t.io"})
    assert len([m for m in mailer.OUTBOX if m["to"] == "admin@t.io"]) == 3

def test_code_format_is_validated_and_hash_not_plaintext(client):
    assert client.post("/api/auth/otp/verify", json={"email": "viewer_all@t.io", "code": "12ab56"}).status_code == 422
    client.post("/api/auth/otp/request", json={"email": "viewer_all@t.io"}); code = code_for("viewer_all@t.io")
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True); h = bytes(cx.execute("SELECT code_hash FROM login_codes").fetchone()[0]); cx.close()
    assert code.encode() not in h and len(h) == 32

def test_disabled_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(config, "OTP_PEPPER", "")
    assert client.get("/api/auth/methods").json()["otp"] is False
    assert client.post("/api/auth/otp/request", json={"email": "viewer_all@t.io"}).status_code == 503
