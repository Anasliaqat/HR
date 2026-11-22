"""Candidate-only job discovery, applications, and private status."""
from uuid import UUID, uuid4
from pathlib import Path
from datetime import datetime, timezone
import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.resume_evaluation import ResumeEvaluation
from app.api.resumes import UPLOAD_DIRECTORY, ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, _process_resume_evaluation
from app.schemas.applications import ApplicationResponse
from app.security import require_candidate

router = APIRouter(prefix="/portal", tags=["candidate portal"])

class ApplyPayload(BaseModel):
    job_id: UUID
    phone: str | None = Field(default=None, max_length=40)
    details: dict[str, object] = Field(default_factory=dict)
    email_consent: bool = False

@router.get("/jobs")
def public_jobs(db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.status == "open").order_by(Job.created_at.desc())).all()
    return [{"id":str(j.id),"title":j.title,"description":j.description,"department":j.department,"location":j.location,"employment_type":j.employment_type,"required_skills":j.required_skills,"required_experience_years":j.required_experience_years} for j in jobs]

@router.post("/applications", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def apply(payload: ApplyPayload, principal: dict = Depends(require_candidate), db: Session = Depends(get_db)):
    candidate = db.get(Candidate, UUID(principal["id"]))
    job = db.get(Job, payload.job_id)
    if job is None or job.status != "open":
        raise HTTPException(status_code=404, detail="Open job not found")
    application = Application(candidate_id=candidate.id, job_id=job.id)
    candidate.phone = payload.phone
    candidate.details = payload.details
    candidate.email_consent = payload.email_consent
    db.add(application)
    try: db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="You have already applied for this job") from None
    db.refresh(application)
    return application

@router.get("/applications")
def my_applications(principal: dict = Depends(require_candidate), db: Session = Depends(get_db)):
    rows = db.scalars(select(Application).where(Application.candidate_id == UUID(principal["id"])).order_by(Application.applied_at.desc())).all()
    return [{"id":str(a.id),"job_id":str(a.job_id),"job_title":a.job.title,"status":a.status,"applied_at":a.applied_at} for a in rows]


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
