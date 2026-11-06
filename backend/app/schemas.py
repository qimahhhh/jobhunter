from __future__ import annotations

from pydantic import BaseModel, Field


class ProfileInput(BaseModel):
    summary: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)


class JobInput(BaseModel):
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    description: str = Field(min_length=1)
    requirements: str = Field(min_length=1)
    source_name: str = "user-provided"
    source_url: str | None = None


class JobFitRequest(BaseModel):
    profile: ProfileInput
    job: JobInput


class JobVerification(BaseModel):
    status: str
    checks: dict[str, bool]
    source_name: str
    source_url: str | None


class FitReport(BaseModel):
    summary: str
    match_points: list[str]
    gaps: list[str]
    recommendation: str
    confidence: float


class InterviewQuestion(BaseModel):
    type: str
    question: str
    why: str


class RunEvent(BaseModel):
    stage: str
    status: str
    duration_ms: int
    detail: str


class JobFitResponse(BaseModel):
    request_id: str
    job: JobVerification
    fit_report: FitReport
    resume_suggestions: list[str]
    interview_questions: list[InterviewQuestion]
    warnings: list[str]
    run_log: list[RunEvent]
