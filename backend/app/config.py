"""Application settings loaded from environment variables."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    app_name: str = "AI-Powered HR Hiring Automation"
    environment: str = "development"
    api_v1_prefix: str = "/api"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_url: str = ""
    openai_api_key: str = ""
    vapi_api_key: str = ""
    vapi_assistant_id: str = ""
    vapi_phone_number_id: str = ""
    vapi_webhook_secret: str = ""
    vapi_public_phone_number: str = ""
    phone_default_region: str = "PK"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    google_calendar_credentials_file: str = ""
    google_calendar_time_zone: str = "UTC"
    scheduling_test_mode: bool = True
    resend_api_key: str = ""
    email_from_address: str = ""
    email_automation_reject_below_score: int = 50
    email_automation_review_through_score: int = 60
    email_automation_interview_from_score: int = 70
    email_automation_interview_through_score: int = 90
    email_automation_above_range_action: Literal[
        "pending_review", "interview_eligible"
    ] = "pending_review"

    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
