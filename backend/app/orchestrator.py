from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import TypeVar

from .agents import CareerAnalystAgent, ContentAgent, JobVerifierAgent
from .schemas import JobFitRequest, JobFitResponse, RunEvent


T = TypeVar("T")


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
        events: list[RunEvent],
        stage: str,
        operation: Callable[[], T],
    ) -> T:
        started = time.perf_counter()
        try:
            value = operation()
        except Exception as exc:
            events.append(
                RunEvent(
                    stage=stage,
                    status="failed",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
            raise

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
        events: list[RunEvent] = []
        verification = self._run_stage(
            events,
            self.verifier.name,
            lambda: self.verifier.run(request.job),
        )
        fit_report = self._run_stage(
            events,
            self.analyst.name,
            lambda: self.analyst.run(request.profile, request.job),
        )
        resume_suggestions, interview_questions = self._run_stage(
            events,
            self.content.name,
            lambda: self.content.run(request.job, fit_report),
        )

        warnings: list[str] = []
        if verification.status == "needs_review":
            warnings.append(
                "The job has no source URL; verify it manually before a real application decision."
            )
        if not request.profile.experiences:
            warnings.append("No experience was provided; analysis uses only summary and skills.")

        return JobFitResponse(
            request_id=uuid.uuid4().hex,
            job=verification,
            fit_report=fit_report,
            resume_suggestions=resume_suggestions,
            interview_questions=interview_questions,
            warnings=warnings,
            run_log=events,
        )
