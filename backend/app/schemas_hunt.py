from __future__ import annotations

from pydantic import BaseModel, Field

from .schemas import ResumeDraftResponse, RunEvent
from .schemas_resources import JobMatchRead
from .schemas_search import JobQuery, JobSearchResponse


class JobHuntRequest(BaseModel):
    """One request that walks the demo path end to end.

    ``match_top`` exists because matching is per pair: the user gets a
    shortlist, not a table of everything that was scanned.
    """

    profile_id: str
    query: JobQuery = Field(default_factory=JobQuery)
    match_top: int = Field(default=3, ge=0, le=10)
    with_resume: bool = False
    max_chunk_tokens: int = Field(default=900, ge=50, le=4000)


class JobHuntSkip(BaseModel):
    """A candidate the matching step refused, with the reason.

    Search filters by the query, matching filters by the profile's hard
    constraints. They are allowed to disagree, and when they do the run must say
    so per job instead of aborting or silently dropping it.
    """

    job_id: str
    title: str
    reasons: list[str] = Field(default_factory=list)


class JobHuntResponse(BaseModel):
    profile_id: str
    search: JobSearchResponse
    matches: list[JobMatchRead] = Field(default_factory=list)
    skipped: list[JobHuntSkip] = Field(default_factory=list)
    resume: ResumeDraftResponse | None = None
    run_log: list[RunEvent] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
