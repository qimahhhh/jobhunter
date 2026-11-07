from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .agents import CareerAnalystAgent
from .filters import FilterOutcome, hard_filter
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
    EmploymentType,
    JobFitRequest,
    JobFitResponse,
    FitReport,
    JobInput,
    ProfileInput,
)
from .schemas_resources import (
    JobCreate,
    JobMatchCreate,
    ProfileCreate,
    ResumeCreate,
    UserCreate,
    UserRequirements,
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
            requirements=data.requirements.model_dump(),
            capabilities=data.capabilities.model_dump(),
            missing_information=list(data.missing_information),
            evidence=list(data.evidence),
            source_resume_id=data.source_resume_id,
        )
        session.add(profile)
    else:
        # Re-confirming replaces the whole profile: the draft is the source of
        # truth the user just reviewed, not a patch to merge into old fields.
        profile.requirements = data.requirements.model_dump()
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


def create_job(session: Session, data: JobCreate) -> Job:
    job = _job_input_to_job(data, id=_id())
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


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
