from __future__ import annotations

import unittest

from backend.app.llm import LLMError
from backend.app.resume_draft import blocks_from_profile, draft_resume

PROFILE = {
    "summary": "计算机专业本科在读，有后端实习经历。",
    "skills": ["Python", "Go"],
    "experiences": ["字节跳动 后端开发实习：负责推荐接口优化，QPS 提升 40%"],
}


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


def _draft(experiences: list[dict[str, object]], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "headline": "计算机专业本科在读 · 后端开发",
        "summary": "计算机专业本科在读。",
        "experiences": experiences,
        "skills": ["Python", "Go"],
        "education": [],
        "suggestions": ["补充实习时间区间"],
    }
    payload.update(overrides)
    return payload


class BaseResumeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.blocks = blocks_from_profile(PROFILE)

    def test_valid_bullets_keep_their_sources(self) -> None:
        client = FakeClient(
            [
                _draft(
                    [
                        {
                            "heading": "字节跳动 | 后端开发实习",
                            "bullets": [
                                {
                                    "text": "负责推荐接口优化，QPS 提升 40%",
                                    "sources": ["c003"],
                                }
                            ],
                        }
                    ]
                )
            ]
        )

        result = draft_resume(self.blocks, client)

        self.assertIsNotNone(result.content)
        bullet = result.content.experiences[0].bullets[0]
        self.assertEqual(bullet.sources, ["c003"])
        self.assertEqual([chunk.chunk_id for chunk in result.cited], ["c003"])
        self.assertEqual(result.unverified_bullets, 0)
        self.assertFalse(result.degraded)
        self.assertEqual(result.notes, [])

    def test_invented_source_is_dropped_with_the_bullet(self) -> None:
        client = FakeClient(
            [
                _draft(
                    [
                        {
                            "heading": "字节跳动 | 后端开发实习",
                            "bullets": [{"text": "做过推荐系统", "sources": ["c999"]}],
                        }
                    ]
                )
            ]
        )

        result = draft_resume(self.blocks, client)

        self.assertEqual(result.unresolved, ["c999"])
        self.assertEqual(result.unverified_bullets, 1)
        self.assertEqual(result.content.experiences, [])
        self.assertFalse(result.degraded)
        self.assertTrue(any("c999" in note for note in result.notes))
        self.assertTrue(any("1 条要点没有有效出处" in note for note in result.notes))

    def test_number_missing_from_the_cited_text_is_reported(self) -> None:
        client = FakeClient(
            [
                _draft(
                    [
                        {
                            "heading": "字节跳动 | 后端开发实习",
                            "bullets": [
                                {"text": "QPS 提升 45%", "sources": ["c003"]}
                            ],
                        }
                    ]
                )
            ]
        )

        result = draft_resume(self.blocks, client)

        # Rewriting may change wording; changing a number is inventing a result.
        self.assertTrue(any("45%" in note for note in result.notes))
        self.assertEqual(result.content.experiences[0].bullets[0].sources, ["c003"])

    def test_broken_reply_is_retried_once(self) -> None:
        client = FakeClient(
            [
                LLMError("model reply was not JSON"),
                _draft(
                    [
                        {
                            "heading": "字节跳动",
                            "bullets": [{"text": "QPS 提升 40%", "sources": "c003"}],
                        }
                    ]
                ),
            ]
        )

        result = draft_resume(self.blocks, client)

        self.assertEqual(len(client.calls), 2)
        self.assertIn("上一次回复被拒绝了", client.calls[1])
        self.assertEqual(result.content.experiences[0].bullets[0].sources, ["c003"])

    def test_two_broken_replies_degrade_without_raising(self) -> None:
        client = FakeClient([LLMError("boom"), LLMError("boom again")])

        result = draft_resume(self.blocks, client)

        self.assertIsNone(result.content)
        self.assertTrue(result.degraded)
        self.assertTrue(any("模型生成失败" in note for note in result.notes))

    def test_empty_material_never_calls_the_model(self) -> None:
        client = FakeClient([])

        result = draft_resume([], client)

        self.assertEqual(client.calls, [])
        self.assertTrue(result.degraded)
        self.assertEqual(result.chunk_ids, [])

    def test_suggestions_are_kept_but_do_not_rescue_an_empty_draft(self) -> None:
        client = FakeClient(
            [
                {
                    "summary": "",
                    "suggestions": ["补充量化结果"],
                }
            ]
        )

        result = draft_resume(self.blocks, client)

        self.assertEqual(result.content.suggestions, ["补充量化结果"])
        self.assertTrue(result.degraded)


class ProfileBlocksTest(unittest.TestCase):
    def test_only_capability_fields_become_material(self) -> None:
        blocks = blocks_from_profile(
            {
                "summary": "计算机专业本科在读。",
                "skills": ["Python"],
                "experiences": ["字节跳动 后端开发实习"],
                "target_roles": ["算法工程师"],
                "suggested_roles": ["AI 应用开发实习生"],
            }
        )

        text = " ".join(block.text for block in blocks)
        self.assertIn("计算机专业本科在读", text)
        self.assertIn("字节跳动 后端开发实习", text)
        # Where the user wants to go is not something they have done.
        self.assertNotIn("算法工程师", text)
        self.assertNotIn("AI 应用开发实习生", text)


if __name__ == "__main__":
    unittest.main()
