"""Tests for the file entry points: PDF layout cells and DOCX styles.

Everything above ``blocks_from_pdf`` is pure data, so these tests feed the
parser's output directly instead of committing a resume PDF as a fixture. A
real resume in the repository would be both a privacy problem and a slow test;
the parts that break on a real resume are the cell splitting and the section
assignment, which is exactly what happens here.

Two known gaps are deliberately not locked in yet, because they are bugs, not
behaviour: a cell that starts mid-word after a PDF line wrap ("候" at the end
of one line, "选提取" at the start of the next) is still stored as text with a
newline glued in, and a resume whose section headings print after their
content still assigns the content to the previous section.
"""

from __future__ import annotations

from io import BytesIO
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from backend.app.chunking import (
    _page_cells,
    blocks_from_docx,
    blocks_from_pages,
    blocks_from_pdf,
)


class FakePage:
    """Stands in for a pdfplumber page, which only needs ``extract_text``."""

    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self, layout: bool = False) -> str:
        return self._text


class PageCellTest(unittest.TestCase):
    def test_two_column_row_is_split_on_the_wide_gap(self) -> None:
        page = FakePage("张三            2024.09 - 2028.06")

        self.assertEqual(_page_cells(page), ["张三", "2024.09 - 2028.06"])

    def test_space_between_cjk_characters_is_removed(self) -> None:
        page = FakePage("教 育 背 景")

        self.assertEqual(_page_cells(page), ["教育背景"])

    def test_right_column_does_not_absorb_the_next_heading(self) -> None:
        page = FakePage("张三            2024.09 - 2028.06\n教育背景            Python、Go")
        blocks = blocks_from_pages([_page_cells(page)])

        self.assertEqual([block.text for block in blocks], ["张三", "2024.09 - 2028.06", "Python、Go"])
        self.assertEqual(
            [block.section for block in blocks], ["other", "other", "教育背景"]
        )


class PageFurnitureIntegrationTest(unittest.TestCase):
    def test_repeated_header_and_page_numbers_never_reach_a_block(self) -> None:
        pages = [
            ["张三 简历", "第1页", "实习经历"],
            ["张三 简历", "第2页", "负责推荐接口的性能优化。"],
            ["张三 简历", "第3页", "技能"],
        ]

        blocks = blocks_from_pages(pages)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].text, "负责推荐接口的性能优化。")
        self.assertEqual(blocks[0].section, "实习经历")
        self.assertTrue(all("张三" not in block.text for block in blocks))


class RecordingPage(FakePage):
    """A page that remembers whether it was read in layout mode."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.layout_used: bool | None = None

    def extract_text(self, layout: bool = False) -> str:
        self.layout_used = layout
        return super().extract_text(layout=layout)


class FakePdfHandle:
    """Stands in for ``pdfplumber.open(...)``, which is a context manager."""

    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> "FakePdfHandle":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class FakePdfplumber(types.ModuleType):
    """A stand-in for the lazily imported pdfplumber module."""

    def __init__(self, pages: list[FakePage]) -> None:
        super().__init__("pdfplumber")
        self._pages = pages
        self.opened_path: str | None = None

    def open(self, path: str) -> FakePdfHandle:
        self.opened_path = path
        return FakePdfHandle(self._pages)


class PdfEntryTest(unittest.TestCase):
    """The glue between ``blocks_from_pdf`` and pdfplumber.

    Without a real file, so the parts that could break on a file are still
    exercised: every page is read, layout mode is on, and a missing library
    produces the install hint instead of an ImportError.
    """

    def test_every_page_is_read_in_layout_mode(self) -> None:
        first = RecordingPage("张三            2024.09 - 2028.06")
        second = RecordingPage("实习经历\n负责推荐接口的性能优化。")
        module = FakePdfplumber([first, second])

        with mock.patch.dict(sys.modules, {"pdfplumber": module}):
            blocks = blocks_from_pdf("resume.pdf")

        self.assertEqual(module.opened_path, "resume.pdf")
        self.assertEqual([first.layout_used, second.layout_used], [True, True])
        self.assertEqual(
            [block.text for block in blocks],
            ["张三", "2024.09 - 2028.06", "负责推荐接口的性能优化。"],
        )
        self.assertEqual(blocks[-1].section, "实习经历")

    def test_missing_pdfplumber_names_the_install_command(self) -> None:
        with mock.patch.dict(sys.modules, {"pdfplumber": None}):
            with self.assertRaises(RuntimeError) as raised:
                blocks_from_pdf("resume.pdf")

        self.assertIn("pdfplumber", str(raised.exception))

    def test_binary_stream_is_handed_to_pdfplumber_unconverted(self) -> None:
        module = FakePdfplumber([RecordingPage("张三")])
        stream = BytesIO(b"%PDF-fake")

        with mock.patch.dict(sys.modules, {"pdfplumber": module}):
            blocks = blocks_from_pdf(stream)

        # The upload route hands the parser a stream. Converting it with str()
        # would pass pdfplumber a filename like "<_io.BytesIO object at 0x...>".
        self.assertIs(module.opened_path, stream)
        self.assertEqual([block.text for block in blocks], ["张三"])


class DocxSourceTest(unittest.TestCase):
    def _write_docx(self, directory: str) -> Path:
        try:
            from docx import Document
        except ImportError:  # pragma: no cover - dependency guard
            raise unittest.SkipTest("python-docx is not installed")

        path = Path(directory) / "resume.docx"
        document = Document()
        document.add_heading("实习经历", level=1)
        document.add_paragraph("字节跳动 后端开发实习")
        document.add_paragraph("")  # empty paragraphs must not become blocks
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Python"
        table.cell(0, 1).text = "Go"
        document.save(path)
        return path

    def test_heading_style_beats_the_punctuation_guess(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocks = blocks_from_docx(self._write_docx(directory))

        self.assertEqual(blocks[0].text, "字节跳动 后端开发实习")
        self.assertEqual(blocks[0].section, "实习经历")

    def test_table_row_becomes_one_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocks = blocks_from_docx(self._write_docx(directory))

        self.assertEqual(blocks[-1].text, "Python | Go")
        self.assertEqual(blocks[-1].section, "实习经历")

    def test_empty_paragraphs_are_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocks = blocks_from_docx(self._write_docx(directory))

        self.assertEqual(len(blocks), 2)
        self.assertTrue(all(block.text.strip() for block in blocks))


if __name__ == "__main__":
    unittest.main()
