from __future__ import annotations

import json
import unittest
from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import get_session
from backend.app.main import app
from backend.app.models import Base


class ApiResponse:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body

    def json(self) -> Any:
        return json.loads(self.body)


async def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    query: str = "",
) -> ApiResponse:
    body = b"" if payload is None else json.dumps(payload).encode()
    headers = [(b"host", b"testserver")]
    if payload is not None:
        headers.append((b"content-type", b"application/json"))
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


if __name__ == "__main__":
    unittest.main()
