from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base
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
                score=0.8,
                match_points=["Python"],
                gaps=["SQL"],
                recommendation="Prepare evidence",
                confidence=0.7,
            ),
        )

        self.assertEqual(get_job_match(self.session, match.id).score, 0.8)
        self.assertEqual(resume.version, 1)
        self.assertEqual(job.verification_status, "source_attached")
        self.assertEqual(UserRead.model_validate(user).email, "student@example.com")
        self.assertEqual(JobMatchRead.model_validate(match).score, 0.8)


if __name__ == "__main__":
    unittest.main()
