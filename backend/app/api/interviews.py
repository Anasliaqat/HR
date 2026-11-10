"""HR interview scheduling endpoints."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import EmailStr
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.scheduling_agent import find_available_slots
from app.config import settings
from app.database.connection import get_db
from app.models.candidate import Candidate
from app.models.interview import Interview
from app.models.job import Job
from app.models.application import Application
from app.models.user import User
from app.schemas.interviews import (
    AvailableSlotsResponse,
    InterviewResponse,
    InterviewRescheduleRequest,
    InterviewScheduleRequest,
    InterviewDetailsUpdate,
    InterviewSlot,
    InterviewUpdate,
    interview_end_time,
)
from app.services.calendar_service import (
    CalendarServiceError,
    CalendarSlotUnavailable,
    create_event,
    delete_event,
    get_busy_intervals,
    update_event,
)
from app.services.email_service import send_interview_notifications
from app.services.email_automation_service import (
    EmailAutomationError,
    send_application_email,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/interviews", tags=["interviews"])


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_candidate_and_job(
    db: Session,
    candidate_id: UUID,
    job_id: UUID,
) -> tuple[Candidate, Job]:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return candidate, job


def _get_interview(db: Session, interview_id: UUID) -> Interview:
    interview = db.get(Interview, interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


def _ensure_no_local_conflict(
    db: Session,
    *,
    candidate_id: UUID,
    interviewer_email: str,
    start_at: datetime,
    end_at: datetime,
    exclude_interview_id: UUID | None = None,
) -> None:
    query = select(Interview.id).where(
        Interview.status == "scheduled",
        or_(
            Interview.candidate_id == candidate_id,
            func.lower(Interview.interviewer_email) == interviewer_email.casefold(),
        ),
        Interview.start_at < end_at,
        Interview.end_at > start_at,
    )
    if exclude_interview_id is not None:
        query = query.where(Interview.id != exclude_interview_id)
    if db.scalar(query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The candidate or interviewer already has an interview at this time",
        )


def _ensure_calendar_available(
    calendar_id: str,
    start_at: datetime,
    end_at: datetime,
    *,
    exclude_event_id: str | None = None,
) -> None:
    try:
        busy_intervals = get_busy_intervals(
            calendar_id,
            start_at,
            end_at,
            exclude_event_id=exclude_event_id,
        )
    except CalendarServiceError as exc:
        logger.warning("Calendar availability check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not verify interviewer calendar availability",
        ) from exc
    requested_start = _aware_utc(start_at)
    requested_end = _aware_utc(end_at)
    if any(
        _aware_utc(busy_start) < requested_end
        and _aware_utc(busy_end) > requested_start
        for busy_start, busy_end in busy_intervals
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The interviewer calendar is busy during the selected time",
        )


def _event_details(
    candidate: Candidate,
    job: Job,
    interviewer_email: str,
) -> tuple[str, str]:
    return (
        f"Interview: {job.title}",
        (
            f"Candidate: {candidate.full_name}\n"
            f"Position: {job.title}\n"
            f"Interviewer: {interviewer_email}"
        ),
    )


def _save_notification_result(
    db: Session,
    interview: Interview,
    candidate: Candidate,
    job: Job,
    *,
    cancelled: bool = False,
) -> None:
    agent_review_reason = db.scalar(
        select(Application.agent_review_reason).where(
            Application.candidate_id == candidate.id,
            Application.job_id == job.id,
        )
    )
    result = send_interview_notifications(
        interview,
        candidate,
        job,
        cancelled=cancelled,
        notify_candidate=not bool(agent_review_reason),
    )
    interview.notifications_status = result.status
    interview.notification_error = "; ".join(result.errors) or None
    db.commit()
    db.refresh(interview)


@router.get("/available-slots", response_model=AvailableSlotsResponse)
def get_available_slots(
    interviewer_email: EmailStr | None = Query(default=None),
    time_min: datetime | None = Query(default=None),
    time_max: datetime | None = Query(default=None),
    duration_minutes: int = Query(default=30, ge=15, le=240),
    candidate_id: UUID | None = Query(default=None),
    interview_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AvailableSlotsResponse:
    if interviewer_email is None:
        return AvailableSlotsResponse(
            available_slots=[],
            message="Select an interviewer to find available times.",
            test_mode=settings.scheduling_test_mode,
        )
    if (time_min is None) != (time_max is None):
        raise HTTPException(
            status_code=422,
            detail="time_min and time_max must be provided together",
        )
    if time_min is None:
        time_min = datetime.now(timezone.utc)
        time_max = time_min + timedelta(days=14)
    assert time_max is not None
    if time_min.tzinfo is None or time_max.tzinfo is None:
        raise HTTPException(status_code=422, detail="Availability range requires time zones")
    if time_max <= time_min:
        raise HTTPException(status_code=422, detail="time_max must follow time_min")

    exclude_event_id = None
    if interview_id is not None:
        interview = _get_interview(db, interview_id)
        if interview.status != "scheduled":
            raise HTTPException(
                status_code=409,
                detail="Only scheduled interviews can be rescheduled",
            )
        if interview.interviewer_email.casefold() != str(interviewer_email).casefold():
            raise HTTPException(
                status_code=422,
                detail="The selected interviewer must match the existing interview",
            )
        candidate_id = interview.candidate_id
        exclude_event_id = interview.calendar_event_id
    if candidate_id is not None and db.get(Candidate, candidate_id) is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    try:
        busy_intervals = get_busy_intervals(
            str(interviewer_email),
            time_min,
            time_max,
            exclude_event_id=exclude_event_id,
        )
    except CalendarServiceError as exc:
        logger.warning("Calendar availability lookup failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve interviewer availability",
        ) from exc

    query = select(Interview).where(
        Interview.status == "scheduled",
        Interview.start_at < time_max,
        Interview.end_at > time_min,
        or_(
            func.lower(Interview.interviewer_email) == str(interviewer_email).casefold(),
            *([Interview.candidate_id == candidate_id] if candidate_id else []),
        ),
    )
    if interview_id is not None:
        query = query.where(Interview.id != interview_id)
    reservations = [
        (_aware_utc(item.start_at), _aware_utc(item.end_at))
        for item in db.scalars(query).all()
    ]
    try:
        slots = find_available_slots(
            time_min=time_min,
            time_max=time_max,
            duration_minutes=duration_minutes,
            busy_intervals=busy_intervals,
            working_intervals=reservations,
            time_zone=settings.google_calendar_time_zone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AvailableSlotsResponse(
        available_slots=[
            InterviewSlot(start_at=start, end_at=end) for start, end in slots
        ],
        message=f"Found {len(slots)} available interview slot(s).",
        test_mode=settings.scheduling_test_mode,
    )


@router.get("/interviewers")
def list_interviewers(db: Session = Depends(get_db)) -> list[dict[str, str]]:
    interviewers = db.scalars(
        select(User)
        .where(User.is_active.is_(True), User.role.in_(("interviewer", "hr")))
        .order_by(User.full_name)
    ).all()
    return [
        {"id": str(user.id), "name": user.full_name, "email": user.email}
        for user in interviewers
    ]


@router.post(
    "/schedule",
    response_model=InterviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def schedule_interview(
    payload: InterviewScheduleRequest,
    db: Session = Depends(get_db),
) -> Interview:
    candidate, job = _get_candidate_and_job(db, payload.candidate_id, payload.job_id)
    application = db.scalar(
        select(Application).where(
            Application.candidate_id == candidate.id,
            Application.job_id == job.id,
        )
    )
    if not payload.hr_approved:
        raise HTTPException(status_code=409, detail="HR approval is required")
    if not candidate.hr_approved and (
        application is None
        or application.status not in {"interview_eligible", "approved_by_hr"}
    ):
        raise HTTPException(
            status_code=409,
            detail="Candidate must be approved by HR before scheduling",
        )

    start_at = _aware_utc(payload.start_at)
    end_at = interview_end_time(start_at, payload.duration_minutes)
    interviewer_email = str(payload.interviewer_email)
    _ensure_no_local_conflict(
        db,
        candidate_id=candidate.id,
        interviewer_email=interviewer_email,
        start_at=start_at,
        end_at=end_at,
    )
    _ensure_calendar_available(interviewer_email, start_at, end_at)
    interviewer = db.scalar(
        select(User).where(func.lower(User.email) == interviewer_email.casefold())
    )
    if interviewer is not None and interviewer.role == "candidate":
        raise HTTPException(status_code=422, detail="A candidate cannot be an interviewer")
    summary, description = _event_details(candidate, job, interviewer_email)
    try:
        event_id = create_event(
            calendar_id=interviewer_email,
            summary=summary,
            description=description,
            start_at=start_at,
            end_at=end_at,
            location=payload.meeting_details,
        )
    except CalendarSlotUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected calendar slot became unavailable",
        ) from exc
    except CalendarServiceError as exc:
        logger.warning("Calendar event creation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Calendar event creation failed; interview was not scheduled",
        ) from exc

    interview = Interview(
        candidate_id=candidate.id,
        job_id=job.id,
        interviewer_id=interviewer.id if interviewer else None,
        interviewer_email=interviewer_email,
        interview_mode=payload.interview_mode,
        meeting_details=payload.meeting_details,
        start_at=start_at,
        end_at=end_at,
        status="scheduled",
        calendar_event_id=event_id,
        notifications_status="pending",
        test_mode=settings.scheduling_test_mode,
    )
    db.add(interview)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            delete_event(interviewer_email, event_id)
        except CalendarServiceError:
            logger.exception("Could not remove orphan calendar event %s", event_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview could not be saved after calendar creation",
        ) from exc
    db.refresh(interview)
    _save_notification_result(db, interview, candidate, job)
    if not interview.test_mode:
        if application is not None:
            try:
                send_application_email(
                    db,
                    application,
                    "interview_invitation",
                    interview,
                )
            except EmailAutomationError:
                logger.exception(
                    "Could not create an interview invitation for %s.",
                    interview.id,
                )
    return interview


@router.get("", response_model=list[InterviewResponse])
def list_interviews(db: Session = Depends(get_db)) -> list[Interview]:
    return list(
        db.scalars(select(Interview).order_by(Interview.start_at.desc())).all()
    )


@router.patch("/{interview_id}", response_model=InterviewResponse)
def update_interview(
    interview_id: UUID,
    payload: InterviewUpdate,
    db: Session = Depends(get_db),
) -> Interview:
    interview = _get_interview(db, interview_id)
    if payload.status == "scheduled":
        raise HTTPException(
            status_code=409,
            detail="Use the reschedule endpoint to keep an interview scheduled",
        )
    if interview.status != "scheduled":
        raise HTTPException(
            status_code=409,
            detail="Only scheduled interviews can be completed or cancelled",
        )
    if payload.status == "cancelled":
        try:
            delete_event(interview.interviewer_email, interview.calendar_event_id)
        except CalendarServiceError as exc:
            logger.warning("Calendar event deletion failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Calendar event could not be cancelled",
            ) from exc
    interview.status = payload.status
    db.commit()
    db.refresh(interview)
    if payload.status == "cancelled":
        _save_notification_result(
            db,
            interview,
            interview.candidate,
            interview.job,
            cancelled=True,
        )
    return interview


@router.patch(
    "/{interview_id}/details",
    response_model=InterviewResponse,
)
def update_interview_details(
    interview_id: UUID,
    payload: InterviewDetailsUpdate,
    db: Session = Depends(get_db),
) -> Interview:
    interview = _get_interview(db, interview_id)
    if interview.status != "scheduled":
        raise HTTPException(status_code=409, detail="Only scheduled interviews can be updated")
    previous_details = interview.meeting_details
    summary, description = _event_details(
        interview.candidate,
        interview.job,
        interview.interviewer_email,
    )
    try:
        update_event(
            calendar_id=interview.interviewer_email,
            event_id=interview.calendar_event_id or "",
            summary=summary,
            description=description,
            start_at=_aware_utc(interview.start_at),
            end_at=_aware_utc(interview.end_at),
            location=payload.meeting_details,
        )
    except CalendarServiceError as exc:
        raise HTTPException(
            status_code=502,
            detail="Calendar could not update the interview details",
        ) from exc
    interview.interview_mode = payload.interview_mode
    interview.meeting_details = payload.meeting_details
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            update_event(
                calendar_id=interview.interviewer_email,
                event_id=interview.calendar_event_id or "",
                summary=summary,
                description=description,
                start_at=_aware_utc(interview.start_at),
                end_at=_aware_utc(interview.end_at),
                location=previous_details,
            )
        except CalendarServiceError:
            logger.exception(
                "Could not restore calendar details after database failure"
            )
        raise HTTPException(
            status_code=503,
            detail="Interview details could not be saved",
        ) from exc
    db.refresh(interview)
    if not interview.test_mode:
        application = db.scalar(
            select(Application).where(
                Application.candidate_id == interview.candidate_id,
                Application.job_id == interview.job_id,
            )
        )
        if application is not None:
            try:
                send_application_email(
                    db,
                    application,
                    "interview_invitation",
                    interview,
                )
            except EmailAutomationError:
                logger.exception(
                    "Could not send an invitation after details were updated for %s.",
                    interview.id,
                )
    return interview


@router.put("/{interview_id}/reschedule", response_model=InterviewResponse)
def reschedule_interview(
    interview_id: UUID,
    payload: InterviewRescheduleRequest,
    db: Session = Depends(get_db),
) -> Interview:
    interview = _get_interview(db, interview_id)
    if interview.status != "scheduled":
        raise HTTPException(status_code=409, detail="Only scheduled interviews can be rescheduled")
    if not payload.hr_approved:
        raise HTTPException(status_code=409, detail="HR approval is required")
    start_at = _aware_utc(payload.start_at)
    end_at = interview_end_time(start_at, payload.duration_minutes)
    _ensure_no_local_conflict(
        db,
        candidate_id=interview.candidate_id,
        interviewer_email=interview.interviewer_email,
        start_at=start_at,
        end_at=end_at,
        exclude_interview_id=interview.id,
    )
    _ensure_calendar_available(
        interview.interviewer_email,
        start_at,
        end_at,
        exclude_event_id=interview.calendar_event_id,
    )
    summary, description = _event_details(
        interview.candidate,
        interview.job,
        interview.interviewer_email,
    )
    try:
        event_id = update_event(
            calendar_id=interview.interviewer_email,
            event_id=interview.calendar_event_id or "",
            summary=summary,
            description=description,
            start_at=start_at,
            end_at=end_at,
            location=interview.meeting_details,
        )
    except CalendarSlotUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected calendar slot became unavailable",
        ) from exc
    except CalendarServiceError as exc:
        logger.warning("Calendar event update failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Calendar could not update the interview",
        ) from exc
    old_start = interview.start_at
    old_end = interview.end_at
    old_event_id = interview.calendar_event_id
    interview.start_at = start_at
    interview.end_at = end_at
    interview.calendar_event_id = event_id
    interview.notifications_status = "pending"
    interview.notification_error = None
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            update_event(
                calendar_id=interview.interviewer_email,
                event_id=old_event_id or event_id,
                summary=summary,
                description=description,
                start_at=_aware_utc(old_start),
                end_at=_aware_utc(old_end),
                location=interview.meeting_details,
            )
        except CalendarServiceError:
            logger.exception("Could not restore calendar event after database failure")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview could not be saved after calendar update",
        ) from exc
    db.refresh(interview)
    _save_notification_result(db, interview, interview.candidate, interview.job)
    if not interview.test_mode:
        application = db.scalar(
            select(Application).where(
                Application.candidate_id == interview.candidate_id,
                Application.job_id == interview.job_id,
            )
        )
        if application is not None:
            try:
                send_application_email(
                    db,
                    application,
                    "interview_invitation",
                    interview,
                )
            except EmailAutomationError:
                logger.exception(
                    "Could not create an updated interview invitation for %s.",
                    interview.id,
                )
    return interview


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview(interview_id: UUID, db: Session = Depends(get_db)) -> Response:
    interview = _get_interview(db, interview_id)
    if interview.status == "scheduled":
        try:
            delete_event(interview.interviewer_email, interview.calendar_event_id)
        except CalendarServiceError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Calendar event could not be deleted",
            ) from exc
    db.delete(interview)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
