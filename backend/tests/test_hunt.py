from __future__ import annotations

import unittest
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base
from backend.app.orchestrator import JobHuntOrchestrator
from backend.app.routers import run_job_hunt
from backend.app.schemas_hunt import JobHuntRequest
from backend.app.schemas_resources import (
    CapabilityProfile,
    JobCreate,
    ProfileCreate,
    UserCreate,
    UserRequirements,
)
from backend.app.schemas_search import JobQuery
from backend.app.services import (
    NotFoundError,
    create_job,
    create_profile,
    create_user,
)


class _FakeClient:
    """Replays scripted replies so the resume stage runs without a network."""

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        return self.replies.pop(0)


def _job(
    title: str,
    *,
    location: str | None = "北京",
    employment_type: str = "internship",
    requirements: str = "熟悉 Python",
    company: str = "Example",
) -> JobCreate:
    return JobCreate(
        title=title,
        company=company,
        description="负责相关业务开发",
        requirements=requirements,
        employment_type=employment_type,
        source_name="manual",
        location=location,
    )


class JobHuntPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )()

    def tearDown(self) -> None:
        self.session.close()

    def _profile(self):
        user = create_user(
            self.session,
            UserCreate(email="hunt@example.com", display_name="Hunter"),
        )
        return create_profile(
            self.session,
            ProfileCreate(
                user_id=user.id,
                requirements=UserRequirements(
                    desired_role="AI 实习生",
                    locations=["北京"],
                    employment_type="internship",
                ),
                capabilities=CapabilityProfile(
                    summary="计算机专业学生",
                    skills=["Python"],
                    target_roles=["AI 实习生"],
                ),
            ),
        )

    def test_pipeline_returns_candidates_matches_and_trace(self) -> None:
        profile = self._profile()
        job = create_job(self.session, _job("AI 实习生"))

        result = JobHuntOrchestrator().run(
            self.session, JobHuntRequest(profile_id=profile.id)
        )

        self.assertEqual([c.job_id for c in result.search.candidates], [job.id])
        self.assertEqual([match.job_id for match in result.matches], [job.id])
        self.assertEqual(result.skipped, [])
        self.assertEqual(
            [event.stage for event in result.run_log], ["job_hunter", "matching"]
        )
        self.assertIsNone(result.resume)

    def test_search_and_matching_may_disagree_and_the_run_says_so(self) -> None:
        profile = self._profile()
        shanghai = create_job(self.session, _job("AI 实习生", location="上海"))

        result = JobHuntOrchestrator().run(
            self.session,
            JobHuntRequest(
                profile_id=profile.id, query=JobQuery(locations=["上海"])
            ),
        )

        # Search follows the explicit query, matching follows the profile.
        self.assertEqual([c.job_id for c in result.search.candidates], [shanghai.id])
        self.assertEqual(result.matches, [])
        self.assertEqual(len(result.skipped), 1)
        self.assertIn("上海", result.skipped[0].reasons[0])
        self.assertTrue(any("skipped" in note for note in result.notes))

    def test_match_top_caps_how_many_pairs_are_scored(self) -> None:
        profile = self._profile()
        for index in range(3):
            create_job(self.session, _job(f"AI 实习生 {index}"))

        result = JobHuntOrchestrator().run(
            self.session, JobHuntRequest(profile_id=profile.id, match_top=1)
        )

        self.assertEqual(len(result.matches), 1)
        self.assertEqual(len(result.search.candidates), 3)

    def test_resume_stage_runs_only_when_asked(self) -> None:
        profile = self._profile()
        create_job(self.session, _job("AI 实习生"))
        client = _FakeClient(
            [
                {
                    "summary": "计算机专业学生，熟悉 Python。",
                    "experiences": [],
                    "skills": ["Python"],
                    "education": [],
                    "suggestions": [],
                }
            ]
        )

        result = JobHuntOrchestrator(client).run(
            self.session, JobHuntRequest(profile_id=profile.id, with_resume=True)
        )

        self.assertIsNotNone(result.resume)
        self.assertFalse(result.resume.degraded)
        self.assertIn("resume", [event.stage for event in result.run_log])

    def test_asking_for_a_resume_without_a_client_fails_loudly(self) -> None:
        profile = self._profile()

        with self.assertRaises(ValueError):
            JobHuntOrchestrator().run(
                self.session, JobHuntRequest(profile_id=profile.id, with_resume=True)
            )

    def test_missing_profile_is_reported_as_not_found(self) -> None:
        with self.assertRaises(NotFoundError):
            JobHuntOrchestrator().run(
                self.session, JobHuntRequest(profile_id="missing-profile")
            )

    def test_route_wires_the_pipeline(self) -> None:
        profile = self._profile()
        job = create_job(self.session, _job("AI 实习生"))

        result = run_job_hunt(
            JobHuntRequest(profile_id=profile.id), session=self.session
        )

        self.assertEqual(result.profile_id, profile.id)
        self.assertEqual([match.job_id for match in result.matches], [job.id])


if __name__ == "__main__":
    unittest.main()
