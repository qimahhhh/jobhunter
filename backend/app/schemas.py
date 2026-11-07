from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


EmploymentType = Literal["internship", "part_time", "full_time", "contract"]
SalaryPeriod = Literal["day", "month", "year"]
JobStatus = Literal[
    "active",
    "expired",
    "pending_verification",
    "source_unavailable",
    "unknown",
]


class ProfileInput(BaseModel):
    summary: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)


class ProfileDraft(BaseModel):
    """What the extraction call is asked to return.

    The coercions are deliberate. A model that answers with one string where a
    list was asked for is a formatting slip, not a reason to throw away the
    whole extraction, and ``evidence`` has to survive intact because it is the
    only thing tying a claim back to the resume.
    """

    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)
    recommended_roles: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    @field_validator(
        "skills",
        "experiences",
        "recommended_roles",
        "missing_information",
        "evidence",
        mode="before",
    )
    @classmethod
    def _as_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class ResumeExtractionRequest(BaseModel):
    text: str = Field(min_length=1)
    user_id: str | None = None
    max_chunk_tokens: int = Field(default=900, ge=50, le=4000)


class ResumeBullet(BaseModel):
    """One line of a resume entry, with the chunks that support it.

    ``sources`` is not decoration: a bullet whose sources do not exist in the
    context is dropped, because a rewritten resume that cannot be checked is
    worse than no rewrite.
    """

    text: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)

    @field_validator("sources", mode="before")
    @classmethod
    def _as_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class ResumeExperience(BaseModel):
    heading: str = ""
    bullets: list[ResumeBullet] = Field(default_factory=list)


class ResumeDraftContent(BaseModel):
    """What the model is asked to return for a base resume.

    Everything here is a wording change of the profile. ``suggestions`` is the
    only place that may say something the material does not, and it is advice
    about the resume, not a claim about the candidate.
    """

    headline: str = ""
    summary: str = ""
    experiences: list[ResumeExperience] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ResumeDraftRequest(BaseModel):
    profile_id: str
    max_chunk_tokens: int = Field(default=900, ge=50, le=4000)


class CitedChunk(BaseModel):
    id: str
    source: str
    section: str
    text: str


class ResumeDraftResponse(BaseModel):
    profile_id: str
    headline: str
    summary: str
    experiences: list[ResumeExperience]
    skills: list[str]
    education: list[str]
    suggestions: list[str]
    cited_chunks: list[CitedChunk]
    unresolved_evidence: list[str]
    unverified_bullets: int
    degraded: bool
    notes: list[str]


class ResumeSourceBundleRequest(BaseModel):
    """Several inputs for one draft: resume text, projects, self description.

    Files cannot travel in this body, so a PDF or DOCX resumes through
    ``/profiles/extract/file``; this endpoint is for the case where the user has
    a project structure or a self description to add to the material.
    """

    resume_text: str | None = None
    self_description: str | None = None
    projects: dict[str, Any] | list[Any] | None = None
    user_id: str | None = None
    max_chunk_tokens: int = Field(default=900, ge=50, le=4000)

    @model_validator(mode="after")
    def _has_a_source(self) -> "ResumeSourceBundleRequest":
        provided = (
            self.resume_text,
            self.self_description,
            self.projects,
        )
        if not any(value.strip() if isinstance(value, str) else value for value in provided):
            raise ValueError(
                "至少需要一份输入：resume_text、self_description 或 projects"
            )
        return self


class ResumeExtractionResponse(BaseModel):
    """A draft plus the record it can be traced back to.

    ``resume_id`` is present only when the caller supplied ``user_id``: the
    parsed chunks are then stored, so a citation id can be resolved back to the
    text it came from after the request is gone.
    """

    profile: ProfileInput | None
    recommended_roles: list[str]
    missing_information: list[str]
    evidence: list[str]
    unresolved_evidence: list[str]
    chunk_ids: list[str]
    degraded: bool
    resume_id: str | None = None
    notes: list[str]


class JobInput(BaseModel):
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    description: str = Field(min_length=1)
    requirements: str = Field(min_length=1)
    employment_type: EmploymentType
    source_name: str = "user-provided"
    source_url: str | None = None


class JobFitRequest(BaseModel):
    profile: ProfileInput
    job: JobInput


class JobVerification(BaseModel):
    status: JobStatus
    checks: dict[str, bool]
    source_name: str
    source_url: str | None


class MatchResult(BaseModel):
    score: float = Field(ge=0, le=1)
    match_points: list[str]
    gaps: list[str]
    recommendation: str
    confidence: float


class FitReport(MatchResult):
    summary: str


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


class JobFitFailureResponse(BaseModel):
    request_id: str
    status: Literal["failed"]
    failed_stage: str
    error_type: str
    message: str
    run_log: list[RunEvent]
