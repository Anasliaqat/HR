"""Resume upload and review API routes."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import get_db, get_engine
from app.agents.email_automation_agent import apply_resume_score_outcome
from app.agents.resume_agent import score_resume
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.resume_evaluation import ResumeEvaluation
from app.schemas.resumes import (
    ResumeEvaluationRequest,
    ResumeEvaluationResponse,
    ResumeResponse,
)
from app.services.resume_parser import extract_profile, extract_text

router = APIRouter(prefix="/resumes", tags=["resumes"])
logger = logging.getLogger(__name__)
UPLOAD_DIRECTORY = Path(__file__).resolve().parents[2] / "uploads"
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


@router.get("", response_model=list[ResumeResponse])
def list_resumes(db: Session = Depends(get_db)) -> list[ResumeEvaluation]:
    return list(
        db.scalars(
            select(ResumeEvaluation).order_by(ResumeEvaluation.uploaded_at.desc())
        ).all()
    )


@router.post(
    "/upload",
    response_model=ResumeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_resume(
    candidate_id: UUID = Form(...),
    file: UploadFile = File(...),
    application_id: UUID | None = Form(default=None),
    job_id: UUID | None = Form(default=None),
    db: Session = Depends(get_db),
) -> ResumeResponse:
    if db.get(Candidate, candidate_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )
    application = None
    if application_id is not None:
        application = db.get(Application, application_id)
        if application is None or application.candidate_id != candidate_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found for this candidate",
            )
        if job_id is not None and application.job_id != job_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The selected job does not match this candidate's application",
            )
        job_id = application.job_id
    if job_id is not None and db.get(Job, job_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, DOCX, and TXT resumes are supported",
        )

    content = bytearray()
    while chunk := await file.read(64 * 1024):
        content.extend(chunk)
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Resume exceeds the 10 MB upload limit",
            )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded resume is empty",
        )

    resume_id = uuid4()
    stored_name = f"{resume_id}{extension}"
    stored_path = UPLOAD_DIRECTORY / stored_name
    try:
        await asyncio.to_thread(UPLOAD_DIRECTORY.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(stored_path.write_bytes, content)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save uploaded resume",
        ) from exc
    try:
        await asyncio.to_thread(extract_text, stored_path)
    except ValueError as exc:
        await asyncio.to_thread(stored_path.unlink, missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        await asyncio.to_thread(stored_path.unlink, missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded resume file could not be read",
        ) from exc

    resume = ResumeEvaluation(
        id=resume_id,
        candidate_id=candidate_id,
        application_id=application_id,
        job_id=job_id,
        file_name=Path(filename).name,
        file_path=str(stored_path),
        content_type=file.content_type,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(resume)
    try:
        db.commit()
    except SQLAlchemyError:
        await asyncio.to_thread(stored_path.unlink, missing_ok=True)
        raise
    db.refresh(resume)
    return resume


def _get_resume_and_job(
    resume_id: UUID,
    payload: ResumeEvaluationRequest | None,
    db: Session,
) -> tuple[ResumeEvaluation, Job]:
    resume = db.get(ResumeEvaluation, resume_id)
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )
    job_id = payload.job_id if payload else None
    application = (
        db.get(Application, resume.application_id)
        if resume.application_id is not None
        else None
    )
    if job_id is None:
        job_id = resume.job_id
    if job_id is None and application is not None:
        job_id = application.job_id
    if (
        job_id is not None
        and application is not None
        and application.job_id != job_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The requested job does not match the resume's application",
        )
    if job_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide a job_id or link this resume to an application before evaluation",
        )
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return resume, job


def _score_and_store_resume(
    db: Session,
    resume: ResumeEvaluation,
    job: Job,
) -> ResumeEvaluationResponse:
    extracted_text = extract_text(resume.file_path)
    profile = extract_profile(extracted_text)
    result = score_resume(
        profile,
        job_title=job.title,
        job_description=job.description,
        required_skills=job.required_skills,
        required_experience_years=job.required_experience_years,
        required_education=job.education,
    )
    details = result.model_dump(
        mode="json", exclude={"score", "explanation", "review_status"}
    )
    details["job_id"] = str(job.id)
    details["job_title"] = job.title
    resume.score = result.score
    resume.extracted_text = extracted_text
    resume.extracted_skills = profile.skills
    resume.evaluation_details = details
    resume.explanation = result.explanation
    resume.evaluation_status = "completed"
    resume.review_status = "pending_hr_review"
    db.commit()
    db.refresh(resume)
    apply_resume_score_outcome(db, resume)
    return ResumeEvaluationResponse(
        resume_id=resume.id,
        score=result.score,
        explanation=result.explanation,
        review_status=resume.review_status,
        extracted_text=extracted_text,
        **details,
    )


def _mark_evaluation_failed(
    db: Session,
    resume_id: UUID,
    message: str,
) -> None:
    db.rollback()
    resume = db.get(ResumeEvaluation, resume_id)
    if resume is None:
        return
    resume.evaluation_status = "failed"
    resume.evaluation_details = {"error": message}
    db.commit()


def _process_resume_evaluation(resume_id: UUID, job_id: UUID) -> None:
    session_factory = sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )
    with session_factory() as db:
        resume = db.get(ResumeEvaluation, resume_id)
        job = db.get(Job, job_id)
        if resume is None:
            logger.warning("Resume %s was removed before evaluation started.", resume_id)
            return
        if job is None:
            _mark_evaluation_failed(db, resume_id, "The selected job no longer exists.")
            return
        try:
            _score_and_store_resume(db, resume, job)
        except ValueError as exc:
            _mark_evaluation_failed(db, resume_id, str(exc))
            logger.warning("Resume evaluation failed for %s: %s", resume_id, exc)
        except OSError:
            _mark_evaluation_failed(
                db,
                resume_id,
                "The uploaded resume file could not be read.",
            )
            logger.exception("Unable to read resume %s for evaluation.", resume_id)
        except RuntimeError as exc:
            _mark_evaluation_failed(db, resume_id, str(exc))
            logger.exception("Resume scoring agent failed for %s.", resume_id)
        except Exception:
            _mark_evaluation_failed(
                db,
                resume_id,
                "Resume evaluation failed unexpectedly.",
            )
            logger.exception("Unexpected resume scoring failure for %s.", resume_id)


@router.post(
    "/{resume_id}/evaluate",
    response_model=ResumeEvaluationResponse,
)
def evaluate_resume(
    resume_id: UUID,
    payload: ResumeEvaluationRequest | None = None,
    db: Session = Depends(get_db),
) -> ResumeEvaluationResponse:
    resume, job = _get_resume_and_job(resume_id, payload, db)
    resume.evaluation_status = "processing"
    resume.job_id = job.id
    db.commit()
    try:
        return _score_and_store_resume(db, resume, job)
    except ValueError as exc:
        _mark_evaluation_failed(db, resume_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        _mark_evaluation_failed(
            db,
            resume_id,
            "The uploaded resume file could not be read.",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded resume file could not be read",
        ) from exc
    except RuntimeError as exc:
        _mark_evaluation_failed(db, resume_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        _mark_evaluation_failed(
            db,
            resume_id,
            "Resume evaluation failed unexpectedly.",
        )
        logger.exception("Unexpected resume scoring failure for %s", resume_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Resume evaluation failed unexpectedly",
        ) from exc


@router.post(
    "/{resume_id}/evaluate/async",
    response_model=ResumeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"model": ResumeResponse}},
)
def start_resume_evaluation(
    resume_id: UUID,
    background_tasks: BackgroundTasks,
    response: Response,
    payload: ResumeEvaluationRequest | None = None,
    db: Session = Depends(get_db),
) -> ResumeEvaluation:
    resume, job = _get_resume_and_job(resume_id, payload, db)
    force = payload.force if payload else False
    if resume.evaluation_status == "processing" and not force:
        response.status_code = status.HTTP_200_OK
        return resume
    if resume.evaluation_status == "completed" and not force:
        response.status_code = status.HTTP_200_OK
        return resume

    if force:
        resume.score = None
        resume.extracted_text = None
        resume.extracted_skills = []
        resume.evaluation_details = None
        resume.explanation = None
        resume.review_status = "pending_hr_review"
    resume.evaluation_status = "processing"
    resume.job_id = job.id
    db.commit()
    db.refresh(resume)
    background_tasks.add_task(_process_resume_evaluation, resume.id, job.id)
    return resume


@router.get(
    "/{resume_id}/status",
    response_model=ResumeResponse,
)
def get_resume_evaluation_status(
    resume_id: UUID,
    db: Session = Depends(get_db),
) -> ResumeEvaluation:
    resume = db.get(ResumeEvaluation, resume_id)
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )
    return resume


@router.get(
    "/{resume_id}/score",
    response_model=ResumeEvaluationResponse,
)
def get_resume_score(
    resume_id: UUID,
    db: Session = Depends(get_db),
) -> ResumeEvaluationResponse:
    resume = db.get(ResumeEvaluation, resume_id)
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )
    if resume.score is None or resume.explanation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume has not been evaluated",
        )
    return ResumeEvaluationResponse(
        resume_id=resume.id,
        score=resume.score,
        explanation=resume.explanation,
        review_status=resume.review_status,
        extracted_text=resume.extracted_text,
        **(resume.evaluation_details or {}),
    )


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    resume = db.get(ResumeEvaluation, resume_id)
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )
    try:
        await asyncio.to_thread(Path(resume.file_path).unlink, missing_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to remove uploaded resume file",
        ) from exc
    db.delete(resume)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
