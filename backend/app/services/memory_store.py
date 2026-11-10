"""Temporary in-memory storage for API development before database integration."""

from uuid import UUID

from app.schemas.candidates import CandidateResponse
from app.schemas.interviews import InterviewResponse
from app.schemas.jobs import JobResponse
from app.schemas.resumes import ResumeEvaluationResponse, ResumeResponse
from app.schemas.screening import ScreeningResponse

jobs: dict[UUID, JobResponse] = {}
candidates: dict[UUID, CandidateResponse] = {}
resumes: dict[UUID, ResumeResponse] = {}
resume_files: dict[UUID, str] = {}
resume_evaluations: dict[UUID, ResumeEvaluationResponse] = {}
screenings: dict[UUID, ScreeningResponse] = {}
interviews: dict[UUID, InterviewResponse] = {}
