from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .models import Job
from .schemas import SalaryPeriod
from .schemas_resources import UserRequirements


MONTHLY_WORKDAYS = 21
REMOTE_MARKERS = {"remote", "线上", "远程", "不限", "全国"}
EMPLOYMENT_LABELS: dict[str, str] = {
    "internship": "实习",
    "part_time": "兼职",
    "full_time": "正式",
    "contract": "合同制",
}
_LOCATION_SPLIT = re.compile(r"[/、,，;；|·\s]+")


def to_monthly(amount: int | None, period: SalaryPeriod | None) -> int | None:
    """Convert an amount to an approximate monthly figure.

    ``day`` uses 21 workdays per month so an internship day rate is comparable
    with a monthly salary instead of being rejected as obviously too low.
    Unknown periods are treated as monthly.
    """

    if amount is None:
        return None
    if period == "day":
        return amount * MONTHLY_WORKDAYS
    if period == "year":
        return round(amount / 12)
    return amount


def location_tokens(value: str) -> list[str]:
    return [
        token.strip().lower()
        for token in _LOCATION_SPLIT.split(value)
        if token.strip()
    ]


class FilterOutcome(BaseModel):
    passed: bool
    rejections: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


def _label(value: str) -> str:
    return EMPLOYMENT_LABELS.get(value, value)


def _check_employment_type(
    job: Job, requirements: UserRequirements
) -> tuple[bool | None, str]:
    if job.employment_type is None:
        return None, "岗位类型信息缺失"
    if job.employment_type != requirements.employment_type:
        return (
            False,
            f"岗位类型为{_label(job.employment_type)}，"
            f"期望{_label(requirements.employment_type)}",
        )
    return True, ""


def _check_location(job: Job, requirements: UserRequirements) -> tuple[bool | None, str]:
    wanted = [
        token
        for location in requirements.locations
        for token in location_tokens(location)
    ]
    if not wanted:
        return True, ""
    if not job.location:
        return None, "岗位地点信息缺失"
    job_tokens = location_tokens(job.location)
    if any(token in REMOTE_MARKERS for token in job_tokens):
        return True, ""
    for want in wanted:
        for actual in job_tokens:
            if want in actual or actual in want:
                return True, ""
    return (
        False,
        f"岗位地点为{job.location}，期望{', '.join(requirements.locations)}",
    )


def _check_salary(job: Job, requirements: UserRequirements) -> tuple[bool | None, str]:
    if requirements.salary_min is None:
        return True, ""
    if job.salary_min is None and job.salary_max is None:
        return None, "岗位薪资信息缺失"
    if job.salary_period is None:
        return None, "岗位薪资周期未标注，无法与期望值比较"

    ceiling = to_monthly(
        job.salary_max if job.salary_max is not None else job.salary_min,
        job.salary_period,
    )
    if ceiling is None:
        return None, "岗位薪资信息缺失"

    floor = to_monthly(requirements.salary_min, requirements.salary_period)
    if floor is not None and ceiling < floor:
        return False, f"岗位月薪上限约 {ceiling}，低于期望下限 {floor}"
    return True, ""


def hard_filter(job: Job, requirements: UserRequirements) -> FilterOutcome:
    """Apply the deterministic hard constraints before any scoring.

    A missing field is reported as unknown instead of rejected, so incomplete
    job data never silently disappears from the result list.
    """

    rejections: list[str] = []
    unknowns: list[str] = []

    checks = (
        _check_employment_type(job, requirements),
        _check_location(job, requirements),
    )
    for ok, reason in checks:
        if ok is False:
            rejections.append(reason)
        elif ok is None:
            unknowns.append(reason)

    salary_ok, salary_reason = _check_salary(job, requirements)
    if salary_ok is False:
        rejections.append(salary_reason)
    elif salary_ok is None:
        unknowns.append(salary_reason)

    return FilterOutcome(
        passed=not rejections,
        rejections=rejections,
        unknowns=unknowns,
    )
