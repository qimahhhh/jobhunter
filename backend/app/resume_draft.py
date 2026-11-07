"""Turn a stored profile into a base resume, one checked bullet at a time.

No job description enters this module. A base resume answers "how do I say what
I did", while the tailored version answers "what should this job see"; mixing
the two produces a resume that is neither.

The contract is the same one the extraction stage uses: every bullet names the
chunks it came from, a bullet whose citations do not exist is dropped instead of
trusted, and a number that does not appear in the cited text is reported as a
warning. Rewriting is allowed; inventing is not.
"""

from __future__ import annotations

import re
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
4. bullet 里的数字必须能在被引用的原文里找到；改数字等同于编造。
5. 不要写求职意向、目标岗位，或任何针对某个 JD 的措辞，那是下一阶段的事。
6. suggestions 写这份简历本身的修改建议：哪些内容该删、哪里缺少量化、哪段过长，每条一句。
7. 只返回一个 JSON 对象，不要 markdown 代码块，不要任何解释文字。字段形状：
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
    """A base resume draft plus what the checks found wrong with it."""

    content: ResumeDraftContent | None
    cited: list[Chunk]
    unresolved: list[str]
    unverified_bullets: int
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
            degraded=True,
            notes=[f"模型生成失败（已重试一次）：{error}"],
            chunk_ids=chunk_ids,
        )

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

    notes: list[str] = []
    if unresolved:
        notes.append("丢弃了不存在的出处：" + "、".join(unresolved))
    if unverified:
        notes.append(f"{unverified} 条要点没有有效出处，已从草稿中移除")
    if number_gaps:
        notes.append("数字缺少原文依据：" + "；".join(number_gaps[:3]))

    content = ResumeDraftContent(
        headline=draft.headline.strip(),
        summary=draft.summary.strip(),
        experiences=experiences,
        skills=[skill.strip() for skill in draft.skills if skill.strip()],
        education=[item.strip() for item in draft.education if item.strip()],
        suggestions=[item.strip() for item in draft.suggestions if item.strip()],
    )

    return DraftResult(
        content=content,
        cited=[known[ref] for ref in used],
        unresolved=unresolved,
        unverified_bullets=unverified,
        degraded=not content.summary.strip() and not content.experiences,
        notes=notes,
        chunk_ids=chunk_ids,
    )
