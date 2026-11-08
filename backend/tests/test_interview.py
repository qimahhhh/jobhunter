from __future__ import annotations

import unittest
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.jd_extract import requirements_for
from backend.app.models import Base
from backend.app.schemas_interview import InterviewAnswerRequest, InterviewStartRequest
from backend.app.schemas_resources import (
    CapabilityProfile,
    JobCreate,
    ProfileCreate,
    UserCreate,
    UserRequirements,
)
from backend.app.services import (
    InterviewFinishedError,
    answer_interview,
    create_job,
    create_profile,
    create_user,
    read_interview,
    start_interview_session,
)

REQUIREMENTS = {
    "requirements": [
        {
            "text": "熟悉 Python",
            "kind": "must",
            "dimension": "skill",
            "terms": [{"any_of": ["Python"]}],
        },
        {
            "text": "熟悉 Go",
            "kind": "must",
            "dimension": "skill",
            "terms": [{"any_of": ["Go"]}],
        },
    ]
}


class _FakeClient:
    """Replays scripted replies so no test reaches the network."""

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.calls: list[str] = []

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        self.calls.append(user)
        return self.replies.pop(0)


def _plan(*targets: dict[str, Any]) -> dict[str, Any]:
    return {"opening": "我们聊聊后端相关的经历。", "targets": list(targets)}


class InterviewTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )()

        user = create_user(
            self.session,
            UserCreate(email="interview@example.com", display_name="Candidate"),
        )
        self.profile = create_profile(
            self.session,
            ProfileCreate(
                user_id=user.id,
                requirements=UserRequirements(desired_role="后端开发实习生"),
                capabilities=CapabilityProfile(
                    summary="计算机专业学生，熟悉后端开发",
                    skills=["Python"],
                    experiences=["用 Python 写过一个爬虫"],
                ),
            ),
        )
        self.job = create_job(
            self.session,
            JobCreate(
                title="后端开发实习生",
                company="示例科技",
                description="负责服务端接口开发",
                requirements="熟悉 Python；熟悉 Go",
                employment_type="internship",
                source_name="manual",
            ),
        )
        # Seed the requirement cache so a test's client only has to serve the
        # interview itself; the cache hit is what keeps the call count honest.
        requirements_for(
            self.session, self.job.requirements, self.job.description, _FakeClient([REQUIREMENTS])
        )

    def tearDown(self) -> None:
        self.session.close()

    def _start(self, client: _FakeClient, *, max_turns: int = 5):
        return start_interview_session(
            self.session,
            InterviewStartRequest(
                profile_id=self.profile.id, job_id=self.job.id, max_turns=max_turns
            ),
            client,
        )

    def _answer(self, interview_id: str, client: _FakeClient, text: str = "做过一个接口"):
        return answer_interview(
            self.session, interview_id, InterviewAnswerRequest(answer=text), client
        )

    def test_start_stores_the_plan_and_puts_one_question_on_screen(self) -> None:
        client = _FakeClient(
            [
                _plan(
                    {
                        "requirement_id": "r1",
                        "question": "讲讲你用 Python 写过的那个爬虫",
                        "why": "必备技能",
                    }
                )
            ]
        )

        session = self._start(client)

        self.assertEqual(session.status, "in_progress")
        self.assertEqual(len(session.turns), 1)
        self.assertEqual(session.turns[0].requirement_id, "r1")
        self.assertEqual(session.turns[0].requirement_text, "熟悉 Python")
        self.assertIsNone(session.turns[0].answer)
        self.assertEqual(session.plan.opening, "我们聊聊后端相关的经历。")
        # The cache note is expected; a degradation note would not be.
        self.assertTrue(any("缓存" in note for note in session.notes))
        self.assertFalse(
            any("失败" in note or "不可用" in note for note in session.notes)
        )
        # Stored before any answer exists: the plan is the intention later turns
        # are allowed to deviate from, not a script they must follow.
        stored = read_interview(self.session, session.id)
        self.assertEqual([t.requirement_id for t in stored.turns], ["r1"])
        self.assertEqual(stored.remaining, ["r1", "r2"])

    def test_a_plan_naming_a_requirement_that_does_not_exist_is_replaced(self) -> None:
        client = _FakeClient(
            [_plan({"requirement_id": "r99", "question": "编造的问题", "why": ""})]
        )

        session = self._start(client)

        self.assertEqual(session.plan.targets[0].requirement_id, "r1")
        self.assertNotEqual(session.turns[0].question, "编造的问题")
        self.assertTrue(any("没有指向" in note for note in session.notes))

    def test_a_second_probe_on_the_same_requirement_is_refused(self) -> None:
        client = _FakeClient(
            [
                _plan({"requirement_id": "r1", "question": "讲讲那个爬虫", "why": "必备技能"}),
                {
                    "action": "probe",
                    "requirement_id": "r1",
                    "question": "并发怎么处理的？",
                    "why": "回答里提到了并发",
                },
                {
                    "action": "probe",
                    "requirement_id": "r1",
                    "question": "再追一层试试",
                    "why": "还想问",
                },
            ]
        )
        session = self._start(client)

        session = self._answer(session.id, client)
        self.assertEqual(len(session.turns), 2)
        self.assertEqual(session.turns[1].kind, "probe")

        # One follow-up per requirement is a limit the model cannot talk its way
        # past; the frame moves on to what has not been asked at all.
        session = self._answer(session.id, client)
        self.assertEqual(len(session.turns), 3)
        self.assertEqual(session.turns[2].requirement_id, "r2")
        self.assertEqual(session.turns[2].kind, "ask")
        self.assertTrue(any("不可用" in note for note in session.notes))

    def test_an_invented_requirement_is_replaced_by_an_uncovered_one(self) -> None:
        client = _FakeClient(
            [
                _plan({"requirement_id": "r1", "question": "讲讲那个爬虫", "why": "必备技能"}),
                {
                    "action": "ask",
                    "requirement_id": "r99",
                    "question": "你熟悉 Kubernetes 吗",
                    "why": "",
                },
            ]
        )
        session = self._start(client)

        session = self._answer(session.id, client)

        self.assertEqual(session.turns[1].requirement_id, "r2")
        self.assertTrue(any("不可用" in note for note in session.notes))

    def test_a_finish_without_a_reason_is_not_accepted(self) -> None:
        client = _FakeClient(
            [
                _plan({"requirement_id": "r1", "question": "讲讲那个爬虫", "why": "必备技能"}),
                {"action": "finish", "reason": "  "},
            ]
        )
        session = self._start(client)

        session = self._answer(session.id, client)

        self.assertEqual(session.status, "in_progress")
        self.assertEqual(session.turns[-1].requirement_id, "r2")

    def test_the_turn_budget_ends_the_interview_without_asking_the_model(self) -> None:
        client = _FakeClient(
            [
                _plan({"requirement_id": "r1", "question": "讲讲那个爬虫", "why": "必备技能"}),
                {
                    "action": "ask",
                    "requirement_id": "r2",
                    "question": "Go 用过吗？",
                    "why": "第二条必备技能",
                },
            ]
        )
        session = self._start(client, max_turns=2)

        session = self._answer(session.id, client)
        self.assertEqual(len(session.turns), 2)
        session = self._answer(session.id, client)

        self.assertEqual(session.status, "finished")
        self.assertIn("上限", session.finish_reason)
        # Two calls for two planning/deciding steps: hitting the budget is a
        # frame decision, so it costs nothing.
        self.assertEqual(len(client.calls), 2)

    def test_answering_a_finished_interview_is_refused(self) -> None:
        client = _FakeClient(
            [
                _plan({"requirement_id": "r1", "question": "讲讲那个爬虫", "why": "必备技能"}),
                {"action": "finish", "reason": "候选人的经历已经覆盖了这两条要求"},
            ]
        )
        session = self._start(client)

        session = self._answer(session.id, client)
        self.assertEqual(session.status, "finished")
        self.assertIn("覆盖", session.finish_reason)

        with self.assertRaises(InterviewFinishedError):
            self._answer(session.id, client)


if __name__ == "__main__":
    unittest.main()
