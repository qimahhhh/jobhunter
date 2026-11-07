"""Turn the three profile sources into traceable blocks and prompt-ready chunks.

This is the preparation stage of the Career Agent. An uploaded resume, a
structured profile and free-text self description are all reduced to the same
``Block`` list, packed into ``Chunk`` objects that each carry a stable id, and
rendered into one prompt context. Nothing here calls a model.

The chunk ids are the point: every field the model returns can cite the chunks
it came from, and :func:`unresolved_evidence` turns a fabricated citation into
a plain set difference instead of a guess.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

ChunkMode = Literal["single_pass", "map_reduce"]

DEFAULT_MAX_CHUNK_TOKENS = 900
DEFAULT_CONTEXT_BUDGET = 6000

_CJK_RANGE = "\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af"
_CJK_RE = re.compile(f"[{_CJK_RANGE}]")
# layout=True keeps the horizontal whitespace, so CJK text often arrives as
# "教 育 背 景". Spaces between two CJK characters are always noise.
_CJK_GAP_RE = re.compile(f"(?<=[{_CJK_RANGE}])\\s+(?=[{_CJK_RANGE}])")
_CELL_SPLIT_RE = re.compile(r"\s{2,}")
_SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;\n]?")
_BULLET_RE = re.compile(r"^[-*•·▪◦]\s*|^\d{1,2}[.、)）]\s*")
_PAGE_NUMBER_RE = re.compile(
    r"^(?:[-–—\s]*\d{1,3}[-–—\s]*|第?\s*\d{1,3}\s*页(?:\s*/\s*共?\s*\d{1,3}\s*页)?)$"
)
_NUMBERING_RE = re.compile(
    r"^[#*·•▪◦\-—\s]*(?:\d{1,2}[).、．]|[一二三四五六七八九十]{1,2}[、.．]"
    r"|[（(][一二三四五六七八九十0-9]{1,2}[)）])"
)
_HEADING_PUNCT_RE = re.compile(r"[。；;！!？?，,:：]")

# Section names seen in Chinese and English resumes. A line that matches one of
# these (or starts with one, when short) opens a new section instead of being
# treated as experience text.
_HEADING_WORDS = (
    "个人信息",
    "基本信息",
    "联系方式",
    "求职意向",
    "教育背景",
    "教育经历",
    "实习经历",
    "实习经验",
    "工作经历",
    "工作经验",
    "项目经历",
    "项目经验",
    "科研经历",
    "校园经历",
    "学生工作",
    "社团经历",
    "技能",
    "专业技能",
    "技能特长",
    "证书",
    "获奖情况",
    "荣誉奖项",
    "竞赛经历",
    "自我评价",
    "个人总结",
    "语言能力",
    "研究经历",
    "发表论文",
    "个人项目",
    "profile",
    "summary",
    "objective",
    "education",
    "experience",
    "work experience",
    "internship",
    "projects",
    "skills",
    "awards",
    "honors",
    "publications",
)


@dataclass
class Block:
    """One semantic unit of a source: a line, an entry, or a field."""

    block_id: str
    source: str
    section: str
    text: str
    order: int
    kind: str = "paragraph"


@dataclass
class Chunk:
    """Blocks packed for one model call, with the ids needed to cite them."""

    chunk_id: str
    source: str
    section: str
    text: str
    block_ids: list[str]
    order: int
    tokens: int


@dataclass(frozen=True)
class ContextPlan:
    """How the chunks should be sent: all at once, or in budgeted groups."""

    mode: ChunkMode
    total_tokens: int
    budget: int
    groups: list[list[Chunk]]


def estimate_tokens(text: str) -> int:
    """Rough token count for budgeting, without loading a tokenizer.

    CJK characters cost about one token each on current tokenizers, ASCII about
    four characters per token. Slightly over-estimating is the safe direction
    when the number decides whether the input still fits.
    """

    if not text.strip():
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return cjk + max(1, other // 4)


def _clean_section(text: str) -> str:
    value = text.strip().strip("#*·•▪◦-—[]【】 ")
    value = _NUMBERING_RE.sub("", value, count=1)
    return value.strip().strip(":：】]").strip()


def _looks_like_heading(text: str) -> bool:
    """Guess whether a line is a section heading rather than content.

    Resumes are short lines with no sentence punctuation; keeping the check
    conservative matters more than catching every heading, because a false
    positive moves real experience text into the section label.
    """

    value = _clean_section(text)
    if not value or len(value) > 24:
        return False
    if _HEADING_PUNCT_RE.search(value):
        return False
    if value in _HEADING_WORDS:
        return True
    if len(value) <= 12 and any(value.startswith(word) for word in _HEADING_WORDS):
        return True
    # ``upper() == value`` also holds for text with no cased characters, so a
    # date cell ("2023.09-2027.06"), a bare year or a row of "=" used to open a
    # section and pull the following lines into it. ``isupper()`` needs at least
    # one cased character, and rejecting digits keeps numeric layout cells as
    # content instead of turning them into section labels.
    if (
        value.isascii()
        and value.isupper()
        and len(value) >= 4
        and not any(character.isdigit() for character in value)
    ):
        return True
    return False


def _stamp(blocks: list[Block], prefix: str) -> list[Block]:
    for index, block in enumerate(blocks, start=1):
        block.block_id = f"{prefix}{index:03d}"
        block.order = index - 1
    return blocks


def _assemble(
    entries: Iterable[tuple[str, str]],
    *,
    source: str,
    prefix: str,
) -> list[Block]:
    """Build blocks from ``(kind, text)`` pairs, tracking the current section.

    ``kind`` is ``"heading"`` when the format already knows the line is a
    heading (DOCX styles), which beats guessing from punctuation.
    """

    blocks: list[Block] = []
    section = "other"
    for kind, text in entries:
        value = text.strip()
        if not value:
            continue
        if kind == "heading" or _looks_like_heading(value):
            section = _clean_section(value) or section
            continue
        blocks.append(
            Block(
                block_id="",
                source=source,
                section=section,
                text=value,
                order=len(blocks),
                kind="paragraph",
            )
        )
    return _stamp(blocks, prefix)


def _page_cells(page: Any) -> list[str]:
    """Split one PDF page into layout cells.

    ``extract_text(layout=True)`` keeps horizontal whitespace, so a two-column
    resume arrives as one line per row with a wide gap between the columns.
    Splitting on those gaps keeps each column contiguous; splitting on line
    breaks instead would interleave left and right cells.
    """

    text = page.extract_text(layout=True) or ""
    cells: list[str] = []
    for line in text.splitlines():
        for cell in _CELL_SPLIT_RE.split(line.strip()):
            value = _CJK_GAP_RE.sub("", cell).strip()
            if value:
                cells.append(value)
    return cells


def _strip_page_furniture(pages: Sequence[Sequence[str]]) -> list[list[str]]:
    """Drop page numbers and headers repeated on most pages.

    A resume header printed on every page becomes a separate "experience" for
    the model otherwise, and repeated lines also skew the section detection.
    """

    if len(pages) < 3:
        # Page numbers are the only noise worth removing from a one-page resume.
        return [
            [cell for cell in page if not _PAGE_NUMBER_RE.match(cell.strip())]
            for page in pages
        ]

    kept: list[list[str]] = []
    counts: Counter[str] = Counter()
    for page in pages:
        counts.update({cell.strip() for cell in page})

    threshold = max(2, int(len(pages) * 0.6))
    repeated = {
        cell for cell, count in counts.items() if count >= threshold and len(cell) <= 40
    }
    for page in pages:
        kept.append(
            [
                cell
                for cell in page
                if cell.strip() not in repeated
                and not _PAGE_NUMBER_RE.match(cell.strip())
            ]
        )
    return kept


def blocks_from_pdf(path: str | Path) -> list[Block]:
    """Extract blocks from a PDF resume.

    Expects ``pdfplumber``; imported lazily so the rest of the app runs without
    it. Two-column layouts are handled by splitting each row on wide gaps, not
    by column detection, so unusual layouts still need a manual look.
    """

    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("PDF input needs pdfplumber: pip install pdfplumber") from exc

    pages: list[list[str]] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            pages.append(_page_cells(page))

    cells = [cell for page in _strip_page_furniture(pages) for cell in page]
    return _assemble((("text", cell) for cell in cells), source="resume", prefix="res")


def blocks_from_docx(path: str | Path) -> list[Block]:
    """Extract blocks from a DOCX resume, trusting Word's heading styles."""

    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "DOCX input needs python-docx: pip install python-docx"
        ) from exc

    document = Document(str(path))
    entries: list[tuple[str, str]] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
        if style.startswith("heading") or style in {"title", "subtitle"}:
            entries.append(("heading", text))
        else:
            entries.append(("text", text))

    for table in document.tables:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if values:
                entries.append(("text", " | ".join(values)))

    return _assemble(entries, source="resume", prefix="res")


def blocks_from_text(text: str, *, source: str = "free_text") -> list[Block]:
    """Extract blocks from free text such as a self description."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    cells: list[str] = []
    for paragraph in re.split(r"\n\s*\n", normalized):
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue
        # Only break a paragraph into lines when those lines are clearly a list
        # or carry headings; otherwise joining keeps a sentence whole.
        if len(lines) > 1 and (
            any(_looks_like_heading(line) for line in lines)
            or any(_BULLET_RE.match(line) for line in lines)
        ):
            cells.extend(lines)
        else:
            cells.append(" ".join(lines))

    return _assemble((("text", cell) for cell in cells), source=source, prefix="txt")


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _scalar(value: Any) -> str | None:
    if _is_scalar(value):
        return str(value)
    if isinstance(value, (list, tuple)) and all(_is_scalar(item) for item in value):
        return ", ".join(str(item) for item in value)
    return None


def _field_texts(value: Any) -> list[str]:
    """One text per experience-like entry, so a job is never split in half."""

    if isinstance(value, Mapping):
        pairs = [
            f"{key}: {rendered}"
            for key, child in value.items()
            if (rendered := _scalar(child)) is not None and rendered.strip()
        ]
        return [" | ".join(pairs)] if pairs else []

    if isinstance(value, (list, tuple)):
        texts: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                texts.extend(_field_texts(item))
            elif (rendered := _scalar(item)) is not None and rendered.strip():
                texts.append(rendered)
        return texts

    rendered = _scalar(value)
    return [rendered] if rendered is not None and rendered.strip() else []


def blocks_from_mapping(
    data: Mapping[str, Any], *, source: str = "profile_json"
) -> list[Block]:
    """Extract blocks from an already structured profile.

    The section is the top-level field, so ``experiences`` stays one section and
    its entries pack into the same chunk instead of one chunk per field.
    """

    blocks: list[Block] = []
    for key, value in data.items():
        for text in _field_texts(value):
            blocks.append(
                Block(
                    block_id="",
                    source=source,
                    section=str(key),
                    text=text,
                    order=len(blocks),
                    kind="field",
                )
            )
    return _stamp(blocks, "json")


def merge_blocks(*groups: Iterable[Block]) -> list[Block]:
    """Concatenate blocks from several sources and give them build-wide ids.

    Ids are renumbered here because each source is stamped independently; merge
    before chunking so ``Chunk.block_ids`` is unique across the whole input.
    """

    merged: list[Block] = []
    for group in groups:
        merged.extend(group)
    for index, block in enumerate(merged, start=1):
        merged[index - 1] = replace(block, block_id=f"b{index:04d}", order=index - 1)
    return merged


def _split_sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_RE.findall(text) if part.strip()]


def _slice_text(text: str, max_tokens: int) -> list[str]:
    # Fallback for a single sentence longer than the budget; one CJK character
    # is roughly one token, so slicing by characters is close enough.
    step = max(1, max_tokens)
    return [text[index : index + step] for index in range(0, len(text), step)]


def _split_oversized(block: Block, max_tokens: int) -> list[str]:
    """Split one over-long block on sentence boundaries with a one-line overlap."""

    sentences = _split_sentences(block.text)
    if not sentences:
        return [block.text]

    pieces: list[str] = []
    current: list[str] = []
    running = 0

    for sentence in sentences:
        tokens = estimate_tokens(sentence)
        if tokens > max_tokens:
            if current:
                pieces.append("".join(current))
                current = []
                running = 0
            pieces.extend(_slice_text(sentence, max_tokens))
            continue

        if current and running + tokens > max_tokens:
            pieces.append("".join(current))
            # Repeat the previous sentence so a claim at the boundary keeps its
            # context, unless that sentence alone eats half the budget.
            overlap = (
                current[-1]
                if len(current) > 1 and estimate_tokens(current[-1]) * 2 <= max_tokens
                else ""
            )
            current = [overlap] if overlap else []
            running = estimate_tokens(overlap)

        current.append(sentence)
        running += tokens

    if current:
        pieces.append("".join(current))
    return pieces


def _group_blocks(blocks: Sequence[Block], max_tokens: int) -> list[list[Block]]:
    """Group consecutive blocks so each group's rendered text fits the budget.

    The budget is checked against the text that will actually be sent, not the
    sum of per-block estimates. Per-block estimates floor at one token and skip
    the newline separators, so their sum is optimistic: a group could pass the
    check here and still overflow once joined, which sent ``chunk_blocks`` down
    its split-one-block fallback and lost the rest of the group.
    """

    groups: list[list[Block]] = []
    current: list[Block] = []
    section = ""

    for block in blocks:
        overflows = False
        if current and block.section == section:
            candidate = "\n".join(item.text for item in (*current, block))
            overflows = estimate_tokens(candidate) > max_tokens
        if current and (block.section != section or overflows):
            groups.append(current)
            current = []
        if not current:
            section = block.section
        current.append(block)

    if current:
        groups.append(current)
    return groups


def _make_chunk(index: int, blocks: Sequence[Block], text: str) -> Chunk:
    return Chunk(
        chunk_id=f"c{index + 1:03d}",
        source=blocks[0].source,
        section=blocks[0].section,
        text=text,
        block_ids=[block.block_id for block in blocks],
        order=index,
        tokens=estimate_tokens(text),
    )


def chunk_blocks(
    blocks: Sequence[Block], *, max_tokens: int = DEFAULT_MAX_CHUNK_TOKENS
) -> list[Chunk]:
    """Pack blocks into chunks that never cross a section boundary."""

    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    chunks: list[Chunk] = []
    for group in _group_blocks(blocks, max_tokens):
        text = "\n".join(block.text for block in group)
        if estimate_tokens(text) <= max_tokens:
            chunks.append(_make_chunk(len(chunks), group, text))
            continue
        # A group only reaches this branch when a single block alone is over
        # the budget. Split every block anyway: splitting group[0] and moving
        # on silently dropped the rest, turning a prompt-size problem into
        # missing evidence that no citation could recover.
        for block in group:
            for piece in _split_oversized(block, max_tokens):
                chunks.append(_make_chunk(len(chunks), [block], piece))
    return chunks


def render_context(chunks: Sequence[Chunk]) -> str:
    """Render chunks with the header the model must cite back."""

    return "\n\n".join(
        f"[chunk:{chunk.chunk_id} | source:{chunk.source} | section:{chunk.section}]"
        f"\n{chunk.text}"
        for chunk in chunks
    )


def plan_context(
    chunks: Sequence[Chunk], *, budget: int = DEFAULT_CONTEXT_BUDGET
) -> ContextPlan:
    """Decide between one full-context call and a budgeted map-reduce pass.

    A resume plus a self description normally fits ``single_pass``; the grouped
    branch exists for when job data is added to the same prompt later.
    """

    if budget <= 0:
        raise ValueError("budget must be positive")

    total = estimate_tokens(render_context(chunks))
    if total <= budget:
        return ContextPlan(
            mode="single_pass",
            total_tokens=total,
            budget=budget,
            groups=[list(chunks)],
        )

    groups: list[list[Chunk]] = []
    current: list[Chunk] = []
    running = 0
    for chunk in chunks:
        if current and running + chunk.tokens > budget:
            groups.append(current)
            current = []
            running = 0
        current.append(chunk)
        running += chunk.tokens
    if current:
        groups.append(current)

    return ContextPlan(
        mode="map_reduce", total_tokens=total, budget=budget, groups=groups
    )


def unresolved_evidence(refs: Iterable[str], chunks: Sequence[Chunk]) -> list[str]:
    """Chunk ids the model cited that do not exist.

    A non-empty result means the citation was invented (or the wrong context was
    sent), so the field should be retried rather than trusted.
    """

    known = {chunk.chunk_id for chunk in chunks}
    return [ref for ref in dict.fromkeys(refs) if ref not in known]
