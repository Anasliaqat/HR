"""Candidate API routes."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database.connection import get_db
from app.models.candidate import Candidate
from app.schemas.candidates import (
    CandidateCreate,
    CandidateEmailConsentUpdate,
    CandidateResponse,
)
from app.services.phone_service import normalize_phone_number

router = APIRouter(prefix="/candidates", tags=["candidates"])


def _normalized_phone(phone: str | None) -> str | None:
    if not phone or not phone.strip():
        return None
    normalized = normalize_phone_number(phone, settings.phone_default_region)
    if normalized is None:
        raise HTTPException(
            status_code=422,
            detail="Phone number must be valid for the configured phone region",
        )
    return normalized


@router.post(
    "",
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_candidate(
    candidate: CandidateCreate,
    db: Session = Depends(get_db),
) -> Candidate:
    normalized_email = str(candidate.email).casefold()
    existing = db.scalar(
        select(Candidate).where(func.lower(Candidate.email) == normalized_email)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A candidate with this email already exists",
        )

    candidate_data = candidate.model_dump()
    candidate_data["phone"] = _normalized_phone(candidate.phone)
    created_candidate = Candidate(**candidate_data)
    db.add(created_candidate)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A candidate with this email already exists",
        ) from exc
    db.refresh(created_candidate)
    return created_candidate


@router.get("", response_model=list[CandidateResponse])
def get_candidates(db: Session = Depends(get_db)) -> list[Candidate]:
    return list(db.scalars(select(Candidate).order_by(Candidate.created_at.desc())).all())

@router.post("/{candidate_id}/approve", response_model=CandidateResponse)
def approve_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_db),
) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    candidate.hr_approved = True
    candidate.hr_approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(candidate)
    return candidate


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_db),
) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )
    return candidate


@router.put(
    "/{candidate_id}/email-consent",
    response_model=CandidateResponse,
)
def update_candidate_email_consent(
    candidate_id: UUID,
    payload: CandidateEmailConsentUpdate,
    db: Session = Depends(get_db),
) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )
    candidate.email_consent = payload.email_consent
    candidate.email_consent_at = (
        datetime.now(timezone.utc) if payload.email_consent else None
    )
    db.commit()
    db.refresh(candidate)
    return candidate


@router.put("/{candidate_id}", response_model=CandidateResponse)
def update_candidate(
    candidate_id: UUID,
    payload: CandidateCreate,
    db: Session = Depends(get_db),
) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )
    normalized_email = str(payload.email).casefold()
    duplicate = db.scalar(
        select(Candidate).where(
            func.lower(Candidate.email) == normalized_email,
            Candidate.id != candidate_id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A candidate with this email already exists",
        )
    candidate_data = payload.model_dump()
    candidate_data["phone"] = _normalized_phone(payload.phone)
    for field, value in candidate_data.items():
        setattr(candidate, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A candidate with this email already exists",
        ) from exc
    db.refresh(candidate)
    return candidate


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )
    if candidate.resume_evaluations:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delete uploaded resumes before deleting this candidate",
        )
    db.delete(candidate)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
