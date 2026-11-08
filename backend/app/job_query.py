"""Turn a job direction into extra words a search can use.

Only the query side of the hunt touches a model, and only in one direction: the
model proposes synonyms, tool names and posting aliases, which are then matched
against postings already in the database. It never sees the stored rows and
never returns a job, a company, a city or a salary — a suggestion that cannot be
matched against the database cannot invent anything.

The expansion is deliberately weak by construction. Its terms only widen the
candidate gate; scoring still runs on the words the user actually typed, so a
job found purely through a synonym is reported with score 0.0 and a reason that
says exactly that, instead of borrowing credibility it did not earn.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from .llm import LLMClient
from .schemas_search import JobQuery

MAX_ALIASES = 8
MAX_ALIAS_CHARS = 16
_SENTENCE_PUNCTUATION = "，。；、！？,.;!?"

SYSTEM_PROMPT = """你是岗位检索的关键词改写助手。任务：把用户的求职方向扩展成可用于文本匹配的同义词、岗位别名和常见技术词。

规则：
1. 最多 8 个词，每个不超过 16 个字符；优先给同义词、岗位别名、相关技术栈。
2. 不要输出公司名、城市、薪资、学历、经验年限，也不要生成任何岗位、招聘信息或链接。
3. 不要重复用户已经给出的词。
4. 宁少勿滥：拿不准就不给，不要为凑数添加无关词。
5. 只返回一个 JSON 对象：{"keywords": ["..."], "rationale": "一句话说明改写思路"}"""


class QueryExpansion(BaseModel):
    """What the model is allowed to return, and nothing else."""

    keywords: list[str] = Field(default_factory=list)
    rationale: str = ""

    @field_validator("keywords", mode="before")
    @classmethod
    def _as_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


def _message(query: JobQuery) -> str:
    lines = []
    if query.role:
        lines.append(f"求职方向：{query.role}")
    if query.keywords:
        lines.append("已有的关键词：" + "、".join(query.keywords))
    lines.append("请给出可以补充的检索关键词。")
    return "\n".join(lines)


def _clean(terms: list[str], taken: set[str], limit: int) -> list[str]:
    """Keep short, standalone words; drop anything else the model offers.

    A term that reads like a sentence ("根据你的描述，建议关注…") is not a search
    word, and one longer than a phrase would never match a posting title. Both
    are dropped here rather than silently joining the query.
    """

    cleaned: list[str] = []
    seen = set(taken)
    for term in terms:
        value = " ".join(str(term).split())
        if not value or len(value) > MAX_ALIAS_CHARS:
            continue
        if any(mark in value for mark in _SENTENCE_PUNCTUATION):
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
        if len(cleaned) >= limit:
            break
    return cleaned


def expand_query(
    query: JobQuery, client: LLMClient, *, limit: int = MAX_ALIASES
) -> tuple[list[str], str]:
    """Ask the model for extra matching terms, and never fail the search.

    Returns the accepted aliases and one line explaining what happened, so the
    response can say "expanded with 机器视觉" or "the model was unreachable"
    instead of either pretending nothing happened or aborting.
    """

    if not query.role.strip() and not query.keywords:
        return [], "查询没有方向或关键词，跳过了模型改写。"

    try:
        payload = client.complete_json(system=SYSTEM_PROMPT, user=_message(query))
        expansion = QueryExpansion.model_validate(payload)
    except Exception as exc:  # an optional step must never break the search
        return [], f"查询改写跳过（{type(exc).__name__}），按原有关键词检索。"

    taken = {query.role.strip().lower()}
    taken.update(keyword.strip().lower() for keyword in query.keywords)
    aliases = _clean(expansion.keywords, taken, limit)
    if not aliases:
        return [], "模型没有给出可用的补充关键词，按原有关键词检索。"
    return aliases, "模型补充了同义词/别名：" + "、".join(aliases)
