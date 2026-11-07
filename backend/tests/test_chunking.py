from __future__ import annotations

import unittest

from backend.app.chunking import (
    Block,
    _strip_page_furniture,
    blocks_from_mapping,
    blocks_from_text,
    chunk_blocks,
    estimate_tokens,
    merge_blocks,
    plan_context,
    render_context,
    unresolved_evidence,
)

RESUME_TEXT = """张三
教育背景
北京邮电大学 计算机科学与技术 2023.09-2027.06
实习经历
2025.03-2025.06 字节跳动 后端开发实习
负责推荐接口的性能优化，QPS 提升 40%。
技能
Python、Go、SQL
"""


class ResumeSectionTest(unittest.TestCase):
    def test_resume_headings_become_sections(self) -> None:
        blocks = blocks_from_text(RESUME_TEXT)

        self.assertEqual(
            [block.section for block in blocks],
            ["other", "教育背景", "实习经历", "实习经历", "技能"],
        )

    def test_key_value_line_is_not_mistaken_for_a_heading(self) -> None:
        blocks = blocks_from_text("技能：Python、Go\n负责后端开发工作，维护三个服务。")

        self.assertEqual(blocks[0].section, "other")
        self.assertIn("Python", blocks[0].text)

    def test_date_cell_is_not_mistaken_for_a_heading(self) -> None:
        blocks = blocks_from_text(
            "2023.09-2027.06\n\n北京邮电大学 计算机科学与技术\n\n2024"
        )

        self.assertEqual([block.section for block in blocks], ["other"] * 3)
        self.assertEqual(blocks[0].text, "2023.09-2027.06")
        self.assertEqual(blocks[2].text, "2024")

    def test_separator_row_is_not_mistaken_for_a_heading(self) -> None:
        blocks = blocks_from_text("========\n\n负责后端开发工作，维护三个服务。")

        self.assertEqual(blocks[0].section, "other")
        self.assertEqual(blocks[0].text, "========")

    def test_all_caps_heading_still_opens_a_section(self) -> None:
        blocks = blocks_from_text("TECHNICAL SKILLS\n\nPython、Go、SQL")

        self.assertEqual(blocks[0].section, "TECHNICAL SKILLS")
        self.assertIn("Python", blocks[0].text)

    def test_chunks_never_cross_a_section_boundary(self) -> None:
        chunks = chunk_blocks(blocks_from_text(RESUME_TEXT))

        self.assertEqual(
            [chunk.section for chunk in chunks],
            ["other", "教育背景", "实习经历", "技能"],
        )
        self.assertIn("QPS", chunks[2].text)
        self.assertEqual(len(chunks[2].block_ids), 2)

    def test_ids_stay_addressable(self) -> None:
        chunks = chunk_blocks(blocks_from_text(RESUME_TEXT))
        rendered = render_context(chunks)

        for chunk in chunks:
            self.assertIn(f"[chunk:{chunk.chunk_id} | source:{chunk.source}", rendered)


class OversizedBlockTest(unittest.TestCase):
    def _long_block(self, sentences: list[str]) -> Block:
        return Block(
            block_id="b0001",
            source="resume",
            section="实习经历",
            text="".join(sentences),
            order=0,
        )

    def test_over_long_block_is_split_on_sentences(self) -> None:
        sentences = [
            f"第{index}段经历负责推荐系统的接口优化与性能调优。" for index in range(1, 9)
        ]
        chunks = chunk_blocks([self._long_block(sentences)], max_tokens=60)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.tokens <= 60 for chunk in chunks))

    def test_split_repeats_the_previous_sentence_as_overlap(self) -> None:
        sentences = [
            f"第{index}段经历负责推荐系统的接口优化与性能调优。" for index in range(1, 9)
        ]
        chunks = chunk_blocks([self._long_block(sentences)], max_tokens=60)

        self.assertTrue(chunks[1].text.startswith(sentences[1]))
        self.assertIn(sentences[1], chunks[0].text)

    def test_single_sentence_over_budget_is_still_split(self) -> None:
        block = self._long_block(["熟悉" + "机器学习" * 200 + "。"])
        chunks = chunk_blocks([block], max_tokens=50)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.text.strip() for chunk in chunks))


class BlockCoverageTest(unittest.TestCase):
    def test_short_blocks_are_not_dropped_when_the_join_overflows(self) -> None:
        # Three 7-character blocks estimate to one token each, so their sum fits
        # a 4-token budget while the joined text estimates to five.
        blocks = [
            Block(
                block_id=f"b{index:04d}",
                source="resume",
                section="skills",
                text="abcdefg",
                order=index,
            )
            for index in range(3)
        ]

        chunks = chunk_blocks(blocks, max_tokens=4)

        covered = {block_id for chunk in chunks for block_id in chunk.block_ids}
        self.assertEqual(covered, {"b0000", "b0001", "b0002"})

    def test_every_block_survives_every_budget(self) -> None:
        blocks = blocks_from_text(RESUME_TEXT)
        expected = {block.block_id for block in blocks}

        for max_tokens in (4, 8, 16, 40, 900):
            with self.subTest(max_tokens=max_tokens):
                chunks = chunk_blocks(blocks, max_tokens=max_tokens)
                covered = {
                    block_id for chunk in chunks for block_id in chunk.block_ids
                }

                self.assertEqual(covered, expected)
                self.assertTrue(all(chunk.text.strip() for chunk in chunks))


class StructuredSourceTest(unittest.TestCase):
    def test_each_experience_stays_in_one_block(self) -> None:
        blocks = blocks_from_mapping(
            {
                "summary": "计算机专业学生",
                "skills": ["Python", "SQL"],
                "experiences": [
                    {"company": "字节跳动", "title": "后端开发实习"},
                    {"company": "阿里巴巴", "title": "算法实习"},
                ],
            }
        )

        experiences = [block for block in blocks if block.section == "experiences"]
        self.assertEqual(len(experiences), 2)
        self.assertIn("字节跳动", experiences[0].text)
        self.assertIn("title", experiences[0].text)
        self.assertEqual(experiences[0].kind, "field")

    def test_nested_mapping_keeps_its_fields(self) -> None:
        blocks = blocks_from_mapping({"a": {"b": {"c": 1}}})

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].section, "a")
        self.assertEqual(blocks[0].text, "b: c: 1")

    def test_nested_mapping_keeps_the_key_path(self) -> None:
        blocks = blocks_from_mapping(
            {"education": {"school": {"name": "北京邮电大学", "city": "北京"}}}
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].section, "education")
        self.assertEqual(blocks[0].text, "school: name: 北京邮电大学 | city: 北京")

    def test_scalars_beside_a_nested_mapping_both_survive(self) -> None:
        blocks = blocks_from_mapping(
            {"profile": {"name": "张三", "links": {"github": "github.com/zhangsan"}}}
        )

        self.assertEqual(
            [block.text for block in blocks],
            ["name: 张三", "links: github: github.com/zhangsan"],
        )

    def test_empty_nested_mapping_adds_no_block(self) -> None:
        self.assertEqual(blocks_from_mapping({"profile": {"links": {}}}), [])

    def test_merge_blocks_gives_unique_ids_across_sources(self) -> None:
        merged = merge_blocks(
            blocks_from_text("实习经历\n负责接口优化。"),
            blocks_from_mapping({"skills": ["Go"]}),
        )

        ids = [block.block_id for block in merged]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(ids[0].startswith("b"))


class ContextBudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.chunks = chunk_blocks(blocks_from_text(RESUME_TEXT))

    def test_small_input_is_sent_in_one_pass(self) -> None:
        plan = plan_context(self.chunks, budget=6000)

        self.assertEqual(plan.mode, "single_pass")
        self.assertEqual(len(plan.groups), 1)
        self.assertEqual(len(plan.groups[0]), len(self.chunks))

    def test_tight_budget_switches_to_grouped_sending(self) -> None:
        plan = plan_context(self.chunks, budget=10)

        self.assertEqual(plan.mode, "map_reduce")
        self.assertGreater(len(plan.groups), 1)

    def test_budget_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            plan_context(self.chunks, budget=0)


class EvidenceCheckTest(unittest.TestCase):
    def test_unknown_chunk_id_is_reported(self) -> None:
        chunks = chunk_blocks(blocks_from_text(RESUME_TEXT))

        missing = unresolved_evidence(
            [chunks[0].chunk_id, "c999", "c999"], chunks
        )

        self.assertEqual(missing, ["c999"])

    def test_cjk_text_produces_a_non_zero_budget_estimate(self) -> None:
        self.assertGreater(estimate_tokens("熟悉机器学习"), 4)
        self.assertEqual(estimate_tokens("   "), 0)


class PageFurnitureTest(unittest.TestCase):
    def test_repeated_header_and_page_numbers_are_dropped(self) -> None:
        pages = [
            ["张三 简历", "第1页", "字节跳动 后端实习"],
            ["张三 简历", "第2页", "阿里巴巴 算法实习"],
            ["张三 简历", "第3页", "技能 Python"],
        ]

        cleaned = _strip_page_furniture(pages)

        self.assertEqual(cleaned[0], ["字节跳动 后端实习"])
        self.assertEqual(cleaned[2], ["技能 Python"])

    def test_short_document_keeps_its_content(self) -> None:
        pages = [["教育背景", "北京邮电大学"], ["项目经历", "求职助手"]]

        self.assertEqual(_strip_page_furniture(pages), pages)


if __name__ == "__main__":
    unittest.main()
