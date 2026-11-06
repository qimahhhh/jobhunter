from __future__ import annotations

import re
from typing import Iterable

from .schemas import FitReport, InterviewQuestion, JobInput, JobVerification, ProfileInput


def _terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9+#]{2,}", value.lower())
        if token not in {"and", "the", "with", "for", "you", "are", "this"}
    }


def _format_terms(terms: Iterable[str], limit: int = 5) -> list[str]:
    return sorted(terms)[:limit]


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
            status="source_attached" if checks["has_source_url"] else "needs_review",
            checks=checks,
            source_name=job.source_name,
            source_url=job.source_url,
        )


class CareerAnalystAgent:
    name = "career_analyst"

    def run(self, profile: ProfileInput, job: JobInput) -> FitReport:
        profile_terms = _terms(
            " ".join([profile.summary, *profile.skills, *profile.experiences])
        )
        job_terms = _terms(job.requirements)
        overlap = profile_terms & job_terms
        gaps = job_terms - profile_terms

        match_points = [f"Skill appears in both inputs: {term}" for term in _format_terms(overlap)]
        if not match_points:
            match_points = ["No directly comparable skill keyword was provided yet."]

        gap_output = [
            f"Job requirement is not explicit in the profile: {term}"
            for term in _format_terms(gaps)
        ]
        if not gap_output:
            gap_output = ["No obvious keyword gap was found; validate project depth manually."]

        return FitReport(
            summary=(
                f"Initial result: the profile and {job.title} have verifiable keyword overlap. "
                "This prepares a job search checklist and is not a hiring probability."
            ),
            match_points=match_points,
            gaps=gap_output,
            recommendation=(
                "Prioritize quantified evidence for the job requirements and check resume "
                "keywords against the source job description."
            ),
            confidence=round(min(0.9, 0.4 + 0.1 * len(overlap)), 2),
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
