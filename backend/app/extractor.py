"""Turn resume text into a checked profile draft with one model call.

The chunk ids are the contract. The model may only cite ids that exist in the
context it was given, and any citation that does not exist is reported back
instead of being trusted, so a profile the model invented is visible as
``degraded`` rather than as a confident wrong answer.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from .chunking import (
    DEFAULT_CONTEXT_BUDGET,
    Block,
    Chunk,
    blocks_from_text,
    chunk_blocks,
    merge_blocks,
    plan_context,
    render_context,
    unresolved_evidence,
)
from .llm import LLMClient, LLMError
from .schemas import ProfileDraft, ProfileInput

SYSTEM_PROMPT = """你是简历抽取器。把给定的简历上下文整理成一份结构化候选人画像。

规则：
1. 只使用上下文里出现过的事实。不要补充技能、公司、日期、学校或数字。
2. summary、skills、experiences 里的每条结论都要有出处：把上下文里 chunk 表头的 id（例如 c001）填进 evidence。没有有效 chunk id 支撑的结论会被丢弃。
3. recommended_roles 是从技能和经历推断的可探索岗位方向，missing_information 是简历里缺失、值得向用户补充询问的信息；这两项属于推断和信息缺口，不写进 evidence，推不出来就留空数组。
4. 只返回一个 JSON 对象。不要 markdown 代码块，不要任何解释文字。
5. 字段形状：
{
  "summary": "2-3 句话介绍这位候选人，不要写简历里没有的形容词",
  "skills": ["具体的语言、工具、方法，按简历原文写"],
  "experiences": ["每段实习或项目一条，保留角色、组织和量化结果"],
  "recommended_roles": ["根据技能和经历推断的岗位方向，例如 AI 应用开发实习生；推不出来就留空"],
  "missing_information": ["简历里缺失、建议向用户补充询问的信息，例如期望城市、可实习时长；没有就留空"],
  "evidence": ["c001"]
}"""


MERGE_PROMPT = """你是简历抽取结果的合并器。给你同一份材料在不同分段上得到的几份局部画像，请合并成一份。

规则：
1. 只合并已经有的事实和数字，不要新增任何技能、公司、日期或成绩。
2. 同一个内容重复出现时，保留表述最完整的一条。
3. summary 要覆盖全部分段，不要只讲其中一段。
4. evidence 取并集，只能使用局部画像里已经出现过的 chunk id。
5. 只返回一个 JSON 对象，字段与局部画像相同。"""


def _user_prompt(context: str, hint: str = "") -> str:
    prompt = (
        "简历上下文如下，每段以一个 [chunk:... | source:... | section:...] 表头开始：\n\n"
        f"{context}\n\n只返回 JSON 对象。"
    )
    if hint:
        prompt = (
            f"{prompt}\n\n上一次回复被拒绝了：{hint}\n"
            "请严格按照要求的 JSON 结构重新回答一次。"
        )
    return prompt


@dataclass(frozen=True)
class ExtractionResult:
    """What one extraction attempt produced.

    ``degraded`` is the field callers must check: a draft without a single
    valid chunk id is unchecked, and showing it as a verified profile is the
    failure mode this whole module exists to prevent.
    """

    profile: ProfileInput | None
    recommended_roles: list[str]
    missing_information: list[str]
    evidence: list[str]
    unresolved: list[str]
    chunk_ids: list[str]
    degraded: bool
    notes: list[str]


def _draft(client: LLMClient, context: str, hint: str = "") -> ProfileDraft:
    payload = client.complete_json(system=SYSTEM_PROMPT, user=_user_prompt(context, hint))
    return ProfileDraft.model_validate(payload)


def _draft_with_retry(
    client: LLMClient, context: str
) -> tuple[ProfileDraft | None, str]:
    """One call, repeated once with the rejection reason as a hint.

    A malformed reply is usually a formatting slip rather than a reason to send
    the user back to an empty form.
    """

    error = ""
    for _ in range(2):
        try:
            return _draft(client, context, hint=error), ""
        except (LLMError, ValidationError) as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
    return None, error


def _union(values: Iterable[str]) -> list[str]:
    """Order-preserving dedupe across the partial drafts."""

    seen: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _merge_parts(parts: Sequence[ProfileDraft]) -> ProfileDraft:
    """Deterministic fallback when the merge call itself fails.

    Lists are unioned and the first usable summary is kept, so the user still
    gets everything that was extracted instead of an error page.
    """

    return ProfileDraft(
        summary=next(
            (part.summary.strip() for part in parts if part.summary.strip()), ""
        ),
        skills=_union(skill for part in parts for skill in part.skills),
        experiences=_union(item for part in parts for item in part.experiences),
        recommended_roles=_union(
            role for part in parts for role in part.recommended_roles
        ),
        missing_information=_union(
            item for part in parts for item in part.missing_information
        ),
        evidence=_union(ref for part in parts for ref in part.evidence),
    )


def _merge_with_model(
    client: LLMClient, parts: Sequence[ProfileDraft]
) -> ProfileDraft | None:
    """Ask the model to fold the partial drafts into one.

    The partial drafts are handed over as JSON so the merger has nothing to
    summarize from memory, and the reply is validated against the same schema.
    """

    payload = "\n\n".join(
        f"[part:{index}]\n{json.dumps(part.model_dump(), ensure_ascii=False)}"
        for index, part in enumerate(parts, start=1)
    )
    try:
        reply = client.complete_json(
            system=MERGE_PROMPT,
            user=f"局部画像如下：\n\n{payload}\n\n只返回合并后的 JSON 对象。",
        )
        return ProfileDraft.model_validate(reply)
    except (LLMError, ValidationError):
        return None


def _draft_in_groups(
    client: LLMClient,
    groups: Sequence[Sequence[Chunk]],
    notes: list[str],
) -> tuple[ProfileDraft | None, str]:
    """Extract each group on its own, then merge the partial drafts.

    A group that fails twice is reported and skipped: one unreadable section
    should not cost the user the rest of the material.
    """

    parts: list[ProfileDraft] = []
    error = ""
    for group in groups:
        part, group_error = _draft_with_retry(client, render_context(group))
        if part is None:
            error = group_error
            continue
        parts.append(part)

    if not parts:
        return None, error or "所有分组都抽取失败"

    failed = len(groups) - len(parts)
    if failed:
        notes.append(f"{failed} 个分组抽取失败，合并结果可能不完整：{error}")

    merged = _merge_with_model(client, parts)
    if merged is None:
        notes.append("合并调用失败，已按去重拼接合并，summary 只保留了第一段可用内容")
        return _merge_parts(parts), ""

    notes.append(f"输入超出单次上下文预算，分 {len(groups)} 组抽取后合并")
    return merged, ""


def extract_profile(
    text: str,
    client: LLMClient,
    *,
    max_chunk_tokens: int = 900,
    max_context_tokens: int = DEFAULT_CONTEXT_BUDGET,
) -> ExtractionResult:
    """Chunk free text and turn it into a checked draft."""

    return extract_profile_from_blocks(
        blocks_from_text(text),
        client,
        max_chunk_tokens=max_chunk_tokens,
        max_context_tokens=max_context_tokens,
    )


def extract_profile_from_blocks(
    blocks: Sequence[Block],
    client: LLMClient,
    *,
    max_chunk_tokens: int = 900,
    max_context_tokens: int = DEFAULT_CONTEXT_BUDGET,
) -> ExtractionResult:
    """Same pipeline, for blocks that came from a file or from several sources.

    ``blocks_from_pdf`` and ``blocks_from_docx`` do layout work that
    ``blocks_from_text`` cannot, so a file has to enter here instead of being
    flattened back into a string and re-split as plain text.

    When the rendered chunks exceed ``max_context_tokens`` the material is
    extracted group by group and merged, because trimming the prompt would
    quietly change the answer instead of failing.
    """

    return extract_profile_from_chunks(
        chunk_blocks(merge_blocks(blocks), max_tokens=max_chunk_tokens),
        client,
        max_context_tokens=max_context_tokens,
    )


def extract_profile_from_chunks(
    chunks: Sequence[Chunk],
    client: LLMClient,
    *,
    max_context_tokens: int = DEFAULT_CONTEXT_BUDGET,
) -> ExtractionResult:
    """Extract from chunks that were already built, and possibly already stored.

    Split out so a route can persist the chunks it is about to send: a citation
    is only resolvable afterwards if the stored chunk ids are the ones the model
    actually saw.
    """

    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if not chunks:
        return ExtractionResult(
            profile=None,
            recommended_roles=[],
            missing_information=[],
            evidence=[],
            unresolved=[],
            chunk_ids=[],
            degraded=True,
            notes=["简历原文没有产生任何 block，检查输入是否为空或全是格式噪声"],
        )

    plan = plan_context(chunks, budget=max_context_tokens)
    notes: list[str] = []

    if plan.mode == "single_pass":
        draft, error = _draft_with_retry(client, render_context(chunks))
    else:
        draft, error = _draft_in_groups(client, plan.groups, notes)

    if draft is None:
        return ExtractionResult(
            profile=None,
            recommended_roles=[],
            missing_information=[],
            evidence=[],
            unresolved=[],
            chunk_ids=chunk_ids,
            degraded=True,
            notes=notes + [f"模型抽取失败（已重试一次）：{error}"],
        )

    unresolved = unresolved_evidence(draft.evidence, chunks)
    evidence = [ref for ref in dict.fromkeys(draft.evidence) if ref not in unresolved]

    if unresolved:
        notes.append("丢弃了没有 chunk 支撑的引用：" + ", ".join(unresolved))
    if not evidence:
        notes.append("模型没有给出任何有效 chunk id，这份草稿未经验证，不要当成已验证画像展示")

    profile = None
    if draft.summary.strip():
        profile = ProfileInput(
            summary=draft.summary.strip(),
            skills=[skill.strip() for skill in draft.skills if skill.strip()],
            experiences=[item.strip() for item in draft.experiences if item.strip()],
        )
    else:
        notes.append("模型没有返回 summary，这份草稿无法作为画像使用")

    return ExtractionResult(
        profile=profile,
        recommended_roles=[
            role.strip() for role in draft.recommended_roles if role.strip()
        ],
        missing_information=[
            item.strip() for item in draft.missing_information if item.strip()
        ],
        evidence=evidence,
        unresolved=unresolved,
        chunk_ids=chunk_ids,
        degraded=profile is None or not evidence,
        notes=notes,
    )
