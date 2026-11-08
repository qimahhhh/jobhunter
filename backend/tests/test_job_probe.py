from __future__ import annotations

import unittest
from datetime import timedelta
from unittest import mock

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.job_probe import JobProber
from backend.app.models import Base, Job, utc_now
from backend.app.routers import probe_job_sources
from backend.app.schemas_resources import (
    JobCreate,
    JobExpiryRequest,
    JobProbeRequest,
    JobVerificationDecision,
    JobVerificationRequest,
)
from backend.app.services import (
    create_job,
    expire_stale_jobs,
    probe_jobs,
    verify_jobs,
)


def _prober(handler, **kwargs) -> JobProber:
    return JobProber(
        timeout=1.0, transport=httpx.MockTransport(handler), **kwargs
    )


def _job(url: str | None = "https://example.com/notice/1", **overrides) -> JobCreate:
    payload = {
        "title": "Python 开发实习生",
        "company": "Example",
        "description": "负责相关业务开发",
        "requirements": "熟悉 Python",
        "employment_type": "internship",
        "source_name": "offerxiansheng.com",
        "source_url": url,
        "location": "北京",
    }
    payload.update(overrides)
    return JobCreate(**payload)


class ProbeRuleTest(unittest.TestCase):
    """What the machine is and is not allowed to conclude."""

    def test_missing_page_is_gone(self) -> None:
        prober = _prober(lambda request: httpx.Response(404))

        outcome = prober.probe("job-1", "https://example.com/notice/1")

        self.assertEqual(outcome.verdict, "gone")
        self.assertIn("404", outcome.detail)

    def test_gone_page_is_gone(self) -> None:
        prober = _prober(lambda request: httpx.Response(410))

        self.assertEqual(prober.probe("job-1", "https://example.com/1").verdict, "gone")

    def test_closed_marker_closes_the_posting(self) -> None:
        prober = _prober(
            lambda request: httpx.Response(
                200, text="<html><body>报名已截止</body></html>"
            )
        )

        outcome = prober.probe("job-1", "https://example.com/notice/1")

        self.assertEqual(outcome.verdict, "gone")
        # The detail names the marker that matched, not the page's phrasing.
        self.assertIn("已截止", outcome.detail)

    def test_a_page_that_still_loads_is_not_evidence_of_hiring(self) -> None:
        prober = _prober(lambda request: httpx.Response(200, text="招聘公告正文"))

        outcome = prober.probe("job-1", "https://example.com/notice/1")

        self.assertEqual(outcome.verdict, "alive")

    def test_gbk_page_is_not_read_as_no_marker(self) -> None:
        # The markers are Chinese; decoding a GB18030 page as UTF-8 would mangle
        # exactly the text this check depends on.
        prober = _prober(
            lambda request: httpx.Response(200, content="岗位已下线".encode("gb18030"))
        )

        self.assertEqual(prober.probe("job-1", "https://example.com/1").verdict, "gone")

    def test_refused_request_is_unreachable_not_gone(self) -> None:
        prober = _prober(lambda request: httpx.Response(403))

        self.assertEqual(
            prober.probe("job-1", "https://example.com/1").verdict, "unreachable"
        )

    def test_network_failure_is_unreachable(self) -> None:
        def handler(request):
            raise httpx.ConnectError("boom")

        self.assertEqual(
            _prober(handler).probe("job-1", "https://example.com/1").verdict,
            "unreachable",
        )

    def test_a_posting_without_a_link_is_not_checked(self) -> None:
        self.assertEqual(
            _prober(lambda request: httpx.Response(200)).probe("job-1", None).verdict,
            "no_source",
        )


class ProbeServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )()

    def tearDown(self) -> None:
        self.session.close()

    def test_gone_posting_is_expired_and_the_verdict_is_machine_made(self) -> None:
        job = create_job(self.session, _job())

        result = probe_jobs(
            self.session,
            JobProbeRequest(),
            prober=_prober(lambda request: httpx.Response(404)),
        )

        row = self.session.get(Job, job.id)
        self.assertEqual(result.expired, [job.id])
        self.assertEqual(row.verification_status, "expired")
        self.assertIsNotNone(row.last_checked_at)
        # No human touched it, so there is no verification time behind it.
        self.assertIsNone(row.last_verified_at)

    def test_alive_posting_keeps_its_status(self) -> None:
        job = create_job(self.session, _job())

        result = probe_jobs(
            self.session,
            JobProbeRequest(),
            prober=_prober(lambda request: httpx.Response(200, text="招聘公告")),
        )

        row = self.session.get(Job, job.id)
        self.assertEqual(result.alive, 1)
        self.assertEqual(row.verification_status, "pending_verification")
        self.assertIsNotNone(row.last_checked_at)

    def test_unreachable_source_does_not_overwrite_a_human_verdict(self) -> None:
        job = create_job(self.session, _job())
        verify_jobs(
            self.session,
            JobVerificationRequest(
                decisions=[JobVerificationDecision(job_id=job.id, status="active")]
            ),
        )

        def handler(request):
            raise httpx.ConnectError("boom")

        probe_jobs(self.session, JobProbeRequest(), prober=_prober(handler))

        self.assertEqual(self.session.get(Job, job.id).verification_status, "active")

    def test_unreachable_source_downgrades_an_unconfirmed_posting(self) -> None:
        job = create_job(self.session, _job())

        def handler(request):
            raise httpx.ConnectError("boom")

        result = probe_jobs(self.session, JobProbeRequest(), prober=_prober(handler))

        row = self.session.get(Job, job.id)
        self.assertEqual([item for item in result.unavailable], [job.id])
        self.assertEqual(row.verification_status, "source_unavailable")

    def test_stale_posting_is_expired_instead_of_deleted(self) -> None:
        stale = create_job(self.session, _job())
        stale.collected_at = utc_now() - timedelta(days=30)
        fresh = create_job(self.session, _job(title="机器学习实习生"))
        self.session.commit()

        result = expire_stale_jobs(self.session, JobExpiryRequest(max_age_days=14))

        self.assertEqual(result.expired, [stale.id])
        row = self.session.get(Job, stale.id)
        self.assertIsNotNone(row)
        self.assertEqual(row.verification_status, "expired")
        self.assertEqual(
            self.session.get(Job, fresh.id).verification_status,
            "pending_verification",
        )

    def test_route_wires_the_prober(self) -> None:
        job = create_job(self.session, _job())

        with mock.patch(
            "backend.app.services.JobProber",
            return_value=_prober(lambda request: httpx.Response(404)),
        ):
            response = probe_job_sources(JobProbeRequest(), session=self.session)

        self.assertEqual(response.checked, 1)
        self.assertEqual(response.expired, [job.id])


if __name__ == "__main__":
    unittest.main()
