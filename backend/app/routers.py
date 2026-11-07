from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .db import get_session
from .schemas_resources import (
    JobCreate,
    JobMatchCreate,
    JobMatchRead,
    JobRead,
    ProfileCreate,
    ProfileRead,
    ResumeCreate,
    ResumeRead,
    UserCreate,
    UserRead,
)
from .services import (
    NotFoundError,
    create_job,
    create_job_match,
    create_profile,
    create_resume,
    create_user,
    get_job,
    get_job_match,
    get_profile,
    get_resume,
    get_user,
)


router = APIRouter()


def _session(session: Session = Depends(get_session)) -> Session:
    return session


def _read_or_404(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/users", response_model=UserRead, status_code=201)
def add_user(data: UserCreate, session: Session = Depends(_session)) -> UserRead:
    return UserRead.model_validate(create_user(session, data))


@router.get("/users/{user_id}", response_model=UserRead)
def read_user(user_id: str, session: Session = Depends(_session)) -> UserRead:
    return UserRead.model_validate(_read_or_404(lambda: get_user(session, user_id)))


@router.post("/profiles", response_model=ProfileRead, status_code=201)
def add_profile(data: ProfileCreate, session: Session = Depends(_session)) -> ProfileRead:
    return ProfileRead.model_validate(create_profile(session, data))


@router.get("/profiles/{profile_id}", response_model=ProfileRead)
def read_profile(profile_id: str, session: Session = Depends(_session)) -> ProfileRead:
    return ProfileRead.model_validate(_read_or_404(lambda: get_profile(session, profile_id)))


@router.post("/resumes", response_model=ResumeRead, status_code=201)
def add_resume(data: ResumeCreate, session: Session = Depends(_session)) -> ResumeRead:
    return ResumeRead.model_validate(create_resume(session, data))


@router.get("/resumes/{resume_id}", response_model=ResumeRead)
def read_resume(resume_id: str, session: Session = Depends(_session)) -> ResumeRead:
    return ResumeRead.model_validate(_read_or_404(lambda: get_resume(session, resume_id)))


@router.post("/jobs", response_model=JobRead, status_code=201)
def add_job(data: JobCreate, session: Session = Depends(_session)) -> JobRead:
    return JobRead.model_validate(create_job(session, data))


@router.get("/jobs/{job_id}", response_model=JobRead)
def read_job(job_id: str, session: Session = Depends(_session)) -> JobRead:
    return JobRead.model_validate(_read_or_404(lambda: get_job(session, job_id)))


@router.post("/job-matches", response_model=JobMatchRead, status_code=201)
def add_job_match(data: JobMatchCreate, session: Session = Depends(_session)) -> JobMatchRead:
    return JobMatchRead.model_validate(create_job_match(session, data))


@router.get("/job-matches/{match_id}", response_model=JobMatchRead)
def read_job_match(match_id: str, session: Session = Depends(_session)) -> JobMatchRead:
    return JobMatchRead.model_validate(_read_or_404(lambda: get_job_match(session, match_id)))
