from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
import re

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .db import get_session, init_db
from .orchestrator import JobFitOrchestrator, JobFitRunError
from .routers import router
from .schemas import JobFitFailureResponse, JobFitRequest, JobFitResponse
from .services import create_job_fit_analysis


logger = logging.getLogger(__name__)


def _cors_origin_pattern() -> str:
    configured_origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    local_frontend = r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?"
    if configured_origins:
        allowed_origins = "|".join(re.escape(origin) for origin in configured_origins)
        return rf"^(?:{allowed_origins})$"
    return rf"^(?:{local_frontend})$"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI-Job-Hunter API",
    version="0.1.0",
    description="Minimal FastAPI foundation for the hackathon MVP.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_cors_origin_pattern(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
orchestrator = JobFitOrchestrator()
app.include_router(router, prefix="/api/v1", tags=["resources"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-job-hunter"}


@app.post(
    "/api/v1/job-fit",
    response_model=JobFitResponse,
    responses={500: {"model": JobFitFailureResponse}},
)
def job_fit(
    request: JobFitRequest,
    session: Session = Depends(get_session),
) -> JobFitResponse | JSONResponse:
    try:
        response = orchestrator.run(request)
        create_job_fit_analysis(session, request, response)
        return response
    except JobFitRunError as exc:
        logger.exception(
            "job-fit request %s failed at stage %s; run_log=%s",
            exc.request_id,
            exc.failed_stage,
            [event.model_dump() for event in exc.run_log],
        )
        return JSONResponse(
            status_code=500,
            content=exc.to_response().model_dump(mode="json"),
        )
