"""Application settings loaded from environment variables."""
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
# Auto-generated signing key used when AUTH_SECRET_KEY is not set (gitignored).
AUTH_SECRET_FILE = Path(__file__).resolve().parents[1] / ".auth_secret"


class Settings(BaseSettings):
    app_name: str = "AI-Powered HR Hiring Automation"
    environment: str = "development"
    api_v1_prefix: str = "/api"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_url: str = "sqlite:///./hr_hiring_local.db"

    # Authentication. The HR portal has exactly one allowed login email.
    auth_secret_key: str = ""
    hr_allowed_email: str = "anasarman997@gmail.com"
    # When set, the HR account is created/updated at startup so HR can log in
    # without waiting for an emailed verification code. Minimum 12 characters.
    hr_password: str = ""

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

    # CV score policy: at or below the reject score the candidate gets an
    # automatic rejection email; at or above the approve score they get an
    # automatic approval email; everything in between waits for an HR decision.
    email_automation_reject_below_score: int = 50
    email_automation_auto_approve_from_score: int = 90

    @field_validator("database_url", mode="before")
    @classmethod
    def default_local_database(cls, value: str | None) -> str:
        return value.strip() if isinstance(value, str) and value.strip() else "sqlite:///./hr_hiring_local.db"

    model_config = SettingsConfigDict(env_file=BACKEND_ENV_FILE, env_file_encoding="utf-8", extra="ignore")


settings = Settings()
