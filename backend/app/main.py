from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import init_db
from .orchestrator import JobFitOrchestrator
from .routers import router
from .schemas import JobFitRequest, JobFitResponse


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


@app.post("/api/v1/job-fit", response_model=JobFitResponse)
def job_fit(request: JobFitRequest) -> JobFitResponse:
    return orchestrator.run(request)
