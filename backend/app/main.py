import datetime as dt, difflib, ipaddress, json, re
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, Request, Response, Query
from pydantic import BaseModel, Field, EmailStr
from . import config, rbac, mailer, security as sec
from .db import get_db

app = FastAPI(title="Fiber@Home Knowledge Intelligence Platform API", version="1.0.0",
              docs_url="/api/docs", openapi_url="/api/openapi.json")

PAGE_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data: blob:; font-src data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    api = request.url.path.startswith("/api")
    page = request.url.path == "/"
    csp = PAGE_CSP if page else "default-src 'none'; frame-ancestors 'none'" if api else "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    resp.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store", "Content-Security-Policy": csp,
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains"})
    return resp

# ------------------------------------------------------------------ helpers
def client_ip(request: Request):
    """Real client address. X-Forwarded-For is trusted only when the app runs behind a platform proxy we control (Vercel / Caddy)."""
    if config.TRUST_PROXY_HEADERS:
        xf = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        try: return str(ipaddress.ip_address(xf))
        except ValueError: pass
    return request.client.host if request.client else None

def audit(cx, user, action, otype=None, oid=None, detail=None, request: Request | None = None, email=None):
    ip = client_ip(request) if request else None
    try: ipaddress.ip_address(ip or "")
    except ValueError: ip = None
    cx.execute("INSERT INTO audit_log(actor,actor_email,action,object_type,object_id,detail,ip) VALUES(%s,%s,%s,%s,%s,%s,%s)",
               (user["id"] if user else None, (user or {}).get("email", email), action, otype, str(oid) if oid else None, json.dumps(detail or {}), ip))

def _load_user(request: Request, cx, check_csrf: bool):
    tok = request.cookies.get("fhl_session")
    if not tok: raise HTTPException(401, "Sign in to continue.")
    now = dt.datetime.now(dt.timezone.utc)
    s = cx.execute("""SELECT s.id,s.user_id,s.csrf_hash,u.email,u.display_name,u.is_active FROM sessions s JOIN users u ON u.id=s.user_id
                      WHERE s.token_hash=%s AND NOT s.revoked AND s.expires_at>%s AND s.last_seen>%s""",
                   (sec.sha(tok), now, now - dt.timedelta(minutes=config.SESSION_IDLE_MINUTES))).fetchone()
    if not s or not s["is_active"]: raise HTTPException(401, "Your session has expired. Please sign in again.")
    if check_csrf and request.method not in ("GET", "HEAD", "OPTIONS"):
        c = request.headers.get("x-csrf-token", "")
        if not c or not sec.safe_eq(bytes(sec.sha(c)).hex(), bytes(s["csrf_hash"]).hex()): raise HTTPException(403, "Security check failed. Reload the page and try again.")
    cx.execute("UPDATE sessions SET last_seen=%s WHERE id=%s", (now, s["id"]))
    return {"id": s["user_id"], "email": s["email"], "name": s["display_name"], "session": s["id"], "roles": rbac.roles_of(cx, s["user_id"])}

def current_user(request: Request, cx=Depends(get_db)):          # NOTE: no extra parameters here - they would become query-string options
    return _load_user(request, cx, True)

def start_session(cx, response: Response, user_id):
    tok, csrf = sec.new_token(), sec.new_token()
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=config.SESSION_ABSOLUTE_HOURS)
    cx.execute("INSERT INTO sessions(user_id,token_hash,csrf_hash,expires_at) VALUES(%s,%s,%s,%s)", (user_id, sec.sha(tok), sec.sha(csrf), exp))
    response.set_cookie("fhl_session", tok, httponly=True, secure=config.COOKIE_SECURE, samesite="strict", max_age=config.SESSION_ABSOLUTE_HOURS * 3600, path="/")
    return csrf

# ------------------------------------------------------------------ auth
class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)

@app.post("/api/auth/login", tags=["auth"])
def login(body: Login, request: Request, response: Response, cx=Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)
    u = cx.execute("SELECT * FROM users WHERE lower(email)=lower(%s)", (body.email,)).fetchone()
    if u and u["locked_until"] and u["locked_until"] > now:
        audit(cx, None, "login.locked", "user", u["id"], request=request, email=body.email)
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    if not (u and u["is_active"] and sec.verify_password(u["password_hash"], body.password)):
        if u:
            n = u["failed_logins"] + 1
            cx.execute("UPDATE users SET failed_logins=%s, locked_until=%s WHERE id=%s",
                       (n, now + dt.timedelta(minutes=config.LOCKOUT_MINUTES) if n >= config.MAX_FAILED_LOGINS else None, u["id"]))
        audit(cx, None, "login.failed", "user", u["id"] if u else None, request=request, email=body.email)
        cx.commit()   # keep the failure record even though we raise
        raise HTTPException(401, "The email or password is incorrect.")
    cx.execute("UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=%s", (u["id"],))
    csrf = start_session(cx, response, u["id"])
    user = {"id": u["id"], "email": u["email"]}
    audit(cx, user, "login.success", "user", u["id"], request=request)
    return {"csrf_token": csrf, "name": u["display_name"]}


class OtpRequest(BaseModel):
    email: EmailStr

class OtpVerify(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")

def _otp_domain_ok(email: str) -> bool:
    d = email.rsplit("@", 1)[-1].lower()
    return "*" in config.OTP_ALLOWED_DOMAINS or d in config.OTP_ALLOWED_DOMAINS

@app.get("/api/auth/methods", tags=["auth"])
def auth_methods():
    """Lets the sign-in screen show only the methods this server actually supports."""
    return {"password": True, "otp": config.otp_enabled(), "sso": bool(config.ENTRA_TENANT_ID and config.ENTRA_CLIENT_ID),
            "otp_ttl_minutes": config.OTP_TTL_MINUTES, "otp_resend_seconds": config.OTP_RESEND_SECONDS}

@app.post("/api/auth/otp/request", tags=["auth"])
def otp_request(body: OtpRequest, request: Request, cx=Depends(get_db)):
    """Always answers the same way, whether or not the email has access, so the endpoint cannot be used to discover accounts."""
    if not config.otp_enabled(): raise HTTPException(503, "One-time password sign-in is not configured on this server.")
    generic = {"sent": True, "ttl_minutes": config.OTP_TTL_MINUTES, "resend_after": config.OTP_RESEND_SECONDS}
    now = dt.datetime.now(dt.timezone.utc)
    u = cx.execute("SELECT * FROM users WHERE lower(email)=lower(%s)", (body.email,)).fetchone()
    if not (u and u["is_active"] and _otp_domain_ok(body.email)):
        audit(cx, None, "otp.request.ignored", "user", u["id"] if u else None, request=request, email=body.email); return generic
    if u["locked_until"] and u["locked_until"] > now:
        audit(cx, None, "otp.request.locked", "user", u["id"], request=request, email=body.email); return generic
    last = cx.execute("SELECT max(created_at) AS t, count(*) FILTER (WHERE created_at > %s) AS n FROM login_codes WHERE user_id=%s",
                      (now - dt.timedelta(hours=1), u["id"])).fetchone()
    if (last["t"] and (now - last["t"]).total_seconds() < config.OTP_RESEND_SECONDS) or last["n"] >= config.OTP_MAX_PER_HOUR:
        audit(cx, None, "otp.request.throttled", "user", u["id"], request=request, email=body.email); return generic
    code = sec.new_otp()
    cx.execute("UPDATE login_codes SET used=true WHERE user_id=%s AND NOT used", (u["id"],))       # only the newest code works
    cx.execute("INSERT INTO login_codes(user_id,code_hash,expires_at) VALUES(%s,%s,%s)",
               (u["id"], sec.otp_hash(u["id"], code), now + dt.timedelta(minutes=config.OTP_TTL_MINUTES)))
    try: mailer.send_code(u["email"], code, config.OTP_TTL_MINUTES); audit(cx, None, "otp.sent", "user", u["id"], request=request, email=body.email)
    except Exception as e:
        audit(cx, None, "otp.send_failed", "user", u["id"], {"error": type(e).__name__}, request=request, email=body.email)
    return generic

@app.post("/api/auth/otp/verify", tags=["auth"])
def otp_verify(body: OtpVerify, request: Request, response: Response, cx=Depends(get_db)):
    if not config.otp_enabled(): raise HTTPException(503, "One-time password sign-in is not configured on this server.")
    now = dt.datetime.now(dt.timezone.utc)
    bad = HTTPException(401, "That code is incorrect or has expired. Check the code or request a new one.")
    u = cx.execute("SELECT * FROM users WHERE lower(email)=lower(%s)", (body.email,)).fetchone()
    if not (u and u["is_active"] and _otp_domain_ok(body.email)):
        sec.otp_hash("00000000-0000-0000-0000-000000000000", body.code); raise bad                 # similar timing for unknown users
    if u["locked_until"] and u["locked_until"] > now: raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    row = cx.execute("SELECT * FROM login_codes WHERE user_id=%s AND NOT used AND expires_at>%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE", (u["id"], now)).fetchone()
    if not row: sec.otp_hash(u["id"], body.code); audit(cx, None, "otp.failed", "user", u["id"], {"why": "none"}, request=request, email=body.email); cx.commit(); raise bad
    if row["attempts"] >= config.OTP_MAX_ATTEMPTS:
        cx.execute("UPDATE login_codes SET used=true WHERE id=%s", (row["id"],)); audit(cx, None, "otp.exhausted", "user", u["id"], request=request, email=body.email); cx.commit()
        raise HTTPException(429, "Too many incorrect codes. Request a new code.")
    if not sec.safe_eq(bytes(sec.otp_hash(u["id"], body.code)).hex(), bytes(row["code_hash"]).hex()):
        cx.execute("UPDATE login_codes SET attempts=attempts+1 WHERE id=%s", (row["id"],))
        audit(cx, None, "otp.failed", "user", u["id"], {"why": "mismatch"}, request=request, email=body.email); cx.commit(); raise bad
    cx.execute("UPDATE login_codes SET used=true WHERE id=%s", (row["id"],))
    cx.execute("UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=%s", (u["id"],))
    csrf = start_session(cx, response, u["id"]); audit(cx, {"id": u["id"], "email": u["email"]}, "login.otp", "user", u["id"], request=request)
    return {"csrf_token": csrf, "name": u["display_name"]}

class EntraToken(BaseModel):
    id_token: str

@app.post("/api/auth/sso/entra", tags=["auth"])
def sso_entra(body: EntraToken, request: Request, response: Response, cx=Depends(get_db)):
    try: claims = sec.verify_entra_id_token(body.id_token)
    except PermissionError as e: raise HTTPException(503, str(e))
    except Exception: raise HTTPException(401, "Single sign-on failed. Contact your administrator.")
    email = (claims.get("preferred_username") or claims.get("email") or "").lower()
    u = cx.execute("SELECT * FROM users WHERE idp_subject=%s OR lower(email)=%s", (claims["sub"], email)).fetchone()
    if not u:   # JIT provisioning with NO roles: access must be granted by an administrator
        u = cx.execute("INSERT INTO users(email,display_name,idp_subject) VALUES(%s,%s,%s) RETURNING *", (email, claims.get("name", email), claims["sub"])).fetchone()
    elif not u["idp_subject"]: cx.execute("UPDATE users SET idp_subject=%s WHERE id=%s", (claims["sub"], u["id"]))
    if not u["is_active"]: raise HTTPException(403, "This account is disabled.")
    csrf = start_session(cx, response, u["id"]); audit(cx, {"id": u["id"], "email": email}, "login.sso", "user", u["id"], request=request)
    return {"csrf_token": csrf, "name": u["display_name"]}

@app.post("/api/auth/logout", tags=["auth"])
def logout(response: Response, cx=Depends(get_db), request: Request = None):
    user = _load_user(request, cx, False)
    cx.execute("UPDATE sessions SET revoked=true WHERE id=%s", (user["session"],)); audit(cx, user, "logout", request=request)
    response.delete_cookie("fhl_session", path="/"); return {"ok": True}

@app.get("/api/auth/me", tags=["auth"])
def me(user=Depends(current_user)):
    return {"email": user["email"], "name": user["name"], "roles": user["roles"]}

# ------------------------------------------------------------------ search (hybrid: full-text OR-semantics + trigram similarity)
ACR = {"nttn": "nationwide telecommunication transmission network", "btrc": "bangladesh telecommunication regulatory commission", "isp": "internet service provider",
       "iig": "international internet gateway", "icx": "interconnection exchange", "dwdm": "dense wavelength division multiplexing", "bdix": "bangladesh internet exchange", "fhl": "fiber at home"}
def expand(q: str) -> str:
    return q + " " + " ".join(ACR[w] for w in re.findall(r"[a-z0-9]+", q.lower()) if w in ACR)
def search_entries(cx, user, q: str, dept: str | None, limit: int = 5):
    allowed = rbac.depts_for(cx, user, "read")          # permission is applied INSIDE the retrieval query
    if allowed is not None and not allowed: return []
    words = list(dict.fromkeys(re.findall(r"[A-Za-z0-9]+", expand(q))))[:24]
    if not words: return []
    return cx.execute("""
      WITH qq AS (SELECT to_tsquery('english', %(tq)s) AS tq)
      SELECT e.id,e.dept_id,e.title,e.reference,e.source,e.category,e.version,
             ts_headline('english', e.body, qq.tq, 'MaxWords=60,MinWords=25,StartSel=,StopSel=') AS snippet, e.body,
             (ts_rank_cd(e.tsv, qq.tq, 32) + 0.6*similarity(e.title, %(q)s)) AS score
      FROM entries e, qq
      WHERE e.status='published' AND (%(all)s OR e.dept_id = ANY(%(allowed)s)) AND (%(dept)s::text IS NULL OR e.dept_id=%(dept)s)
        AND (e.tsv @@ qq.tq OR similarity(e.title, %(q)s) > 0.25)
      ORDER BY score DESC LIMIT %(lim)s""",
      {"tq": " | ".join(words), "q": q, "all": allowed is None, "allowed": list(allowed or []), "dept": dept, "lim": limit}).fetchall()

STOP = set("a an the is are was were be been of in on at to for from by with and or not do does did can could should would will what which who whom whose how when where why this that these those it its my our your their me us you we they i about under into as if than then so there here any all please tell give explain say said says out up off rule rules".split())
def term_coverage(q: str, rows) -> float:
    """Share of the question's content words found (by 5-letter stem) in the top entry. Guards against confident answers to off-topic questions."""
    hay = " ".join(r["title"] + " " + r["body"] + " " + (r["category"] or "") for r in rows[:3]).lower()
    terms = [w for w in re.findall(r"[a-z0-9]+", q.lower()) if w not in STOP]
    if not terms: return 0.0
    return sum(1 for w in terms if w[:5] in hay) / len(terms)

class Ask(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    dept: str | None = None

@app.post("/api/ask", tags=["assistant"])
def ask(body: Ask, request: Request, user=Depends(current_user), cx=Depends(get_db)):
    rows = search_entries(cx, user, body.query, body.dept)
    ok = bool(rows) and rows[0]["score"] >= config.RELEVANCE_THRESHOLD and term_coverage(body.query, rows) >= config.MIN_TERM_COVERAGE
    ev = cx.execute("INSERT INTO search_events(user_id,query,answered,top_entry,n_results) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                    (user["id"], body.query, ok, rows[0]["id"] if ok else None, len(rows))).fetchone()
    if not ok:
        cx.execute("INSERT INTO gaps(query,dept_id) VALUES(%s,%s)", (body.query, body.dept))
        return {"answered": False, "search_event": ev["id"], "answer": None, "citations": [],
                "message": "I could not find this in the approved knowledge base. The question has been logged for the knowledge owners."}
    top = rows[0]
    conflict = [r["id"] for r in rows[1:] if r["source"] != top["source"] and difflib.SequenceMatcher(None, r["title"].lower(), top["title"].lower()).ratio() > .8
                and difflib.SequenceMatcher(None, r["body"], top["body"]).ratio() < .6]
    return {"answered": True, "search_event": ev["id"], "answer": top["body"], "mode": "extractive",
            "citations": [{"entry_id": r["id"], "title": r["title"], "source": r["source"], "reference": r["reference"], "department": r["dept_id"],
                           "snippet": r["snippet"], "relevance": round(float(r["score"]), 3)} for r in rows if r["score"] >= 0.4 * top["score"]],
            "conflicts_with": conflict, "note": "Answer text is quoted verbatim from the first citation. No text is generated."}

class Fb(BaseModel):
    search_event: int; helpful: bool; comment: str | None = Field(None, max_length=1000)
@app.post("/api/feedback", tags=["assistant"])
def feedback(body: Fb, user=Depends(current_user), cx=Depends(get_db)):
    cx.execute("INSERT INTO feedback(user_id,search_event,helpful,comment) VALUES(%s,%s,%s,%s)", (user["id"], body.search_event, body.helpful, body.comment)); return {"ok": True}

# ------------------------------------------------------------------ entries + approval workflow
@app.get("/api/entries", tags=["entries"])
def list_entries(dept: str | None = None, status: str = "published", q: str | None = None, limit: int = Query(50, le=200), offset: int = 0,
                 user=Depends(current_user), cx=Depends(get_db)):
    allowed = rbac.depts_for(cx, user, "read")
    if status != "published":      # unpublished work is visible only to the people who write or review it, and only in their departments
        w, r = rbac.depts_for(cx, user, "write"), rbac.depts_for(cx, user, "review")
        allowed = None if (w is None or r is None) else (w | r)
        if allowed is not None and not allowed: raise HTTPException(403, "You do not have permission to view unpublished entries.")
    return cx.execute("""SELECT id,dept_id,category,subcategory,kind,title,reference,source,status::text,version,updated_at FROM entries
        WHERE status=%(s)s::doc_status AND (%(all)s OR dept_id=ANY(%(al)s)) AND (%(d)s::text IS NULL OR dept_id=%(d)s)
          AND (%(q)s::text IS NULL OR title ILIKE '%%'||%(q)s||'%%') ORDER BY id LIMIT %(l)s OFFSET %(o)s""",
        {"s": status, "all": allowed is None, "al": list(allowed or []), "d": dept, "q": q, "l": limit, "o": offset}).fetchall()

def get_entry(cx, user, eid, perm="read"):
    e = cx.execute("SELECT * FROM entries WHERE id=%s", (eid,)).fetchone()
    d = rbac.depts_for(cx, user, perm)
    if not e or (d is not None and e["dept_id"] not in d): raise HTTPException(404, "Entry not found.")
    return e

@app.get("/api/entries/{eid}", tags=["entries"])
def read_entry(eid: str, user=Depends(current_user), cx=Depends(get_db)):
    e = get_entry(cx, user, eid)
    if e["status"] != "published" and not (rbac.depts_for(cx, user, "write") is None or e["dept_id"] in (rbac.depts_for(cx, user, "write") | (rbac.depts_for(cx, user, "review") or set()))):
        raise HTTPException(404, "Entry not found.")
    e.pop("tsv", None); return e

class NewEntry(BaseModel):
    dept_id: str; category: str = Field(min_length=1, max_length=200); subcategory: str | None = Field(None, max_length=300)
    kind: Literal["doc", "qa", "team"] = "team"; title: str = Field(min_length=3, max_length=300); body: str = Field(min_length=3, max_length=20000)
    reference: str | None = Field(None, max_length=300); source: str = Field(min_length=2, max_length=300)

@app.post("/api/entries", tags=["entries"], status_code=201)
def create_entry(body: NewEntry, request: Request, user=Depends(current_user), cx=Depends(get_db)):
    rbac.require(cx, user, "write", body.dept_id)
    if not cx.execute("SELECT 1 FROM departments WHERE id=%s", (body.dept_id,)).fetchone(): raise HTTPException(422, "Unknown department.")
    eid = "E%06d" % cx.execute("SELECT coalesce(max(substring(id from 2)::int),0)+1 AS n FROM entries WHERE id ~ '^E[0-9]+$'").fetchone()["n"]
    cx.execute("INSERT INTO entries(id,dept_id,category,subcategory,kind,title,body,reference,source,status,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s)",
               (eid, body.dept_id, body.category, body.subcategory, body.kind, body.title, body.body, body.reference, body.source, user["id"]))
    audit(cx, user, "entry.create", "entry", eid, {"dept": body.dept_id}, request); return {"id": eid, "status": "draft"}

def transition(cx, user, request, eid, frm, to, perm, action, sod=False):
    e = get_entry(cx, user, eid, perm)
    if e["status"] != frm: raise HTTPException(409, f"This entry is '{e['status']}', so it cannot move to '{to}'.")
    if sod and e["created_by"] == user["id"]: raise HTTPException(403, "Separation of duties: the author cannot approve their own entry.")
    cx.execute("UPDATE entries SET status=%s::doc_status, updated_at=now() WHERE id=%s", (to, eid))
    if to == "published" and e["supersedes"]:
        cx.execute("UPDATE entries SET status='superseded', updated_at=now() WHERE id=%s AND status='published'", (e["supersedes"],))
    audit(cx, user, action, "entry", eid, {"from": frm, "to": to}, request); return {"id": eid, "status": to}

@app.post("/api/entries/{eid}/submit", tags=["workflow"])
def submit(eid: str, request: Request, user=Depends(current_user), cx=Depends(get_db)): return transition(cx, user, request, eid, "draft", "review", "write", "entry.submit")
class Decision(BaseModel):
    approve: bool; note: str | None = Field(None, max_length=1000)
@app.post("/api/entries/{eid}/review", tags=["workflow"])
def review(eid: str, body: Decision, request: Request, user=Depends(current_user), cx=Depends(get_db)):
    return transition(cx, user, request, eid, "review", "approved" if body.approve else "draft", "review", "entry.approve" if body.approve else "entry.reject", sod=True)
@app.post("/api/entries/{eid}/publish", tags=["workflow"])
def publish(eid: str, request: Request, user=Depends(current_user), cx=Depends(get_db)): return transition(cx, user, request, eid, "approved", "published", "review", "entry.publish", sod=True)
@app.post("/api/entries/{eid}/archive", tags=["workflow"])
def archive(eid: str, request: Request, user=Depends(current_user), cx=Depends(get_db)): return transition(cx, user, request, eid, "published", "archived", "review", "entry.archive")
@app.post("/api/entries/{eid}/revise", tags=["workflow"], status_code=201)
def revise(eid: str, request: Request, user=Depends(current_user), cx=Depends(get_db)):
    e = get_entry(cx, user, eid, "write")
    if e["status"] != "published": raise HTTPException(409, "Only a published entry can be revised.")
    if cx.execute("SELECT 1 FROM entries WHERE supersedes=%s AND status IN ('draft','review','approved')", (eid,)).fetchone(): raise HTTPException(409, "A revision is already in progress.")
    nid = "E%06d" % cx.execute("SELECT coalesce(max(substring(id from 2)::int),0)+1 AS n FROM entries WHERE id ~ '^E[0-9]+$'").fetchone()["n"]
    cx.execute("""INSERT INTO entries(id,dept_id,document_id,category,subcategory,kind,title,body,reference,source,status,version,supersedes,created_by)
                  SELECT %s,dept_id,document_id,category,subcategory,kind,title,body,reference,source,'draft',version+1,id,%s FROM entries WHERE id=%s""", (nid, user["id"], eid))
    audit(cx, user, "entry.revise", "entry", nid, {"supersedes": eid}, request); return {"id": nid, "status": "draft", "supersedes": eid}
class Edit(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=300); body: str | None = Field(None, min_length=3, max_length=20000); reference: str | None = Field(None, max_length=300)
@app.patch("/api/entries/{eid}", tags=["entries"])
def edit_entry(eid: str, body: Edit, request: Request, user=Depends(current_user), cx=Depends(get_db)):
    e = get_entry(cx, user, eid, "write")
    if e["status"] != "draft": raise HTTPException(409, "Only drafts can be edited. Use 'revise' for a published entry.")
    d = body.model_dump(exclude_none=True)
    for k, v in d.items(): cx.execute(f"UPDATE entries SET {k}=%s, updated_at=now() WHERE id=%s", (v, eid))   # keys come from the validated model
    audit(cx, user, "entry.edit", "entry", eid, {"fields": list(d)}, request); return {"id": eid}

# ------------------------------------------------------------------ gaps, dashboard, audit, admin
@app.get("/api/gaps", tags=["gaps"])
def gaps(status: str = "open", user=Depends(current_user), cx=Depends(get_db)):
    d = rbac.depts_for(cx, user, "write")
    if d is not None and not d and not rbac.depts_for(cx, user, "review"): raise HTTPException(403, "You do not have permission to do this.")
    return cx.execute("SELECT g.*, count(*) OVER() AS total FROM gaps g WHERE status=%s ORDER BY created_at DESC LIMIT 200", (status,)).fetchall()
class GapUp(BaseModel): status: Literal["open", "assigned", "resolved"]; assignee: str | None = None
@app.patch("/api/gaps/{gid}", tags=["gaps"])
def gap_update(gid: int, body: GapUp, request: Request, user=Depends(current_user), cx=Depends(get_db)):
    if not (rbac.depts_for(cx, user, "write") is None or rbac.depts_for(cx, user, "write")): raise HTTPException(403, "You do not have permission to do this.")
    cx.execute("UPDATE gaps SET status=%s, assignee=%s, resolved_at=CASE WHEN %s='resolved' THEN now() END WHERE id=%s", (body.status, body.assignee, body.status, gid))
    audit(cx, user, "gap.update", "gap", gid, body.model_dump(), request); return {"ok": True}

@app.get("/api/dashboard", tags=["dashboard"])
def dashboard(user=Depends(current_user), cx=Depends(get_db)):
    allowed = rbac.depts_for(cx, user, "read"); P = {"all": allowed is None, "al": list(allowed or [])}
    one = lambda sql, p=P: cx.execute(sql, p).fetchone()
    return {
      "approved_entries": one("SELECT count(*) AS n FROM entries WHERE status='published' AND (%(all)s OR dept_id=ANY(%(al)s))")["n"],
      "by_department": cx.execute("SELECT d.id,d.name,count(e.id) FILTER (WHERE e.status='published') AS entries FROM departments d LEFT JOIN entries e ON e.dept_id=d.id WHERE (%(all)s OR d.id=ANY(%(al)s)) GROUP BY d.id,d.name ORDER BY entries DESC,d.name", P).fetchall(),
      "pending_approvals": one("SELECT count(*) AS n FROM entries WHERE status='review' AND (%(all)s OR dept_id=ANY(%(al)s))")["n"],
      "documents_overdue_review": one("SELECT count(*) AS n FROM documents WHERE review_due<current_date AND status='published' AND (%(all)s OR dept_id=ANY(%(al)s))")["n"],
      "searches_30d": one("SELECT count(*) AS n FROM search_events WHERE at>now()-interval '30 days'")["n"],
      "unanswered_30d": one("SELECT count(*) AS n FROM search_events WHERE NOT answered AND at>now()-interval '30 days'")["n"],
      "open_gaps": one("SELECT count(*) AS n FROM gaps WHERE status='open'")["n"],
      "top_queries_30d": cx.execute("SELECT lower(query) AS query,count(*) AS n FROM search_events WHERE at>now()-interval '30 days' GROUP BY 1 ORDER BY n DESC LIMIT 10").fetchall(),
      "feedback": cx.execute("SELECT count(*) FILTER (WHERE helpful) AS helpful,count(*) FILTER (WHERE NOT helpful) AS not_helpful FROM feedback").fetchone(),
      "recent_updates": cx.execute("SELECT id,title,dept_id,status::text,updated_at FROM entries WHERE (%(all)s OR dept_id=ANY(%(al)s)) AND id ~ '^E' ORDER BY updated_at DESC LIMIT 8", P).fetchall(),
      "coverage_percent": None, "coverage_note": "Roadmap coverage is not modelled in the database yet (planned module)."}

@app.get("/api/audit", tags=["admin"])
def audit_list(limit: int = Query(100, le=500), user=Depends(current_user), cx=Depends(get_db)):
    rbac.require(cx, user, "admin")
    return cx.execute("SELECT id,at,actor_email,action,object_type,object_id,detail,host(ip) AS ip FROM audit_log ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
@app.get("/api/audit/verify", tags=["admin"])
def audit_verify(user=Depends(current_user), cx=Depends(get_db)):
    rbac.require(cx, user, "admin")
    bad = cx.execute("""SELECT id FROM (SELECT id,prev_hash,row_hash,lag(row_hash) OVER (ORDER BY id) AS expect,
        encode(digest(coalesce(prev_hash,'')||at::text||coalesce(actor_email,'')||action||coalesce(object_type,'')||coalesce(object_id,'')||detail::text,'sha256'),'hex') AS calc FROM audit_log) x
        WHERE row_hash<>calc OR prev_hash<>coalesce(expect,'')""").fetchall()
    return {"intact": not bad, "broken_at": [b["id"] for b in bad]}

class NewUser(BaseModel):
    email: EmailStr; display_name: str = Field(min_length=1, max_length=120); password: str | None = None
@app.post("/api/admin/users", tags=["admin"], status_code=201)
def create_user(body: NewUser, request: Request, user=Depends(current_user), cx=Depends(get_db)):
    rbac.require(cx, user, "admin")
    if body.password and (m := sec.validate_password_policy(body.password)): raise HTTPException(422, m)
    if cx.execute("SELECT 1 FROM users WHERE lower(email)=lower(%s)", (body.email,)).fetchone(): raise HTTPException(409, "A user with this email already exists.")
    r = cx.execute("INSERT INTO users(email,display_name,password_hash) VALUES(%s,%s,%s) RETURNING id", (body.email, body.display_name, sec.hash_password(body.password) if body.password else None)).fetchone()
    audit(cx, user, "user.create", "user", r["id"], {"email": body.email}, request); return {"id": r["id"]}
class RoleGrant(BaseModel): dept_id: str | None = None; role: Literal["admin", "editor", "reviewer", "viewer"]
class RoleSet(BaseModel): roles: list[RoleGrant]
@app.put("/api/admin/users/{uid}/roles", tags=["admin"])
def set_roles(uid: str, body: RoleSet, request: Request, user=Depends(current_user), cx=Depends(get_db)):
    rbac.require(cx, user, "admin")
    if any(g.role == "admin" and g.dept_id for g in body.roles): raise HTTPException(422, "The administrator role is organisation-wide.")
    cx.execute("DELETE FROM user_roles WHERE user_id=%s", (uid,))
    for g in body.roles: cx.execute("INSERT INTO user_roles(user_id,dept_id,role) VALUES(%s,%s,%s)", (uid, g.dept_id, g.role))
    cx.execute("UPDATE sessions SET revoked=true WHERE user_id=%s AND id<>%s", (uid, user["session"]))
    audit(cx, user, "user.roles", "user", uid, body.model_dump(), request); return {"ok": True}

@app.get("/api/health", tags=["ops"])
def health(cx=Depends(get_db)): cx.execute("SELECT 1"); return {"status": "ok"}

# ------------------------------------------------------------------ static front end (registered last so /api routes win)
import pathlib
from fastapi.responses import FileResponse
_WEB = next((c for c in (pathlib.Path(__file__).resolve().parents[2] / "web", pathlib.Path.cwd() / "web", pathlib.Path("/var/task/web")) if (c / "login.html").exists()),
            pathlib.Path(__file__).resolve().parents[2] / "web")
_NOSTORE = {"Cache-Control": "no-store, max-age=0"}
@app.get("/", include_in_schema=False)
def index(request: Request, cx=Depends(get_db)):
    """The public address shows ONLY the sign-in page. The vault (which contains the company knowledge) is sent only
    when the request carries a valid session, i.e. after the emailed one-time code has been verified."""
    try: _load_user(request, cx, False); name = "vault.html"
    except HTTPException: name = "login.html"
    f = _WEB / name
    if not f.exists(): raise HTTPException(503, "The front end has not been built. Run: python3 frontend-src/build_frontend.py")
    return FileResponse(f, media_type="text/html", headers=_NOSTORE)
