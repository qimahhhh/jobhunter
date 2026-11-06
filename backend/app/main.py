from __future__ import annotations

from fastapi import FastAPI

from .orchestrator import JobFitOrchestrator
from .schemas import JobFitRequest, JobFitResponse


app = FastAPI(
    title="AI-Job-Hunter API",
    version="0.1.0",
    description="Minimal FastAPI foundation for the hackathon MVP.",
)
orchestrator = JobFitOrchestrator()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-job-hunter"}


@app.post("/api/v1/job-fit", response_model=JobFitResponse)
def job_fit(request: JobFitRequest) -> JobFitResponse:
    return orchestrator.run(request)
