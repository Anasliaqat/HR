"""Password hashing, signed access tokens, and role dependencies."""
import base64, hashlib, hmac, json, secrets, smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.config import settings
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

def _secret() -> bytes:
    if len(settings.auth_secret_key) < 32:
        raise HTTPException(status_code=503, detail="AUTH_SECRET_KEY must contain at least 32 characters")
    return settings.auth_secret_key.encode()

def create_access_token(subject: str, role: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub":subject,"role":role,"exp":int((datetime.now(timezone.utc)+timedelta(hours=TOKEN_TTL_HOURS)).timestamp())}).encode()).rstrip(b"=")
    signing = header+b"."+payload
    signature = base64.urlsafe_b64encode(hmac.new(_secret(), signing, hashlib.sha256).digest()).rstrip(b"=")
    return (signing+b"."+signature).decode()

def decode_access_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
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
    account = db.get(model, data["sub"])
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
    if not all((settings.smtp_host, settings.smtp_user, settings.smtp_password, settings.smtp_from_email)):
        raise HTTPException(status_code=503, detail="Email verification is not configured. Set SMTP settings before HR signup.")
    message = EmailMessage()
    message["Subject"] = "Your HR portal verification code"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(f"Your HR portal verification code is {code}. It expires in 10 minutes.")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    except Exception:
        raise HTTPException(status_code=502, detail="Could not send verification email. Check SMTP configuration.") from None
