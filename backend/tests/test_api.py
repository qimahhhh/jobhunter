from __future__ import annotations

from io import BytesIO
import json
import unittest
from collections.abc import Iterator
from typing import Any
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.chunking import Block
from backend.app.db import get_session
from backend.app.llm import LLMError
from backend.app.main import app
from backend.app.models import Base


class ApiResponse:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body

    def json(self) -> Any:
        return json.loads(self.body)


async def _raw_request(
    method: str,
    path: str,
    body: bytes,
    query: str = "",
    content_type: str | None = None,
) -> ApiResponse:
    headers = [(b"host", b"testserver")]
    if content_type is not None:
        headers.append((b"content-type", content_type.encode()))
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "http_version": "1.1", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
    }
    await app(scope, receive, send)
    start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    response_headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start["headers"]
    }
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return ApiResponse(start["status"], response_headers, response_body)


async def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    query: str = "",
) -> ApiResponse:
    body = b"" if payload is None else json.dumps(payload).encode()
    return await _raw_request(
        method,
        path,
        body,
        query=query,
        content_type="application/json" if payload is not None else None,
    )


def _job_payload(employment_type: str = "internship") -> dict[str, Any]:
    return {
        "title": "AI Intern",
        "company": "Example",
        "description": "AI workflows",
        "requirements": "Python",
        "employment_type": employment_type,
        "source_name": "manual",
    }


class ApiContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
        )

        def override_get_session() -> Iterator[Session]:
            session = self.session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_session] = override_get_session

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    async def _create_profile(self) -> str:
        user_response = await _request(
            "POST",
            "/api/v1/users",
            {
                "email": "student@example.com",
                "display_name": "Student",
            },
        )
        self.assertEqual(user_response.status, 201)
        profile_response = await _request(
            "POST",
            "/api/v1/profiles",
            {
                "user_id": user_response.json()["id"],
                "requirements": {"desired_role": "AI Intern"},
                "capabilities": {
                    "summary": "Python student",
                    "skills": ["Python", "FastAPI"],
                    "experiences": ["Built an API"],
                },
            },
        )
        self.assertEqual(profile_response.status, 201)
        return profile_response.json()["id"]

    async def test_job_fit_is_persisted_and_readable_through_http(self) -> None:
        request_payload = {
            "profile": {"summary": "Python student", "skills": ["Python"]},
            "job": _job_payload(),
        }
        create_response = await _request("POST", "/api/v1/job-fit", request_payload)

        self.assertEqual(create_response.status, 200)
        created = create_response.json()
        self.assertTrue(created["request_id"])

        history_response = await _request("GET", "/api/v1/job-fit")
        detail_response = await _request(
            "GET",
            f"/api/v1/job-fit/{created['request_id']}",
        )

        self.assertEqual(history_response.status, 200)
        self.assertEqual(detail_response.status, 200)
        history = history_response.json()
        detail = detail_response.json()
        self.assertEqual([item["request_id"] for item in history], [created["request_id"]])
        self.assertEqual(
            detail["request"],
            {
                "profile": {
                    "summary": "Python student",
                    "skills": ["Python"],
                    "experiences": [],
                },
                "job": {
                    "title": "AI Intern",
                    "company": "Example",
                    "description": "AI workflows",
                    "requirements": "Python",
                    "employment_type": "internship",
                    "source_name": "manual",
                    "source_url": None,
                },
            },
        )
        self.assertEqual(detail["result"], created)

    async def test_job_match_computes_and_persists_server_results(self) -> None:
        profile_id = await self._create_profile()
        job_response = await _request("POST", "/api/v1/jobs", _job_payload())
        self.assertEqual(job_response.status, 201)

        match_response = await _request(
            "POST",
            "/api/v1/job-matches",
            {
                "user_profile_id": profile_id,
                "job_id": job_response.json()["id"],
            },
        )

        self.assertEqual(match_response.status, 201)
        match = match_response.json()
        self.assertEqual(match["score"], 1.0)
        self.assertEqual(match["match_points"], ["python"])
        self.assertEqual(match["gaps"], [])
        self.assertTrue(match["recommendation"])
        self.assertEqual(match["confidence"], 0.5)

        detail_response = await _request(
            "GET",
            f"/api/v1/job-matches/{match['id']}",
        )
        self.assertEqual(detail_response.status, 200)
        self.assertEqual(detail_response.json(), match)

        client_result_response = await _request(
            "POST",
            "/api/v1/job-matches",
            {
                "user_profile_id": profile_id,
                "job_id": job_response.json()["id"],
                "score": 0.99,
                "gaps": ["client-supplied"],
                "recommendation": "client-supplied",
            },
        )
        self.assertEqual(client_result_response.status, 422)

    async def test_job_employment_type_contract_and_filter(self) -> None:
        invalid_payload = _job_payload()
        invalid_payload.pop("employment_type")
        missing_type_response = await _request("POST", "/api/v1/jobs", invalid_payload)
        self.assertEqual(missing_type_response.status, 422)

        internship_response = await _request("POST", "/api/v1/jobs", _job_payload())
        full_time_response = await _request(
            "POST",
            "/api/v1/jobs",
            _job_payload(employment_type="full_time"),
        )
        self.assertEqual(internship_response.status, 201)
        self.assertEqual(full_time_response.status, 201)

        filtered_response = await _request(
            "GET",
            "/api/v1/jobs",
            query="employment_type=internship",
        )
        invalid_filter_response = await _request(
            "GET",
            "/api/v1/jobs",
            query="employment_type=unknown",
        )

        self.assertEqual(filtered_response.status, 200)
        self.assertEqual(
            [job["id"] for job in filtered_response.json()],
            [internship_response.json()["id"]],
        )
        self.assertEqual(invalid_filter_response.status, 422)

    async def test_job_match_rejects_jobs_failing_hard_constraints(self) -> None:
        profile_id = await self._create_profile()
        job_response = await _request(
            "POST",
            "/api/v1/jobs",
            _job_payload(employment_type="full_time"),
        )
        self.assertEqual(job_response.status, 201)

        rejected_response = await _request(
            "POST",
            "/api/v1/job-matches",
            {
                "user_profile_id": profile_id,
                "job_id": job_response.json()["id"],
            },
        )

        self.assertEqual(rejected_response.status, 422)
        detail = rejected_response.json()["detail"]
        self.assertEqual(detail["message"], "hard constraints not met")
        self.assertTrue(detail["rejections"])
        self.assertIn("正式", detail["rejections"][0])

    async def test_creating_profile_or_resume_for_missing_user_returns_404(self) -> None:
        profile_response = await _request(
            "POST",
            "/api/v1/profiles",
            {
                "user_id": "missing-user",
                "requirements": {"desired_role": "AI Intern"},
                "capabilities": {"summary": "Python student"},
            },
        )
        resume_response = await _request(
            "POST",
            "/api/v1/resumes",
            {"user_id": "missing-user", "source_name": "student-resume"},
        )

        self.assertEqual(profile_response.status, 404)
        self.assertEqual(profile_response.json()["detail"], "user not found")
        self.assertEqual(resume_response.status, 404)
        self.assertEqual(resume_response.json()["detail"], "user not found")

    async def test_job_match_with_missing_reference_returns_404(self) -> None:
        profile_id = await self._create_profile()

        missing_profile = await _request(
            "POST",
            "/api/v1/job-matches",
            {"user_profile_id": "missing-profile", "job_id": "missing-job"},
        )
        missing_job = await _request(
            "POST",
            "/api/v1/job-matches",
            {"user_profile_id": profile_id, "job_id": "missing-job"},
        )

        self.assertEqual(missing_profile.status, 404)
        self.assertEqual(missing_profile.json()["detail"], "profile not found")
        self.assertEqual(missing_job.status, 404)
        self.assertEqual(missing_job.json()["detail"], "job not found")

    async def test_job_status_is_pending_verification_after_creation(self) -> None:
        response = await _request("POST", "/api/v1/jobs", _job_payload())

        self.assertEqual(response.status, 201)
        job = response.json()
        self.assertEqual(job["verification_status"], "pending_verification")
        self.assertIsNotNone(job["collected_at"])
        self.assertIsNone(job["last_verified_at"])

    async def test_confirmed_extraction_is_saved_as_the_profile(self) -> None:
        user_response = await _request(
            "POST",
            "/api/v1/users",
            {"email": "confirm@example.com", "display_name": "Confirm"},
        )
        confirm_response = await _request(
            "POST",
            "/api/v1/profiles/extract/confirm",
            {
                "user_id": user_response.json()["id"],
                "requirements": {"desired_role": "AI 应用开发实习"},
                "profile": {
                    "summary": "学生",
                    "skills": ["Python"],
                    "experiences": ["字节跳动 后端开发实习"],
                },
                "recommended_roles": ["AI 应用开发实习生"],
            },
        )

        self.assertEqual(confirm_response.status, 201)
        saved = confirm_response.json()
        self.assertEqual(saved["capabilities"]["summary"], "学生")
        self.assertEqual(saved["capabilities"]["target_roles"], ["AI 应用开发实习生"])

        fetched = await _request("GET", f"/api/v1/profiles/{saved['id']}")
        self.assertEqual(fetched.status, 200)
        self.assertEqual(fetched.json()["capabilities"]["skills"], ["Python"])

    async def test_confirming_for_a_missing_user_returns_404(self) -> None:
        confirm_response = await _request(
            "POST",
            "/api/v1/profiles/extract/confirm",
            {
                "user_id": "missing-user",
                "requirements": {"desired_role": "AI 应用开发实习"},
                "profile": {"summary": "学生", "skills": [], "experiences": []},
            },
        )

        self.assertEqual(confirm_response.status, 404)
        self.assertEqual(confirm_response.json()["detail"], "user not found")

    async def _create_user(self, email: str) -> str:
        response = await _request(
            "POST",
            "/api/v1/users",
            {"email": email, "display_name": "Tester"},
        )
        self.assertEqual(response.status, 201)
        return response.json()["id"]

    async def _confirm_draft(
        self,
        user_id: str,
        summary: str,
        *,
        recommended_roles: list[str] | None = None,
        target_roles: list[str] | None = None,
        missing_information: list[str] | None = None,
    ) -> ApiResponse:
        payload: dict[str, Any] = {
            "user_id": user_id,
            "requirements": {"desired_role": "AI 应用开发实习"},
            "profile": {"summary": summary, "skills": ["Python"], "experiences": []},
        }
        if recommended_roles is not None:
            payload["recommended_roles"] = recommended_roles
        if target_roles is not None:
            payload["target_roles"] = target_roles
        if missing_information is not None:
            payload["missing_information"] = missing_information
        return await _request("POST", "/api/v1/profiles/extract/confirm", payload)

    async def test_confirming_twice_updates_one_profile(self) -> None:
        user_id = await self._create_user("again@example.com")

        first = await self._confirm_draft(user_id, "第一版")
        second = await self._confirm_draft(user_id, "第二版")

        self.assertEqual(first.status, 201)
        self.assertEqual(second.status, 201)
        # One profile per user: re-confirming replaces the row instead of
        # leaving a second profile nobody can tell apart.
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(second.json()["capabilities"]["summary"], "第二版")

    async def test_unedited_suggestions_are_stored_as_suggestions(self) -> None:
        user_id = await self._create_user("suggested@example.com")

        response = await self._confirm_draft(
            user_id, "学生", recommended_roles=["AI 应用开发实习生"]
        )

        capabilities = response.json()["capabilities"]
        self.assertEqual(capabilities["suggested_roles"], ["AI 应用开发实习生"])
        self.assertEqual(capabilities["target_roles"], ["AI 应用开发实习生"])
        self.assertEqual(capabilities["target_roles_source"], "suggested")

    async def test_edited_target_roles_are_stored_as_confirmed(self) -> None:
        user_id = await self._create_user("confirmed@example.com")

        response = await self._confirm_draft(
            user_id,
            "学生",
            recommended_roles=["AI 应用开发实习生"],
            target_roles=["算法实习生"],
        )

        capabilities = response.json()["capabilities"]
        self.assertEqual(capabilities["suggested_roles"], ["AI 应用开发实习生"])
        self.assertEqual(capabilities["target_roles"], ["算法实习生"])
        self.assertEqual(capabilities["target_roles_source"], "confirmed")

    async def test_missing_information_survives_the_hand_off(self) -> None:
        user_id = await self._create_user("gaps@example.com")

        response = await self._confirm_draft(
            user_id, "学生", missing_information=["期望城市", "可实习时长"]
        )
        saved = response.json()

        self.assertEqual(saved["missing_information"], ["期望城市", "可实习时长"])
        fetched = await _request("GET", f"/api/v1/profiles/{saved['id']}")
        self.assertEqual(
            fetched.json()["missing_information"], ["期望城市", "可实习时长"]
        )


async def _upload(
    path: str,
    content: bytes,
    filename: str = "resume.pdf",
) -> ApiResponse:
    return await _raw_request(
        "POST",
        path,
        content,
        query=f"filename={filename}",
        content_type="application/octet-stream",
    )


class _FakeClient:
    """Stands in for DeepSeek: replays scripted replies and records the prompts."""

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, str]] = []

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        self.calls.append({"system": system, "user": user})
        return self.replies.pop(0)


class ExtractionApiTest(unittest.IsolatedAsyncioTestCase):
    """The extraction endpoints: free text and uploaded resume files."""

    async def test_uploaded_pdf_reaches_the_parser_and_returns_the_draft(self) -> None:
        blocks = [
            Block("res001", "resume", "教育背景", "北京交通大学", 0),
            Block("res002", "resume", "实习经历", "字节跳动 后端开发实习", 1),
        ]
        client = _FakeClient(
            [
                {
                    "summary": "学生",
                    "skills": ["Python"],
                    "experiences": [],
                    "evidence": ["c002", "c999"],
                }
            ]
        )
        with mock.patch(
            "backend.app.routers.blocks_from_pdf", return_value=blocks
        ) as parse:
            with mock.patch("backend.app.routers._client", return_value=client):
                response = await _upload(
                    "/api/v1/profiles/extract/file", b"%PDF-fake", "resume.pdf"
                )

        self.assertEqual(response.status, 200)
        body = response.json()
        self.assertEqual(body["chunk_ids"], ["c001", "c002"])
        self.assertEqual(body["evidence"], ["c002"])
        self.assertEqual(body["unresolved_evidence"], ["c999"])
        self.assertFalse(body["degraded"])
        self.assertEqual(body["profile"]["summary"], "学生")
        self.assertEqual(parse.call_args[0][0].read(), b"%PDF-fake")

    async def test_uploaded_docx_reaches_the_model_with_its_sections(self) -> None:
        try:
            from docx import Document
        except ImportError:  # pragma: no cover - dependency guard
            self.skipTest("python-docx is not installed")

        document = Document()
        document.add_heading("实习经历", level=1)
        document.add_paragraph("字节跳动 后端开发实习")
        buffer = BytesIO()
        document.save(buffer)

        client = _FakeClient(
            [
                {
                    "summary": "有实习经历的学生",
                    "skills": [],
                    "experiences": ["字节跳动 后端开发实习"],
                    "evidence": ["c001"],
                }
            ]
        )
        with mock.patch("backend.app.routers._client", return_value=client):
            response = await _upload(
                "/api/v1/profiles/extract/file", buffer.getvalue(), "resume.docx"
            )

        self.assertEqual(response.status, 200)
        prompt = client.calls[0]["user"]
        self.assertIn("[chunk:c001 | source:resume | section:实习经历]", prompt)
        self.assertIn("字节跳动 后端开发实习", prompt)
        self.assertEqual(response.json()["profile"]["summary"], "有实习经历的学生")

    async def test_unsupported_file_type_is_rejected(self) -> None:
        with mock.patch("backend.app.routers._client") as client:
            response = await _upload(
                "/api/v1/profiles/extract/file", b"plain text", "resume.txt"
            )

        self.assertEqual(response.status, 415)
        client.assert_not_called()

    async def test_empty_upload_is_rejected(self) -> None:
        with mock.patch("backend.app.routers.blocks_from_pdf", return_value=[]) as parse:
            response = await _upload("/api/v1/profiles/extract/file", b"", "resume.pdf")

        self.assertEqual(response.status, 400)
        parse.assert_not_called()

    async def test_oversized_upload_is_rejected(self) -> None:
        with mock.patch("backend.app.routers._MAX_UPLOAD_BYTES", 8):
            response = await _upload(
                "/api/v1/profiles/extract/file", b"0123456789", "resume.pdf"
            )

        self.assertEqual(response.status, 413)

    async def test_missing_model_config_returns_503(self) -> None:
        with mock.patch("backend.app.routers.blocks_from_pdf", return_value=[]):
            with mock.patch(
                "backend.app.routers._client", side_effect=LLMError("missing key")
            ):
                response = await _upload(
                    "/api/v1/profiles/extract/file", b"%PDF-fake", "resume.pdf"
                )

        self.assertEqual(response.status, 503)

    async def test_broken_file_is_reported_as_a_client_error(self) -> None:
        with mock.patch(
            "backend.app.routers.blocks_from_pdf", side_effect=ValueError("bad pdf")
        ):
            with mock.patch("backend.app.routers._client"):
                response = await _upload(
                    "/api/v1/profiles/extract/file", b"%PDF-fake", "resume.pdf"
                )

        self.assertEqual(response.status, 400)
        self.assertIn("bad pdf", response.json()["detail"])

    async def test_draft_carries_guidance_fields(self) -> None:
        client = _FakeClient(
            [
                {
                    "summary": "学生",
                    "skills": [],
                    "experiences": [],
                    "recommended_roles": ["AI 应用开发实习生"],
                    "missing_information": ["期望城市"],
                    "evidence": ["c001"],
                }
            ]
        )
        with mock.patch("backend.app.routers._client", return_value=client):
            response = await _request(
                "POST",
                "/api/v1/profiles/extract",
                {"text": "张三\n\n教育背景\n\n北京邮电大学"},
            )

        body = response.json()
        self.assertEqual(body["recommended_roles"], ["AI 应用开发实习生"])
        self.assertEqual(body["missing_information"], ["期望城市"])

    async def test_text_endpoint_contract_is_unchanged(self) -> None:
        client = _FakeClient(
            [
                {
                    "summary": "学生",
                    "skills": ["Python"],
                    "experiences": [],
                    "evidence": ["c001"],
                }
            ]
        )
        with mock.patch("backend.app.routers._client", return_value=client):
            response = await _request(
                "POST",
                "/api/v1/profiles/extract",
                {"text": "张三\n\n教育背景\n\n北京邮电大学"},
            )

        self.assertEqual(response.status, 200)
        body = response.json()
        self.assertEqual(body["profile"]["summary"], "学生")
        self.assertEqual(body["evidence"], ["c001"])
        self.assertFalse(body["degraded"])


if __name__ == "__main__":
    unittest.main()
