"""FastAPI application entry point."""
from contextlib import asynccontextmanager
import logging
from collections.abc import AsyncGenerator
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.api import applications, candidates, email_automation, interviews, jobs, resumes, screening, auth, portal
from app.config import settings
from app.database.connection import DatabaseConfigurationError, get_engine, init_db
from app.security import require_hr
from app.services.bootstrap import ensure_hr_account
logger = logging.getLogger(__name__)
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    ensure_hr_account()
    yield
app = FastAPI(title=settings.app_name, lifespan=lifespan)
cors_origins = {origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()}
cors_origins.update({"http://localhost:5173", "http://127.0.0.1:5173"})
# While developing, Vite may fall back to another port (5174, 5175, ...) when 5173 is
# busy, so any localhost port is accepted. Production only allows CORS_ORIGINS.
dev_origin_regex = r"http://(localhost|127\.0\.0\.1):\d+" if settings.environment == "development" else None
app.add_middleware(CORSMiddleware, allow_origins=sorted(cors_origins), allow_origin_regex=dev_origin_regex, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(portal.router, prefix=settings.api_v1_prefix)
hr_guard = [Depends(require_hr)]
app.include_router(jobs.router, prefix=settings.api_v1_prefix, dependencies=hr_guard)
app.include_router(candidates.router, prefix=settings.api_v1_prefix, dependencies=hr_guard)
app.include_router(applications.router, prefix=settings.api_v1_prefix, dependencies=hr_guard)
app.include_router(resumes.router, prefix=settings.api_v1_prefix, dependencies=hr_guard)
app.include_router(screening.router, prefix=settings.api_v1_prefix, dependencies=hr_guard)
app.include_router(screening.public_router, prefix=settings.api_v1_prefix)
app.include_router(interviews.router, prefix=settings.api_v1_prefix, dependencies=hr_guard)
app.include_router(email_automation.router, prefix=settings.api_v1_prefix, dependencies=hr_guard)
@app.exception_handler(SQLAlchemyError)
async def handle_database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database operation failed: %s", exc)
    return JSONResponse(status_code=503, content={"detail":"Database operation failed; check database availability"})
@app.get("/", tags=["health"])
async def home() -> dict[str, str]:
    return {"message":"AI-Powered HR Hiring Automation API","documentation":"/docs"}
@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    try:
        with get_engine().connect() as connection: connection.execute(text("SELECT 1"))
    except (DatabaseConfigurationError, SQLAlchemyError):
        logger.exception("Health check failed because the database is unavailable.")
        raise HTTPException(status_code=503, detail="Database is unavailable. Check DATABASE_URL and database service.") from None
    return {"status":"ok","database":"connected"}
