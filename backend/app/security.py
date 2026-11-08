import hashlib, hmac, secrets, datetime as dt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from . import config
_ph = PasswordHasher()
def hash_password(p: str) -> str: return _ph.hash(p)
def verify_password(h: str | None, p: str) -> bool:
    if not h: _ph.hash(p); return False          # equalise timing for unknown users
    try: return _ph.verify(h, p)
    except (VerifyMismatchError, InvalidHashError): return False
def sha(b: str) -> bytes: return hashlib.sha256(b.encode()).digest()
def new_token() -> str: return secrets.token_urlsafe(32)
def safe_eq(a: str, b: str) -> bool: return hmac.compare_digest(a.encode(), b.encode())
def validate_password_policy(p: str) -> str | None:
    if len(p) < 12: return "Password must be at least 12 characters."
    if p.lower() == p or p.upper() == p or not any(c.isdigit() for c in p): return "Use upper and lower case letters and at least one digit."
    return None

def verify_entra_id_token(token: str, jwks_client=None, tenant=None, client_id=None) -> dict:
    """Validate a Microsoft Entra ID (OIDC) id_token: signature (JWKS), issuer, audience, expiry, tenant."""
    import jwt
    tenant = tenant or config.ENTRA_TENANT_ID; client_id = client_id or config.ENTRA_CLIENT_ID
    if not tenant or not client_id: raise PermissionError("SSO is not configured")
    jwks_client = jwks_client or jwt.PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys")
    key = jwks_client.get_signing_key_from_jwt(token).key
    claims = jwt.decode(token, key, algorithms=["RS256"], audience=client_id,
                        issuer=f"https://login.microsoftonline.com/{tenant}/v2.0", options={"require": ["exp", "iss", "aud", "sub"]})
    if claims.get("tid") != tenant: raise PermissionError("wrong tenant")
    return claims

def new_otp() -> str: return f"{secrets.randbelow(1_000_000):06d}"
def otp_hash(user_id, code: str) -> bytes:
    return hmac.new(config.OTP_PEPPER.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).digest()
