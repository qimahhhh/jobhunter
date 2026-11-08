from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .schemas import EmploymentType, JobStatus, SalaryPeriod
from .schemas_resources import JobCreate


class JobQuery(BaseModel):
    """What the user is looking for, in terms a search can act on.

    Every field is optional on purpose: an empty query lists the newest
    postings instead of pretending that nothing matched. A constraint that is
    left empty is not applied, so a search that names a city but no salary
    never rejects a posting for having no salary.
    """

    role: str = ""
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    employment_type: EmploymentType | None = None
    salary_min: int | None = None
    salary_period: SalaryPeriod = "month"
    # Opt-in and deliberately lossy: the user asks for "only what has been
    # verified as open", so unverified rows are dropped rather than shown with
    # a caveat. Off by default, because an empty demo is worse than a labelled
    # one.
    verified_only: bool = False
    limit: int = Field(default=10, ge=1, le=50)


class JobCandidate(BaseModel):
    job_id: str
    title: str
    company: str
    location: str | None = None
    employment_type: EmploymentType | None = None
    source_name: str
    source_url: str | None = None
    score: float = Field(ge=0, le=1)
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    reason: str
    warnings: list[str] = Field(default_factory=list)
    verification_status: JobStatus | None = None
    last_verified_at: datetime | None = None
    collected_at: datetime | None = None


class JobExclusion(BaseModel):
    """A posting that was scanned and dropped, with why.

    Kept in the response because "the job is missing" and "the job was filtered
    out for a named reason" are different answers, and only the second one can
    be argued with.
    """

    job_id: str
    title: str
    company: str
    reasons: list[str] = Field(default_factory=list)


class JobSearchResult(BaseModel):
    query: JobQuery
    candidates: list[JobCandidate] = Field(default_factory=list)
    excluded: list[JobExclusion] = Field(default_factory=list)
    total_scanned: int = 0
    # Postings the SQL prefilter dropped in bulk. They are counted rather than
    # listed: naming each one would mean reading them, which is the scan the
    # prefilter exists to avoid. Keeping the number makes the difference between
    # "not a match" and "never looked at" visible instead of silent.
    prefiltered_out: int = 0
    notes: list[str] = Field(default_factory=list)


class JobSearchRequest(BaseModel):
    query: JobQuery = Field(default_factory=JobQuery)
    profile_id: str | None = None


class JobSearchResponse(JobSearchResult):
    applied_profile_id: str | None = None


class JobIngestRequest(BaseModel):
    """A batch of postings from one collector.

    Separate from ``POST /jobs`` because the two mean different things: that
    one records a job someone typed in, this one says "these are what the source
    had today" and is idempotent.
    """

    jobs: list[JobCreate] = Field(default_factory=list)


class JobIngestResponse(BaseModel):
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    total: int = 0


class JobCollectRequest(BaseModel):
    """How much to pull from a live source in one triggered collection."""

    limit: int = Field(default=20, ge=1, le=100)


class JobCollectResponse(JobIngestResponse):
    source: str
    fetched: int = 0
    warnings: list[str] = Field(default_factory=list)
