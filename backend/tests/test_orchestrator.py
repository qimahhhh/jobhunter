from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import main as api
from backend.app.models import Base
from backend.app.orchestrator import JobFitOrchestrator, JobFitRunError
from backend.app.schemas import JobFitRequest, JobInput, ProfileInput, RunEvent
from backend.app.services import get_job_fit_analysis


class FailingAnalystAgent:
    name = "career_analyst"

    def run(self, profile: ProfileInput, job: JobInput):
        raise RuntimeError("analysis backend timed out")


def make_request() -> JobFitRequest:
    return JobFitRequest(
        profile=ProfileInput(
            summary="Python student with FastAPI and PostgreSQL project experience",
            skills=["Python", "FastAPI", "SQL"],
            experiences=["Built a job tracking API"],
        ),
        job=JobInput(
            title="AI Application Intern",
            company="Example Company",
            description="Build AI-assisted workflows.",
            requirements="Python, FastAPI, SQL, communication",
            employment_type="internship",
            source_name="manual-check",
            source_url="https://example.com/jobs/1",
        ),
    )


class JobFitOrchestratorTest(unittest.TestCase):
    def test_runs_all_stages_and_returns_traceable_report(self) -> None:
        response = JobFitOrchestrator().run(make_request())

        self.assertEqual(response.job.status, "source_attached")
        self.assertGreaterEqual(len(response.fit_report.match_points), 1)
        self.assertGreaterEqual(len(response.resume_suggestions), 1)
        self.assertEqual(len(response.interview_questions), 3)
        self.assertEqual([event.status for event in response.run_log], ["ok", "ok", "ok"])
        self.assertTrue(response.request_id)
        self.assertGreaterEqual(response.fit_report.score, 0)
        self.assertLessEqual(response.fit_report.score, 1)

    def test_api_persists_successful_analysis(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

        response = api.job_fit(make_request(), session=session)
        analysis = get_job_fit_analysis(session, response.request_id)

        self.assertEqual(analysis.result["request_id"], response.request_id)
        self.assertEqual(analysis.result["fit_report"]["score"], response.fit_report.score)
        session.close()

    def test_failed_stage_preserves_run_log(self) -> None:
        orchestrator = JobFitOrchestrator(analyst=FailingAnalystAgent())

        with self.assertRaises(JobFitRunError) as context:
            orchestrator.run(make_request())

        error = context.exception
        self.assertEqual(error.failed_stage, "career_analyst")
        self.assertEqual(error.error_type, "RuntimeError")
        self.assertEqual(error.message, "analysis backend timed out")
        self.assertEqual([event.status for event in error.run_log], ["ok", "failed"])
        self.assertEqual(error.run_log[-1].stage, "career_analyst")
        self.assertIn("RuntimeError", error.run_log[-1].detail)
        self.assertTrue(error.request_id)

    def test_api_failure_returns_run_log_and_keeps_server_trace(self) -> None:
        failure = JobFitRunError(
            request_id="request-123",
            run_log=[
                RunEvent(
                    stage="job_verifier",
                    status="ok",
                    duration_ms=1,
                    detail="completed",
                ),
                RunEvent(
                    stage="career_analyst",
                    status="failed",
                    duration_ms=2,
                    detail="RuntimeError: analysis backend timed out",
                ),
            ],
            failed_stage="career_analyst",
            error_type="RuntimeError",
            message="analysis backend timed out",
        )

        with patch.object(api.orchestrator, "run", side_effect=failure):
            with self.assertLogs("backend.app.main", level="ERROR") as logs:
                response = api.job_fit(make_request(), session=None)

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(body["request_id"], "request-123")
        self.assertEqual(body["failed_stage"], "career_analyst")
        self.assertEqual([event["status"] for event in body["run_log"]], ["ok", "failed"])
        self.assertIsNotNone(logs.records[0].exc_info)
        self.assertIn("career_analyst", logs.records[0].getMessage())


if __name__ == "__main__":
    unittest.main()
