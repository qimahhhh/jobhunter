from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .chunking import blocks_from_docx, blocks_from_pdf
from .db import get_session
from .extraction_service import ResumeExtractionService
from .job_sources import SourceConfigError, SourceUnavailableError
from .llm import DeepSeekClient, LLMClient, LLMError
from .orchestrator import JobFitOrchestrator, JobFitRunError, JobHuntOrchestrator
from .schemas import (
    EmploymentType,
    JobFitFailureResponse,
    JobFitRequest,
    JobFitResponse,
    JobStatus,
    ResumeDraftRequest,
    ResumeDraftResponse,
    ResumeExtractionRequest,
    ResumeExtractionResponse,
    ResumeSourceBundleRequest,
)
from .schemas_hunt import JobHuntRequest, JobHuntResponse
from .schemas_resources import (
    CapabilityProfile,
    JobCreate,
    JobFitAnalysisRead,
    JobMatchCreate,
    JobMatchRead,
    JobRead,
    ProfileConfirmationRequest,
    ProfileCreate,
    ProfileRead,
    ResumeCreate,
    ResumeRead,
    UserCreate,
    UserRead,
    JobVerificationRequest,
    JobVerificationResponse,
    JobProbeRequest,
    JobProbeResponse,
    JobExpiryRequest,
    JobExpiryResponse,
)
from .schemas_search import (
    JobCollectRequest,
    JobCollectResponse,
    JobIngestRequest,
    JobIngestResponse,
    JobSearchRequest,
    JobSearchResponse,
)
from .services import (
    ConflictError,
    ConstraintRejectedError,
    NotFoundError,
    collect_jobs,
    create_job,
    create_job_fit_analysis,
    create_job_match,
    create_profile,
    create_resume,
    create_user,
    draft_resume_for_profile,
    expire_stale_jobs,
    get_job,
    get_job_fit_analysis,
    get_job_match,
    get_profile,
    get_resume,
    get_user,
    ingest_jobs,
    list_job_fit_analyses,
    list_jobs,
    probe_jobs,
    search_jobs,
    verify_jobs,
)


logger = logging.getLogger(__name__)

router = APIRouter()
health_router = APIRouter(tags=["Health"])
orchestrator = JobFitOrchestrator()
_llm_client: LLMClient | None = None


def _client() -> LLMClient:
    """Build the model client on first use.

    Keeping it lazy means the API still starts and serves every other route
    when no key is configured; the failure shows up as a 503 on the one endpoint
    that actually needs a model.
    """

    global _llm_client
    if _llm_client is None:
        _llm_client = DeepSeekClient()
    return _llm_client


def _llm_or_503() -> LLMClient:
    """A client, or the 503 that says this deployment has no key."""

    try:
        return _client()
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
    """Create the user's profile, or update the one they already have."""

    profile = _or_404(lambda: create_profile(session, data))
    return ProfileRead.model_validate(profile)


@router.get("/profiles/{profile_id}", response_model=ProfileRead)
def read_profile(profile_id: str, session: Session = Depends(_session)) -> ProfileRead:
    return ProfileRead.model_validate(_or_404(lambda: get_profile(session, profile_id)))


@router.post(
    "/profiles/extract",
    response_model=ResumeExtractionResponse,
    responses={503: {"description": "model client is not configured"}},
)
def extract_profile_from_resume(
    data: ResumeExtractionRequest,
    session: Session = Depends(_session),
) -> ResumeExtractionResponse:
    """Chunk resume text and let the model draft a profile from it.

    The draft is not persisted here: it comes back with the chunk ids it cited
    so a human can check it before confirming through
    ``POST /profiles/extract/confirm``. Passing ``user_id`` stores the parsed
    chunks as a resume record, which is what makes those ids resolvable later.
    """

    service = ResumeExtractionService(session, _llm_or_503())
    return _or_404(lambda: service.from_text(data))


_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


async def _read_upload(request: Request) -> bytes:
    """Read the request body, refusing anything past the size limit early."""

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"简历文件不能超过 {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
            )
    return bytes(body)


@router.post(
    "/profiles/extract/file",
    response_model=ResumeExtractionResponse,
    responses={
        400: {"description": "the uploaded file cannot be parsed"},
        413: {"description": "the uploaded file is too large"},
        415: {"description": "only .pdf and .docx resumes are supported"},
        503: {"description": "model client is not configured"},
    },
)
async def extract_profile_from_upload(
    request: Request,
    filename: str = Query(min_length=1),
    user_id: str | None = Query(default=None),
    max_chunk_tokens: int = Query(default=900, ge=50, le=4000),
    session: Session = Depends(_session),
) -> ResumeExtractionResponse:
    """Parse an uploaded resume and let the model draft a profile from it.

    The body is the raw file bytes and ``filename`` carries the extension that
    picks the parser, so a client uploads with one ``fetch`` and the server
    needs no multipart support. The draft itself is not stored: it comes back
    with the chunk ids it cited so a human can check it before confirming
    through ``POST /profiles/extract/confirm``. Passing ``user_id`` stores the
    parsed chunks as a resume record first, so those ids stay resolvable.
    """

    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        parse = blocks_from_pdf
    elif suffix == ".docx":
        parse = blocks_from_docx
    else:
        raise HTTPException(
            status_code=415,
            detail=f"只支持 .pdf / .docx 简历文件，收到：{filename}",
        )

    # Resolve the user before reading the body: an unknown id should not cost a
    # 20MB buffer and a PDF parse before it fails.
    if user_id:
        _or_404(lambda: get_user(session, user_id))

    content = await _read_upload(request)
    if not content:
        raise HTTPException(status_code=400, detail="简历文件是空的")

    try:
        blocks = await run_in_threadpool(parse, BytesIO(content))
    except RuntimeError as exc:  # the optional parser dependency is missing
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"简历文件解析失败：{exc}") from exc

    service = ResumeExtractionService(session, _llm_or_503())

    # The chunk writes and one model turn are both blocking. The route is async
    # only because the body is streamed, so the whole use case goes to the
    # thread pool: otherwise one 5s extraction stalls every other request.
    try:
        return await run_in_threadpool(
            service.from_blocks,
            blocks,
            user_id=user_id,
            source_type=suffix.lstrip("."),
            source_name=filename,
            max_chunk_tokens=max_chunk_tokens,
        )
    except NotFoundError as exc:
        # The user was resolved before the body was read; this covers the case
        # where the row disappears while a large upload is in flight.
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/profiles/extract/bundle",
    response_model=ResumeExtractionResponse,
    responses={
        422: {"description": "no source was provided"},
        503: {"description": "model client is not configured"},
    },
)
def extract_profile_from_bundle(
    data: ResumeSourceBundleRequest,
    session: Session = Depends(_session),
) -> ResumeExtractionResponse:
    """Draft a profile from resume text, a self description and projects.

    All three inputs are optional and at least one is required. They are merged
    before chunking, so a citation still names the source it came from and the
    difference between "I interned there" and "my project used that" survives
    into the draft.
    """

    service = ResumeExtractionService(session, _llm_or_503())
    return _or_404(lambda: service.from_bundle(data))


@router.post(
    "/profiles/extract/confirm",
    response_model=ProfileRead,
    status_code=201,
    responses={404: {"description": "the referenced user does not exist"}},
)
def confirm_extracted_profile(
    data: ProfileConfirmationRequest, session: Session = Depends(_session)
) -> ProfileRead:
    """Save a reviewed extraction draft as the user's profile.

    This is the human-in-the-loop confirmation node of profile building: the
    draft that ``/profiles/extract`` returned comes back here after the user
    checked and edited it, and only then does it become a persisted profile.

    The two role lists are kept apart. ``recommended_roles`` stay as
    ``suggested_roles``; ``target_roles`` is what the user left in the form, and
    when they omit it the suggestions are copied but marked ``suggested``, so a
    direction nobody agreed to is never displayed as a decision.
    """

    suggestions = [role.strip() for role in data.recommended_roles if role.strip()]
    if data.target_roles is None:
        confirmed = list(suggestions)
        source = "suggested"
    else:
        confirmed = [role.strip() for role in data.target_roles if role.strip()]
        source = "confirmed"

    payload = ProfileCreate(
        user_id=data.user_id,
        requirements=data.requirements,
        capabilities=CapabilityProfile(
            summary=data.profile.summary,
            skills=data.profile.skills,
            experiences=data.profile.experiences,
            target_roles=confirmed,
            suggested_roles=suggestions,
            target_roles_source=source,
        ),
        missing_information=[
            item.strip() for item in data.missing_information if item.strip()
        ],
        evidence=[ref.strip() for ref in data.evidence if ref.strip()],
        source_resume_id=data.resume_id,
    )
    profile = _or_404(lambda: create_profile(session, payload))
    return ProfileRead.model_validate(profile)


@router.post(
    "/resumes/draft",
    response_model=ResumeDraftResponse,
    responses={
        404: {"description": "the profile or its source resume does not exist"},
        503: {"description": "model client is not configured"},
    },
)
def draft_base_resume(
    data: ResumeDraftRequest,
    session: Session = Depends(_session),
) -> ResumeDraftResponse:
    """Draft a base resume from a stored profile, without a job description.

    This is the "how do I say what I did" step: the material is the profile plus
    the chunks saved when it was extracted, so a rewritten bullet can still be
    traced back to the paragraph it came from. Tailoring to a posting is a
    separate step that adds a job to the same pipeline.
    """

    profile = _or_404(lambda: get_profile(session, data.profile_id))
    return draft_resume_for_profile(
        session, profile, _llm_or_503(), data.max_chunk_tokens
    )


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
    verification_status: JobStatus | None = None,
    session: Session = Depends(_session),
) -> list[JobRead]:
    return [
        JobRead.model_validate(job)
        for job in list_jobs(
            session,
            employment_type=employment_type,
            verification_status=verification_status,
        )
    ]


@router.post("/jobs/ingest", response_model=JobIngestResponse, status_code=201)
def ingest_job_batch(
    data: JobIngestRequest, session: Session = Depends(_session)
) -> JobIngestResponse:
    """Store a collector's batch and report what was new.

    Idempotent on purpose: running the same collection twice must not double the
    job list. A posting that reappears is the same row with a fresh
    ``last_seen_at``, which is what later tells an active posting from an
    expired one.
    """

    return ingest_jobs(session, data)


@router.post(
    "/jobs/collect",
    response_model=JobCollectResponse,
    status_code=201,
    responses={
        502: {"description": "job source is unavailable"},
        503: {"description": "job source is not configured"},
    },
)
def collect_job_batch(
    data: JobCollectRequest, session: Session = Depends(_session)
) -> JobCollectResponse:
    """Pull the newest postings from the live source and merge them in.

    Collection is user-triggered: this is the fetching step behind
    ``/jobs/ingest``, not a background crawler. Failures are named instead of
    swallowed, because "the search found nothing" and "the source was
    unreachable" are different answers. The source license forbids bulk
    storage, so the stored rows carry facts and a link back to the notice,
    never the notice text itself.
    """

    try:
        return collect_jobs(session, data)
    except SourceConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SourceUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/jobs/verify",
    response_model=JobVerificationResponse,
)
def verify_job_statuses(
    data: JobVerificationRequest, session: Session = Depends(_session)
) -> JobVerificationResponse:
    """Record human verdicts on whether postings are still open.

    The step the plan calls "don't turn 'found a job' into 'still hiring'": a
    posting is only ``active`` because someone looked at it, and the moment
    they looked is stored with it. Reverting to ``pending_verification``
    withdraws the claim and clears the date.
    """

    return verify_jobs(session, data)


@router.post("/jobs/probe", response_model=JobProbeResponse)
def probe_job_sources(
    data: JobProbeRequest, session: Session = Depends(_session)
) -> JobProbeResponse:
    """Check stored postings against the pages they were collected from.

    The machine can only downgrade: a 404 or an 已截止 marker closes a posting,
    while a page that still loads proves nothing about hiring and therefore
    changes no status. Every check records ``last_checked_at``, which is kept
    separate from ``last_verified_at`` so "a machine looked" and "a person
    confirmed" never get confused.
    """

    return probe_jobs(session, data)


@router.post("/jobs/expire-stale", response_model=JobExpiryResponse)
def expire_stale_postings(
    data: JobExpiryRequest, session: Session = Depends(_session)
) -> JobExpiryResponse:
    """Stop recommending postings no collection has returned for a while.

    Marked expired rather than deleted, and reversible: if the source publishes
    the posting again the collector puts it back to pending for a fresh look.
    """

    return expire_stale_jobs(session, data)


@router.post("/job-search", response_model=JobSearchResponse)
def run_job_search(
    data: JobSearchRequest, session: Session = Depends(_session)
) -> JobSearchResponse:
    """Rank stored postings for a query, optionally seeded from a profile.

    Exclusions are part of the answer: a job that is missing because it is in
    another city is a different outcome from a job that was never collected,
    and only the first one can be explained to the user.
    """

    return _or_404(lambda: search_jobs(session, data))


@router.post("/job-hunt", response_model=JobHuntResponse)
def run_job_hunt(
    data: JobHuntRequest, session: Session = Depends(_session)
) -> JobHuntResponse:
    """Search, match and optionally draft a resume in one request.

    The chain exists so nobody has to hand-carry ids between three calls: the
    candidates of ``/job-search`` are matched here, and the matches are the jobs
    the user would pick from. A candidate that search keeps but matching refuses
    comes back in ``skipped`` with its reason, so the two steps disagreeing is
    visible instead of looking like a bug.

    ``with_resume`` costs one model call, so the client is only built when the
    caller asks for it: a deployment without a key still serves the pipeline.
    """

    client = _llm_or_503() if data.with_resume else None
    return _or_404(lambda: JobHuntOrchestrator(client).run(session, data))


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
