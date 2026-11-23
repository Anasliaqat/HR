"""Registration, verification, and login endpoints."""
import hashlib, secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.config import settings
from app.database.connection import get_db
from app.models.user import User
from app.models.candidate import Candidate
from app.services import login_throttle
from app.security import burn_password_check, get_principal, hash_password, verify_password, create_access_token, send_verification_code

router = APIRouter(prefix="/auth", tags=["authentication"])

class RegisterPayload(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

class VerifyPayload(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)

class LoginPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

def _token(account, role):
    return {"access_token": create_access_token(str(account.id), role), "token_type":"bearer", "role":role, "email":account.email, "full_name":account.full_name}

@router.post("/hr/register", status_code=201)
def register_hr(payload: RegisterPayload, db: Session = Depends(get_db)):
    email = str(payload.email).casefold()
    if email != settings.hr_allowed_email.casefold():
        raise HTTPException(status_code=403, detail="This email is not authorized for HR registration")
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="An HR account already exists for this email")
    code = f"{secrets.randbelow(1000000):06d}"
    user = User(email=email, full_name=payload.full_name, password_hash=hash_password(payload.password), role="hr", is_active=False, is_verified=False, verification_code_hash=hashlib.sha256(code.encode()).hexdigest(), verification_expires_at=datetime.now(timezone.utc)+timedelta(minutes=10))
    db.add(user)
    db.commit()
    try:
        send_verification_code(email, code)
    except Exception:
        db.delete(user); db.commit()
        raise
    return {"message":"Verification code sent to the authorized HR email. It expires in 10 minutes."}

@router.post("/hr/verify")
def verify_hr(payload: VerifyPayload, request: Request, db: Session = Depends(get_db)):
    email = str(payload.email).casefold()
    address = request.client.host if request.client else "unknown"
    login_throttle.check_allowed(email, address)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or user.is_verified or not user.verification_code_hash or not user.verification_expires_at:
        login_throttle.record_failure(email, address)
        raise HTTPException(status_code=400, detail="No pending HR verification was found")
    expires_at = user.verification_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc) or not secrets.compare_digest(user.verification_code_hash, hashlib.sha256(payload.code.encode()).hexdigest()):
        login_throttle.record_failure(email, address)
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    login_throttle.record_success(email)
    user.is_verified = True; user.is_active = True
    user.verification_code_hash = None; user.verification_expires_at = None
    db.commit(); db.refresh(user)
    return _token(user, "hr")

@router.post("/candidate/register", status_code=201)
def register_candidate(payload: RegisterPayload, db: Session = Depends(get_db)):
    email = str(payload.email).casefold()
    if email == settings.hr_allowed_email.strip().casefold():
        raise HTTPException(status_code=403, detail="This email is reserved for the HR portal. Use a different email to apply for jobs.")
    if db.scalar(select(Candidate).where(func.lower(Candidate.email) == email)):
        raise HTTPException(status_code=409, detail="An account or profile already exists for this email. Log in instead, or ask HR to remove the old profile if it was entered for you.")
    candidate = Candidate(full_name=payload.full_name, email=email, password_hash=hash_password(payload.password))
    db.add(candidate); db.commit(); db.refresh(candidate)
    return _token(candidate, "candidate")

@router.post("/login")
def login(payload: LoginPayload, request: Request, db: Session = Depends(get_db)):
    email = str(payload.email).casefold()
    address = request.client.host if request.client else "unknown"
    login_throttle.check_allowed(email, address)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user and user.role == "hr" and user.is_active and user.is_verified and verify_password(payload.password, user.password_hash):
        login_throttle.record_success(email)
        return _token(user, "hr")
    candidate = db.scalar(select(Candidate).where(func.lower(Candidate.email) == email))
    if candidate and candidate.password_hash and verify_password(payload.password, candidate.password_hash):
        login_throttle.record_success(email)
        return _token(candidate, "candidate")
    if user is None and not (candidate and candidate.password_hash):
        burn_password_check(payload.password)
    login_throttle.record_failure(email, address)
    raise HTTPException(status_code=401, detail="Email or password is incorrect")


@router.get("/me")
def me(principal: dict = Depends(get_principal)):
    """Who the current token belongs to; the frontend uses this to validate a saved login."""
    return principal
