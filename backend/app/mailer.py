import smtplib, ssl, logging, json, os, re, urllib.request, urllib.error
from email.message import EmailMessage
from . import config
log = logging.getLogger("fhl.mailer")
OUTBOX: list[dict] = []          # used only when SMTP_HOST == "memory" (automated tests)

def send_code(to: str, code: str, minutes: int) -> None:
    subject = "Your Knowledge Vault sign-in code"
    text = (f"Your Fiber@Home Knowledge Vault code is {code}\n\nIt expires in {minutes} minutes and can be used once.\n"
            "If you did not try to sign in, you can ignore this email; nobody can sign in without this code.")
    html = (f"<div style=\"font-family:Arial,sans-serif;color:#101D30;max-width:420px\"><p style=\"font-size:15px\">Your Fiber@Home Knowledge Vault code is</p>"
            f"<p style=\"font-size:32px;letter-spacing:8px;font-weight:700;color:#CE242B;margin:8px 0\">{code}</p>"
            f"<p style=\"font-size:13px;color:#4B525B\">It expires in {minutes} minutes and can be used once. If you did not try to sign in, you can ignore this email.</p></div>")
    if config.SMTP_HOST == "memory":
        OUTBOX.append({"to": to, "code": code, "subject": subject}); return
    key = os.environ.get("BREVO_API_KEY", "").strip()
    if key:
        _brevo(key, to, subject, text, html); return
    m = EmailMessage(); m["From"] = config.SMTP_FROM; m["To"] = to; m["Subject"] = subject
    m.set_content(text); m.add_alternative(html, subtype="html")
    errors = []
    for port, sec in _attempts():
        try: _deliver(m, config.SMTP_HOST, port, sec); return
        except Exception as e:
            errors.append(f"{port}/{sec}: {type(e).__name__}: {str(e)[:70]}"); log.warning("mail attempt failed %s", errors[-1])
    raise RuntimeError(" | ".join(errors))

def _attempts() -> list:
    """The configured port/mode first, then the other standard pairing (465 TLS-from-start, 587 STARTTLS) so one wrong dashboard value cannot block sign-in."""
    first = (config.SMTP_PORT, config.SMTP_SECURITY); out = [first]
    if config.SMTP_SECURITY != "none":
        for alt in ((465, "ssl"), (587, "starttls")):
            if alt not in out: out.append(alt)
    return out

def _deliver(m, host, port, sec):
    ctx = ssl.create_default_context()
    if sec == "ssl": s = smtplib.SMTP_SSL(host, port, timeout=12, context=ctx)
    else:
        s = smtplib.SMTP(host, port, timeout=12)
        if sec == "starttls": s.starttls(context=ctx)
    try:
        if config.SMTP_USER: s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        s.send_message(m)
    finally:
        try: s.quit()
        except Exception: pass


def _brevo(key, to, subject, text, html):
    """HTTPS delivery (works on Vercel, where outbound SMTP is cut off)."""
    frm = config.SMTP_FROM; mt = re.match(r"\s*(.*?)\s*<([^>]+)>\s*$", frm)
    sender = {"name": mt.group(1).strip("\"' ") or "Fiber@Home Knowledge Vault", "email": mt.group(2)} if mt else {"name": "Fiber@Home Knowledge Vault", "email": frm}
    body = json.dumps({"sender": sender, "to": [{"email": to}], "subject": subject, "htmlContent": html, "textContent": text}).encode()
    req = urllib.request.Request("https://api.brevo.com/v3/smtp/email", data=body, method="POST",
        headers={"api-key": key, "content-type": "application/json", "accept": "application/json"})
    try: urllib.request.urlopen(req, timeout=15).read()
    except urllib.error.HTTPError as e: raise RuntimeError(f"brevo HTTP {e.code}: {e.read()[:200].decode('utf8','replace')}")
