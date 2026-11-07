from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timezone

from .agents import readable_terms, term_set
from .filters import hard_filter
from .models import Job
from .schemas_resources import UserRequirements
from .schemas_search import (
    JobCandidate,
    JobExclusion,
    JobQuery,
    JobSearchResult,
)


_FOLD_RE = re.compile(r"[\s\-_/·|、，,：:（）()\[\]【】]+")
_DISPLAY_LIMIT = 5


def _fold(value: str) -> str:
    """Case, spacing and punctuation carry no identity in a posting."""

    return _FOLD_RE.sub("", value).strip().lower()


def dedupe_key(*, title: str, company: str, location: str | None = None) -> str:
    """Identity of a posting, stable across platforms and re-posts.

    The location is part of the key because the same title at the same company
    in two cities is two postings, not one duplicate. The key is deliberately
    exact: it folds cosmetic differences only, and leaves fuzzy "is this the
    same job" matching to a human review instead of guessing.
    """

    parts = (_fold(company), _fold(title), _fold(location or ""))
    return "|".join(part for part in parts if part)


def _query_text(query: JobQuery) -> str:
    return " ".join([query.role, *query.keywords]).strip()


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

    SQLite drops the offset, so a timestamp that round-tripped through the
    database comes back naive while a just-written one is still aware. Both are
    the same instant, so normalising here is what keeps "newest first" honest:
    converting the two directly either raises, or silently reads the stored UTC
    wall time as local time and shifts every row by the offset.
    """

    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _sort_key(candidate: JobCandidate) -> tuple[float, float]:
    """Best match first, then newest. Both descending."""

    return (-candidate.score, -_epoch(candidate.collected_at))


def _candidate(
    job: Job, query_terms: set[str], warnings: list[str]
) -> JobCandidate | None:
    """Score one posting, or return ``None`` when it is simply not about the query.

    Query terms found in the title count double: a posting whose name is the
    role is a better hit than one that only mentions the skill in its body.
    """

    title_terms = term_set(job.title)
    body_terms = term_set(job.requirements) | term_set(job.description)
    matched = query_terms & (title_terms | body_terms)

    if query_terms and not matched:
        return None

    missing = query_terms - matched
    display_text = " ".join([job.title, job.requirements, job.description])

    if query_terms:
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
        missing=readable_terms(display_text, missing, _DISPLAY_LIMIT),
        reason=reason,
        warnings=list(warnings),
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
        requirements = _requirements(query)
        candidates: list[JobCandidate] = []
        excluded: list[JobExclusion] = []
        scanned = 0

        for job in jobs:
            scanned += 1
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

            candidate = _candidate(job, query_terms, outcome.unknowns)
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
