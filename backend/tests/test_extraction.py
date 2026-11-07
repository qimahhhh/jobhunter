from __future__ import annotations

import unittest

from backend.app.chunking import Block
from backend.app.extractor import (
    SYSTEM_PROMPT,
    extract_profile,
    extract_profile_from_blocks,
)
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

    def test_guidance_fields_are_parsed_and_coerced(self) -> None:
        client = FakeClient(
            [
                {
                    "summary": "学生",
                    "skills": [],
                    "experiences": [],
                    "recommended_roles": "AI 应用开发实习生",
                    "missing_information": ["期望城市", "可实习时长"],
                    "evidence": ["c001"],
                }
            ]
        )

        result = extract_profile(RESUME, client)

        self.assertEqual(result.recommended_roles, ["AI 应用开发实习生"])
        self.assertEqual(result.missing_information, ["期望城市", "可实习时长"])
        self.assertIn("recommended_roles", SYSTEM_PROMPT)
        self.assertIn("missing_information", SYSTEM_PROMPT)

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

    def test_inferred_fields_are_carried_through_and_coerced(self) -> None:
        client = FakeClient(
            [
                {
                    "summary": "学生",
                    "skills": [],
                    "experiences": [],
                    "recommended_roles": ["AI 应用开发实习生"],
                    "missing_information": "期望城市",
                    "evidence": ["c001"],
                }
            ]
        )

        result = extract_profile(RESUME, client)

        self.assertEqual(result.recommended_roles, ["AI 应用开发实习生"])
        self.assertEqual(result.missing_information, ["期望城市"])
        self.assertFalse(result.degraded)

    def test_suggestions_do_not_make_an_uncited_draft_confident(self) -> None:
        client = FakeClient(
            [
                {
                    "summary": "学生",
                    "skills": [],
                    "experiences": [],
                    "recommended_roles": ["算法工程师"],
                    "missing_information": ["期望城市"],
                    "evidence": [],
                }
            ]
        )

        result = extract_profile(RESUME, client)

        # Suggestions are inference, not claims: they must never turn a draft
        # with no valid citation into something that looks verified.
        self.assertEqual(result.recommended_roles, ["算法工程师"])
        self.assertTrue(result.degraded)
        self.assertEqual(result.evidence, [])

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


class BlocksExtractionTest(unittest.TestCase):
    """The PDF/DOCX entry: layout blocks keep their sections and raw text."""

    def setUp(self) -> None:
        self.blocks = [
            Block("res001", "resume", "教育背景", "北京交通大学", 0, kind="heading"),
            Block("res002", "resume", "教育背景", "211 - 本科 - 计算机科学与技术", 1),
            Block("res003", "resume", "教育背景", "2024.09 - 2028.06", 2),
            Block(
                "res004",
                "resume",
                "实习经历",
                "字节跳动 后端开发实习\n\n负责推荐接口的性能优化。",
                3,
            ),
        ]

    def test_layout_sections_survive_into_the_prompt(self) -> None:
        client = FakeClient(
            [{"summary": "学生", "skills": [], "experiences": [], "evidence": ["c002", "c999"]}]
        )

        result = extract_profile_from_blocks(self.blocks, client)

        prompt = client.calls[0]
        self.assertIn("[chunk:c001 | source:resume | section:教育背景]", prompt)
        self.assertIn("[chunk:c002 | source:resume | section:实习经历]", prompt)
        self.assertIn("2024.09 - 2028.06", prompt)
        self.assertEqual(result.chunk_ids, ["c001", "c002"])
        self.assertEqual(result.evidence, ["c002"])
        self.assertEqual(result.unresolved, ["c999"])
        self.assertFalse(result.degraded)

    def test_block_text_is_not_re_split_as_plain_text(self) -> None:
        client = FakeClient(
            [{"summary": "学生", "skills": [], "experiences": [], "evidence": ["c002"]}]
        )

        extract_profile_from_blocks(self.blocks, client)

        # blocks_from_text would break the entry on the blank line; the layout
        # path must deliver it intact so the model sees one entry, not two.
        self.assertIn("字节跳动 后端开发实习\n\n负责推荐接口的性能优化。", client.calls[0])

    def test_empty_block_list_never_calls_the_model(self) -> None:
        client = FakeClient([])

        result = extract_profile_from_blocks([], client)

        self.assertEqual(client.calls, [])
        self.assertIsNone(result.profile)
        self.assertTrue(result.degraded)
        self.assertEqual(result.chunk_ids, [])


if __name__ == "__main__":
    unittest.main()
