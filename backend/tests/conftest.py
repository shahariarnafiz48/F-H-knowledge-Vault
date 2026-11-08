import os, subprocess, pathlib, pytest, psycopg
os.environ.update(DATABASE_URL="postgresql://pgu@127.0.0.1/fhl_test", COOKIE_SECURE="false")
ROOT = pathlib.Path(__file__).resolve().parents[2]
@pytest.fixture(scope="session", autouse=True)
def db():
    a = psycopg.connect("postgresql://pgu@127.0.0.1/postgres", autocommit=True)
    a.execute("DROP DATABASE IF EXISTS fhl_test WITH (FORCE)"); a.execute("CREATE DATABASE fhl_test"); a.close()
    subprocess.run(["psql", "-h", "127.0.0.1", "-U", "pgu", "-d", "fhl_test", "-q", "-v", "ON_ERROR_STOP=1", "-f", str(ROOT / "db/schema.sql")], check=True, capture_output=True)
    env = dict(os.environ); subprocess.run(["python3", "-I", str(ROOT / "scripts/migrate_kb.py")], check=True, capture_output=True, env=env)
    from app import security as sec
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    pw = sec.hash_password("Correct-Horse-9")
    def mk(email, roles):
        uid = cx.execute("INSERT INTO users(email,display_name,password_hash) VALUES(%s,%s,%s) RETURNING id", (email, email.split("@")[0], pw)).fetchone()[0]
        for d, r in roles: cx.execute("INSERT INTO user_roles(user_id,dept_id,role) VALUES(%s,%s,%s)", (uid, d, r))
    mk("admin@t.io", [(None, "admin")]); mk("viewer_corp@t.io", [("corp", "viewer")]); mk("viewer_all@t.io", [(None, "viewer")])
    mk("editor_corp@t.io", [("corp", "editor"), ("corp", "viewer")]); mk("reviewer_corp@t.io", [("corp", "reviewer")]); mk("norole@t.io", [])
    yield
@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
def login(c, email, pw="Correct-Horse-9"):
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    if r.status_code == 200: c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r
