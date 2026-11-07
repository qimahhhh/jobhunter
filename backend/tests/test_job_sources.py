from __future__ import annotations

import os
import unittest
from typing import Any
from unittest import mock

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import get_session
from backend.app.job_sources import (
    OfferCampusSource,
    SourceConfigError,
    SourceUnavailableError,
    notices_to_jobs,
)
from backend.app.main import app
from backend.app.models import Base, Job
from backend.app.schemas_search import JobCollectRequest
from backend.app.services import collect_jobs


def _notice(**overrides: Any) -> dict[str, Any]:
    notice: dict[str, Any] = {
        "id": "ext_TEST=",
        "recruitInfoName": "示例集团2026校园招聘",
        "enterpriseName": "示例集团有限公司",
        "date": 2026,
        "tag": "秋招专场",
        "recruitPosInfoNameList": "财务/审计/税务,法务合规",
        "content": "会计,工程管理",
        "cityNameList": "自贡市",
        "domesticEducation": "本科,硕士",
        "domesticGraduationDate": "2027",
        "announcementUrl": "https://example.com/notice/1",
        "url": "投递邮箱:hr@example.com",
        "richText": "<p>不允许落盘的公告正文</p>",
        "source": "offerxiansheng.com",
    }
    notice.update(overrides)
    return notice


def _envelope(items: list[Any]) -> dict[str, Any]:
    return {"code": 1000, "message": "success", "data": {"items": items}}


class _StubSource:
    name = "stub-source"

    def __init__(
        self,
        items: list[Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._items = items or []
        self._error = error
        self.limits: list[int] = []

    def fetch_recent(self, *, limit: int) -> list[Any]:
        self.limits.append(limit)
        if self._error is not None:
            raise self._error
        return self._items


class NoticesToJobsTest(unittest.TestCase):
    def test_one_notice_splits_into_one_posting_per_opening(self) -> None:
        jobs, warnings = notices_to_jobs([_notice()])

        self.assertEqual(warnings, [])
        self.assertEqual([job.title for job in jobs], ["会计", "工程管理"])
        self.assertEqual(jobs[0].company, "示例集团有限公司")
        self.assertEqual(jobs[0].location, "自贡市")

    def test_opening_names_fall_back_to_families_then_notice_title(self) -> None:
        families, _ = notices_to_jobs([_notice(content="")])
        self.assertEqual(
            [job.title for job in families], ["财务/审计/税务", "法务合规"]
        )

        single, _ = notices_to_jobs([_notice(content="", recruitPosInfoNameList="")])
        self.assertEqual([job.title for job in single], ["示例集团2026校园招聘"])

    def test_employment_type_reads_the_published_label(self) -> None:
        full_time, _ = notices_to_jobs([_notice()])
        self.assertEqual(
            {job.employment_type for job in full_time}, {"full_time"}
        )

        intern, _ = notices_to_jobs([_notice(tag="暑期实习专场")])
        self.assertEqual({job.employment_type for job in intern}, {"internship"})

    def test_notice_text_is_dropped_and_facts_are_kept(self) -> None:
        jobs, _ = notices_to_jobs([_notice()])

        for job in jobs:
            self.assertNotIn("不允许落盘", job.description)
            self.assertNotIn("不允许落盘", job.requirements)
            self.assertIn("学历要求：本科,硕士", job.requirements)
            self.assertEqual(job.source_url, "https://example.com/notice/1")

    def test_non_link_urls_never_become_the_source_url(self) -> None:
        jobs, _ = notices_to_jobs(
            [_notice(announcementUrl="", url="投递邮箱:hr@example.com")]
        )
        self.assertTrue(all(job.source_url is None for job in jobs))

    def test_unusable_records_are_skipped_with_a_warning(self) -> None:
        jobs, warnings = notices_to_jobs(
            ["not a dict", _notice(enterpriseName=""), _notice()]
        )

        self.assertEqual(len(jobs), 2)
        self.assertEqual(len(warnings), 2)
        self.assertIn("第 1 条", warnings[0])
        self.assertIn("企业名称", warnings[1])


class OfferCampusSourceTest(unittest.TestCase):
    def _source(
        self, handler: Any, *, api_key: str = "test-key"
    ) -> OfferCampusSource:
        return OfferCampusSource(
            api_key=api_key,
            base_url="https://api.example.test/open/v1",
            transport=httpx.MockTransport(handler),
        )

    def test_fetch_recent_sends_the_bearer_header_and_returns_items(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["authorization"] = request.headers.get("Authorization", "")
            seen["path"] = request.url.path
            seen["limit"] = request.url.params.get("limit")
            return httpx.Response(200, json=_envelope([_notice()]))

        items = self._source(handler).fetch_recent(limit=7)

        self.assertEqual(len(items), 1)
        self.assertEqual(seen["authorization"], "Bearer test-key")
        self.assertEqual(seen["path"], "/open/v1/campus-recruit/recent")
        self.assertEqual(seen["limit"], "7")

    def test_missing_key_is_a_configuration_error(self) -> None:
        with mock.patch.dict(os.environ, {"OFFER_CAMPUS_API_KEY": ""}):
            with self.assertRaises(SourceConfigError):
                OfferCampusSource(api_key="")

    def test_failed_envelope_is_reported_as_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"code": 303, "message": "auth_error"})

        with self.assertRaises(SourceUnavailableError):
            self._source(handler).fetch_recent(limit=5)

    def test_unusable_shapes_are_reported_as_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"code": 1000, "data": {}})

        with self.assertRaises(SourceUnavailableError):
            self._source(handler).fetch_recent(limit=5)

    def test_http_failures_become_unavailable_not_success(self) -> None:
        for status in (401, 403, 500):
            def handler(request: httpx.Request, status: int = status) -> httpx.Response:
                return httpx.Response(status)

            with self.assertRaises(SourceUnavailableError):
                self._source(handler).fetch_recent(limit=5)

    def test_transport_failures_become_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        with self.assertRaises(SourceUnavailableError):
            self._source(handler).fetch_recent(limit=5)


class CollectJobsTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )()

    def tearDown(self) -> None:
        self.session.close()

    def test_collection_merges_without_duplicating(self) -> None:
        source = _StubSource(items=[_notice()])

        first = collect_jobs(self.session, JobCollectRequest(limit=5), source=source)
        second = collect_jobs(self.session, JobCollectRequest(limit=5), source=source)

        self.assertEqual(first.fetched, 1)
        self.assertEqual(len(first.created), 2)
        self.assertEqual(len(second.updated), 2)
        self.assertEqual(second.created, [])
        self.assertEqual(self.session.query(Job).count(), 2)
        self.assertEqual(source.limits, [5, 5])
        self.assertTrue(any("薪资" in warning for warning in first.warnings))

    def test_collected_rows_carry_facts_and_links(self) -> None:
        collect_jobs(self.session, JobCollectRequest(limit=5), source=_StubSource([_notice()]))

        job = self.session.query(Job).filter(Job.title == "会计").one()
        self.assertEqual(job.source_url, "https://example.com/notice/1")
        self.assertEqual(job.verification_status, "pending_verification")
        self.assertIn("学历要求", job.requirements)


class CollectEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session_factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )

        def override_get_session() -> Any:
            session = self.session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_session] = override_get_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_collect_reports_what_it_merged(self) -> None:
        with mock.patch(
            "backend.app.services.OfferCampusSource",
            return_value=_StubSource(items=[_notice()]),
        ):
            response = self.client.post("/api/v1/jobs/collect", json={"limit": 5})

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["source"], "stub-source")
        self.assertEqual(body["fetched"], 1)
        self.assertEqual(len(body["created"]), 2)

    def test_unconfigured_source_is_503(self) -> None:
        with mock.patch(
            "backend.app.services.OfferCampusSource",
            side_effect=SourceConfigError("OFFER_CAMPUS_API_KEY 未配置"),
        ):
            response = self.client.post("/api/v1/jobs/collect", json={})

        self.assertEqual(response.status_code, 503)

    def test_unreachable_source_is_502(self) -> None:
        stub = _StubSource(error=SourceUnavailableError("岗位来源请求失败"))
        with mock.patch(
            "backend.app.services.OfferCampusSource", return_value=stub
        ):
            response = self.client.post("/api/v1/jobs/collect", json={})

        self.assertEqual(response.status_code, 502)
