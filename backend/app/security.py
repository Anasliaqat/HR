"""Password hashing, signed access tokens, and role dependencies."""
import base64, hashlib, hmac, json, logging, os, secrets
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.config import AUTH_SECRET_FILE, settings
from app.services.smtp_mailer import SmtpDeliveryError, send_message
from app.database.connection import get_db
from app.models.user import User
from app.models.candidate import Candidate

bearer = HTTPBearer(auto_error=False)
TOKEN_TTL_HOURS = 12

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()

def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_text, digest_text = stored.split("$", 2)
        if scheme != "scrypt": return False
        salt = base64.urlsafe_b64decode(salt_text)
        expected = base64.urlsafe_b64decode(digest_text)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

logger = logging.getLogger(__name__)
# The value shipped in older .env.example files. It is public, so never trust it.
_PLACEHOLDER_SECRETS = {"replace-with-a-random-secret-at-least-32-characters"}
_local_secret_cache: bytes | None = None

def _local_secret() -> bytes:
    """A random signing key kept in backend/.auth_secret (gitignored), created on first use."""
    global _local_secret_cache
    if _local_secret_cache is not None:
        return _local_secret_cache
    try:
        existing = AUTH_SECRET_FILE.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            _local_secret_cache = existing.encode()
            return _local_secret_cache
    except OSError:
        pass
    generated = secrets.token_urlsafe(48)
    try:
        descriptor = os.open(AUTH_SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(generated)
        logger.warning("AUTH_SECRET_KEY is not set; generated a private signing key in %s.", AUTH_SECRET_FILE.name)
    except OSError:
        logger.warning("AUTH_SECRET_KEY is not set and the key file could not be saved; logins will reset on restart.")
    _local_secret_cache = generated.encode()
    return _local_secret_cache

def _secret() -> bytes:
    configured = settings.auth_secret_key.strip()
    if len(configured) >= 32 and configured not in _PLACEHOLDER_SECRETS:
        return configured.encode()
    return _local_secret()

def create_access_token(subject: str, role: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub":subject,"role":role,"exp":int((datetime.now(timezone.utc)+timedelta(hours=TOKEN_TTL_HOURS)).timestamp())}).encode()).rstrip(b"=")
    signing = header+b"."+payload
    signature = base64.urlsafe_b64encode(hmac.new(_secret(), signing, hashlib.sha256).digest()).rstrip(b"=")
    return (signing+b"."+signature).decode()

def decode_access_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
        if json.loads(base64.urlsafe_b64decode(header+"="*((4-len(header)%4)%4))).get("alg") != "HS256": raise ValueError()
        signing = (header+"."+payload).encode()
        expected = base64.urlsafe_b64encode(hmac.new(_secret(), signing, hashlib.sha256).digest()).rstrip(b"=").decode()
        if not hmac.compare_digest(signature, expected): raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload+"="*((4-len(payload)%4)%4)))
        if int(data["exp"]) < int(datetime.now(timezone.utc).timestamp()): raise ValueError()
        if data.get("role") not in {"hr","candidate"}: raise ValueError()
        return data
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from None

def get_principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> dict:
    if credentials is None: raise HTTPException(status_code=401, detail="Login required")
    data = decode_access_token(credentials.credentials)
    model = User if data["role"] == "hr" else Candidate
    try:
        account_id = UUID(str(data["sub"]))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None
    account = db.get(model, account_id)
    if account is None or (data["role"] == "hr" and (not account.is_active or not account.is_verified)):
        raise HTTPException(status_code=401, detail="Account is inactive")
    return {"id": str(account.id), "role": data["role"], "email": account.email}

def require_hr(principal: dict = Depends(get_principal)) -> dict:
    if principal["role"] != "hr": raise HTTPException(status_code=403, detail="HR access required")
    return principal

def require_candidate(principal: dict = Depends(get_principal)) -> dict:
    if principal["role"] != "candidate": raise HTTPException(status_code=403, detail="Candidate access required")
    return principal

def send_verification_code(email: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Your HR portal verification code"
    message["From"] = settings.smtp_from_email or settings.smtp_user
    message["To"] = email
    message.set_content(f"Your HR portal verification code is {code}. It expires in 10 minutes.")
    try:
        send_message(message)
    except SmtpDeliveryError as exc:
        raise HTTPException(status_code=502, detail=f"Could not send the verification email. {exc}") from None


# A real scrypt hash of a random value, so a login for an unknown email costs the
# same time as one for a real account and cannot be used to discover who is registered.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))

def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)
