from __future__ import annotations

import re

from .schemas import FitReport, InterviewQuestion, JobInput, JobVerification, ProfileInput


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


def _unmeasured_report(reason: str, recommendation: str) -> FitReport:
    """Zero score that says nothing was measured instead of "nothing matches"."""

    return FitReport(
        summary=(
            f"Keyword analysis could not run: {reason}. "
            "The 0.0 score means nothing was measured, not that the required "
            "skills are missing."
        ),
        score=0.0,
        match_points=[],
        gaps=[],
        recommendation=recommendation,
        confidence=0.0,
    )


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
    name = "career_analyst"

    def run(self, profile: ProfileInput, job: JobInput) -> FitReport:
        profile_text = " ".join(
            [profile.summary, *profile.skills, *profile.experiences]
        )
        profile_terms = _terms(profile_text)
        job_terms = _terms(job.requirements)

        # An empty term set means the text could not be parsed, which is a very
        # different answer from "parsed fine, no overlap" - never report it as
        # full keyword coverage.
        if not job_terms:
            return _unmeasured_report(
                f"the requirements of {job.title} contain no comparable terms",
                "Rewrite the requirements as concrete skills, tools or methods "
                "before relying on this score.",
            )
        if not profile_terms:
            return _unmeasured_report(
                "the profile contains no comparable terms",
                "Add concrete skills to the profile summary before relying on "
                "this score.",
            )

        overlap = profile_terms & job_terms
        gaps = job_terms - profile_terms
        score = round(len(overlap) / len(job_terms), 2)

        match_points = _display_terms(job.requirements, overlap)
        gap_output = _display_terms(job.requirements, gaps)

        return FitReport(
            summary=(
                f"Initial result: the profile and {job.title} have "
                f"{len(overlap)} matched keyword units and {len(gaps)} unmatched ones. "
                "This prepares a job search checklist and is not a hiring probability."
            ),
            score=score,
            match_points=match_points,
            gaps=gap_output,
            recommendation=(
                "Prioritize quantified evidence for: "
                + ", ".join(gap_output)
                + "."
                if gap_output
                else "All explicit job keywords are covered; validate project depth and results manually."
            ),
            confidence=(
                0.0
                if not overlap
                else round(min(0.9, 0.4 + 0.1 * len(overlap)), 2)
            ),
        )


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
