from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .db import get_session
from .orchestrator import JobFitOrchestrator, JobFitRunError
from .schemas import (
    EmploymentType,
    JobFitFailureResponse,
    JobFitRequest,
    JobFitResponse,
)
from .schemas_resources import (
    JobCreate,
    JobFitAnalysisRead,
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
    ConflictError,
    ConstraintRejectedError,
    NotFoundError,
    create_job,
    create_job_fit_analysis,
    create_job_match,
    create_profile,
    create_resume,
    create_user,
    get_job,
    get_job_fit_analysis,
    get_job_match,
    get_profile,
    get_resume,
    get_user,
    list_job_fit_analyses,
    list_jobs,
)


logger = logging.getLogger(__name__)

router = APIRouter()
health_router = APIRouter(tags=["Health"])
orchestrator = JobFitOrchestrator()


def _session(session: Session = Depends(get_session)) -> Session:
    return session


def _or_404(operation: Callable[[], Any]) -> Any:
    """Translate a missing row into HTTP 404.

    Covers both direct reads and references resolved while creating a resource
    (``POST /profiles`` resolves the user, ``POST /job-matches`` resolves the
    profile and the job), so a bad id never escapes as an unhandled 500.
    """

    try:
        return operation()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@health_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-job-hunter"}


@router.post(
    "/job-fit",
    response_model=JobFitResponse,
    responses={500: {"model": JobFitFailureResponse}},
)
def job_fit(
    request: JobFitRequest,
    session: Session = Depends(get_session),
) -> JobFitResponse | JSONResponse:
    try:
        response = orchestrator.run(request)
        create_job_fit_analysis(session, request, response)
        return response
    except JobFitRunError as exc:
        logger.exception(
            "job-fit request %s failed at stage %s; run_log=%s",
            exc.request_id,
            exc.failed_stage,
            [event.model_dump() for event in exc.run_log],
        )
        return JSONResponse(
            status_code=500,
            content=exc.to_response().model_dump(mode="json"),
        )


@router.post("/users", response_model=UserRead, status_code=201)
def add_user(data: UserCreate, session: Session = Depends(_session)) -> UserRead:
    try:
        user = create_user(session, data)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail="该邮箱已存在") from exc
    return UserRead.model_validate(user)


@router.get("/users/{user_id}", response_model=UserRead)
def read_user(user_id: str, session: Session = Depends(_session)) -> UserRead:
    return UserRead.model_validate(_or_404(lambda: get_user(session, user_id)))


@router.post("/profiles", response_model=ProfileRead, status_code=201)
def add_profile(data: ProfileCreate, session: Session = Depends(_session)) -> ProfileRead:
    profile = _or_404(lambda: create_profile(session, data))
    return ProfileRead.model_validate(profile)


@router.get("/profiles/{profile_id}", response_model=ProfileRead)
def read_profile(profile_id: str, session: Session = Depends(_session)) -> ProfileRead:
    return ProfileRead.model_validate(_or_404(lambda: get_profile(session, profile_id)))


@router.post("/resumes", response_model=ResumeRead, status_code=201)
def add_resume(data: ResumeCreate, session: Session = Depends(_session)) -> ResumeRead:
    resume = _or_404(lambda: create_resume(session, data))
    return ResumeRead.model_validate(resume)


@router.get("/resumes/{resume_id}", response_model=ResumeRead)
def read_resume(resume_id: str, session: Session = Depends(_session)) -> ResumeRead:
    return ResumeRead.model_validate(_or_404(lambda: get_resume(session, resume_id)))


@router.post("/jobs", response_model=JobRead, status_code=201)
def add_job(data: JobCreate, session: Session = Depends(_session)) -> JobRead:
    return JobRead.model_validate(create_job(session, data))


@router.get("/jobs", response_model=list[JobRead])
def read_jobs(
    employment_type: EmploymentType | None = None,
    session: Session = Depends(_session),
) -> list[JobRead]:
    return [
        JobRead.model_validate(job)
        for job in list_jobs(session, employment_type=employment_type)
    ]


@router.get("/jobs/{job_id}", response_model=JobRead)
def read_job(job_id: str, session: Session = Depends(_session)) -> JobRead:
    return JobRead.model_validate(_or_404(lambda: get_job(session, job_id)))


@router.post("/job-matches", response_model=JobMatchRead, status_code=201)
def add_job_match(data: JobMatchCreate, session: Session = Depends(_session)) -> JobMatchRead:
    try:
        match = create_job_match(session, data)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConstraintRejectedError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "hard constraints not met",
                "rejections": exc.outcome.rejections,
                "unknowns": exc.outcome.unknowns,
            },
        ) from exc
    return JobMatchRead.model_validate(match)


@router.get("/job-matches/{match_id}", response_model=JobMatchRead)
def read_job_match(match_id: str, session: Session = Depends(_session)) -> JobMatchRead:
    return JobMatchRead.model_validate(_or_404(lambda: get_job_match(session, match_id)))


@router.get("/job-fit", response_model=list[JobFitAnalysisRead])
def read_job_fit_analyses(
    session: Session = Depends(_session),
) -> list[JobFitAnalysisRead]:
    return [
        JobFitAnalysisRead.model_validate(analysis)
        for analysis in list_job_fit_analyses(session)
    ]


@router.get("/job-fit/{request_id}", response_model=JobFitAnalysisRead)
def read_job_fit_analysis(
    request_id: str,
    session: Session = Depends(_session),
) -> JobFitAnalysisRead:
    return JobFitAnalysisRead.model_validate(
        _or_404(lambda: get_job_fit_analysis(session, request_id))
    )
