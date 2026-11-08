from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .agents import CareerAnalystAgent
from .chunking import DEFAULT_MAX_CHUNK_TOKENS
from .filters import (
    REMOTE_MARKERS,
    FilterOutcome,
    hard_filter,
    location_tokens,
)
from .job_hunter import JobHunterAgent, dedupe_key
from .job_sources import JobSource, OfferCampusSource, notices_to_jobs
from .llm import LLMClient
from .models import (
    Job,
    JobFitAnalysis,
    JobMatch,
    Resume,
    User,
    UserProfile,
    utc_now,
)
from .schemas import (
    CitedChunk,
    EmploymentType,
    JobFitRequest,
    JobFitResponse,
    FitReport,
    JobInput,
    ProfileInput,
    ResumeDraftContent,
    ResumeDraftResponse,
)
from .schemas_resources import (
    JobCreate,
    JobMatchCreate,
    ProfileCreate,
    ResumeCreate,
    UserCreate,
    UserRequirements,
)
from .schemas_search import (
    JobCollectRequest,
    JobCollectResponse,
    JobIngestRequest,
    JobIngestResponse,
    JobQuery,
    JobSearchRequest,
    JobSearchResponse,
)
from .resume_draft import (
    blocks_from_profile,
    blocks_from_stored_chunks,
    draft_resume,
)


class NotFoundError(ValueError):
    pass


class ConflictError(ValueError):
    pass


class ConstraintRejectedError(ValueError):
    """Raised when a job fails the deterministic hard constraints."""

    def __init__(self, outcome: FilterOutcome) -> None:
        self.outcome = outcome
        super().__init__("; ".join(outcome.rejections))


def _id() -> str:
    return uuid.uuid4().hex


def _job_input_to_job(data: JobInput, *, id: str) -> Job:
    return Job(
        id=id,
        **data.model_dump(),
        verification_status="pending_verification",
        collected_at=utc_now(),
    )


def _fit_report_to_job_match(
    report: FitReport,
    *,
    id: str,
    user_profile_id: str,
    job_id: str,
    unknowns: list[str] | None = None,
) -> JobMatch:
    return JobMatch(
        id=id,
        user_profile_id=user_profile_id,
        job_id=job_id,
        score=report.score,
        match_points=report.match_points,
        gaps=report.gaps,
        recommendation=report.recommendation,
        confidence=report.confidence,
        unknowns=list(unknowns or []),
    )


def create_user(session: Session, data: UserCreate) -> User:
    user = User(id=_id(), **data.model_dump())
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("email already exists") from exc
    session.refresh(user)
    return user


def get_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    return user


def _stored_requirements(requirements: UserRequirements) -> dict[str, Any]:
    """Store the requirements together with how the job type was decided.

    Pydantic knows which fields the caller actually sent; once serialised to
    JSON that knowledge is gone. Stamping it at the boundary is what lets a
    later search tell a confirmed 实习 from a default that nobody picked.
    """

    payload = requirements.model_dump()
    if "employment_type" in requirements.model_fields_set:
        payload["employment_type_source"] = "confirmed"
    return payload


def create_profile(session: Session, data: ProfileCreate) -> UserProfile:
    """Create the user's profile, or update the one they already have.

    A profile is a property of the user rather than a log entry: confirming a
    corrected draft twice must leave one row, not two profiles that nobody can
    tell apart. The unique index on ``user_id`` backs this up for concurrent
    writers; this lookup keeps the ordinary path free of IntegrityError noise.
    """

    get_user(session, data.user_id)
    profile = session.scalar(
        select(UserProfile).where(UserProfile.user_id == data.user_id)
    )
    if profile is None:
        profile = UserProfile(
            id=_id(),
            user_id=data.user_id,
            requirements=_stored_requirements(data.requirements),
            capabilities=data.capabilities.model_dump(),
            missing_information=list(data.missing_information),
            evidence=list(data.evidence),
            source_resume_id=data.source_resume_id,
        )
        session.add(profile)
    else:
        # Re-confirming replaces the whole profile: the draft is the source of
        # truth the user just reviewed, not a patch to merge into old fields.
        profile.requirements = _stored_requirements(data.requirements)
        profile.capabilities = data.capabilities.model_dump()
        profile.missing_information = list(data.missing_information)
        profile.evidence = list(data.evidence)
        profile.source_resume_id = data.source_resume_id

    session.commit()
    session.refresh(profile)
    return profile


def get_profile(session: Session, profile_id: str) -> UserProfile:
    profile = session.get(UserProfile, profile_id)
    if profile is None:
        raise NotFoundError("profile not found")
    return profile


def create_resume(session: Session, data: ResumeCreate) -> Resume:
    get_user(session, data.user_id)
    resume = Resume(id=_id(), **data.model_dump())
    session.add(resume)
    session.commit()
    session.refresh(resume)
    return resume


def get_resume(session: Session, resume_id: str) -> Resume:
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise NotFoundError("resume not found")
    return resume


def draft_resume_for_profile(
    session: Session,
    profile: UserProfile,
    client: LLMClient,
    max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
) -> ResumeDraftResponse:
    """Draft a base resume from a stored profile and its source chunks.

    Shared by ``POST /resumes/draft`` and the hunt pipeline: both entry points
    have to build the same material, or the same profile would produce two
    different resumes depending on which route was called. The caller resolves
    the profile first so a missing id is still a 404 and never costs a model
    call.
    """

    blocks = blocks_from_profile(profile.capabilities or {})
    if profile.source_resume_id:
        source = get_resume(session, profile.source_resume_id)
        blocks.extend(
            blocks_from_stored_chunks((source.content or {}).get("chunks", []))
        )

    result = draft_resume(blocks, client, max_chunk_tokens=max_chunk_tokens)
    content = result.content or ResumeDraftContent()
    return ResumeDraftResponse(
        profile_id=profile.id,
        headline=content.headline,
        summary=content.summary,
        experiences=content.experiences,
        skills=content.skills,
        education=content.education,
        suggestions=content.suggestions,
        cited_chunks=[
            CitedChunk(
                id=chunk.chunk_id,
                source=chunk.source,
                section=chunk.section,
                text=chunk.text,
            )
            for chunk in result.cited
        ],
        unresolved_evidence=result.unresolved,
        unverified_bullets=result.unverified_bullets,
        unverified_fields=result.unverified_fields,
        degraded=result.degraded,
        notes=result.notes,
    )


def create_job(session: Session, data: JobCreate) -> Job:
    """Record a job someone entered by hand.

    A manual entry carries no ``dedupe_key``. Two openings with the same title
    at the same company can be two real postings, and a unique index cannot
    tell the difference, so deduplication belongs to ``ingest_jobs``: there the
    caller is a collector stating "this is what the source published today".
    """

    job = _job_input_to_job(data, id=_id())
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def ingest_jobs(session: Session, data: JobIngestRequest) -> JobIngestResponse:
    """Store a collector's batch, treating a known posting as the same posting.

    The first source stays as provenance, because that is what a verification
    links back to. The facts the posting publishes (salary, location, text) are
    refreshed, and ``last_seen_at`` becomes now, so an expired posting is one
    that stopped being seen rather than one that was deleted.
    """

    created: list[str] = []
    updated: list[str] = []
    seen_at = utc_now()
    known: dict[str, Job] = {}

    for item in data.jobs:
        key = dedupe_key(
            title=item.title, company=item.company, location=item.location
        )
        # ``known`` covers a source that lists the same posting twice in one
        # batch: with autoflush off the pending insert is invisible to the
        # lookup, and the second copy would hit the unique index on commit.
        job = known.get(key)
        if job is None:
            job = session.scalar(select(Job).where(Job.dedupe_key == key))
        if job is None:
            job = _job_input_to_job(item, id=_id())
            job.dedupe_key = key
            job.last_seen_at = seen_at
            session.add(job)
            known[key] = job
            created.append(job.id)
            continue

        job.description = item.description
        job.requirements = item.requirements
        job.employment_type = item.employment_type
        job.location = item.location
        job.salary_min = item.salary_min
        job.salary_max = item.salary_max
        job.salary_period = item.salary_period
        job.last_seen_at = seen_at
        known[key] = job
        updated.append(job.id)

    session.commit()
    return JobIngestResponse(
        created=created, updated=updated, total=len(data.jobs)
    )


def collect_jobs(
    session: Session,
    data: JobCollectRequest,
    source: JobSource | None = None,
) -> JobCollectResponse:
    """Pull one batch from a live source and merge it into the stored jobs.

    The collector fetches and normalises; ``ingest_jobs`` keeps the dedupe and
    the "first source stays as provenance" rule. Collection happens when the
    user triggers it: this is the fetching step behind ``/jobs/ingest``, not a
    background crawler. ``source`` is injectable so tests can feed fixtures
    without touching the network.
    """

    collector: JobSource = source or OfferCampusSource()
    items = collector.fetch_recent(limit=data.limit)
    jobs, warnings = notices_to_jobs(items)
    result = ingest_jobs(session, JobIngestRequest(jobs=jobs))
    if jobs:
        warnings.append("岗位来源未提供薪资字段，薪资下限约束在搜索时按未知处理。")
    return JobCollectResponse(
        source=collector.name,
        fetched=len(items),
        created=result.created,
        updated=result.updated,
        total=result.total,
        warnings=warnings,
    )


def get_job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise NotFoundError("job not found")
    return job


def list_jobs(
    session: Session,
    employment_type: EmploymentType | None = None,
) -> list[Job]:
    query = session.query(Job)
    if employment_type is not None:
        query = query.filter(Job.employment_type == employment_type)
    return list(query.order_by(Job.created_at.desc()).all())


def _query_with_profile_defaults(
    query: JobQuery, profile: UserProfile
) -> tuple[JobQuery, list[str]]:
    """Fill a query from the stored profile, without overriding explicit input.

    The profile is a set of expectations the user already confirmed, so it is a
    reasonable default and never a replacement: anything the caller typed wins.
    Only the fields that were actually taken from the profile are reported, so a
    result can say where its constraints came from.
    """

    requirements = UserRequirements.model_validate(profile.requirements)
    capabilities = profile.capabilities or {}
    updates: dict[str, object] = {}
    notes: list[str] = []
    constrained = False

    if not query.role:
        roles = [
            role for role in capabilities.get("target_roles", []) if role.strip()
        ]
        updates["role"] = (roles[0] if roles else "") or requirements.desired_role
        notes.append("搜索方向取自画像的目标岗位")

    if not query.keywords:
        skills = [
            skill for skill in capabilities.get("skills", []) if skill.strip()
        ][:8]
        if skills:
            updates["keywords"] = skills
            notes.append("检索关键词取自画像技能的前 8 项")

    if not query.locations and requirements.locations:
        updates["locations"] = list(requirements.locations)
        constrained = True

    # Only a job type the user actually confirmed becomes a filter. Inheriting
    # the schema default would answer "you asked for internships" to someone
    # who never chose one, and every full-time posting would vanish with a
    # reasonable-looking reason.
    if (
        query.employment_type is None
        and requirements.employment_type_source == "confirmed"
    ):
        updates["employment_type"] = requirements.employment_type
        constrained = True

    if query.salary_min is None and requirements.salary_min is not None:
        updates["salary_min"] = requirements.salary_min
        updates["salary_period"] = requirements.salary_period
        constrained = True

    if constrained:
        notes.append("地点、薪资下限与已确认的岗位类型沿用了画像中的求职期望")

    return query.model_copy(update=updates), notes


def _narrow_job_query(session: Session, query: JobQuery):
    """Narrow the scan in SQL without dropping a row the agent would keep.

    Only conditions that are safe here go into the statement. A posting whose
    type or city is simply missing must still reach the agent, because the
    agent reports it as an unknown instead of a rejection; filtering those out
    in SQL would turn "incomplete data" into "not a match" silently. Keyword
    matching stays in Python, where the tokenisation lives.
    """

    statement = session.query(Job)

    if query.employment_type is not None:
        statement = statement.filter(
            or_(
                Job.employment_type == query.employment_type,
                Job.employment_type.is_(None),
            )
        )

    tokens = [
        token for location in query.locations for token in location_tokens(location)
    ]
    if tokens:
        patterns = [Job.location.ilike(f"%{token}%") for token in tokens]
        patterns.extend(
            Job.location.ilike(f"%{marker}%") for marker in REMOTE_MARKERS
        )
        statement = statement.filter(or_(Job.location.is_(None), *patterns))

    return statement.order_by(Job.collected_at.desc())


def search_jobs(session: Session, data: JobSearchRequest) -> JobSearchResponse:
    """Rank the stored postings for a query, optionally seeded from a profile."""

    query = data.query
    notes: list[str] = []
    if data.profile_id:
        profile = get_profile(session, data.profile_id)
        query, profile_notes = _query_with_profile_defaults(query, profile)
        notes.extend(profile_notes)

    jobs = _narrow_job_query(session, query).all()
    prefiltered_out = session.query(Job).count() - len(jobs)
    if prefiltered_out:
        notes.append(
            f"SQL 预筛选排除了 {prefiltered_out} 条不满足岗位类型或地点的岗位，"
            "这部分只给数量、不逐条列出原因。"
        )

    result = JobHunterAgent().run(jobs, query)
    return JobSearchResponse(
        query=result.query,
        candidates=result.candidates,
        excluded=result.excluded,
        total_scanned=result.total_scanned,
        prefiltered_out=prefiltered_out,
        notes=notes + result.notes,
        applied_profile_id=data.profile_id,
    )


def create_job_match(session: Session, data: JobMatchCreate) -> JobMatch:
    profile = get_profile(session, data.user_profile_id)
    job = get_job(session, data.job_id)

    requirements = UserRequirements.model_validate(profile.requirements)
    outcome = hard_filter(job, requirements)
    if not outcome.passed:
        raise ConstraintRejectedError(outcome)

    capabilities = profile.capabilities
    report = CareerAnalystAgent().run(
        ProfileInput(
            summary=capabilities["summary"],
            skills=capabilities.get("skills", []),
            experiences=capabilities.get("experiences", []),
        ),
        JobInput(
            title=job.title,
            company=job.company,
            description=job.description,
            requirements=job.requirements,
            # A job row may predate the employment_type column; fall back to the
            # expectation so the keyword analysis can still run.
            employment_type=job.employment_type or requirements.employment_type,
            source_name=job.source_name,
            source_url=job.source_url,
        ),
    )
    match = _fit_report_to_job_match(
        report,
        id=_id(),
        user_profile_id=data.user_profile_id,
        job_id=data.job_id,
        unknowns=outcome.unknowns,
    )
    session.add(match)
    session.commit()
    session.refresh(match)
    return match


def get_job_match(session: Session, match_id: str) -> JobMatch:
    match = session.get(JobMatch, match_id)
    if match is None:
        raise NotFoundError("job match not found")
    return match


def create_job_fit_analysis(
    session: Session,
    request: JobFitRequest,
    result: JobFitResponse,
) -> JobFitAnalysis:
    analysis = JobFitAnalysis(
        request_id=result.request_id,
        request=request.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
    )
    session.add(analysis)
    session.commit()
    session.refresh(analysis)
    return analysis


def get_job_fit_analysis(session: Session, request_id: str) -> JobFitAnalysis:
    analysis = session.get(JobFitAnalysis, request_id)
    if analysis is None:
        raise NotFoundError("job fit analysis not found")
    return analysis


def list_job_fit_analyses(session: Session) -> list[JobFitAnalysis]:
    return list(
        session.query(JobFitAnalysis).order_by(JobFitAnalysis.created_at.desc()).all()
    )
