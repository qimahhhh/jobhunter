from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Job, JobMatch, Resume, User, UserProfile
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
    job = Job(
        id=_id(),
        **data.model_dump(),
        verification_status="source_attached" if data.source_url else "needs_review",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise NotFoundError("job not found")
    return job


def create_job_match(session: Session, data: JobMatchCreate) -> JobMatch:
    get_profile(session, data.user_profile_id)
    get_job(session, data.job_id)
    match = JobMatch(id=_id(), **data.model_dump())
    session.add(match)
    session.commit()
    session.refresh(match)
    return match


def get_job_match(session: Session, match_id: str) -> JobMatch:
    match = session.get(JobMatch, match_id)
    if match is None:
        raise NotFoundError("job match not found")
    return match
