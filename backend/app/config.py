import os
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://pgu@127.0.0.1/fhl")
SESSION_ABSOLUTE_HOURS = int(os.environ.get("SESSION_ABSOLUTE_HOURS", "12"))
SESSION_IDLE_MINUTES = int(os.environ.get("SESSION_IDLE_MINUTES", "30"))
SERVERLESS = bool(os.environ.get("VERCEL"))                         # Vercel: no long-lived pool, trust the platform proxy header
TRUST_PROXY_HEADERS = SERVERLESS or os.environ.get("TRUST_PROXY_HEADERS", "false").lower() == "true"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true"   # false only for local HTTP development
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
# Microsoft Entra ID (optional until the tenant is provided)
ENTRA_TENANT_ID = os.environ.get("ENTRA_TENANT_ID", "")
ENTRA_CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID", "")
RELEVANCE_THRESHOLD = float(os.environ.get("RELEVANCE_THRESHOLD", "0.05"))
MIN_TERM_COVERAGE = float(os.environ.get("MIN_TERM_COVERAGE", "0.67"))

# Email one-time passcodes (OTP). Disabled until a pepper and an SMTP server are configured.
OTP_PEPPER = os.environ.get("OTP_PEPPER", "")                       # long random secret, kept outside the database
OTP_TTL_MINUTES = int(os.environ.get("OTP_TTL_MINUTES", "10"))
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))
OTP_RESEND_SECONDS = int(os.environ.get("OTP_RESEND_SECONDS", "30"))
OTP_MAX_PER_HOUR = int(os.environ.get("OTP_MAX_PER_HOUR", "5"))
OTP_ALLOWED_DOMAINS = [d.strip().lower() for d in os.environ.get("OTP_ALLOWED_DOMAINS", "fiberathome.net").split(",") if d.strip()]  # "*" = any
SMTP_HOST = os.environ.get("SMTP_HOST", "")                          # "memory" is for automated tests only
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", ""); SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "Fiber@Home Knowledge Vault <no-reply@fiberathome.net>")
SMTP_SECURITY = os.environ.get("SMTP_SECURITY", "starttls")          # starttls | ssl | none
def otp_enabled() -> bool: return bool(OTP_PEPPER and SMTP_HOST)
