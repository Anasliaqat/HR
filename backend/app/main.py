"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api import (
    applications,
    candidates,
    email_automation,
    interviews,
    jobs,
    resumes,
    screening,
)
from app.config import settings
from app.database.connection import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

cors_origins = {
    origin.strip()
    for origin in settings.cors_origins.split(",")
    if origin.strip()
}
cors_origins.update(
    {"http://localhost:5173", "http://127.0.0.1:5173"}
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix=settings.api_v1_prefix)
app.include_router(candidates.router, prefix=settings.api_v1_prefix)
app.include_router(applications.router, prefix=settings.api_v1_prefix)
app.include_router(resumes.router, prefix=settings.api_v1_prefix)
app.include_router(screening.router, prefix=settings.api_v1_prefix)
app.include_router(interviews.router, prefix=settings.api_v1_prefix)
app.include_router(email_automation.router, prefix=settings.api_v1_prefix)


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(
    _: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    logger.exception("Database operation failed: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database operation failed; check database availability"},
    )


@app.get("/", tags=["health"])
async def home() -> dict[str, str]:
    return {
        "message": "AI-Powered HR Hiring Automation API",
        "documentation": "/docs",
    }


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
