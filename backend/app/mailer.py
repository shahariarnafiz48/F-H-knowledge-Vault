import smtplib, ssl, logging
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
    m = EmailMessage(); m["From"] = config.SMTP_FROM; m["To"] = to; m["Subject"] = subject
    m.set_content(text); m.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    if config.SMTP_SECURITY == "ssl": s = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15, context=ctx)
    else:
        s = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
        if config.SMTP_SECURITY == "starttls": s.starttls(context=ctx)
    try:
        if config.SMTP_USER: s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        s.send_message(m)
    finally:
        try: s.quit()
        except Exception: pass
