"""HR-initiated Vapi screening calls and authenticated result webhooks."""

import hmac
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.agents.screening_agent import (
    ScreeningSummary,
    build_vapi_call_payload,
    candidate_consented_on_call,
    summarize_screening,
)
from app.config import settings
from app.database.connection import get_db
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.email_log import EmailLog
from app.models.job import Job
from app.models.screening import Screening
from app.schemas.screening import (
    ScreeningDashboardResponse,
    ScreeningResponse,
    ScreeningStartRequest,
)
from app.services.phone_service import normalize_phone_number
from app.services.voice_service import VapiServiceError, create_outbound_call

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/screening", tags=["screening"])

_IN_PROGRESS_STATUSES = {"queued", "ringing", "in_progress"}
_VAPI_STATUS_MAP = {
    "scheduled": "queued",
    "queued": "queued",
    "ringing": "ringing",
    "in-progress": "in_progress",
    "in_progress": "in_progress",
}
_FAILED_END_REASONS = (
    "error",
    "failed",
    "busy",
    "no-answer",
    "did-not-answer",
    "timeout",
    "voicemail",
    "rejected",
    "cancelled",
    "canceled",
)


def _is_failed_end(reason: str | None) -> bool:
    normalized = (reason or "").casefold()
    return any(indicator in normalized for indicator in _FAILED_END_REASONS)


def _response(screening: Screening) -> ScreeningResponse:
    availability = (screening.answers or {}).get("interview_availability") or None
    return ScreeningResponse(
        id=screening.id,
        candidate_id=screening.candidate_id,
        application_id=screening.application_id,
        status=screening.call_status,
        call_id=screening.call_id,
        started_at=screening.started_at,
        ended_at=screening.ended_at,
        summary=screening.summary,
        answers=screening.answers or {},
        job_related_highlights=screening.job_related_highlights or [],
        interview_availability=availability,
        transcript=screening.transcript,
        recording_url=screening.recording_url,
        ended_reason=screening.ended_reason,
        consent_confirmed_on_call=screening.consent_confirmed_on_call,
        consent_obtained_at=screening.consent_obtained_at,
        created_at=screening.created_at,
    )


def _dashboard_response(screening: Screening) -> ScreeningDashboardResponse:
    return ScreeningDashboardResponse(
        **_response(screening).model_dump(),
        candidate_name=screening.candidate.full_name,
        phone=screening.candidate.phone,
        job_title=screening.application.job.title
        if screening.application and screening.application.job
        else None,
    )


def _parse_event_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def _caller_number(message: dict[str, Any], call: dict[str, Any]) -> str | None:
    customer = call.get("customer")
    if not isinstance(customer, dict):
        customer = message.get("customer")
    if isinstance(customer, dict):
        number = customer.get("number")
        if isinstance(number, str):
            return number
    number = call.get("from")
    return number if isinstance(number, str) else None


def _matching_application(
    db: Session,
    candidate: Candidate,
) -> Application | None:
    applications = list(
        db.scalars(
            select(Application)
            .join(
                EmailLog,
                EmailLog.application_id == Application.id,
            )
            .options(joinedload(Application.job))
            .where(
                Application.candidate_id == candidate.id,
                Application.status.in_(("interview_eligible", "approved_by_hr")),
                EmailLog.email_type == "screening_invitation",
                EmailLog.status == "sent",
                EmailLog.deleted_at.is_(None),
            )
            .order_by(Application.applied_at.desc())
        ).all()
    )
    unique_applications = {application.id: application for application in applications}
    return next(iter(unique_applications.values())) if len(unique_applications) == 1 else None


def _handle_assistant_request(
    message: dict[str, Any],
    call: dict[str, Any],
    db: Session,
) -> dict[str, Any]:
    if not settings.vapi_assistant_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPI_ASSISTANT_ID is not configured",
        )

    call_id = call.get("id")
    if isinstance(call_id, str):
        existing = db.scalar(select(Screening).where(Screening.call_id == call_id))
        if existing is not None:
            return {"assistantId": settings.vapi_assistant_id}

    caller_number = _caller_number(message, call)
    normalized_caller = normalize_phone_number(
        caller_number, settings.phone_default_region
    )
    if normalized_caller is not None and isinstance(call_id, str):
        candidates = db.scalars(select(Candidate).where(Candidate.phone.is_not(None)))
        matching_candidates = [
            candidate
            for candidate in candidates
            if normalize_phone_number(
                candidate.phone, settings.phone_default_region
            )
            == normalized_caller
        ]
        if len(matching_candidates) == 1:
            candidate = matching_candidates[0]
            application = _matching_application(db, candidate)
            if application is not None:
                screening = Screening(
                    candidate_id=candidate.id,
                    application_id=application.id,
                    call_id=call_id,
                    call_status="queued",
                    started_at=_parse_event_datetime(call.get("startedAt")),
                )
                db.add(screening)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    existing = db.scalar(
                        select(Screening).where(Screening.call_id == call_id)
                    )
                    if existing is None:
                        raise
        else:
            logger.info(
                "Inbound Vapi call is not uniquely attributable; no candidate context was provided."
            )
    return {"assistantId": settings.vapi_assistant_id}


@router.post(
    "/{candidate_id}/start",
    response_model=ScreeningResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_screening(
    candidate_id: UUID,
    payload: ScreeningStartRequest,
    db: Session = Depends(get_db),
) -> ScreeningResponse:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )
    if not candidate.hr_approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate must be approved by HR before screening",
        )
    if not payload.consent_confirmed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="HR must confirm the candidate consented to screening and transcription",
        )
    if not candidate.phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate must have a phone number before screening",
        )
    if not (
        settings.vapi_api_key
        and settings.vapi_assistant_id
        and settings.vapi_phone_number_id
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Vapi is not configured; set VAPI_API_KEY, "
                "VAPI_ASSISTANT_ID, and VAPI_PHONE_NUMBER_ID"
            ),
        )

    application = db.get(Application, payload.application_id)
    if application is None or application.candidate_id != candidate_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found for this candidate",
        )
    job = db.get(Job, application.job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found for this application",
        )

    active_screening = db.scalar(
        select(Screening).where(
            Screening.application_id == application.id,
            Screening.call_status.in_(_IN_PROGRESS_STATUSES),
        )
    )
    if active_screening is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A screening call is already active for this application",
        )

    screening = Screening(
        candidate_id=candidate_id,
        application_id=application.id,
        call_status="queued",
        consent_obtained_at=datetime.now(timezone.utc),
    )
    db.add(screening)
    db.commit()
    db.refresh(screening)

    try:
        call = create_outbound_call(
            build_vapi_call_payload(candidate, job, str(screening.id))
        )
    except (VapiServiceError, ValueError, RuntimeError) as exc:
        screening.call_status = "failed"
        screening.summary = "Call could not be initiated. HR may retry after checking Vapi configuration."
        db.commit()
        if isinstance(exc, (ValueError, RuntimeError)) and not isinstance(
            exc, VapiServiceError
        ):
            logger.exception("Unable to prepare Vapi screening call.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    screening.call_id = call["id"]
    returned_status = call.get("status")
    if isinstance(returned_status, str):
        screening.call_status = _VAPI_STATUS_MAP.get(
            returned_status, screening.call_status
        )
    db.commit()
    db.refresh(screening)
    return _response(screening)


@router.get("", response_model=list[ScreeningDashboardResponse])
def list_screenings(
    db: Session = Depends(get_db),
) -> list[ScreeningDashboardResponse]:
    screenings = db.scalars(
        select(Screening)
        .options(
            joinedload(Screening.candidate),
            joinedload(Screening.application).joinedload(Application.job),
        )
        .order_by(Screening.created_at.desc())
    ).all()
    return [_dashboard_response(screening) for screening in screenings]


@router.get("/records/{screening_id}", response_model=ScreeningDashboardResponse)
def get_screening_record(
    screening_id: UUID,
    db: Session = Depends(get_db),
) -> ScreeningDashboardResponse:
    screening = db.scalar(
        select(Screening)
        .options(
            joinedload(Screening.candidate),
            joinedload(Screening.application).joinedload(Application.job),
        )
        .where(Screening.id == screening_id)
    )
    if screening is None:
        raise HTTPException(status_code=404, detail="Screening record not found")
    return _dashboard_response(screening)


@router.post("/webhook", response_model=None)
def vapi_webhook(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    x_vapi_secret: str | None = Header(default=None, alias="x-vapi-secret"),
) -> dict[str, Any]:
    if not settings.vapi_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPI_WEBHOOK_SECRET is not configured",
        )
    if not x_vapi_secret or not hmac.compare_digest(
        x_vapi_secret, settings.vapi_webhook_secret
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Vapi webhook secret",
        )

    message = payload.get("message")
    if not isinstance(message, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Vapi webhook payload must contain a message object",
        )
    event_type = message.get("type")
    call = message.get("call")
    call = call if isinstance(call, dict) else {}
    if event_type == "assistant-request":
        return _handle_assistant_request(message, call, db)

    call_id = call.get("id")
    call_name = call.get("name")

    screening = (
        db.scalar(select(Screening).where(Screening.call_id == call_id))
        if isinstance(call_id, str)
        else None
    )
    if screening is None and isinstance(call_name, str):
        prefix = "HR screening "
        if call_name.startswith(prefix):
            try:
                screening = db.get(Screening, UUID(call_name[len(prefix) :]))
            except ValueError:
                screening = None
    if screening is None:
        logger.warning("Ignoring authenticated Vapi event for an unknown call.")
        return {"status": "ok"}

    if event_type == "status-update":
        provider_status = message.get("status")
        if provider_status == "ended":
            reason = message.get("endedReason") or call.get("endedReason")
            screening.ended_reason = reason if isinstance(reason, str) else None
            screening.ended_at = (
                _parse_event_datetime(call.get("endedAt"))
                or datetime.now(timezone.utc)
            )
            screening.call_status = (
                "failed" if _is_failed_end(screening.ended_reason) else "completed"
            )
        elif isinstance(provider_status, str):
            normalized = _VAPI_STATUS_MAP.get(provider_status)
            if normalized and screening.call_status not in {"completed", "failed"}:
                screening.call_status = normalized
                if normalized == "in_progress" and screening.started_at is None:
                    screening.started_at = (
                        _parse_event_datetime(call.get("startedAt"))
                        or datetime.now(timezone.utc)
                    )
    elif event_type == "end-of-call-report":
        if screening.end_report_received:
            return {"status": "ok"}
        screening.end_report_received = True
        reason = message.get("endedReason") or call.get("endedReason")
        screening.ended_reason = reason if isinstance(reason, str) else None
        screening.ended_at = (
            _parse_event_datetime(call.get("endedAt"))
            or datetime.now(timezone.utc)
        )
        if screening.started_at is None:
            screening.started_at = _parse_event_datetime(call.get("startedAt"))
        artifact = message.get("artifact")
        if not isinstance(artifact, dict):
            artifact = call.get("artifact")
        if not isinstance(artifact, dict):
            artifact = {}
        transcript = artifact.get("transcript") or message.get("transcript")
        if isinstance(transcript, str):
            screening.consent_confirmed_on_call = candidate_consented_on_call(
                transcript
            )
            screening.transcript = (
                transcript[:50_000]
                if screening.consent_confirmed_on_call is True
                else None
            )
        recording = artifact.get("recording")
        if screening.consent_confirmed_on_call is True and isinstance(recording, dict):
            recording_url = next(
                (
                    recording.get(key)
                    for key in (
                        "recordingUrl",
                        "stereoRecordingUrl",
                        "monoRecordingUrl",
                        "stereoUrl",
                        "monoUrl",
                        "url",
                    )
                    if isinstance(recording.get(key), str)
                ),
                None,
            )
            screening.recording_url = (
                recording_url if _is_https_url(recording_url) else None
            )
        else:
            screening.recording_url = None
        screening.call_status = (
            "failed" if _is_failed_end(screening.ended_reason) else "completed"
        )

        application = db.get(Application, screening.application_id)
        job = db.get(Job, application.job_id) if application else None
        if screening.consent_confirmed_on_call is False:
            screening.summary = (
                "The candidate did not consent during the call. "
                "No screening responses were summarized."
            )
        elif screening.consent_confirmed_on_call is None:
            screening.summary = (
                "Candidate consent could not be verified from the call transcript. "
                "HR review is required; responses were not summarized."
            )
        elif screening.transcript and job:
            try:
                summary = summarize_screening(screening.transcript, job)
            except Exception:
                logger.exception("Screening summary generation failed.")
                summary = ScreeningSummary(
                    summary=(
                        "The call ended. Automated summarization failed; "
                        "review the transcript and responses manually."
                    ),
                    answers={},
                )
            screening.summary = summary.summary
            screening.answers = {
                **summary.answers,
                "interview_availability": summary.interview_availability or "",
            }
            screening.job_related_highlights = summary.job_related_highlights

    db.commit()
    return {"status": "ok"}


@router.get("/{candidate_id}", response_model=ScreeningResponse)
def get_screening(
    candidate_id: UUID,
    db: Session = Depends(get_db),
) -> ScreeningResponse:
    if db.get(Candidate, candidate_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )
    screening = db.scalar(
        select(Screening)
        .where(Screening.candidate_id == candidate_id)
        .order_by(Screening.created_at.desc())
    )
    if screening is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No screening results are available for this candidate",
        )
    return _response(screening)
