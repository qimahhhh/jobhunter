"""Read a posting into discrete requirements, once per description.

Only structure is asked of the model: which requirements this posting states,
which of them are hard, and which terms would prove one is met. It is never
asked for a score, a weight or an ordering — those come from
``scoring.DEFAULT_CONFIG``, so the same posting scored twice gives the same
number even if the model words the breakdown differently.

The result is cached by text hash. Without the cache, "reproducible" would be a
promise: every run would buy a fresh set of requirements, and the score would
move for no reason a user can see. ``extractor_version`` is part of the key, so
changing the prompt below invalidates the cache deliberately instead of
silently mixing two kinds of requirement.

Nothing here raises on failure. A posting whose structure could not be read is
still scorable by the heuristic splitter in ``scoring``; the returned note says
which of the two happened, and the report carries it on to the caller.
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .llm import LLMClient
from .models import StoredRequirementSet
from .schemas import JobRequirementSet

# Bumped whenever SYSTEM_PROMPT changes enough to produce different
# requirements. It is a cache key, not a version of the code.
EXTRACTOR_VERSION = "jd-v1"

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是招聘需求解析器。把岗位要求拆成一条条可以判定的需求。

规则：
1. 只使用原文出现的词。不要补充岗位没写的要求，不要评价候选人，也不要打分。
2. 每条需求的 text 用原文片段，可以删掉多余的修饰，但不要改写成更宽泛的说法。
3. kind：must 是明确的硬性要求（必备技能、年限、学历），should 是常见的任职要求，
   nice 是加分项。
4. dimension 只能取：skill（具体技术或工具）、experience（年限或职责范围）、
   domain（行业或领域经验）、education（学历专业）、language（外语）、
   other（沟通、抗压这类软性描述）。
5. terms 是"这条需求被满足了没有"的检查项，每个检查项是一个 any_of 数组：
   - 满足其中任意一个词，就算这个检查项满足；
   - "熟悉 Python 或 Java" → 一个检查项 ["Python", "Java"]；
   - "熟悉 Python 和 Go" → 两个检查项 ["Python"] 和 ["Go"]；
   - 用原文里的名词短语，不要拆成单个汉字，不要把整句话塞进去。
6. 纯软性描述如果没有可对照的具体词，terms 给空数组，这条会被标成无法判定，
   这是正确结果，不要为了凑数编一个术语。
7. 只返回一个 JSON 对象，不要 markdown 代码块，不要解释文字：
{
  "requirements": [
    {
      "text": "熟悉 Python，了解 FastAPI 或 Flask",
      "kind": "must",
      "dimension": "skill",
      "terms": [{"any_of": ["Python"]}, {"any_of": ["FastAPI", "Flask"]}]
    }
  ],
  "years_required": null,
  "education_required": null
}"""


def _jd_hash(requirements: str, description: str) -> str:
    """Identity of a posting's text.

    Only NFKC and whitespace are normalised. A hash that ignored more would make
    two genuinely different postings share one requirement set, which is the one
    mistake a cache like this must not make.
    """

    text = unicodedata.normalize(
        "NFKC", f"{requirements.strip()}\n{description.strip()}"
    )
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def _user_prompt(requirements: str, description: str) -> str:
    return (
        "岗位要求：\n"
        f"{requirements.strip()}\n\n"
        "岗位描述：\n"
        f"{description.strip()}\n\n"
        "只返回 JSON 对象。"
    )


def extract_requirements(
    requirements: str, description: str, client: LLMClient
) -> JobRequirementSet:
    """One model call, validated into the same shape the cache stores."""

    payload = client.complete_json(
        system=SYSTEM_PROMPT, user=_user_prompt(requirements, description)
    )
    return JobRequirementSet.model_validate(payload)


def requirements_for(
    session: Session,
    requirements: str,
    description: str,
    client: LLMClient | None,
) -> tuple[JobRequirementSet | None, str]:
    """The posting's requirements, cached, or ``None`` when there are none.

    ``None`` is not an error: it means the caller should fall back to the
    heuristic splitter, and the note explains why in words a user can read.
    """

    jd_hash = _jd_hash(requirements, description)
    stored = session.scalar(
        select(StoredRequirementSet).where(
            StoredRequirementSet.jd_hash == jd_hash,
            StoredRequirementSet.extractor_version == EXTRACTOR_VERSION,
        )
    )
    if stored is not None:
        try:
            return (
                JobRequirementSet.model_validate(stored.payload),
                "岗位需求已解析，复用缓存",
            )
        except Exception:  # a payload written by an older, incompatible shape
            logger.warning(
                "stored requirement set %s no longer validates; re-extracting",
                stored.id,
            )

    if client is None:
        return None, "未配置模型，岗位需求按标点启发式切分"

    try:
        parsed = extract_requirements(requirements, description, client)
    except Exception as exc:
        return None, f"岗位需求解析失败（{type(exc).__name__}），按启发式切分"
    if not parsed.requirements:
        return None, "模型没有解析出可判定的需求，按启发式切分"

    session.add(
        StoredRequirementSet(
            id=uuid.uuid4().hex,
            jd_hash=jd_hash,
            extractor_version=EXTRACTOR_VERSION,
            payload=parsed.model_dump(),
        )
    )
    try:
        session.commit()
    except Exception:
        # Two requests scoring the same posting at once can both miss the row
        # and both insert. Losing that race is harmless: the parse is the same,
        # and the other writer already stored it.
        session.rollback()
        logger.info("requirement set for %s was stored concurrently", jd_hash[:12])
    return parsed, "岗位需求已解析"
