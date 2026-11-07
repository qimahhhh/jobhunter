from __future__ import annotations

import unittest

from backend.app.filters import hard_filter, to_monthly
from backend.app.models import Job
from backend.app.schemas_resources import UserRequirements


def _job(**overrides: object) -> Job:
    values: dict[str, object] = {
        "id": "job-1",
        "title": "AI Intern",
        "company": "Example",
        "description": "AI workflows",
        "requirements": "Python",
        "employment_type": "internship",
        "location": "杭州市滨江区",
        "salary_min": 300,
        "salary_max": 400,
        "salary_period": "day",
        "source_name": "manual",
        "source_url": "https://example.com/jobs/1",
        "verification_status": "pending_verification",
    }
    values.update(overrides)
    return Job(**values)


def _requirements(**overrides: object) -> UserRequirements:
    values: dict[str, object] = {
        "desired_role": "AI Intern",
        "locations": ["杭州"],
        "employment_type": "internship",
        "salary_min": 6000,
        "salary_period": "month",
    }
    values.update(overrides)
    return UserRequirements(**values)


class SalaryConversionTest(unittest.TestCase):
    def test_day_rate_becomes_monthly(self) -> None:
        self.assertEqual(to_monthly(300, "day"), 6300)

    def test_year_rate_becomes_monthly(self) -> None:
        self.assertEqual(to_monthly(120000, "year"), 10000)

    def test_unknown_period_is_treated_as_monthly(self) -> None:
        self.assertEqual(to_monthly(8000, None), 8000)

    def test_missing_amount_stays_missing(self) -> None:
        self.assertIsNone(to_monthly(None, "month"))


class HardFilterTest(unittest.TestCase):
    def test_passes_when_every_hard_constraint_matches(self) -> None:
        outcome = hard_filter(_job(), _requirements())

        self.assertTrue(outcome.passed)
        self.assertEqual(outcome.rejections, [])
        self.assertEqual(outcome.unknowns, [])

    def test_rejects_wrong_city(self) -> None:
        outcome = hard_filter(_job(), _requirements(locations=["北京"]))

        self.assertFalse(outcome.passed)
        self.assertIn("地点", outcome.rejections[0])

    def test_rejects_wrong_employment_type(self) -> None:
        outcome = hard_filter(_job(employment_type="full_time"), _requirements())

        self.assertFalse(outcome.passed)
        self.assertIn("正式", outcome.rejections[0])

    def test_day_rate_is_compared_as_monthly(self) -> None:
        outcome = hard_filter(
            _job(salary_min=200, salary_max=250),
            _requirements(salary_min=6000),
        )

        self.assertFalse(outcome.passed)
        self.assertIn("5250", outcome.rejections[0])

    def test_missing_location_is_unknown_not_rejected(self) -> None:
        outcome = hard_filter(_job(location=None), _requirements())

        self.assertTrue(outcome.passed)
        self.assertIn("地点", outcome.unknowns[0])

    def test_missing_salary_period_is_unknown_not_rejected(self) -> None:
        outcome = hard_filter(_job(salary_period=None), _requirements())

        self.assertTrue(outcome.passed)
        self.assertIn("周期", outcome.unknowns[0])

    def test_announced_floor_below_expectation_is_unknown_not_rejected(self) -> None:
        outcome = hard_filter(
            _job(salary_min=5000, salary_max=None, salary_period="month"),
            _requirements(salary_min=10000),
        )

        self.assertTrue(outcome.passed)
        self.assertEqual(outcome.rejections, [])
        self.assertIn("5000", outcome.unknowns[0])
        self.assertIn("上限", outcome.unknowns[0])

    def test_announced_floor_clearing_expectation_passes_without_unknowns(self) -> None:
        outcome = hard_filter(
            _job(salary_min=12000, salary_max=None, salary_period="month"),
            _requirements(salary_min=10000),
        )

        self.assertTrue(outcome.passed)
        self.assertEqual(outcome.rejections, [])
        self.assertEqual(outcome.unknowns, [])

    def test_remote_job_matches_any_city(self) -> None:
        outcome = hard_filter(_job(location="远程"), _requirements(locations=["北京"]))

        self.assertTrue(outcome.passed)

    def test_empty_locations_means_no_location_constraint(self) -> None:
        outcome = hard_filter(_job(location="北京"), _requirements(locations=[]))

        self.assertTrue(outcome.passed)


if __name__ == "__main__":
    unittest.main()
