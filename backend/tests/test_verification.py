from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, Job
from backend.app.routers import verify_job_statuses
from backend.app.schemas_resources import (
    JobCreate,
    JobVerificationDecision,
    JobVerificationRequest,
)
from backend.app.schemas_search import JobIngestRequest, JobQuery, JobSearchRequest
from backend.app.services import (
    create_job,
    ingest_jobs,
    list_jobs,
    search_jobs,
    verify_jobs,
)


def _job(title: str = "Python 开发实习生", **overrides) -> JobCreate:
    payload = {
        "title": title,
        "company": "Example",
        "description": "负责相关业务开发",
        "requirements": "熟悉 Python",
        "employment_type": "internship",
        "source_name": "offerxiansheng.com",
        "source_url": "https://example.com/notice/1",
        "location": "北京",
    }
    payload.update(overrides)
    return JobCreate(**payload)


class JobVerificationTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )()

    def tearDown(self) -> None:
        self.session.close()

    def _verify(self, job_id: str, status: str):
        return verify_jobs(
            self.session,
            JobVerificationRequest(
                decisions=[JobVerificationDecision(job_id=job_id, status=status)]
            ),
        )

    def test_a_verdict_stores_the_status_and_the_moment(self) -> None:
        job = create_job(self.session, _job())

        result = self._verify(job.id, "active")

        self.assertEqual([item.id for item in result.updated], [job.id])
        active = list_jobs(self.session, verification_status="active")
        self.assertEqual([item.id for item in active], [job.id])
        # "active" without a date would be a claim nobody can check.
        self.assertIsNotNone(active[0].last_verified_at)

    def test_withdrawing_a_verdict_clears_its_date(self) -> None:
        job = create_job(self.session, _job())
        self._verify(job.id, "active")

        self._verify(job.id, "pending_verification")

        pending = list_jobs(self.session, verification_status="pending_verification")
        self.assertEqual([item.id for item in pending], [job.id])
        self.assertIsNone(pending[0].last_verified_at)

    def test_an_unknown_id_is_rejected_and_the_rest_still_lands(self) -> None:
        job = create_job(self.session, _job())

        result = verify_jobs(
            self.session,
            JobVerificationRequest(
                decisions=[
                    JobVerificationDecision(job_id=job.id, status="active"),
                    JobVerificationDecision(job_id="missing-job", status="expired"),
                ]
            ),
        )

        self.assertEqual(len(result.updated), 1)
        self.assertEqual([item.job_id for item in result.rejected], ["missing-job"])
        self.assertEqual(
            [item.id for item in list_jobs(self.session, verification_status="active")],
            [job.id],
        )

    def test_expired_postings_leave_the_shortlist_with_a_reason(self) -> None:
        job = create_job(self.session, _job())
        self._verify(job.id, "expired")

        result = search_jobs(
            self.session, JobSearchRequest(query=JobQuery(keywords=["Python"]))
        )

        self.assertEqual(result.candidates, [])
        self.assertEqual(len(result.excluded), 1)
        self.assertIn("过期", result.excluded[0].reasons[0])

    def test_unverified_postings_carry_a_caveat(self) -> None:
        job = create_job(self.session, _job())

        result = search_jobs(
            self.session, JobSearchRequest(query=JobQuery(keywords=["Python"]))
        )

        candidate = result.candidates[0]
        self.assertEqual(candidate.job_id, job.id)
        self.assertEqual(candidate.verification_status, "pending_verification")
        self.assertIn("尚未核验", candidate.warnings[0])

    def test_verified_only_drops_everything_not_confirmed_open(self) -> None:
        active = create_job(self.session, _job("Python 开发实习生"))
        create_job(self.session, _job("机器学习实习生"))
        self._verify(active.id, "active")

        result = search_jobs(
            self.session,
            JobSearchRequest(query=JobQuery(keywords=["Python"], verified_only=True)),
        )

        self.assertEqual([c.job_id for c in result.candidates], [active.id])
        self.assertEqual(result.prefiltered_out, 1)

    def test_a_reposted_posting_goes_back_to_pending(self) -> None:
        # Ingest on both sides: a manually created row carries no dedupe key, so
        # only the collector path can recognise the repost.
        ingest_jobs(self.session, JobIngestRequest(jobs=[_job()]))
        job = self.session.query(Job).one()
        self._verify(job.id, "expired")

        # The source publishes it again, which contradicts the verdict.
        ingest_jobs(self.session, JobIngestRequest(jobs=[_job()]))

        row = self.session.get(Job, job.id)
        self.assertEqual(row.verification_status, "pending_verification")
        self.assertIsNone(row.last_verified_at)

    def test_route_records_verdicts(self) -> None:
        job = create_job(self.session, _job())

        response = verify_job_statuses(
            JobVerificationRequest(
                decisions=[JobVerificationDecision(job_id=job.id, status="active")]
            ),
            session=self.session,
        )

        self.assertEqual(response.updated[0].verification_status, "active")
        self.assertIsNotNone(response.updated[0].last_verified_at)


if __name__ == "__main__":
    unittest.main()
