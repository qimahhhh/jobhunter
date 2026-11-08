from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

from .agents import CareerAnalystAgent, ContentAgent, JobVerifierAgent
from .llm import LLMClient
from .schemas import (
    JobFitFailureResponse,
    JobFitRequest,
    JobFitResponse,
    RunEvent,
)
from .schemas_hunt import JobHuntRequest, JobHuntResponse, JobHuntSkip
from .schemas_resources import JobMatchCreate, JobMatchRead
from .schemas_search import JobSearchRequest
from .services import (
    ConstraintRejectedError,
    NotFoundError,
    create_job_match,
    draft_resume_for_profile,
    get_profile,
    search_jobs,
)


T = TypeVar("T")


def _stage(name: str, started: float, detail: str) -> RunEvent:
    """A completed stage, timed. Failures propagate instead of being logged.

    ``JobFitOrchestrator`` keeps a failure log because it owns the failure
    response. Here a failure is either a 4xx the caller already understands or
    a bug; in both cases returning a half-filled pipeline would be worse than
    raising.
    """

    return RunEvent(
        stage=name,
        status="ok",
        duration_ms=int((time.perf_counter() - started) * 1000),
        detail=detail,
    )


class JobFitRunError(RuntimeError):
    def __init__(
        self,
        request_id: str,
        run_log: list[RunEvent],
        failed_stage: str,
        error_type: str,
        message: str,
    ) -> None:
        self.request_id = request_id
        self.run_log = run_log.copy()
        self.failed_stage = failed_stage
        self.error_type = error_type
        self.message = message
        super().__init__(f"{failed_stage} failed: {error_type}: {message}")

    def to_response(self) -> JobFitFailureResponse:
        return JobFitFailureResponse(
            request_id=self.request_id,
            status="failed",
            failed_stage=self.failed_stage,
            error_type=self.error_type,
            message=self.message,
            run_log=self.run_log,
        )


class JobFitOrchestrator:
    def __init__(
        self,
        verifier: JobVerifierAgent | None = None,
        analyst: CareerAnalystAgent | None = None,
        content: ContentAgent | None = None,
    ) -> None:
        self.verifier = verifier or JobVerifierAgent()
        self.analyst = analyst or CareerAnalystAgent()
        self.content = content or ContentAgent()

    def _run_stage(
        self,
        request_id: str,
        events: list[RunEvent],
        stage: str,
        operation: Callable[[], T],
    ) -> T:
        started = time.perf_counter()
        try:
            value = operation()
        except Exception as exc:
            error_type = type(exc).__name__
            message = str(exc)
            events.append(
                RunEvent(
                    stage=stage,
                    status="failed",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    detail=f"{error_type}: {message}",
                )
            )
            raise JobFitRunError(
                request_id=request_id,
                run_log=events,
                failed_stage=stage,
                error_type=error_type,
                message=message,
            ) from exc

        events.append(
            RunEvent(
                stage=stage,
                status="ok",
                duration_ms=int((time.perf_counter() - started) * 1000),
                detail="completed",
            )
        )
        return value

    def run(self, request: JobFitRequest) -> JobFitResponse:
        request_id = uuid.uuid4().hex
        events: list[RunEvent] = []
        verification = self._run_stage(
            request_id,
            events,
            self.verifier.name,
            lambda: self.verifier.run(request.job),
        )
        fit_report = self._run_stage(
            request_id,
            events,
            self.analyst.name,
            lambda: self.analyst.run(request.profile, request.job),
        )
        resume_suggestions, interview_questions = self._run_stage(
            request_id,
            events,
            self.content.name,
            lambda: self.content.run(request.job, fit_report),
        )

        warnings: list[str] = []
        if verification.status == "unknown":
            warnings.append(
                "No source URL was provided; this posting cannot be verified before applying."
            )
        elif verification.status == "pending_verification":
            warnings.append(
                "A source URL is attached but the posting has not been verified yet."
            )
        if not request.profile.experiences:
            warnings.append("No experience was provided; analysis uses only summary and skills.")

        return JobFitResponse(
            request_id=request_id,
            job=verification,
            fit_report=fit_report,
            resume_suggestions=resume_suggestions,
            interview_questions=interview_questions,
            warnings=warnings,
            run_log=events,
        )


class JobHuntOrchestrator:
    """Search → match → optional base resume, in one request.

    Nothing new is computed here: every stage is an existing service. The value
    is that the output of one stage is exactly the input of the next, and that
    the two constraint sets are allowed to disagree. Search filters by the
    query, matching filters by the profile's hard constraints, so a candidate
    that survives search can still be refused by matching; that refusal is
    reported per job in ``skipped`` instead of failing the run or vanishing.

    ``client`` is only needed for the resume stage. Passing ``None`` keeps the
    pipeline runnable on a deployment without a model key, and asking for a
    resume in that state fails loudly rather than returning a silently empty
    ``resume``.
    """

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client

    def run(self, session: Session, request: JobHuntRequest) -> JobHuntResponse:
        events: list[RunEvent] = []
        notes: list[str] = []

        started = time.perf_counter()
        search = search_jobs(
            session,
            JobSearchRequest(query=request.query, profile_id=request.profile_id),
        )
        events.append(_stage("job_hunter", started, f"{len(search.candidates)} 个候选"))
        notes.extend(search.notes)

        started = time.perf_counter()
        matches: list[JobMatchRead] = []
        skipped: list[JobHuntSkip] = []
        for candidate in search.candidates[: request.match_top]:
            try:
                match = create_job_match(
                    session,
                    JobMatchCreate(
                        user_profile_id=request.profile_id,
                        job_id=candidate.job_id,
                    ),
                )
            except ConstraintRejectedError as exc:
                skipped.append(
                    JobHuntSkip(
                        job_id=candidate.job_id,
                        title=candidate.title,
                        reasons=[*exc.outcome.rejections, *exc.outcome.unknowns],
                    )
                )
                continue
            except NotFoundError:
                # The job disappeared between the search and this loop.
                skipped.append(
                    JobHuntSkip(
                        job_id=candidate.job_id,
                        title=candidate.title,
                        reasons=["岗位在检索之后被移除"],
                    )
                )
                continue
            matches.append(JobMatchRead.model_validate(match))

        events.append(
            _stage(
                "matching",
                started,
                f"匹配 {len(matches)} 条，跳过 {len(skipped)} 条",
            )
        )
        if skipped:
            notes.append(
                "skipped 里的候选通过了检索条件，但没过画像的硬约束："
                "检索按查询、匹配按画像，两者可以不一致。"
            )

        resume = None
        if request.with_resume:
            if self.client is None:
                raise ValueError(
                    "with_resume 需要模型客户端：调用方应先取得它，而不是生成一份空简历"
                )
            started = time.perf_counter()
            profile = get_profile(session, request.profile_id)
            resume = draft_resume_for_profile(
                session, profile, self.client, request.max_chunk_tokens
            )
            events.append(_stage("resume", started, f"degraded={resume.degraded}"))

        return JobHuntResponse(
            profile_id=request.profile_id,
            search=search,
            matches=matches,
            skipped=skipped,
            resume=resume,
            run_log=events,
            notes=notes,
        )
