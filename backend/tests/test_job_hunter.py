from __future__ import annotations

import unittest
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.job_hunter import JobHunterAgent, dedupe_key
from backend.app.models import Base, Job, utc_now
from backend.app.routers import run_job_search
from backend.app.schemas_resources import (
    CapabilityProfile,
    JobCreate,
    ProfileCreate,
    UserCreate,
    UserRequirements,
)
from backend.app.schemas_search import JobIngestRequest, JobQuery, JobSearchRequest
from backend.app.services import (
    create_job,
    create_profile,
    create_user,
    ingest_jobs,
    list_jobs,
    search_jobs,
)


def _job(
    title: str,
    *,
    company: str = "Example",
    requirements: str = "Python",
    location: str | None = "北京",
    employment_type: str = "internship",
    source_name: str = "manual",
) -> JobCreate:
    return JobCreate(
        title=title,
        company=company,
        description="负责相关业务开发",
        requirements=requirements,
        employment_type=employment_type,
        source_name=source_name,
        location=location,
    )


class JobHunterTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )()

    def tearDown(self) -> None:
        self.session.close()

    def test_dedupe_key_folds_spacing_case_and_punctuation(self) -> None:
        self.assertEqual(
            dedupe_key(title="AI  Intern", company="Example"),
            dedupe_key(title="ai-intern", company=" EXAMPLE "),
        )
        # Same title, same company, another city: two postings, not a duplicate.
        self.assertNotEqual(
            dedupe_key(title="AI Intern", company="Example", location="北京"),
            dedupe_key(title="AI Intern", company="Example", location="上海"),
        )

    def test_search_ranks_title_hits_above_body_hits(self) -> None:
        title_hit = create_job(self.session, _job("Python 开发实习生"))
        body_hit = create_job(
            self.session, _job("后端实习生", requirements="熟悉 Python")
        )

        result = JobHunterAgent().run(
            [title_hit, body_hit], JobQuery(keywords=["Python"])
        )

        self.assertEqual(
            [candidate.job_id for candidate in result.candidates],
            [title_hit.id, body_hit.id],
        )
        self.assertEqual(result.candidates[0].score, 1.0)
        self.assertEqual(result.candidates[1].score, 0.5)
        self.assertEqual(result.candidates[0].matched, ["python"])

    def test_postings_without_any_keyword_overlap_are_dropped_with_a_reason(self) -> None:
        create_job(self.session, _job("Python 开发实习生"))
        create_job(self.session, _job("市场专员", requirements="线下活动执行"))

        result = JobHunterAgent().run(list_jobs(self.session), JobQuery(keywords=["Python"]))

        self.assertEqual([c.title for c in result.candidates], ["Python 开发实习生"])
        self.assertEqual(len(result.excluded), 1)
        self.assertIn("没有重合", result.excluded[0].reasons[0])

    def test_hard_constraint_violation_is_excluded_with_the_reason(self) -> None:
        full_time = create_job(
            self.session, _job("AI 工程师", employment_type="full_time")
        )

        result = JobHunterAgent().run(
            [full_time], JobQuery(employment_type="internship")
        )

        self.assertEqual(result.candidates, [])
        self.assertEqual(len(result.excluded), 1)
        self.assertIn("正式", result.excluded[0].reasons[0])

    def test_missing_field_is_a_warning_not_a_rejection(self) -> None:
        job = create_job(self.session, _job("AI 实习生", location=None))

        result = JobHunterAgent().run([job], JobQuery(locations=["北京"]))

        self.assertEqual(len(result.candidates), 1)
        self.assertTrue(result.candidates[0].warnings)
        self.assertIn("地点", result.candidates[0].warnings[0])

    def test_unmeasurable_query_keeps_jobs_and_says_so(self) -> None:
        older = create_job(self.session, _job("AI 实习生"))
        newer = create_job(self.session, _job("后端实习生", company="Other"))
        older.collected_at = utc_now() - timedelta(hours=2)
        self.session.commit()

        result = JobHunterAgent().run([older, newer], JobQuery())

        self.assertEqual(
            [candidate.job_id for candidate in result.candidates],
            [newer.id, older.id],
        )
        self.assertTrue(all(candidate.score == 0.0 for candidate in result.candidates))
        self.assertTrue(result.notes)

    def test_limit_caps_the_shortlist(self) -> None:
        for index in range(3):
            create_job(self.session, _job(f"Python 实习生 {index}"))

        result = search_jobs(
            self.session, JobSearchRequest(query=JobQuery(keywords=["Python"], limit=2))
        )

        self.assertEqual(len(result.candidates), 2)
        self.assertEqual(result.total_scanned, 3)

    def test_ingesting_the_same_batch_twice_does_not_duplicate(self) -> None:
        batch = JobIngestRequest(jobs=[_job("AI 实习生"), _job("Python 开发实习生")])

        first = ingest_jobs(self.session, batch)
        created_id = first.created[0]
        # Reload from the database: a value still in the identity map is the
        # aware datetime we wrote, while a stored one comes back naive. Comparing
        # the two is a TypeError, and it is the storage that matters here.
        self.session.expire_all()
        first_seen = self.session.get(Job, created_id).last_seen_at

        second = ingest_jobs(self.session, batch)
        self.session.expire_all()
        refreshed = self.session.get(Job, created_id)
        jobs = list_jobs(self.session)

        self.assertEqual((len(first.created), len(first.updated)), (2, 0))
        self.assertEqual((len(second.created), len(second.updated)), (0, 2))
        self.assertEqual(len(jobs), 2)
        self.assertGreaterEqual(refreshed.last_seen_at, first_seen)

    def test_reingest_refreshes_the_facts_but_keeps_the_first_source(self) -> None:
        ingest_jobs(
            self.session,
            JobIngestRequest(
                jobs=[
                    JobCreate(
                        title="AI 实习生",
                        company="Example",
                        description="旧描述",
                        requirements="Python",
                        employment_type="internship",
                        source_name="source-a",
                        location="北京",
                    )
                ]
            ),
        )
        ingest_jobs(
            self.session,
            JobIngestRequest(
                jobs=[
                    JobCreate(
                        title="AI 实习生",
                        company="Example",
                        description="新描述",
                        requirements="Python、PyTorch",
                        employment_type="internship",
                        source_name="source-b",
                        location="北京",
                        salary_min=200,
                        salary_period="day",
                    )
                ]
            ),
        )

        job = list_jobs(self.session)[0]
        self.assertEqual(job.description, "新描述")
        self.assertEqual(job.requirements, "Python、PyTorch")
        self.assertEqual(job.salary_min, 200)
        # Provenance is where it was first verified, not the latest mirror.
        self.assertEqual(job.source_name, "source-a")

    def test_profile_seeds_the_query_without_overriding_explicit_input(self) -> None:
        user = create_user(
            self.session,
            UserCreate(email="hunter@example.com", display_name="Hunter"),
        )
        profile = create_profile(
            self.session,
            ProfileCreate(
                user_id=user.id,
                requirements=UserRequirements(
                    desired_role="算法实习生",
                    locations=["北京"],
                    employment_type="internship",
                ),
                capabilities=CapabilityProfile(
                    summary="计算机专业学生",
                    skills=["Python", "PyTorch"],
                    target_roles=["算法实习生"],
                ),
            ),
        )
        beijing = create_job(
            self.session, _job("算法实习生", requirements="熟悉 Python 与 PyTorch")
        )
        shanghai = create_job(self.session, _job("算法实习生", location="上海"))

        result = run_job_search(
            JobSearchRequest(profile_id=profile.id), session=self.session
        )

        self.assertEqual(result.applied_profile_id, profile.id)
        self.assertEqual([c.job_id for c in result.candidates], [beijing.id])
        self.assertEqual(
            [exclusion.job_id for exclusion in result.excluded], [shanghai.id]
        )
        self.assertEqual(result.query.role, "算法实习生")
        self.assertEqual(result.query.keywords, ["Python", "PyTorch"])
        self.assertTrue(result.notes)

    def test_explicit_query_wins_over_the_profile(self) -> None:
        user = create_user(
            self.session,
            UserCreate(email="explicit@example.com", display_name="Explicit"),
        )
        profile = create_profile(
            self.session,
            ProfileCreate(
                user_id=user.id,
                requirements=UserRequirements(
                    desired_role="算法实习生", locations=["北京"]
                ),
                capabilities=CapabilityProfile(summary="学生", skills=["Python"]),
            ),
        )

        result = search_jobs(
            self.session,
            JobSearchRequest(
                profile_id=profile.id,
                query=JobQuery(role="产品经理", keywords=["需求分析"], locations=["上海"]),
            ),
        )

        self.assertEqual(result.query.role, "产品经理")
        self.assertEqual(result.query.locations, ["上海"])
        self.assertEqual(result.query.keywords, ["需求分析"])

    def test_searching_for_a_missing_profile_raises_not_found(self) -> None:
        with self.assertRaises(ValueError):
            search_jobs(self.session, JobSearchRequest(profile_id="missing"))


if __name__ == "__main__":
    unittest.main()
