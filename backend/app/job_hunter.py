from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

from .agents import readable_terms, term_set
from .filters import hard_filter, location_tokens
from .models import Job, as_utc
from .schemas_resources import UserRequirements
from .schemas_search import (
    JobCandidate,
    JobExclusion,
    JobQuery,
    JobSearchResult,
)


_FOLD_RE = re.compile(r"[\s\-_/·|、，,：:（）()\[\]【】]+")

# Bracketed text that carries no identity: cohort years, urgency banners. A
# bracket holding something else (（算法）vs（工程）) is a real difference and
# stays in the key, because merging two real postings loses one of them.
_TITLE_NOISE_RE = re.compile(
    r"[（(【\[]\s*(?:\d{2,4}\s*届|\d{2,4}\s*[-–—~至]\s*\d{2,4}\s*年?"
    r"|急招|急聘|热招|长期有效|长期招聘)\s*[）)】\]]"
)
_LOCATION_SUFFIXES = ("市",)
_DISPLAY_LIMIT = 5
_EXPIRED_REASON = "岗位已被人工核验为过期，不再推荐"


def _verification_warnings(job: Job) -> list[str]:
    """What the posting's trust state means for the answer.

    "Search found it" is not "it is still open". An unverified posting is
    returned with a caveat rather than presented as available, and an
    unreachable source is reported as unknown instead of rejected, because a
    mirror being down says nothing about the job.
    """

    if job.verification_status in (None, "pending_verification", "unknown"):
        return ["该岗位尚未核验：检索到不等于仍在招聘"]
    if job.verification_status == "source_unavailable":
        return ["来源暂时不可访问，岗位状态未知"]
    return []


def _fold(value: str) -> str:
    """Case, spacing and punctuation carry no identity in a posting."""

    return _FOLD_RE.sub("", value).strip().lower()


def _fold_location(value: str) -> str:
    """City names in a form that survives the usual spelling differences.

    Reuses the same splitting as the hard filter, so "北京市" and "北京", or
    "北京/上海" and "上海、北京", describe one posting instead of two. Order is
    dropped because it is a presentation choice, not part of the job.
    """

    tokens: list[str] = []
    for token in location_tokens(value):
        for suffix in _LOCATION_SUFFIXES:
            if token.endswith(suffix) and len(token) > len(suffix):
                token = token[: -len(suffix)]
        tokens.append(token)
    return ".".join(sorted(set(tokens)))


def dedupe_key(*, title: str, company: str, location: str | None = None) -> str:
    """Identity of a posting, stable across platforms and re-posts.

    The key folds cosmetic noise only: case, spacing, punctuation, cohort years
    and urgency banners in the title, and city spelling. Anything that could be
    a different opening is kept apart, so a false split stays visible while a
    false merge would silently lose a job.
    """

    parts = (
        _fold(company),
        _fold(_TITLE_NOISE_RE.sub("", title)),
        _fold_location(location or ""),
    )
    return "|".join(part for part in parts if part)


def _query_text(query: JobQuery) -> str:
    """The words the user asked for. These are the only ones that score."""

    return " ".join([query.role, *query.keywords]).strip()


def _alias_text(query: JobQuery) -> str:
    """Words the model added. They widen the gate and never enter the score."""

    return " ".join(query.aliases).strip()


def _requirements(query: JobQuery) -> UserRequirements:
    """The query as a constraint object.

    Fields the query left empty are switched off again in ``hard_filter``, so
    this object only has to be a valid carrier, not a complete expectation.
    """

    return UserRequirements(
        desired_role=query.role or "岗位",
        locations=list(query.locations),
        employment_type=query.employment_type or "internship",
        salary_min=query.salary_min,
        salary_period=query.salary_period,
    )


def _epoch(value: datetime | None) -> float:
    """Seconds since the epoch, reading a stored naive value as UTC.

    SQLite keeps no offset, so a timestamp that round-tripped through the
    database comes back naive while a just-written one is still aware. Both
    describe the same instant, and ``as_utc`` is the one place that says so.
    """

    return 0.0 if value is None else as_utc(value).timestamp()


def _sort_key(candidate: JobCandidate) -> tuple[float, float]:
    """Best match first, then newest. Both descending."""

    return (-candidate.score, -_epoch(candidate.collected_at))


def _candidate(
    job: Job,
    query_terms: set[str],
    alias_terms: set[str],
    warnings: list[str],
) -> JobCandidate | None:
    """Score one posting, or return ``None`` when it is simply not about the query.

    Query terms found in the title count double: a posting whose name is the
    role is a better hit than one that only mentions the skill in its body.
    Alias terms can only rescue a posting from being dropped; they never raise
    its score, because they are not what the user asked for.
    """

    title_terms = term_set(job.title)
    body_terms = term_set(job.requirements) | term_set(job.description)
    job_terms = title_terms | body_terms
    matched = query_terms & job_terms
    aliases_hit = alias_terms & job_terms

    if query_terms and not matched and not aliases_hit:
        return None

    missing = query_terms - matched
    display_text = " ".join([job.title, job.requirements, job.description])

    if query_terms and matched:
        title_hits = query_terms & title_terms
        score = round(
            (2 * len(title_hits) + len(matched - title_hits))
            / (2 * len(query_terms)),
            2,
        )
        reason = (
            f"命中 {len(matched)}/{len(query_terms)} 个查询关键词，"
            f"其中 {len(title_hits)} 个出现在岗位名称里。"
        )
        if aliases_hit:
            reason += f"另有 {len(aliases_hit)} 个同义词命中。"
    elif query_terms:
        # Found only through the model's expansion: a real posting, but it
        # answers none of the words the user typed, and the score says so.
        score = 0.0
        reason = "只通过模型补充的同义词命中，未命中原始关键词。"
    else:
        # Nothing to compare is not the same as "matches nothing", so the score
        # says 0.0 and the note says it was never measured.
        score = 0.0
        reason = "未提供关键词，按发布时间倒序排列。"

    return JobCandidate(
        job_id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        employment_type=job.employment_type,
        source_name=job.source_name,
        source_url=job.source_url,
        score=score,
        matched=readable_terms(display_text, matched, _DISPLAY_LIMIT),
        aliases_matched=readable_terms(display_text, aliases_hit, _DISPLAY_LIMIT),
        missing=readable_terms(display_text, missing, _DISPLAY_LIMIT),
        reason=reason,
        warnings=list(warnings),
        verification_status=job.verification_status,
        last_verified_at=job.last_verified_at,
        collected_at=job.collected_at,
    )


class JobHunterAgent:
    """Turn "what I want" into a ranked, explainable shortlist of stored jobs.

    The agent owns no fetching and no scoring model: it scans what the database
    already holds, applies the query's hard constraints, and reports every drop
    with a reason. A collector can therefore be swapped or added without
    touching this class, and a demo can explain each line of the result.
    """

    name = "job_hunter"

    def run(self, jobs: Iterable[Job], query: JobQuery) -> JobSearchResult:
        query_terms = term_set(_query_text(query))
        alias_terms = term_set(_alias_text(query))
        requirements = _requirements(query)
        candidates: list[JobCandidate] = []
        excluded: list[JobExclusion] = []
        scanned = 0

        for job in jobs:
            scanned += 1
            if job.verification_status == "expired":
                # Someone checked and the posting is closed. Recommending it
                # would contradict the review that marked it, so it leaves the
                # shortlist with a reason rather than disappearing.
                excluded.append(
                    JobExclusion(
                        job_id=job.id,
                        title=job.title,
                        company=job.company,
                        reasons=[_EXPIRED_REASON],
                    )
                )
                continue

            outcome = hard_filter(
                job,
                requirements,
                employment_type=query.employment_type is not None,
                location=bool(query.locations),
                salary=query.salary_min is not None,
            )
            if not outcome.passed:
                excluded.append(
                    JobExclusion(
                        job_id=job.id,
                        title=job.title,
                        company=job.company,
                        reasons=list(outcome.rejections),
                    )
                )
                continue

            candidate = _candidate(
                job,
                query_terms,
                alias_terms,
                [*outcome.unknowns, *_verification_warnings(job)],
            )
            if candidate is None:
                excluded.append(
                    JobExclusion(
                        job_id=job.id,
                        title=job.title,
                        company=job.company,
                        reasons=["岗位描述与查询关键词没有重合"],
                    )
                )
                continue
            candidates.append(candidate)

        candidates.sort(key=_sort_key)
        notes: list[str] = []
        if not query_terms:
            notes.append(
                "查询没有提供可比较的关键词，结果按发布时间排序，"
                "score 0.0 表示未测量而不是不匹配。"
            )

        return JobSearchResult(
            query=query,
            candidates=candidates[: query.limit],
            excluded=excluded,
            total_scanned=scanned,
            notes=notes,
        )
