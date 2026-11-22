"""Candidate-only job discovery, applications, and private status."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job
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
    jobs = db.scalars(select(Job).where(Job.status == "published").order_by(Job.created_at.desc())).all()
    return [{"id":str(j.id),"title":j.title,"description":j.description,"department":j.department,"location":j.location,"employment_type":j.employment_type,"required_skills":j.required_skills,"required_experience_years":j.required_experience_years} for j in jobs]

@router.post("/applications", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def apply(payload: ApplyPayload, principal: dict = Depends(require_candidate), db: Session = Depends(get_db)):
    candidate = db.get(Candidate, UUID(principal["id"]))
    job = db.get(Job, payload.job_id)
    if job is None or job.status != "published":
        raise HTTPException(status_code=404, detail="Published job not found")
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
