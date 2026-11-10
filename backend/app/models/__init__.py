"""SQLAlchemy models imported here so metadata registers every table."""

from app.models.agent_run import AgentRun
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.email_log import EmailLog
from app.models.interview import Interview
from app.models.job import Job
from app.models.resume_evaluation import ResumeEvaluation
from app.models.screening import Screening
from app.models.user import User

__all__ = [
    "AgentRun",
    "Application",
    "Candidate",
    "EmailLog",
    "Interview",
    "Job",
    "ResumeEvaluation",
    "Screening",
    "User",
]
