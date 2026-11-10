"""HR email automation, decision, preview, history, and retry endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.agents.email_automation_agent import classify_score
from app.database.connection import get_db
from app.models.application import Application
from app.models.email_log import EmailLog
from app.models.interview import Interview
from app.models.resume_evaluation import ResumeEvaluation
from app.schemas.email_automation import (
    AgentReviewDecisionResponse,
    AgentReviewQueueItem,
    EmailApplicationResponse,
    EmailDecisionRequest,
    EmailLogResponse,
    EmailPreviewResponse,
    EmailSendRequest,
)
from app.services.email_automation_service import (
    EmailAutomationError,
    EmailSendInProgress,
    build_email_preview,
    get_email_log,
    send_application_email,
)

router = APIRouter(prefix="/email-automation", tags=["email automation"])


def _get_application(db: Session, application_id: UUID) -> Application:
    application = db.scalar(
        select(Application)
        .options(joinedload(Application.candidate), joinedload(Application.job))
        .where(Application.id == application_id)
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


def _latest_evaluation(
    db: Session,
    application_id: UUID,
) -> ResumeEvaluation | None:
    return db.scalar(
        select(ResumeEvaluation)
        .where(
            ResumeEvaluation.application_id == application_id,
            ResumeEvaluation.score.is_not(None),
        )
        .order_by(ResumeEvaluation.uploaded_at.desc())
        .limit(1)
    )


def _evaluation_skills(
    resume: ResumeEvaluation | None,
) -> tuple[list[str], list[str], bool | None, bool]:
    if resume is None:
        return [], [], None, False
    details = resume.evaluation_details or {}
    matched = details.get("matched_skills")
    missing = details.get("missing_required_skills", [])
    evidence_keys = (
        "evidence",
        "candidate_strengths",
        "relevant_experience",
        "relevant_projects",
    )
    has_evidence_data = any(key in details for key in evidence_keys)
    has_relevant_evidence = (
        any(
            isinstance(details.get(key), list) and bool(details[key])
            for key in evidence_keys
        )
        if has_evidence_data
        else None
    )
    return (
        matched if isinstance(matched, list) else [],
        missing if isinstance(missing, list) else [],
        has_relevant_evidence,
        isinstance(matched, list),
    )


@router.get("/applications", response_model=list[EmailApplicationResponse])
def list_email_applications(
    db: Session = Depends(get_db),
) -> list[EmailApplicationResponse]:
    applications = list(
        db.scalars(
            select(Application)
            .options(joinedload(Application.candidate), joinedload(Application.job))
            .order_by(Application.applied_at.desc())
        ).all()
    )
    if not applications:
        return []
    application_ids = [application.id for application in applications]
    resumes = db.scalars(
        select(ResumeEvaluation)
        .where(ResumeEvaluation.application_id.in_(application_ids))
        .order_by(ResumeEvaluation.uploaded_at.desc())
    ).all()
    scores: dict[UUID, int] = {}
    latest_resumes: dict[UUID, ResumeEvaluation] = {}
    for resume in resumes:
        if resume.application_id not in latest_resumes and resume.score is not None:
            latest_resumes[resume.application_id] = resume
            scores[resume.application_id] = resume.score
    logs = db.scalars(
        select(EmailLog)
        .where(
            EmailLog.application_id.in_(application_ids),
            EmailLog.deleted_at.is_(None),
        )
        .order_by(EmailLog.created_at.desc())
    ).all()
    logs_by_application: dict[UUID, list[EmailLogResponse]] = {}
    for email_log in logs:
        if email_log.application_id is not None:
            logs_by_application.setdefault(email_log.application_id, []).append(
                EmailLogResponse.model_validate(email_log)
            )
    results = []
    for application in applications:
        score = scores.get(application.id)
        resume = latest_resumes.get(application.id)
        try:
            (
                matched_skills,
                missing_skills,
                has_relevant_evidence,
                has_match_evidence,
            ) = (
                _evaluation_skills(resume)
            )
            score_action = (
                classify_score(
                    score,
                    matched_skills=(
                        matched_skills if has_match_evidence else None
                    ),
                    required_skills=application.job.required_skills,
                    has_relevant_evidence=has_relevant_evidence,
                )
                if score is not None
                else None
            )
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        results.append(EmailApplicationResponse(
            application_id=application.id,
            candidate_id=application.candidate.id,
            candidate_name=application.candidate.full_name,
            recipient_email=application.candidate.email,
            email_consent=application.candidate.email_consent,
            email_consent_at=application.candidate.email_consent_at,
            job_id=application.job.id,
            job_title=application.job.title,
            cv_score=score,
            score_action=score_action,
            application_status=application.status,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            review_reason=application.agent_review_reason,
            emails=logs_by_application.get(application.id, []),
        ))
    return results


@router.get("/review-queue", response_model=list[AgentReviewQueueItem])
def list_agent_review_queue(
    db: Session = Depends(get_db),
) -> list[AgentReviewQueueItem]:
    applications = db.scalars(
        select(Application)
        .options(joinedload(Application.candidate), joinedload(Application.job))
        .where(
            Application.status == "over_agent_review",
            Application.agent_review_reason.is_not(None),
        )
        .order_by(Application.applied_at.desc())
    ).all()
    if not applications:
        return []
    resumes = db.scalars(
        select(ResumeEvaluation)
        .where(
            ResumeEvaluation.application_id.in_(
                [application.id for application in applications]
            ),
            ResumeEvaluation.score.is_not(None),
        )
        .order_by(ResumeEvaluation.uploaded_at.desc())
    ).all()
    latest_resumes: dict[UUID, ResumeEvaluation] = {}
    for resume in resumes:
        if resume.application_id not in latest_resumes:
            latest_resumes[resume.application_id] = resume
    result = []
    for application in applications:
        resume = latest_resumes.get(application.id)
        matched_skills, missing_skills, _, _ = _evaluation_skills(resume)
        result.append(
            AgentReviewQueueItem(
                application_id=application.id,
                candidate_id=application.candidate.id,
                candidate_name=application.candidate.full_name,
                recipient_email=application.candidate.email,
                job_id=application.job.id,
                job_title=application.job.title,
                cv_score=resume.score if resume else None,
                matched_skills=matched_skills,
                missing_skills=missing_skills,
                reason=application.agent_review_reason or "Flagged for HR review.",
                status=application.status,
            )
        )
    return result


@router.get("/history", response_model=list[EmailLogResponse])
def get_email_history(db: Session = Depends(get_db)) -> list[EmailLog]:
    return list(
        db.scalars(
            select(EmailLog)
            .where(EmailLog.deleted_at.is_(None))
            .order_by(EmailLog.created_at.desc())
        ).all()
    )


@router.delete(
    "/applications/{application_id}/history",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_application_email_history(
    application_id: UUID,
    db: Session = Depends(get_db),
) -> None:
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    db.execute(
        update(EmailLog)
        .where(
            EmailLog.application_id == application_id,
            EmailLog.deleted_at.is_(None),
        )
        .values(deleted_at=datetime.now(timezone.utc))
    )
    db.commit()


@router.delete(
    "/history/{email_log_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_email_history_record(
    email_log_id: UUID,
    db: Session = Depends(get_db),
) -> None:
    email_log = db.get(EmailLog, email_log_id)
    if email_log is None or email_log.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Email record not found")
    email_log.deleted_at = datetime.now(timezone.utc)
    db.commit()


@router.get(
    "/applications/{application_id}/preview",
    response_model=EmailPreviewResponse,
)
def preview_application_email(
    application_id: UUID,
    email_type: str = Query(
        pattern="^(rejection|selection|screening_invitation|interview_invitation)$"
    ),
    interview_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> EmailPreviewResponse:
    application = _get_application(db, application_id)
    interview = db.get(Interview, interview_id) if interview_id else None
    try:
        preview = build_email_preview(application, email_type, interview)
    except EmailAutomationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    reason = None
    if (
        application.agent_review_reason
        and application.status == "over_agent_review"
    ):
        reason = "This application is in the Over Agent Review workflow; automated emails are disabled."
    elif not application.candidate.email_consent:
        reason = "Record candidate email consent before sending."
    elif email_type == "rejection" and application.status not in {
        "rejected",
        "rejected_by_hr",
    }:
        reason = "Record a rejection decision before sending this email."
    elif email_type == "selection" and application.status != "approved_by_hr":
        reason = "Record HR approval before sending this email."
    elif email_type == "screening_invitation" and application.status not in {
        "interview_eligible",
        "approved_by_hr",
    }:
        reason = "A screening invitation requires a CV-eligible application."
    elif email_type == "interview_invitation" and (
        interview is None
        or interview.status != "scheduled"
        or interview.test_mode
        or not interview.calendar_event_id
    ):
        reason = "Only a confirmed, non-test calendar booking can receive an invitation."
    return EmailPreviewResponse(
        email_type=email_type,
        recipient_email=preview.recipient_email,
        subject=preview.subject,
        body=preview.body,
        can_send=reason is None,
        reason=reason,
    )


@router.post(
    "/applications/{application_id}/decision",
    response_model=EmailLogResponse,
)
def record_hr_decision(
    application_id: UUID,
    payload: EmailDecisionRequest,
    db: Session = Depends(get_db),
) -> EmailLog:
    application = _get_application(db, application_id)
    if application.agent_review_reason:
        raise HTTPException(
            status_code=409,
            detail=(
                "Use the Over Agent Review decision action. No candidate email "
                "will be sent for this application."
            ),
        )
    resume = _latest_evaluation(db, application.id)
    if resume is None or resume.score is None:
        raise HTTPException(status_code=409, detail="A completed CV score is required")
    matched_skills, _, has_relevant_evidence, has_match_evidence = (
        _evaluation_skills(resume)
    )
    try:
        action = classify_score(
            resume.score,
            matched_skills=matched_skills if has_match_evidence else None,
            required_skills=application.job.required_skills,
            has_relevant_evidence=has_relevant_evidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if action not in {"hr_review", "hr_decision"}:
        raise HTTPException(
            status_code=409,
            detail="This application is not in a configurable HR decision score band",
        )
    if application.status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail="This application already has a recorded workflow decision",
        )

    if payload.decision == "approve":
        application.status = "approved_by_hr"
        email_type = "selection"
    else:
        application.status = "rejected_by_hr"
        email_type = "rejection"
    db.commit()
    try:
        return send_application_email(db, application, email_type)
    except EmailSendInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EmailAutomationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/review-queue/{application_id}/decision",
    response_model=AgentReviewDecisionResponse,
)
def decide_agent_review(
    application_id: UUID,
    payload: EmailDecisionRequest,
    db: Session = Depends(get_db),
) -> AgentReviewDecisionResponse:
    application = _get_application(db, application_id)
    if (
        application.status != "over_agent_review"
        or not application.agent_review_reason
    ):
        raise HTTPException(
            status_code=409,
            detail="Application is not waiting in the Over Agent Review queue",
        )
    application.status = (
        "approved_by_hr" if payload.decision == "approve" else "rejected_by_hr"
    )
    db.commit()
    email_type = "selection" if payload.decision == "approve" else "rejection"
    try:
        email = send_application_email(db, application, email_type)
    except EmailSendInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EmailAutomationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return AgentReviewDecisionResponse(
        application_id=application.id,
        status=application.status,
        review_reason=application.agent_review_reason,
        email=EmailLogResponse.model_validate(email),
    )


@router.post(
    "/applications/{application_id}/send",
    response_model=EmailLogResponse,
)
def send_manual_email(
    application_id: UUID,
    payload: EmailSendRequest,
    db: Session = Depends(get_db),
) -> EmailLog:
    application = _get_application(db, application_id)
    if (
        application.agent_review_reason
        and application.status == "over_agent_review"
    ):
        raise HTTPException(
            status_code=409,
            detail="Candidate emails are disabled for Over Agent Review applications",
        )
    interview = db.get(Interview, payload.interview_id) if payload.interview_id else None
    if payload.email_type == "interview_invitation" and interview is None:
        raise HTTPException(
            status_code=422,
            detail="interview_id is required for an interview invitation",
        )
    try:
        return send_application_email(
            db, application, payload.email_type, interview
        )
    except EmailSendInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EmailAutomationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/history/{email_log_id}/retry", response_model=EmailLogResponse)
def retry_email(
    email_log_id: UUID,
    db: Session = Depends(get_db),
) -> EmailLog:
    email_log = get_email_log(db, email_log_id)
    if email_log is None:
        raise HTTPException(status_code=404, detail="Email record not found")
    if email_log.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Email record was deleted")
    if email_log.status == "sent":
        return email_log
    if email_log.email_type not in {
        "rejection",
        "selection",
        "screening_invitation",
        "interview_invitation",
    }:
        raise HTTPException(
            status_code=409,
            detail="This legacy email record cannot be retried through automation",
        )
    if email_log.application_id is None:
        raise HTTPException(
            status_code=409,
            detail="This email is no longer linked to an application",
        )
    application = _get_application(db, email_log.application_id)
    interview = (
        db.get(Interview, email_log.interview_id)
        if email_log.interview_id is not None
        else None
    )
    try:
        return send_application_email(
            db,
            application,
            email_log.email_type,
            interview,
        )
    except EmailSendInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EmailAutomationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
