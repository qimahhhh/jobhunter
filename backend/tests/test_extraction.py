from __future__ import annotations

import unittest

from backend.app.extractor import extract_profile
from backend.app.llm import LLMError

RESUME = """张三

教育背景

北京邮电大学 计算机科学与技术 2023.09-2027.06

实习经历

字节跳动 后端开发实习
负责推荐接口的性能优化，QPS 提升 40%。

技能

Python、Go、SQL
"""


class FakeClient:
    """Stands in for DeepSeek: replays scripted replies and records the prompts."""

    def __init__(self, replies: list[object]) -> None:
        self.replies = list(replies)
        self.calls: list[str] = []

    def complete_json(self, *, system: str, user: str) -> dict[str, object]:
        self.calls.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply  # type: ignore[return-value]


class ExtractionTest(unittest.TestCase):
    def test_valid_reply_keeps_its_evidence(self) -> None:
        client = FakeClient(
            [
                {
                    "summary": "计算机专业学生，有后端实习经历。",
                    "skills": ["Python", "Go", "SQL"],
                    "experiences": ["字节跳动 后端开发实习"],
                    "evidence": ["c001"],
                }
            ]
        )

        result = extract_profile(RESUME, client)

        self.assertIsNotNone(result.profile)
        self.assertEqual(result.profile.summary, "计算机专业学生，有后端实习经历。")
        self.assertEqual(result.evidence, ["c001"])
        self.assertEqual(result.unresolved, [])
        self.assertFalse(result.degraded)
        self.assertIn("c001", result.chunk_ids)
        self.assertEqual(len(result.chunk_ids), 4)

    def test_prompt_carries_the_chunk_headers(self) -> None:
        client = FakeClient(
            [{"summary": "学生", "skills": [], "experiences": [], "evidence": ["c001"]}]
        )

        extract_profile(RESUME, client)

        self.assertIn("[chunk:c001 | source:free_text", client.calls[0])
        self.assertIn("字节跳动", client.calls[0])

    def test_invented_chunk_id_is_reported_and_dropped(self) -> None:
        client = FakeClient(
            [
                {
                    "summary": "学生",
                    "skills": [],
                    "experiences": [],
                    "evidence": ["c999", "c001"],
                }
            ]
        )

        result = extract_profile(RESUME, client)

        self.assertEqual(result.unresolved, ["c999"])
        self.assertEqual(result.evidence, ["c001"])
        self.assertFalse(result.degraded)
        self.assertTrue(any("c999" in note for note in result.notes))

    def test_reply_without_any_valid_evidence_is_degraded(self) -> None:
        client = FakeClient(
            [{"summary": "学生", "skills": [], "experiences": [], "evidence": ["c999"]}]
        )

        result = extract_profile(RESUME, client)

        self.assertTrue(result.degraded)
        self.assertEqual(result.evidence, [])

    def test_single_string_field_is_coerced_to_a_list(self) -> None:
        client = FakeClient(
            [
                {
                    "summary": "学生",
                    "skills": "Python",
                    "experiences": "字节跳动 后端开发实习",
                    "evidence": "c001",
                }
            ]
        )

        result = extract_profile(RESUME, client)

        self.assertEqual(result.profile.skills, ["Python"])
        self.assertEqual(result.evidence, ["c001"])

    def test_broken_reply_is_retried_once(self) -> None:
        client = FakeClient(
            [
                LLMError("model reply was not JSON"),
                {"summary": "重试成功", "skills": [], "experiences": [], "evidence": ["c001"]},
            ]
        )

        result = extract_profile(RESUME, client)

        self.assertEqual(len(client.calls), 2)
        self.assertIn("上一次回复被拒绝了", client.calls[1])
        self.assertEqual(result.profile.summary, "重试成功")
        self.assertFalse(result.degraded)

    def test_two_broken_replies_degrade_without_raising(self) -> None:
        client = FakeClient([LLMError("boom"), LLMError("boom again")])

        result = extract_profile(RESUME, client)

        self.assertIsNone(result.profile)
        self.assertTrue(result.degraded)
        self.assertIn("c001", result.chunk_ids)
        self.assertTrue(any("模型抽取失败" in note for note in result.notes))

    def test_empty_text_never_calls_the_model(self) -> None:
        client = FakeClient([])

        result = extract_profile("   ", client)

        self.assertEqual(client.calls, [])
        self.assertTrue(result.degraded)
        self.assertEqual(result.chunk_ids, [])


if __name__ == "__main__":
    unittest.main()
