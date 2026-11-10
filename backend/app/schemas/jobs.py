"""Job request and response schemas."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)
    department: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    employment_type: str | None = Field(default=None, max_length=50)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    required_experience_years: int | None = Field(default=None, ge=0, le=80)
    education: str | None = Field(default=None, max_length=5_000)
    number_of_vacancies: int = Field(default=1, ge=1, le=10_000)
    status: Literal["draft", "open", "closed"] = "draft"

    @field_validator("title", "description")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def normalize_skills(cls, skills: list[str]) -> list[str]:
        return list(dict.fromkeys(skill.strip() for skill in skills if skill.strip()))

    @field_validator("department", "location", "employment_type", "education")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class JobResponse(JobCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)
