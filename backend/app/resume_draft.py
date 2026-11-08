"""Turn a stored profile into a base resume, one checked bullet at a time.

No job description enters this module. A base resume answers "how do I say what
I did", while the tailored version answers "what should this job see"; mixing
the two produces a resume that is neither.

The contract is the same one the extraction stage uses: every bullet names the
chunks it came from, a bullet whose citations do not exist is dropped instead of
trusted, and a number that does not appear in the cited text is reported as a
warning. Rewriting is allowed; inventing is not.

A bullet is not the only place a fact can be invented. ``skills`` and
``education`` are copied from the material, so an item whose words appear
nowhere in it is dropped; ``headline``, ``summary`` and every experience
``heading`` carry no citation, so the only check that applies to them is the
number check against the whole material. Wording can be rewritten, a school, a
technology or a figure cannot.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from .chunking import (
    DEFAULT_MAX_CHUNK_TOKENS,
    Block,
    Chunk,
    blocks_from_mapping,
    chunk_blocks,
    merge_blocks,
    render_context,
)
from .llm import LLMClient, LLMError
from .schemas import ResumeBullet, ResumeDraftContent, ResumeExperience

SYSTEM_PROMPT = """你是简历编辑，负责把候选人画像整理成一份基础简历（不针对任何岗位）。

规则：
1. 只能使用材料里已有的事实：公司、项目名、时间、技术栈、数字、成果。不得新增，也不得把没做过的事写成做过。
2. 允许改写措辞、拆分或合并要点、调整顺序，让每条读起来是“做了什么 + 带来什么结果”。
3. 每条 bullet 必须在 sources 里写明依据的材料 chunk id（例如 c002）；出处不存在或写不出来的 bullet 会被删除。
4. bullet、headline、summary 和每条经历的 heading 里的数字，都必须能在材料里找到；改数字等同于编造。
5. skills 和 education 要照抄材料里的原文用词，不要补一个更常见的工具或学校；材料里找不到的技能、学校、专业会被删除。
6. 不要写求职意向、目标岗位，或任何针对某个 JD 的措辞，那是下一阶段的事。
7. suggestions 写这份简历本身的修改建议：哪些内容该删、哪里缺少量化、哪段过长，每条一句。
8. 只返回一个 JSON 对象，不要 markdown 代码块，不要任何解释文字。字段形状：
{
  "headline": "一句话定位，例如 计算机专业本科在读 · 后端与 AI 应用开发",
  "summary": "2-3 句概述，只包含材料里的事实",
  "experiences": [
    {"heading": "公司 | 角色 | 时间", "bullets": [{"text": "……", "sources": ["c002"]}]}
  ],
  "skills": ["按材料原文写"],
  "education": ["学校、专业、时间"],
  "suggestions": ["……"]
}"""

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*%?")


def blocks_from_profile(capabilities: Mapping[str, object]) -> list[Block]:
    """Only the three fields a resume can be built from.

    ``target_roles`` and the suggestion metadata stay out: they describe where
    the user wants to go, not what they have done.
    """

    return blocks_from_mapping(
        {
            "summary": capabilities.get("summary", ""),
            "skills": capabilities.get("skills", []),
            "experiences": capabilities.get("experiences", []),
        },
        source="profile",
    )


def blocks_from_stored_chunks(chunks: Iterable[Mapping[str, object]]) -> list[Block]:
    """Rebuild blocks from the resume record saved during extraction.

    The stored copy is already split by section, so this only has to restore the
    labels; re-chunking then reproduces the same boundaries.
    """

    blocks: list[Block] = []
    for index, chunk in enumerate(chunks):
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        blocks.append(
            Block(
                block_id="",
                source="resume",
                section=str(chunk.get("section") or "resume"),
                text=text,
                order=index,
            )
        )
    return blocks


def _numbers(text: str) -> set[str]:
    """Digits as written, minus separators, so 1,200 and 1200 compare equal."""

    return {
        match.group(0).replace(" ", "").replace(",", "")
        for match in _NUMBER_RE.finditer(text)
    }


# A skill or an education line is made of words, not of citations: "Python",
# "北京邮电大学", "计算机科学与技术". Latin runs keep their internal punctuation
# so "Node.js" and "C++" stay whole; CJK runs are compared as they are written.
_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#._-]*|[\u4e00-\u9fff]{2,}")


def _flatten(text: str) -> str:
    """NFKC, lowercase, no whitespace: the form substring checks compare in.

    Resumes reach a chunk with layout whitespace, full-width punctuation and
    mixed case, so "北京 邮电 大学" and "ｐｙｔｈｏｎ" have to compare equal to the
    plain word before a missing match can be read as a missing fact.
    """

    return "".join(unicodedata.normalize("NFKC", text).lower().split())


def _terms(text: str) -> list[str]:
    """The checkable words of a claim, in the order they were written."""

    normalized = unicodedata.normalize("NFKC", text).lower()
    return [match.group(0) for match in _TERM_RE.finditer(normalized)]


def _unsupported_terms(item: str, material: str) -> list[str]:
    """Terms of ``item`` that appear nowhere in the flattened material.

    ``material`` is the whole source text, not one chunk: a skill may be listed
    in a section that no bullet happened to cite.
    """

    return [
        term for term in dict.fromkeys(_terms(item)) if term not in material
    ]


def _grounded(item: str, material: str) -> bool:
    """Whether at least one word of ``item`` is in the material."""

    terms = _terms(item)
    if not terms:
        # A one-character or punctuation-only item has nothing to match on, so
        # fall back to the raw string instead of calling it unsupported.
        return bool(material) and bool(_flatten(item)) and _flatten(item) in material
    return any(term in material for term in terms)


def _ground_items(
    items: Sequence[str], material: str
) -> tuple[list[str], list[str], list[str]]:
    """Keep the items the material can support, and report the rest.

    An item with no grounded word is a fact nothing in the source backs -- the
    invented skill or school this check exists for -- so it is dropped. An item
    that is only partly grounded ("Python / PyTorch" where the material has
    Python) is kept but reported: dropping it would delete a real line to
    remove half of one, and the user can edit a line they were told about.
    """

    kept: list[str] = []
    dropped: list[str] = []
    partial: list[str] = []
    for item in items:
        if not _grounded(item, material):
            dropped.append(item)
            continue
        unknown = _unsupported_terms(item, material)
        if unknown:
            partial.append(f"{item}（{'、'.join(unknown)} 未在材料中出现）")
        kept.append(item)
    return kept, dropped, partial


def _number_gap(label: str, text: str, material_numbers: set[str]) -> str | None:
    """A field with no citation still has numbers, and numbers are checkable."""

    missing = _numbers(text) - material_numbers
    if not missing:
        return None
    return (
        f"{label}「{text[:30]}」里的 {'、'.join(sorted(missing))} 没有出现在材料中"
    )


def _user_prompt(context: str, hint: str = "") -> str:
    prompt = (
        "候选人材料如下，每段以一个 [chunk:... | source:... | section:...] 表头开始：\n\n"
        f"{context}\n\n只返回 JSON 对象。"
    )
    if hint:
        prompt = (
            f"{prompt}\n\n上一次回复被拒绝了：{hint}\n"
            "请严格按照要求的 JSON 结构重新回答一次。"
        )
    return prompt


@dataclass(frozen=True)
class DraftResult:
    """A base resume draft plus what the checks found wrong with it.

    ``unverified_bullets`` counts dropped experiences lines, ``unverified_fields``
    counts dropped skill and education items; they are separate because they are
    dropped by different checks and mean different things to the user.
    """

    content: ResumeDraftContent | None
    cited: list[Chunk]
    unresolved: list[str]
    unverified_bullets: int
    unverified_fields: int
    degraded: bool
    notes: list[str]
    chunk_ids: list[str]


def _draft(client: LLMClient, context: str, hint: str = "") -> ResumeDraftContent:
    payload = client.complete_json(system=SYSTEM_PROMPT, user=_user_prompt(context, hint))
    return ResumeDraftContent.model_validate(payload)


def _draft_with_retry(
    client: LLMClient, context: str
) -> tuple[ResumeDraftContent | None, str]:
    error = ""
    for _ in range(2):
        try:
            return _draft(client, context, hint=error), ""
        except (LLMError, ValidationError) as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
    return None, error


def draft_resume(
    blocks: Sequence[Block],
    client: LLMClient,
    *,
    max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
) -> DraftResult:
    """Build the resume, then throw away every claim that cannot be checked."""

    chunks = chunk_blocks(merge_blocks(blocks), max_tokens=max_chunk_tokens)
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if not chunks:
        return DraftResult(
            content=None,
            cited=[],
            unresolved=[],
            unverified_bullets=0,
            unverified_fields=0,
            degraded=True,
            notes=["画像没有产生任何 block，无法生成简历"],
            chunk_ids=[],
        )

    known = {chunk.chunk_id: chunk for chunk in chunks}
    draft, error = _draft_with_retry(client, render_context(chunks))
    if draft is None:
        return DraftResult(
            content=None,
            cited=[],
            unresolved=[],
            unverified_bullets=0,
            unverified_fields=0,
            degraded=True,
            notes=[f"模型生成失败（已重试一次）：{error}"],
            chunk_ids=chunk_ids,
        )

    # The whole material, used by the checks that have no citation to lean on.
    # A skill may be listed in a section no bullet cited, so this is the union.
    material = _flatten(" ".join(chunk.text for chunk in chunks))
    material_numbers = {number for chunk in chunks for number in _numbers(chunk.text)}

    unresolved: list[str] = []
    unverified = 0
    number_gaps: list[str] = []
    used: dict[str, None] = {}
    experiences: list[ResumeExperience] = []

    for experience in draft.experiences:
        bullets: list[ResumeBullet] = []
        for bullet in experience.bullets:
            refs = [ref.strip() for ref in dict.fromkeys(bullet.sources) if ref.strip()]
            valid = [ref for ref in refs if ref in known]
            unresolved.extend(
                ref for ref in refs if ref not in known and ref not in unresolved
            )
            if not valid:
                unverified += 1
                continue

            missing = _numbers(bullet.text) - _numbers(
                " ".join(known[ref].text for ref in valid)
            )
            if missing:
                number_gaps.append(
                    f"「{bullet.text[:30]}」里的 {'、'.join(sorted(missing))} 没有出现在被引原文中"
                )

            for ref in valid:
                used.setdefault(ref, None)
            bullets.append(ResumeBullet(text=bullet.text, sources=valid))

        if bullets:
            experiences.append(
                ResumeExperience(heading=experience.heading.strip(), bullets=bullets)
            )

    # These fields have no sources to resolve, so a fabricated one used to pass
    # straight through: a school the user never attended or a stack they never
    # touched landed in the resume while `degraded` stayed False.
    skills, dropped_skills, partial_skills = _ground_items(
        [skill.strip() for skill in draft.skills if skill.strip()], material
    )
    education, dropped_education, partial_education = _ground_items(
        [item.strip() for item in draft.education if item.strip()], material
    )
    dropped_items = dropped_skills + dropped_education
    partial_items = partial_skills + partial_education

    for label, text in [
        ("headline", draft.headline),
        ("summary", draft.summary),
        *(("经历标题", item.heading) for item in draft.experiences),
    ]:
        gap = _number_gap(label, text, material_numbers)
        if gap:
            number_gaps.append(gap)

    notes: list[str] = []
    if unresolved:
        notes.append("丢弃了不存在的出处：" + "、".join(unresolved))
    if unverified:
        notes.append(f"{unverified} 条要点没有有效出处，已从草稿中移除")
    if number_gaps:
        # Every gap, not the first few: a check that stops reporting after three
        # leaves the user unable to tell a four-gap draft from a clean one.
        notes.append(
            f"数字缺少原文依据（共 {len(number_gaps)} 处）：" + "；".join(number_gaps)
        )
    if dropped_items:
        notes.append(
            f"丢弃了材料里没有依据的 {len(dropped_items)} 条技能/学历："
            + "、".join(dropped_items)
        )
    if partial_items:
        notes.append(
            "这些条目只有部分词语能在材料里找到，请人工核对："
            + "；".join(partial_items)
        )

    content = ResumeDraftContent(
        headline=draft.headline.strip(),
        summary=draft.summary.strip(),
        experiences=experiences,
        skills=skills,
        education=education,
        suggestions=[item.strip() for item in draft.suggestions if item.strip()],
    )

    return DraftResult(
        content=content,
        cited=[known[ref] for ref in used],
        unresolved=unresolved,
        unverified_bullets=unverified,
        unverified_fields=len(dropped_items),
        degraded=not content.summary.strip() and not content.experiences,
        notes=notes,
        chunk_ids=chunk_ids,
    )
