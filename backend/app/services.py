from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .agents import CareerAnalystAgent
from .models import Job, JobFitAnalysis, JobMatch, Resume, User, UserProfile
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
)


class NotFoundError(ValueError):
    pass


class ConflictError(ValueError):
    pass


def _id() -> str:
    return uuid.uuid4().hex


def _job_input_to_job(data: JobInput, *, id: str) -> Job:
    values = data.model_dump()
    location = values.pop("location", None)
    salary_min = values.pop("salary_min", None)
    salary_max = values.pop("salary_max", None)
    return Job(
        id=id,
        **values,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        verification_status="source_attached" if data.source_url else "needs_review",
    )


def _fit_report_to_job_match(
    report: FitReport,
    *,
    id: str,
    user_profile_id: str,
    job_id: str,
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
    get_user(session, data.user_id)
    profile = UserProfile(
        id=_id(),
        user_id=data.user_id,
        requirements=data.requirements.model_dump(),
        capabilities=data.capabilities.model_dump(),
    )
    session.add(profile)
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
    if job.employment_type is None:
        raise ValueError("job employment_type is unknown")
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
            employment_type=job.employment_type,
            source_name=job.source_name,
            source_url=job.source_url,
        ),
    )
    match = _fit_report_to_job_match(
        report,
        id=_id(),
        user_profile_id=data.user_profile_id,
        job_id=data.job_id,
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
