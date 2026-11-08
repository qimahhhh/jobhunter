from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import (
    EmploymentType,
    JobFitRequest,
    JobFitResponse,
    JobInput,
    JobStatus,
    MatchResult,
    ProfileInput,
    SalaryPeriod,
)


TargetRoleSource = Literal["suggested", "confirmed"]


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)


class UserRead(UserCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class UserRequirements(BaseModel):
    desired_role: str = Field(min_length=1)
    locations: list[str] = Field(default_factory=list)
    employment_type: EmploymentType = "internship"
    # ``employment_type`` has a default, so the value alone cannot say whether
    # the user chose 实习 or never touched the field. A search that inherits a
    # default turns it into a filter nobody asked for, so the provenance is
    # stored next to the value: only "confirmed" is inherited.
    employment_type_source: Literal["default", "confirmed"] = "default"
    salary_min: int | None = None
    salary_max: int | None = None
    salary_period: SalaryPeriod = "month"
    skill_level: str | None = None


class CapabilityProfile(BaseModel):
    """What the user can do, and the direction the profile is used for.

    ``target_roles`` drives the profile; ``suggested_roles`` keeps what the
    extraction proposed, so the frontend can show "we suggested this" instead
    of presenting an unconfirmed guess as the user's own decision.
    ``target_roles_source`` records which of the two the list came from.
    """

    summary: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    suggested_roles: list[str] = Field(default_factory=list)
    target_roles_source: TargetRoleSource = "confirmed"


class ProfileCreate(BaseModel):
    user_id: str
    requirements: UserRequirements
    capabilities: CapabilityProfile
    missing_information: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    source_resume_id: str | None = None


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    requirements: UserRequirements
    capabilities: CapabilityProfile
    missing_information: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    source_resume_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ProfileConfirmationRequest(BaseModel):
    """The human-in-the-loop hand-off: an extraction draft the user reviewed.

    ``recommended_roles`` is what the model proposed; ``target_roles`` is what
    the user left in the form. Omitting ``target_roles`` means "keep the
    suggestions", which is stored as ``target_roles_source="suggested"`` so an
    unconfirmed direction is never presented as a decision.

    ``missing_information`` carries the gaps the draft reported, because a
    prompt that disappears with the response is a prompt the user never reads.

    ``resume_id`` and ``evidence`` are what make the stored profile traceable:
    the resume holds the parsed chunks, the evidence names the ones the draft
    cited, so a claim can be followed back to the paragraph it came from.
    """

    user_id: str
    requirements: UserRequirements
    profile: ProfileInput
    recommended_roles: list[str] = Field(default_factory=list)
    target_roles: list[str] | None = None
    missing_information: list[str] = Field(default_factory=list)
    resume_id: str | None = None
    evidence: list[str] = Field(default_factory=list)


class ResumeCreate(BaseModel):
    user_id: str
    source_type: Literal["text", "pdf", "docx", "image", "repository"] = "text"
    source_name: str = Field(min_length=1, max_length=255)
    content: dict[str, Any] = Field(default_factory=dict)


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    source_type: str
    source_name: str
    content: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class JobCreate(JobInput):
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    source_name: str = Field(min_length=1, max_length=255)
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_period: SalaryPeriod | None = None


class JobRead(JobCreate):
    model_config = ConfigDict(from_attributes=True)

    employment_type: EmploymentType | None = None
    id: str
    verification_status: JobStatus
    collected_at: datetime
    last_seen_at: datetime | None = None
    last_verified_at: datetime | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# Statuses an operator is allowed to assert. ``unknown`` is left out on
# purpose: it is what the system says when it has no evidence, not a verdict a
# human can record.
VerifiableStatus = Literal[
    "active", "expired", "source_unavailable", "pending_verification"
]


class JobVerificationDecision(BaseModel):
    job_id: str
    status: VerifiableStatus


class JobVerificationRequest(BaseModel):
    """A batch of human verdicts, recorded in one commit.

    Batched because the review step is done by a person with ten tabs open, and
    one commit means a crash halfway cannot leave five verdicts applied and
    five not. An id that no longer exists is reported per entry rather than
    aborting the batch.
    """

    decisions: list[JobVerificationDecision] = Field(min_length=1)


class JobVerificationRejection(BaseModel):
    job_id: str
    reason: str


class JobVerificationResponse(BaseModel):
    updated: list[JobRead] = Field(default_factory=list)
    rejected: list[JobVerificationRejection] = Field(default_factory=list)


ProbeVerdict = Literal["alive", "gone", "unreachable", "no_source"]


class JobProbeRequest(BaseModel):
    """Which stored postings to check against their source page.

    Re-checking ``active`` postings is allowed on purpose: a link that has since
    gone 404 is evidence a human verdict has expired, and the machine is
    allowed to say so even when it is not allowed to say the opposite.
    """

    status: JobStatus = "pending_verification"
    limit: int = Field(default=10, ge=1, le=50)
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=20.0)


class JobProbeResult(BaseModel):
    job_id: str
    title: str
    verdict: ProbeVerdict
    detail: str


class JobProbeResponse(BaseModel):
    checked: int = 0
    alive: int = 0
    results: list[JobProbeResult] = Field(default_factory=list)
    expired: list[str] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)


class JobExpiryRequest(BaseModel):
    """Postings nobody has seen for this long stop being recommended."""

    max_age_days: int = Field(default=14, ge=1, le=365)


class JobExpiryResponse(BaseModel):
    expired: list[str] = Field(default_factory=list)
    max_age_days: int


class JobInputRead(JobInput):
    employment_type: EmploymentType | None = None


class JobFitRequestRead(JobFitRequest):
    job: JobInputRead


class JobMatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_profile_id: str
    job_id: str


class JobMatchRead(JobMatchCreate, MatchResult):
    model_config = ConfigDict(from_attributes=True)

    id: str
    score: float
    match_points: list[str]
    gaps: list[str]
    recommendation: str
    confidence: float
    unknowns: list[str] = Field(default_factory=list)
    created_at: datetime


class JobFitAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    request: JobFitRequestRead
    result: JobFitResponse
    created_at: datetime
