"""Score a posting against a profile, one requirement at a time.

The score decides the order of a shortlist, and an order that changes when the
same pair is scored twice is not an order. So the split is strict: a model reads
a job description into discrete requirements (``jd_extract``), and this module
does the part a model cannot do the same way twice — match, weight and explain.

Coverage is measured per requirement, not per keyword:

* a requirement is a list of term groups;
* a group is satisfied by any one of its alternatives, so "熟悉 Python 或 Java"
  is not read as "both are required";
* an alternative covers the fraction of its own terms that appear in the
  profile, so 分布式系统 mentioned only as 系统 counts as weak, not as met;
* a requirement's coverage is the mean over its groups.

``must`` earns more weight than ``should``, but a missing ``must`` subtracts
nothing: a requirement that rules a candidate out is a hard constraint
(``filters.hard_filter``), not a few points off a total. Keeping those apart is
what makes this number a *ranking* number instead of a mixture of two questions.

The report says where its requirement list came from. A list read by the model
and a list guessed from punctuation are not equally trustworthy, and a score
that cannot say which one it used cannot be argued with afterwards.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .agents import readable_terms, term_set
from .schemas import (
    FitReport,
    JobInput,
    JobRequirement,
    JobRequirementSet,
    ProfileInput,
    RequirementScore,
    RequirementTerm,
)

# A requirement list, when nobody read it properly, is the clauses of the
# posting: Chinese postings separate requirements with ；or 。, and a whole
# paragraph on one line still has to be split somewhere.
_CLAUSE_RE = re.compile(r"[；;。\n]+")


@dataclass(frozen=True)
class ScoringConfig:
    """Every number that decides an order, in one place.

    Weights are not tuned at a call site. One score has to mean the same thing
    for two postings, and a weight changed inside one path is a difference
    nobody can see later. ``must`` outweighs ``nice`` because losing a stated
    hard skill matters more than losing a bonus; the dimension multipliers say
    that a named tool is more checkable than "good communication".
    """

    kind_weight: Mapping[str, float] = field(
        default_factory=lambda: {"must": 3.0, "should": 2.0, "nice": 1.0}
    )
    dimension_multiplier: Mapping[str, float] = field(
        default_factory=lambda: {
            "skill": 1.0,
            "experience": 1.0,
            "domain": 0.8,
            "education": 0.6,
            "language": 0.5,
            "other": 0.2,
        }
    )
    # A split guessed from punctuation cannot be trusted as far as one the model
    # was asked for, so a heuristic score never claims full confidence.
    heuristic_confidence_cap: float = 0.8
    display_limit: int = 5


DEFAULT_CONFIG = ScoringConfig()

# Which part of the profile a term was found in, in the order it is reported.
# The layers do not change the coverage: a skill is a skill. What they change is
# the evidence line, so a user can see whether the claim is on the skills list
# or mentioned in passing inside an experience.
_Layers = Sequence[tuple[str, set[str]]]


def _profile_layers(profile: ProfileInput) -> _Layers:
    return (
        ("skills", term_set(" ".join(profile.skills))),
        ("summary", term_set(profile.summary)),
        ("experiences", term_set(" ".join(profile.experiences))),
    )


def _alternative_coverage(alternative: str, layers: _Layers) -> tuple[float, str]:
    """How much of one alternative is present, and in which layer it was seen.

    The fraction is measured against the alternative's own terms, which is what
    makes a long phrase harder to satisfy than a single word: "分布式系统" in a
    resume that only says 系统 reaches 0.25, and a partial that low should not
    read as satisfied.
    """

    terms = term_set(alternative)
    if not terms:
        return 0.0, ""

    best, best_layer = 0.0, ""
    for name, layer_terms in layers:
        if not layer_terms:
            continue
        hit = len(terms & layer_terms) / len(terms)
        if hit > best:
            best, best_layer = hit, name
    return best, best_layer


def requirement_weight(
    requirement: JobRequirement, config: ScoringConfig = DEFAULT_CONFIG
) -> float:
    """How much one requirement counts, from its kind and dimension.

    Shared with the interview agent, which picks what to ask by the same order
    of importance a score would use — two places deciding "which requirement
    matters most" differently would be two products.
    """

    return config.kind_weight.get(requirement.kind, 1.0) * (
        config.dimension_multiplier.get(requirement.dimension, 1.0)
    )


def _score_requirement(
    requirement: JobRequirement, layers: _Layers, config: ScoringConfig
) -> RequirementScore:
    weight = requirement_weight(requirement, config)

    coverages: list[float] = []
    matched: set[str] = set()
    missing: set[str] = set()
    evidence: list[str] = []

    for group in requirement.terms:
        best, best_layer, best_terms = 0.0, "", set()
        for alternative in group.any_of:
            coverage, layer = _alternative_coverage(alternative, layers)
            if coverage > best:
                best, best_layer, best_terms = coverage, layer, term_set(alternative)

        coverages.append(best)
        if best > 0:
            matched |= best_terms
            if best_layer and best_layer not in evidence:
                evidence.append(best_layer)
        else:
            for alternative in group.any_of:
                missing |= term_set(alternative)

    if not coverages:
        # Nothing checkable was stated, which is not the same as "not met".
        return RequirementScore(
            requirement_id=requirement.requirement_id,
            text=requirement.text,
            kind=requirement.kind,
            dimension=requirement.dimension,
            weight=round(weight, 2),
            coverage=0.0,
            status="unknown",
        )

    # Rounded before it is summed, so the breakdown and the total agree: a user
    # who adds the rows up gets the number on the screen.
    coverage = round(sum(coverages) / len(coverages), 2)
    status = (
        "covered"
        if coverage >= 0.999
        else ("missing" if coverage <= 0 else "partial")
    )
    return RequirementScore(
        requirement_id=requirement.requirement_id,
        text=requirement.text,
        kind=requirement.kind,
        dimension=requirement.dimension,
        weight=round(weight, 2),
        coverage=coverage,
        status=status,
        matched_terms=readable_terms(
            requirement.text, matched, config.display_limit
        ),
        missing_terms=readable_terms(
            requirement.text, missing, config.display_limit
        ),
        evidence=evidence,
    )


def _unmeasured(
    reason: str, recommendation: str, *, source: str
) -> FitReport:
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
        breakdown=[],
        unknowns=[],
        notes=[],
        must_gaps=[],
        must_coverage=0.0,
        score_source=source,  # type: ignore[arg-type]
    )


def heuristic_requirements(job: JobInput) -> JobRequirementSet:
    """Split the posting's requirement text into clauses, one term per group.

    The fallback for a deployment with no model key, or for a posting whose
    structure could not be read. One group per term keeps the old keyword
    coverage as the baseline, while the result keeps the weighted, explainable
    shape — two sources that produce reports of different shape would be two
    features pretending to be one.

    Only ``requirements`` is read. ``description`` is prose about the company
    and the team; scoring it would let a posting's marketing decide its rank.
    """

    clauses = [
        clause.strip()
        for clause in _CLAUSE_RE.split(job.requirements)
        if clause.strip()
    ]

    requirements: list[JobRequirement] = []
    for index, clause in enumerate(clauses, start=1):
        terms = sorted(term_set(clause))
        if not terms:
            continue
        requirements.append(
            JobRequirement(
                requirement_id=f"h{index}",
                text=clause,
                kind="should",
                dimension="skill",
                terms=[RequirementTerm(any_of=[term]) for term in terms],
            )
        )
    return JobRequirementSet(requirements=requirements)


def score_fit(
    profile: ProfileInput,
    job: JobInput,
    requirements: JobRequirementSet | None = None,
    *,
    config: ScoringConfig = DEFAULT_CONFIG,
) -> FitReport:
    """Turn requirements and a profile into a weighted, explained score.

    ``requirements`` is what a model read out of the posting. Passing ``None``
    falls back to the punctuation split, and the report says so in
    ``score_source``: a caller must never have to guess which one produced the
    number it is looking at.
    """

    source = "extracted" if requirements is not None else "heuristic"
    requirement_set = requirements or heuristic_requirements(job)
    layers = _profile_layers(profile)

    if not any(layer_terms for _, layer_terms in layers):
        return _unmeasured(
            "the profile contains no comparable terms",
            "Add concrete skills to the profile summary before relying on "
            "this score.",
            source=source,
        )

    scores = [
        _score_requirement(requirement, layers, config)
        for requirement in requirement_set.requirements
    ]
    measurable = [entry for entry in scores if entry.status != "unknown"]
    if not measurable:
        return _unmeasured(
            f"the requirements of {job.title} contain nothing a profile can be "
            "matched against",
            "Rewrite the requirements as concrete skills, tools or methods "
            "before relying on this score.",
            source=source,
        )

    measurable_weight = sum(entry.weight for entry in measurable)
    total_weight = sum(entry.weight for entry in scores)
    score = round(
        sum(entry.weight * entry.coverage for entry in measurable)
        / measurable_weight,
        2,
    )

    # Confidence is the share of the posting the score actually covers. It used
    # to be a function of how many keywords overlapped, which said nothing about
    # how much of the posting had been measured.
    covered_share = measurable_weight / total_weight if total_weight else 0.0
    confidence = round(
        covered_share
        * (1.0 if source == "extracted" else config.heuristic_confidence_cap),
        2,
    )

    match_points: list[str] = []
    gaps: list[str] = []
    for entry in scores:
        for term in entry.matched_terms:
            if term not in match_points:
                match_points.append(term)
        for term in entry.missing_terms:
            if term not in gaps:
                gaps.append(term)

    unknown = [entry.text for entry in scores if entry.status == "unknown"]
    covered = sum(1 for entry in measurable if entry.status == "covered")
    partial = sum(1 for entry in measurable if entry.status == "partial")
    missing = sum(1 for entry in measurable if entry.status == "missing")

    # The hard requirements, reported separately from the score. A posting can
    # state a must the profile does not meet and still be worth applying to, so
    # this is a list to read before writing the cover letter, not a verdict.
    musts = [
        entry for entry in scores if entry.kind == "must" and entry.status != "unknown"
    ]
    must_weight = sum(entry.weight for entry in musts)
    must_coverage = (
        round(sum(entry.weight * entry.coverage for entry in musts) / must_weight, 2)
        if must_weight
        else 1.0
    )
    must_gaps = [
        entry.text for entry in musts if entry.status in ("missing", "partial")
    ]

    summary = (
        f"Scored {len(measurable)} of {len(scores)} requirements against "
        f"{job.title}: {covered} covered, {partial} partly, {missing} missing"
        + (f", {len(unknown)} could not be judged" if unknown else "")
        + f". Weighted score {score:.0%}. "
        "This prepares a job search checklist and is not a hiring probability."
    )

    return FitReport(
        summary=summary,
        score=score,
        match_points=match_points,
        gaps=gaps,
        recommendation=(
            "Prioritize quantified evidence for: " + ", ".join(gaps) + "."
            if gaps
            else "All explicit job keywords are covered; validate project depth "
            "and results manually."
        ),
        confidence=confidence,
        breakdown=scores,
        unknowns=unknown,
        notes=[],
        must_gaps=must_gaps,
        must_coverage=must_coverage,
        score_source=source,  # type: ignore[arg-type]
    )


def rank_key(score: float, must_coverage: float) -> tuple[float, float]:
    """Order two scored postings: the score first, met musts only on a tie.

    The score already pays for a missing must: its weight stays in the
    denominator while its coverage stays 0. So this second term must never lift
    a lower score above a higher one — that would turn "worth applying first"
    back into "qualified or not", which is the question the score deliberately
    does not answer.

    What it does decide is the tie rounding leaves behind. Without it two
    postings at the same 0.70 fall back to collection time, which says nothing
    about fit and makes the order depend on when a collector happened to run.
    """

    return (-score, -must_coverage)
