from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.jd_extract import requirements_for
from backend.app.models import Base
from backend.app.schemas import (
    JobInput,
    JobRequirement,
    JobRequirementSet,
    ProfileInput,
    RequirementTerm,
)
from backend.app.scoring import score_fit


def _job(requirements: str = "熟悉 Python") -> JobInput:
    return JobInput(
        title="后端开发实习生",
        company="示例科技",
        description="负责服务端接口开发与维护",
        requirements=requirements,
        employment_type="internship",
        source_name="manual",
    )


def _profile(**overrides: object) -> ProfileInput:
    values: dict[str, object] = {
        "summary": "计算机专业学生，熟悉后端开发",
        "skills": ["Python"],
        "experiences": ["用 Python 完成接口开发"],
    }
    values.update(overrides)
    return ProfileInput(**values)


def _requirement(
    text: str,
    *,
    kind: str = "should",
    dimension: str = "skill",
    groups: list[list[str]] | None = None,
) -> JobRequirement:
    return JobRequirement(
        requirement_id="",
        text=text,
        kind=kind,  # type: ignore[arg-type]
        dimension=dimension,  # type: ignore[arg-type]
        terms=[RequirementTerm(any_of=group) for group in (groups or [])],
    )


class RequirementWeightingTest(unittest.TestCase):
    def test_an_or_group_is_satisfied_by_one_alternative(self) -> None:
        only_java = _profile(summary="熟悉 Java 后端开发", skills=["Java"], experiences=[])

        one_group = JobRequirementSet(
            requirements=[
                _requirement("熟悉 Python 或 Java", groups=[["Python", "Java"]])
            ]
        )
        two_groups = JobRequirementSet(
            requirements=[
                _requirement("熟悉 Python 和 Java", groups=[["Python"], ["Java"]])
            ]
        )

        # "或" means either one is enough; "和" means both are required. Reading
        # them the same way is how a posting that fits gets ranked below one
        # that does not.
        self.assertEqual(score_fit(only_java, _job(), one_group).score, 1.0)
        self.assertEqual(score_fit(only_java, _job(), two_groups).score, 0.5)

    def test_a_missing_must_costs_more_than_a_missing_nice(self) -> None:
        must_missing = JobRequirementSet(
            requirements=[
                _requirement("熟悉 Go", kind="must", groups=[["Go"]]),
                _requirement("有开源项目", kind="nice", groups=[["Python"]]),
            ]
        )
        nice_missing = JobRequirementSet(
            requirements=[
                _requirement("熟悉 Go", kind="nice", groups=[["Go"]]),
                _requirement("有开源项目", kind="must", groups=[["Python"]]),
            ]
        )

        low = score_fit(_profile(), _job(), must_missing)
        high = score_fit(_profile(), _job(), nice_missing)

        self.assertLess(low.score, high.score)
        self.assertEqual(
            [(entry.text, entry.status) for entry in low.breakdown],
            [("熟悉 Go", "missing"), ("有开源项目", "covered")],
        )

    def test_a_partly_mentioned_phrase_is_partial_not_covered(self) -> None:
        vague = _profile(summary="做过后端系统开发", skills=[], experiences=[])
        requirement = JobRequirementSet(
            requirements=[
                _requirement("有分布式系统设计经验", dimension="domain", groups=[["分布式系统"]])
            ]
        )

        report = score_fit(vague, _job(), requirement)

        # 系统 alone is not 分布式系统. Full credit here is how a phrasing match
        # turns into a false claim of experience.
        self.assertEqual(report.breakdown[0].status, "partial")
        self.assertEqual(report.breakdown[0].coverage, 0.25)

    def test_unjudged_requirement_leaves_the_denominator(self) -> None:
        requirements = JobRequirementSet(
            requirements=[
                _requirement("熟悉 Python", kind="must", groups=[["Python"]]),
                _requirement("沟通能力强", dimension="other", groups=[]),
            ]
        )

        report = score_fit(_profile(), _job(), requirements)

        self.assertEqual(report.score, 1.0)
        self.assertEqual(report.unknowns, ["沟通能力强"])
        # One of the two requirements could not be measured, so the total does
        # not claim to describe the whole posting.
        self.assertLess(report.confidence, 1.0)

    def test_the_breakdown_adds_up_to_the_score(self) -> None:
        requirements = JobRequirementSet(
            requirements=[
                _requirement("熟悉 Python", kind="must", groups=[["Python"]]),
                _requirement("熟悉 Go", kind="must", groups=[["Go"]]),
                _requirement("有实习经历", kind="nice", dimension="experience", groups=[["实习"]]),
            ]
        )

        report = score_fit(_profile(), _job(), requirements)

        measurable = [entry for entry in report.breakdown if entry.status != "unknown"]
        total = sum(entry.weight for entry in measurable)
        weighted = sum(entry.weight * entry.coverage for entry in measurable)
        self.assertAlmostEqual(report.score, round(weighted / total, 2))

    def test_heuristic_source_is_announced(self) -> None:
        report = score_fit(_profile(), _job("熟悉 Python；了解 SQL"))

        self.assertEqual(report.score_source, "heuristic")
        self.assertEqual(len(report.breakdown), 2)
        self.assertIn("sql", report.gaps)


class _CountingClient:
    """Counts calls, so a cache hit is provable rather than assumed."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json(self, *, system: str, user: str) -> dict[str, object]:
        self.calls += 1
        return self.payload


class RequirementCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )()

    def tearDown(self) -> None:
        self.session.close()

    def test_the_same_posting_is_read_once(self) -> None:
        client = _CountingClient(
            {
                "requirements": [
                    {
                        "text": "熟悉 Python",
                        "kind": "must",
                        "dimension": "skill",
                        "terms": [{"any_of": ["Python"]}],
                    }
                ]
            }
        )

        first, first_note = requirements_for(
            self.session, "熟悉 Python", "负责接口开发", client
        )
        second, second_note = requirements_for(
            self.session, "熟悉 Python", "负责接口开发", client
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(client.calls, 1)
        self.assertIn("解析", first_note)
        self.assertIn("缓存", second_note)

    def test_no_client_means_no_requirement_set(self) -> None:
        parsed, note = requirements_for(
            self.session, "熟悉 Python", "负责接口开发", None
        )

        self.assertIsNone(parsed)
        self.assertIn("未配置模型", note)

    def test_a_failing_model_falls_back_instead_of_raising(self) -> None:
        class _Broken:
            def complete_json(self, *, system: str, user: str) -> dict[str, object]:
                raise RuntimeError("upstream 502")

        parsed, note = requirements_for(
            self.session, "熟悉 Python", "负责接口开发", _Broken()
        )

        self.assertIsNone(parsed)
        self.assertIn("RuntimeError", note)


if __name__ == "__main__":
    unittest.main()
