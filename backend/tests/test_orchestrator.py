from __future__ import annotations

import unittest

from backend.app.orchestrator import JobFitOrchestrator
from backend.app.schemas import JobFitRequest, JobInput, ProfileInput


class JobFitOrchestratorTest(unittest.TestCase):
    def test_runs_all_stages_and_returns_traceable_report(self) -> None:
        request = JobFitRequest(
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
                source_name="manual-check",
                source_url="https://example.com/jobs/1",
            ),
        )

        response = JobFitOrchestrator().run(request)

        self.assertEqual(response.job.status, "source_attached")
        self.assertGreaterEqual(len(response.fit_report.match_points), 1)
        self.assertGreaterEqual(len(response.resume_suggestions), 1)
        self.assertEqual(len(response.interview_questions), 3)
        self.assertEqual([event.status for event in response.run_log], ["ok", "ok", "ok"])
        self.assertTrue(response.request_id)


if __name__ == "__main__":
    unittest.main()
