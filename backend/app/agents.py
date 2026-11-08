from __future__ import annotations

import re

from .schemas import (
    FitReport,
    InterviewQuestion,
    JobInput,
    JobRequirementSet,
    JobVerification,
    ProfileInput,
)


_CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_ASCII_TERM_RE = re.compile(r"[A-Za-z0-9+#]{2,}")
_EN_STOPWORDS = {"and", "the", "with", "for", "you", "are", "this"}
# Chinese JD filler carries no skill signal. Splitting on it keeps the coverage
# ratio honest and stops reported gaps from reading like 熟悉/掌握.
_CJK_FILLERS = (
    "熟悉",
    "熟练",
    "精通",
    "掌握",
    "了解",
    "具备",
    "具有",
    "优先",
    "相关",
    "以及",
    "或者",
    "我们",
    "你们",
    "岗位",
    "职责",
    "任职",
    "加分",
    "要求",
    "能力",
    "以上",
    "和",
    "与",
    "及",
    "的",
    "了",
    "在",
    "有",
)
_CJK_SPLIT_RE = re.compile("|".join(re.escape(word) for word in _CJK_FILLERS))
_DISPLAY_LIMIT = 5


def _cjk_segments(value: str) -> list[str]:
    """Split Chinese text into filler-free phrases of at least two characters."""

    segments: list[str] = []
    for run in _CJK_RUN_RE.findall(value):
        segments.extend(
            part for part in _CJK_SPLIT_RE.split(run) if len(part) >= 2
        )
    return segments


def _cjk_terms(value: str) -> set[str]:
    """Character bigrams for Chinese text.

    Chinese has no whitespace tokenisation, so the previous ASCII-only pattern
    dropped every Chinese skill and requirement. Bigrams need no dictionary and
    still catch partial matches such as 机器学习 vs 机器学习算法.
    """

    terms: set[str] = set()
    for segment in _cjk_segments(value):
        terms.update(
            segment[index : index + 2] for index in range(len(segment) - 1)
        )
    return terms


def _terms(value: str) -> set[str]:
    ascii_terms = {
        token
        for token in _ASCII_TERM_RE.findall(value.lower())
        if token not in _EN_STOPWORDS
    }
    return ascii_terms | _cjk_terms(value)


def _matched_spans(value: str, terms: set[str]) -> list[str]:
    """Merge matched bigrams back into readable spans, in order of appearance."""

    spans: list[str] = []
    for segment in _cjk_segments(value):
        current = ""
        for index in range(len(segment) - 1):
            bigram = segment[index : index + 2]
            if bigram in terms:
                current = current + segment[index + 1] if current else bigram
            else:
                if len(current) >= 2:
                    spans.append(current)
                current = ""
        if len(current) >= 2:
            spans.append(current)
    return spans


def _display_terms(
    value: str, terms: set[str], limit: int = _DISPLAY_LIMIT
) -> list[str]:
    """Report readable terms: ASCII tokens first, then merged Chinese spans."""

    ordered = sorted(term for term in terms if term.isascii())
    ordered.extend(_matched_spans(value, terms))
    unique: list[str] = []
    for term in ordered:
        if term in unique:
            continue
        unique.append(term)
        if len(unique) >= limit:
            break
    return unique


def term_set(value: str) -> set[str]:
    """Comparable terms of a text, shared with the job search.

    Public wrapper so the search does not reimplement tokenisation and end up
    with a slightly different notion of "same keyword" than the fit report.
    """

    return _terms(value)


def readable_terms(
    value: str, terms: set[str], limit: int = _DISPLAY_LIMIT
) -> list[str]:
    """Terms as the text spells them, for a response a human reads."""

    return _display_terms(value, terms, limit)


class JobVerifierAgent:
    name = "job_verifier"

    def run(self, job: JobInput) -> JobVerification:
        checks = {
            "has_title": bool(job.title.strip()),
            "has_company": bool(job.company.strip()),
            "has_requirements": bool(job.requirements.strip()),
            "has_source_url": bool(job.source_url and job.source_url.strip()),
        }
        return JobVerification(
            status="pending_verification" if checks["has_source_url"] else "unknown",
            checks=checks,
            source_name=job.source_name,
            source_url=job.source_url,
        )


class CareerAnalystAgent:
    """Score a posting against a profile, and say why.

    The scoring itself lives in ``scoring``; this class is only the stage
    boundary the orchestrator knows about. The import is deferred on purpose:
    ``scoring`` reads the term helpers from this module, so importing it at
    module scope would make the two files circular.
    """

    name = "career_analyst"

    def run(
        self,
        profile: ProfileInput,
        job: JobInput,
        requirements: JobRequirementSet | None = None,
    ) -> FitReport:
        from .scoring import score_fit

        return score_fit(profile, job, requirements)


class ContentAgent:
    name = "content_agent"

    def run(self, job: JobInput, report: FitReport) -> tuple[list[str], list[InterviewQuestion]]:
        resume_suggestions = [
            f"Add one result-focused bullet directly tied to the requirements for {job.title}.",
            "Add the action, technical stack, measurable result, and your contribution to each experience.",
        ]
        resume_suggestions.extend(f"Prepare evidence for this gap: {gap}" for gap in report.gaps[:2])

        questions = [
            InterviewQuestion(
                type="project",
                question="Introduce one project you led or contributed to deeply, and explain your specific contribution.",
                why="Checks experience authenticity, ownership, and measurable results.",
            ),
            InterviewQuestion(
                type="technical",
                question=f"How would you design a verifiable solution for a core requirement of {job.title}?",
                why="Checks whether technical understanding maps to the actual role.",
            ),
            InterviewQuestion(
                type="behavior",
                question="When a project has schedule risk or missing information, how do you decide and recover?",
                why="Maps to the challenge requirement for exception handling and human decisions.",
            ),
        ]
        return resume_suggestions, questions
