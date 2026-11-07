"""Turn resume text into a checked profile draft with one model call.

The chunk ids are the contract. The model may only cite ids that exist in the
context it was given, and any citation that does not exist is reported back
instead of being trusted, so a profile the model invented is visible as
``degraded`` rather than as a confident wrong answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from .chunking import (
    blocks_from_text,
    chunk_blocks,
    merge_blocks,
    render_context,
    unresolved_evidence,
)
from .llm import LLMClient, LLMError
from .schemas import ProfileDraft, ProfileInput

SYSTEM_PROMPT = """你是简历抽取器。把给定的简历上下文整理成一份结构化候选人画像。

规则：
1. 只使用上下文里出现过的事实。不要补充技能、公司、日期、学校或数字。
2. 每条结论都要有出处：把上下文里 chunk 表头的 id（例如 c001）填进 evidence。没有有效 chunk id 支撑的结论会被丢弃。
3. 只返回一个 JSON 对象。不要 markdown 代码块，不要任何解释文字。
4. 字段形状：
{
  "summary": "2-3 句话介绍这位候选人，不要写简历里没有的形容词",
  "skills": ["具体的语言、工具、方法，按简历原文写"],
  "experiences": ["每段实习或项目一条，保留角色、组织和量化结果"],
  "evidence": ["c001"]
}"""


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
    evidence: list[str]
    unresolved: list[str]
    chunk_ids: list[str]
    degraded: bool
    notes: list[str]


def _draft(client: LLMClient, context: str, hint: str = "") -> ProfileDraft:
    payload = client.complete_json(system=SYSTEM_PROMPT, user=_user_prompt(context, hint))
    return ProfileDraft.model_validate(payload)


def extract_profile(
    text: str,
    client: LLMClient,
    *,
    max_chunk_tokens: int = 900,
) -> ExtractionResult:
    """Chunk the resume, ask the model once, and check what came back."""

    blocks = merge_blocks(blocks_from_text(text))
    chunks = chunk_blocks(blocks, max_tokens=max_chunk_tokens)
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if not chunks:
        return ExtractionResult(
            profile=None,
            evidence=[],
            unresolved=[],
            chunk_ids=[],
            degraded=True,
            notes=["简历原文没有产生任何 block，检查输入是否为空或全是格式噪声"],
        )

    context = render_context(chunks)

    draft: ProfileDraft | None = None
    error = ""
    # One retry, because a malformed reply is usually a formatting slip rather
    # than a reason to send the user back to an empty form.
    for _ in range(2):
        try:
            draft = _draft(client, context, hint=error)
            break
        except (LLMError, ValidationError) as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]

    if draft is None:
        return ExtractionResult(
            profile=None,
            evidence=[],
            unresolved=[],
            chunk_ids=chunk_ids,
            degraded=True,
            notes=[f"模型抽取失败（已重试一次）：{error}"],
        )

    unresolved = unresolved_evidence(draft.evidence, chunks)
    evidence = [ref for ref in dict.fromkeys(draft.evidence) if ref not in unresolved]

    notes: list[str] = []
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
        evidence=evidence,
        unresolved=unresolved,
        chunk_ids=chunk_ids,
        degraded=profile is None or not evidence,
        notes=notes,
    )
