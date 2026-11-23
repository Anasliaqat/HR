"""Candidate-only job discovery, applications, and private status."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.resumes import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, UPLOAD_DIRECTORY, _process_resume_evaluation
from app.config import settings
from app.database.connection import get_db
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.resume_evaluation import ResumeEvaluation
from app.schemas.applications import ApplicationResponse
from app.security import require_candidate
from app.services.phone_service import normalize_phone_number
from app.services.upload_security import UnsafeUploadError, validate_resume_content

router = APIRouter(prefix="/portal", tags=["candidate portal"])

# Candidates only see a simple stage, never scores or internal workflow states.
_SHORTLISTED = {"approved_by_hr", "interview_eligible", "screening", "interview"}
_NOT_SELECTED = {"rejected", "rejected_by_hr"}


def candidate_stage(application_status: str) -> str:
    if application_status in _SHORTLISTED:
        return "shortlisted"
    if application_status in _NOT_SELECTED:
        return "not_selected"
    if application_status == "hired":
        return "hired"
    if application_status == "withdrawn":
        return "withdrawn"
    return "under_review"


class ApplyPayload(BaseModel):
    job_id: UUID
    phone: str | None = Field(default=None, max_length=40)
    details: dict[str, object] = Field(default_factory=dict)
    email_consent: bool = False


async def _read_resume_upload(file: UploadFile) -> tuple[bytes, str]:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Only PDF, DOCX, and TXT resumes are supported")
    content = bytearray()
    while chunk := await file.read(64 * 1024):
        content.extend(chunk)
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="Resume exceeds the 10 MB upload limit")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded resume is empty")
    try:
        validate_resume_content(bytes(content), extension)
    except UnsafeUploadError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from None
    return bytes(content), extension


def _job_summary(job: Job) -> dict:
    return {
        "id": str(job.id), "title": job.title, "description": job.description,
        "department": job.department, "location": job.location,
        "employment_type": job.employment_type, "required_skills": job.required_skills,
        "required_experience_years": job.required_experience_years,
    }


@router.get("/jobs")
def public_jobs(db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.status == "open").order_by(Job.created_at.desc())).all()
    return [_job_summary(job) for job in jobs]


@router.post("/apply", status_code=status.HTTP_201_CREATED)
async def apply_with_resume(
    background_tasks: BackgroundTasks,
    job_id: UUID = Form(...),
    email_consent: bool = Form(False),
    phone: str | None = Form(None),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
    principal: dict = Depends(require_candidate),
    db: Session = Depends(get_db),
):
    """Apply and upload the CV in one step; scoring and the email decision then run automatically."""
    if not email_consent:
        raise HTTPException(
            status_code=422,
            detail="Please agree to receive emails about your application. We email you the outcome.",
        )
    candidate = db.get(Candidate, UUID(principal["id"]))
    job = db.get(Job, job_id)
    if candidate is None or job is None or job.status != "open":
        raise HTTPException(status_code=404, detail="This job is not open for applications")
    if db.scalar(select(Application.id).where(Application.candidate_id == candidate.id, Application.job_id == job.id)):
        raise HTTPException(status_code=409, detail="You have already applied for this job")
    normalized_phone = None
    if phone and phone.strip():
        normalized_phone = normalize_phone_number(phone, settings.phone_default_region)
        if normalized_phone is None:
            raise HTTPException(status_code=422, detail="Enter a valid phone number, for example +923001234567")
    content, extension = await _read_resume_upload(file)

    resume_id = uuid4()
    stored_path = UPLOAD_DIRECTORY / f"{resume_id}{extension}"
    await asyncio.to_thread(UPLOAD_DIRECTORY.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(stored_path.write_bytes, content)

    if normalized_phone:
        candidate.phone = normalized_phone
    if notes and notes.strip():
        candidate.details = {**(candidate.details or {}), "notes": notes.strip()[:2000]}
    if not candidate.email_consent:
        candidate.email_consent = True
        candidate.email_consent_at = datetime.now(timezone.utc)
    application = Application(candidate_id=candidate.id, job_id=job.id)
    db.add(application)
    try:
        db.flush()
        db.add(ResumeEvaluation(
            id=resume_id, candidate_id=candidate.id, application_id=application.id,
            job_id=job.id, file_name=Path(file.filename or "resume").name,
            file_path=str(stored_path), content_type=file.content_type,
            uploaded_at=datetime.now(timezone.utc), evaluation_status="processing",
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="You have already applied for this job") from None
    background_tasks.add_task(_process_resume_evaluation, resume_id, job.id)
    return {
        "application_id": str(application.id),
        "job_title": job.title,
        "stage": candidate_stage(application.status),
        "message": "Application received. We will email you about the outcome.",
    }


@router.post("/applications", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def apply(payload: ApplyPayload, principal: dict = Depends(require_candidate), db: Session = Depends(get_db)):
    candidate = db.get(Candidate, UUID(principal["id"]))
    job = db.get(Job, payload.job_id)
    if job is None or job.status != "open":
        raise HTTPException(status_code=404, detail="Open job not found")
    application = Application(candidate_id=candidate.id, job_id=job.id)
    candidate.phone = payload.phone
    candidate.details = payload.details
    if payload.email_consent and not candidate.email_consent:
        candidate.email_consent = True
        candidate.email_consent_at = datetime.now(timezone.utc)
    db.add(application)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You have already applied for this job") from None
    db.refresh(application)
    return application


@router.get("/applications")
def my_applications(principal: dict = Depends(require_candidate), db: Session = Depends(get_db)):
    rows = db.scalars(select(Application).where(Application.candidate_id == UUID(principal["id"])).order_by(Application.applied_at.desc())).all()
    return [{"id": str(a.id), "job_id": str(a.job_id), "job_title": a.job.title, "status": a.status, "stage": candidate_stage(a.status), "applied_at": a.applied_at} for a in rows]


@router.post("/applications/{application_id}/resume", status_code=status.HTTP_201_CREATED)
async def upload_my_resume(
    application_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    principal: dict = Depends(require_candidate),
    db: Session = Depends(get_db),
):
    application = db.get(Application, application_id)
    if application is None or str(application.candidate_id) != principal["id"]:
        raise HTTPException(status_code=404, detail="Application not found")
    content, extension = await _read_resume_upload(file)
    resume_id = uuid4()
    stored_path = UPLOAD_DIRECTORY / f"{resume_id}{extension}"
    await asyncio.to_thread(UPLOAD_DIRECTORY.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(stored_path.write_bytes, content)
    resume = ResumeEvaluation(
        id=resume_id, candidate_id=application.candidate_id,
        application_id=application.id, job_id=application.job_id,
        file_name=Path(file.filename or "resume").name,
        file_path=str(stored_path), content_type=file.content_type,
        uploaded_at=datetime.now(timezone.utc), evaluation_status="processing",
    )
    db.add(resume)
    db.commit()
    background_tasks.add_task(_process_resume_evaluation, resume.id, application.job_id)
    return {"id": str(resume.id), "file_name": resume.file_name, "evaluation_status": resume.evaluation_status}
