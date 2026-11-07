from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .db import init_db
from .orchestrator import JobFitOrchestrator, JobFitRunError
from .routers import router
from .schemas import JobFitFailureResponse, JobFitRequest, JobFitResponse


logger = logging.getLogger(__name__)


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
def job_fit(request: JobFitRequest) -> JobFitResponse | JSONResponse:
    try:
        return orchestrator.run(request)
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
