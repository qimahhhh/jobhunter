from __future__ import annotations

import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base
from backend.app.routers import add_user
from backend.app.schemas_resources import (
    CapabilityProfile,
    JobCreate,
    JobMatchCreate,
    JobMatchRead,
    ProfileCreate,
    ResumeCreate,
    UserCreate,
    UserRead,
    UserRequirements,
)
from backend.app.services import (
    create_job,
    create_job_match,
    create_profile,
    create_resume,
    create_user,
    get_job_match,
)


class ResourceModelsTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    def tearDown(self) -> None:
        self.session.close()

    def test_creates_user_profile_resume_job_and_match(self) -> None:
        user = create_user(
            self.session,
            UserCreate(email="student@example.com", display_name="Student"),
        )
        profile = create_profile(
            self.session,
            ProfileCreate(
                user_id=user.id,
                requirements=UserRequirements(desired_role="AI Intern"),
                capabilities=CapabilityProfile(
                    summary="Python student",
                    skills=["Python", "FastAPI"],
                    experiences=["Built an API"],
                ),
            ),
        )
        resume = create_resume(
            self.session,
            ResumeCreate(
                user_id=user.id,
                source_name="student-resume",
                content={"summary": "Python student"},
            ),
        )
        job = create_job(
            self.session,
            JobCreate(
                title="AI Intern",
                company="Example",
                description="AI workflows",
                requirements="Python",
                source_name="manual",
                source_url="https://example.com/jobs/1",
            ),
        )
        match = create_job_match(
            self.session,
            JobMatchCreate(
                user_profile_id=profile.id,
                job_id=job.id,
            ),
        )

        self.assertEqual(get_job_match(self.session, match.id).score, 1.0)
        self.assertEqual(match.match_points, ["python"])
        self.assertEqual(match.gaps, [])
        self.assertTrue(match.recommendation)
        self.assertEqual(resume.version, 1)
        self.assertEqual(job.verification_status, "source_attached")
        self.assertEqual(UserRead.model_validate(user).email, "student@example.com")
        self.assertEqual(JobMatchRead.model_validate(match).score, 1.0)

    def test_duplicate_email_returns_conflict_and_keeps_session_usable(self) -> None:
        data = UserCreate(email="duplicate@example.com", display_name="Student")
        add_user(data, session=self.session)

        with self.assertRaises(HTTPException) as context:
            add_user(data, session=self.session)

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(context.exception.detail, "该邮箱已存在")
        create_user(
            self.session,
            UserCreate(email="another@example.com", display_name="Another"),
        )

    def test_job_match_does_not_accept_client_generated_results(self) -> None:
        with self.assertRaises(ValidationError):
            JobMatchCreate.model_validate(
                {
                    "user_profile_id": "profile-id",
                    "job_id": "job-id",
                    "score": 0.99,
                    "gaps": ["client-supplied"],
                    "recommendation": "client-supplied",
                }
            )


if __name__ == "__main__":
    unittest.main()
