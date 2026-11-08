from __future__ import annotations

import uuid
from collections.abc import Sequence
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
from .interview_agent import answered_ids, decide, plan_interview
from .jd_extract import requirements_for
from .job_hunter import JobHunterAgent, dedupe_key
from .job_probe import JobProber
from .job_query import expand_query
from .job_sources import JobSource, OfferCampusSource, notices_to_jobs
from .llm import LLMClient
from .models import (
    InterviewSession,
    Job,
    JobFitAnalysis,
    JobMatch,
    Resume,
    User,
    UserProfile,
    as_utc,
    utc_now,
)
from .schemas import (
    CitedChunk,
    EmploymentType,
    FitReport,
    JobFitRequest,
    JobFitResponse,
    JobInput,
    JobRequirement,
    JobStatus,
    ProfileInput,
    ResumeDraftContent,
    ResumeDraftResponse,
)
from .schemas_resources import (
    JobCreate,
    JobExpiryRequest,
    JobExpiryResponse,
    JobMatchCreate,
    JobProbeRequest,
    JobProbeResponse,
    JobProbeResult,
    JobRead,
    JobVerificationRejection,
    JobVerificationRequest,
    JobVerificationResponse,
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
from .schemas_interview import (
    InterviewAnswerRequest,
    InterviewPlan,
    InterviewSessionRead,
    InterviewStartRequest,
    InterviewTurn,
)
from .scoring import heuristic_requirements


class NotFoundError(ValueError):
    pass


class ConflictError(ValueError):
    pass


class ConstraintRejectedError(ValueError):
    """Raised when a job fails the deterministic hard constraints."""

    def __init__(self, outcome: FilterOutcome) -> None:
        self.outcome = outcome
        super().__init__("; ".join(outcome.rejections))


class InterviewNotPossibleError(ValueError):
    """The posting has no requirement an interview could be built on."""


class InterviewFinishedError(ValueError):
    """The session is over, or has no question waiting for an answer."""


def _id() -> str:
    return uuid.uuid4().hex


def _profile_input(profile: UserProfile) -> ProfileInput:
    """The three fields every model step is allowed to see.

    Built in one place because matching and interviewing both need it: the two
    disagreeing about what a profile contains would make one of them answer a
    slightly different question than the other.
    """

    capabilities = profile.capabilities or {}
    return ProfileInput(
        summary=capabilities["summary"],
        skills=capabilities.get("skills", []),
        experiences=capabilities.get("experiences", []),
    )


def _job_input(job: Job, fallback_type: str) -> JobInput:
    """A stored posting in the shape the agents take.

    A row may predate the ``employment_type`` column, so the caller's
    expectation stands in rather than the field being nullable everywhere.
    """

    return JobInput(
        title=job.title,
        company=job.company,
        description=job.description,
        requirements=job.requirements,
        employment_type=job.employment_type or fallback_type,
        source_name=job.source_name,
        source_url=job.source_url,
    )


# ``Resume.source_type`` of a base draft written by the model. A tailored
# resume is a patch against one stored base, so the row has to outlive the
# response it arrived in.
BASE_DRAFT_SOURCE = "draft"


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
        breakdown=[entry.model_dump() for entry in report.breakdown],
        must_gaps=list(report.must_gaps),
        must_coverage=report.must_coverage,
        score_source=report.score_source,
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


def base_resume_content(
    response: ResumeDraftResponse, *, profile_id: str
) -> dict[str, Any]:
    """The stored shape of a base draft, with one id per bullet.

    The response reads fine without ids; a tailored version cannot work without
    them, because a patch says "rewrite e2-b1" and there has to be an e2-b1 to
    point at. Ids are positional rather than hashed: a patch is generated
    against one stored version, so an id only has to be stable inside that
    version, and a person reading a diff can count their way to e2-b1.

    ``cited_chunks`` travels with the resume on purpose. The chunks themselves
    live in the extraction record, but a profile can be built from a structured
    dump that has no source resume at all, and then the cited text is the only
    thing left to check a rewritten number against.
    """

    return {
        "profile_id": profile_id,
        "headline": response.headline,
        "summary": response.summary,
        "experiences": [
            {
                "heading": experience.heading,
                "bullets": [
                    {
                        "bullet_id": f"e{index}-b{position}",
                        "text": bullet.text,
                        "sources": list(bullet.sources),
                    }
                    for position, bullet in enumerate(experience.bullets, start=1)
                ],
            }
            for index, experience in enumerate(response.experiences, start=1)
        ],
        "skills": list(response.skills),
        "education": list(response.education),
        "suggestions": list(response.suggestions),
        "cited_chunks": [chunk.model_dump() for chunk in response.cited_chunks],
        "notes": list(response.notes),
    }


def save_base_resume(
    session: Session, profile: UserProfile, response: ResumeDraftResponse
) -> Resume:
    """Store a base draft as the next version of this profile's resume.

    Every draft becomes a new row instead of overwriting the previous one: a
    tailored resume patches one specific base, so the base a patch cites has to
    survive the next draft replacing it.

    Versions are counted per profile, not per user. One user applying in two
    directions has two profiles, and a version number that jumped because the
    other direction was drafted would say nothing about either history.

    The lookup filters ``source_type`` in SQL and ``profile_id`` in Python: a
    JSON key comparison is spelled differently on SQLite and PostgreSQL, and one
    profile's draft history is short enough that scanning it costs nothing.
    """

    history = [
        record
        for record in session.query(Resume).filter(
            Resume.source_type == BASE_DRAFT_SOURCE
        )
        if (record.content or {}).get("profile_id") == profile.id
    ]
    version = max((record.version for record in history), default=0) + 1
    record = Resume(
        id=_id(),
        user_id=profile.user_id,
        source_type=BASE_DRAFT_SOURCE,
        source_name=f"基础简历草稿 v{version}",
        version=version,
        content=base_resume_content(response, profile_id=profile.id),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def draft_resume_for_profile(
    session: Session,
    profile: UserProfile,
    client: LLMClient,
    max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
    *,
    persist: bool = False,
) -> ResumeDraftResponse:
    """Draft a base resume from a stored profile and its source chunks.

    Shared by ``POST /resumes/draft`` and the hunt pipeline: both entry points
    have to build the same material, or the same profile would produce two
    different resumes depending on which route was called. The caller resolves
    the profile first so a missing id is still a 404 and never costs a model
    call.

    ``persist`` stores the draft as the next version and returns its id. The
    hunt pipeline leaves it off: a resume the user never opened should not fill
    the history with one row per search.

    A draft that failed its checks is never stored. It is an error report with
    empty content, and a version number would let a later patch cite a base that
    has nothing in it.
    """

    blocks = blocks_from_profile(profile.capabilities or {})
    if profile.source_resume_id:
        source = get_resume(session, profile.source_resume_id)
        blocks.extend(
            blocks_from_stored_chunks((source.content or {}).get("chunks", []))
        )

    result = draft_resume(blocks, client, max_chunk_tokens=max_chunk_tokens)
    content = result.content or ResumeDraftContent()
    response = ResumeDraftResponse(
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
    if not (persist and not result.degraded):
        return response

    record = save_base_resume(session, profile, response)
    return response.model_copy(
        update={"resume_id": record.id, "version": record.version}
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
        if job.verification_status == "expired":
            # The source is still publishing this posting, which contradicts the
            # verdict that closed it. A verdict is bound to a moment, so it goes
            # back to pending for a fresh look instead of hiding a re-opened
            # posting indefinitely.
            job.verification_status = "pending_verification"
            job.last_verified_at = None
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
    verification_status: JobStatus | None = None,
) -> list[Job]:
    query = session.query(Job)
    if employment_type is not None:
        query = query.filter(Job.employment_type == employment_type)
    if verification_status is not None:
        query = query.filter(Job.verification_status == verification_status)
    return list(query.order_by(Job.created_at.desc()).all())


def verify_jobs(
    session: Session, data: JobVerificationRequest
) -> JobVerificationResponse:
    """Record a human's verdict on whether a posting is still open.

    Verification is a claim with a time, not a flag: ``last_verified_at`` moves
    only when an operator asserts something, so "active" can never appear
    without a date behind it. Reverting to ``pending_verification`` clears the
    date, because the previous claim is exactly what is being withdrawn.

    One commit for the whole batch, so a crash halfway cannot leave five
    verdicts applied and five not. An id that no longer exists is reported in
    ``rejected`` instead of aborting the rest.
    """

    updated: list[Job] = []
    rejected: list[JobVerificationRejection] = []
    verified_at = utc_now()

    for decision in data.decisions:
        job = session.get(Job, decision.job_id)
        if job is None:
            rejected.append(
                JobVerificationRejection(
                    job_id=decision.job_id, reason="job not found"
                )
            )
            continue
        job.verification_status = decision.status
        job.last_verified_at = (
            None if decision.status == "pending_verification" else verified_at
        )
        updated.append(job)

    session.commit()
    for job in updated:
        session.refresh(job)

    return JobVerificationResponse(
        updated=[JobRead.model_validate(job) for job in updated],
        rejected=rejected,
    )


def probe_jobs(
    session: Session,
    data: JobProbeRequest,
    prober: JobProber | None = None,
) -> JobProbeResponse:
    """Check stored postings against the pages they came from.

    The machine may only ever downgrade. A 404 or a ``已截止`` marker is
    evidence the posting is closed; a 200 is not evidence that anyone is still
    hiring, so an alive result records that the check happened and changes
    nothing else. An unreachable source only downgrades postings a human has not
    already spoken for, because a site refusing a bot says nothing about the
    job, and a transient timeout must not overwrite a verdict.
    """

    checker = prober or JobProber(timeout=data.timeout_seconds)
    checked_at = utc_now()
    jobs = list_jobs(session, verification_status=data.status)[: data.limit]

    results: list[JobProbeResult] = []
    expired: list[str] = []
    unavailable: list[str] = []
    alive = 0

    for job in jobs:
        outcome = checker.probe(job.id, job.source_url)
        job.last_checked_at = checked_at

        if outcome.verdict == "gone":
            job.verification_status = "expired"
            expired.append(job.id)
        elif outcome.verdict == "unreachable" and job.verification_status != "active":
            job.verification_status = "source_unavailable"
            unavailable.append(job.id)
        elif outcome.verdict == "alive":
            alive += 1

        results.append(
            JobProbeResult(
                job_id=job.id,
                title=job.title,
                verdict=outcome.verdict,
                detail=outcome.detail,
            )
        )

    session.commit()
    return JobProbeResponse(
        checked=len(jobs),
        alive=alive,
        results=results,
        expired=expired,
        unavailable=unavailable,
    )


def expire_stale_jobs(
    session: Session, data: JobExpiryRequest
) -> JobExpiryResponse:
    """Mark postings nobody has seen for a while, without deleting them.

    Age is read from the last moment there was evidence the posting exists:
    collected (``last_seen_at``, falling back to ``collected_at``) or confirmed
    by a person (``last_verified_at``). Taking the latest of the three is what
    stops a collection that simply did not run for a fortnight from expiring a
    posting someone checked yesterday.

    Marked rather than removed: a posting that comes back is picked up by the
    collector again, and a decision that leaves no row behind cannot be
    explained to anyone.

    The comparison happens in Python on purpose. SQLite stores no offset, so a
    cutoff bound into SQL would be compared against a differently shaped string,
    and the same query would behave differently on PostgreSQL.
    """

    now = utc_now()
    threshold = data.max_age_days * 86400
    expired: list[str] = []

    for job in session.query(Job).filter(Job.verification_status != "expired").all():
        stamps = [
            as_utc(value)
            for value in (job.last_seen_at, job.collected_at, job.last_verified_at)
            if value is not None
        ]
        if not stamps:
            continue
        if (now - max(stamps)).total_seconds() > threshold:
            job.verification_status = "expired"
            expired.append(job.id)

    session.commit()
    return JobExpiryResponse(expired=expired, max_age_days=data.max_age_days)


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

    if query.verified_only:
        # The one place where dropping a row is the request itself, so NULL is
        # not spared here: "only verified openings" means exactly that.
        statement = statement.filter(Job.verification_status == "active")

    return statement.order_by(Job.collected_at.desc())


def search_jobs(
    session: Session,
    data: JobSearchRequest,
    client: LLMClient | None = None,
) -> JobSearchResponse:
    """Rank the stored postings for a query, optionally seeded from a profile.

    ``client`` is only used when the query asks for expansion, and its absence
    is a skipped optional step rather than an error: search has to work on a
    deployment with no model key.
    """

    query = data.query
    notes: list[str] = []
    if data.profile_id:
        profile = get_profile(session, data.profile_id)
        query, profile_notes = _query_with_profile_defaults(query, profile)
        notes.extend(profile_notes)

    if query.expand:
        if client is None:
            notes.append("未配置模型，查询改写已跳过，按原有关键词检索。")
        else:
            aliases, expansion_note = expand_query(query, client)
            notes.append(expansion_note)
            if aliases:
                query = query.model_copy(
                    update={"aliases": [*query.aliases, *aliases]}
                )

    jobs = _narrow_job_query(session, query).all()
    prefiltered_out = session.query(Job).count() - len(jobs)
    if query.verified_only:
        notes.append("verified_only：只检索已核验为在招的岗位，未核验和已过期的都不参与排序。")
    if prefiltered_out:
        notes.append(
            f"SQL 预筛选排除了 {prefiltered_out} 条不满足岗位类型、地点或核验状态的岗位，"
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


def create_job_match(
    session: Session,
    data: JobMatchCreate,
    client: LLMClient | None = None,
) -> JobMatch:
    """Score one stored posting against one stored profile.

    ``client`` is optional and only buys the requirement extraction. Passing
    ``None`` still produces a score, a breakdown and a reason for every line —
    the requirements are then split on punctuation instead of read by a model,
    and ``score_source`` says so. A deployment without a key therefore keeps
    working, and a result never has to be guessed at afterwards.
    """

    profile = get_profile(session, data.user_profile_id)
    job = get_job(session, data.job_id)

    requirements = UserRequirements.model_validate(profile.requirements)
    outcome = hard_filter(job, requirements)
    if not outcome.passed:
        raise ConstraintRejectedError(outcome)

    requirement_set, requirement_note = requirements_for(
        session, job.requirements, job.description, client
    )

    report = CareerAnalystAgent().run(
        _profile_input(profile),
        _job_input(job, requirements.employment_type),
        requirement_set,
    )
    report.notes.append(requirement_note)
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


def _requirement_text(
    requirements: Sequence[JobRequirement], requirement_id: str
) -> str:
    for requirement in requirements:
        if requirement.requirement_id == requirement_id:
            return requirement.text
    return ""


def _interview_read(record: InterviewSession) -> InterviewSessionRead:
    """The session plus what is left to ask.

    ``remaining`` is derived rather than stored: a stored copy would be a second
    source of truth for "what has been covered", and the two would drift the
    first time a write half-succeeded.
    """

    turns = [InterviewTurn.model_validate(turn) for turn in record.turns]
    requirements = [
        JobRequirement.model_validate(item) for item in record.requirements
    ]
    asked = answered_ids(turns)
    return InterviewSessionRead(
        id=record.id,
        profile_id=record.user_profile_id,
        job_id=record.job_id,
        status=record.status,  # type: ignore[arg-type]
        max_turns=record.max_turns,
        plan=InterviewPlan.model_validate(record.plan or {}),
        turns=turns,
        remaining=[
            requirement.requirement_id
            for requirement in requirements
            if requirement.requirement_id not in asked
        ],
        finish_reason=record.finish_reason or "",
        notes=list(record.notes or []),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _load_interview(session: Session, interview_id: str) -> InterviewSession:
    record = session.get(InterviewSession, interview_id)
    if record is None:
        raise NotFoundError("interview not found")
    return record


def start_interview_session(
    session: Session,
    data: InterviewStartRequest,
    client: LLMClient,
) -> InterviewSessionRead:
    """Plan an interview and put its first question on screen.

    The plan is stored before the first answer exists, because it is what the
    turn-by-turn decisions are allowed to deviate from. A client is required:
    the whole point of this stage is that a model reads the answer.
    """

    profile = get_profile(session, data.profile_id)
    job = get_job(session, data.job_id)

    requirement_set, requirement_note = requirements_for(
        session, job.requirements, job.description, client
    )
    requirements = (requirement_set or heuristic_requirements(job)).requirements
    if not requirements:
        raise InterviewNotPossibleError(
            "这个岗位没有可判定的需求，先补全岗位要求再安排面试"
        )

    profile_input = _profile_input(profile)
    expectations = UserRequirements.model_validate(profile.requirements)
    job_input = _job_input(job, expectations.employment_type)
    plan, plan_note = plan_interview(profile_input, job_input, requirements, client)

    opening = plan.targets[0]
    first_turn = InterviewTurn(
        index=1,
        kind="ask",
        requirement_id=opening.requirement_id,
        requirement_text=_requirement_text(requirements, opening.requirement_id),
        question=opening.question,
        why=opening.why,
    )
    record = InterviewSession(
        id=_id(),
        user_profile_id=profile.id,
        job_id=job.id,
        status="in_progress",
        max_turns=data.max_turns,
        requirements=[requirement.model_dump() for requirement in requirements],
        plan=plan.model_dump(),
        turns=[first_turn.model_dump()],
        notes=[note for note in (requirement_note, plan_note) if note],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return _interview_read(record)


def answer_interview(
    session: Session,
    interview_id: str,
    data: InterviewAnswerRequest,
    client: LLMClient,
) -> InterviewSessionRead:
    """Record an answer, then let the interviewer choose the next move.

    Three things are enforced here rather than asked of the model: the turn
    budget, one follow-up per requirement (checked in ``interview_agent``), and
    the fact that an answer belongs to the question currently on screen.
    """

    record = _load_interview(session, interview_id)
    if record.status == "finished":
        raise InterviewFinishedError("这场面试已经结束")

    turns = [InterviewTurn.model_validate(turn) for turn in record.turns]
    if not turns or turns[-1].answer is not None:
        raise InterviewFinishedError("没有待回答的问题")
    turns[-1].answer = data.answer

    notes = list(record.notes or [])
    if len(turns) >= record.max_turns:
        record.status = "finished"
        record.finish_reason = f"已达到 {record.max_turns} 轮上限"
        notes.append(f"第 {len(turns)} 轮到达轮次上限，面试结束")
    else:
        profile = get_profile(session, record.user_profile_id)
        job = get_job(session, record.job_id)
        requirements = [
            JobRequirement.model_validate(item) for item in record.requirements
        ]
        expectations = UserRequirements.model_validate(profile.requirements)
        decision = decide(
            _profile_input(profile),
            _job_input(job, expectations.employment_type),
            requirements,
            turns,
            record.max_turns - len(turns),
            client,
        )
        if decision.note:
            notes.append(decision.note)
        if decision.kind == "finish":
            record.status = "finished"
            record.finish_reason = decision.reason
        else:
            turns.append(
                InterviewTurn(
                    index=len(turns) + 1,
                    kind=decision.kind,
                    requirement_id=decision.requirement_id,
                    requirement_text=_requirement_text(
                        requirements, decision.requirement_id
                    ),
                    question=decision.question,
                    why=decision.why,
                )
            )

    record.turns = [turn.model_dump() for turn in turns]
    record.notes = notes
    session.commit()
    session.refresh(record)
    return _interview_read(record)


def read_interview(session: Session, interview_id: str) -> InterviewSessionRead:
    return _interview_read(_load_interview(session, interview_id))


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
