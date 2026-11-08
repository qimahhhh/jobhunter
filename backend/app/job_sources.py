from __future__ import annotations

import os
import re
from typing import Any, Protocol

import httpx

from .llm import _load_env
from .schemas import EmploymentType
from .schemas_resources import JobCreate

DEFAULT_BASE_URL = "https://openapi.offerxiansheng.com/backend-service/open/v1"
SOURCE_NAME = "offerxiansheng.com"

_SPLIT_RE = re.compile(r"[,，、;；]+")


class JobSourceError(RuntimeError):
    """A collector failure the API layer turns into a named HTTP error."""


class SourceConfigError(JobSourceError):
    """This deployment holds no credentials for the source."""


class SourceUnavailableError(JobSourceError):
    """The source could not be reached, or answered with something unusable."""


class JobSource(Protocol):
    """What a collector has to provide to take part in ``collect_jobs``."""

    name: str

    def fetch_recent(self, *, limit: int) -> list[Any]: ...


class OfferCampusSource:
    """Read-only client for the Offer先生 campus recruitment open API.

    The source's license limits its data to personal study and research and
    forbids bulk storage and redistribution. The raw notice text therefore
    stays inside this call: ``fetch_recent`` returns what the API sent, and
    ``notices_to_jobs`` keeps only the short factual fields plus a link back to
    the announcement. What reaches the database is a reference, not a mirror.
    """

    name = SOURCE_NAME

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 15.0,
    ) -> None:
        _load_env()
        self._api_key = (api_key or os.getenv("OFFER_CAMPUS_API_KEY", "")).strip()
        if not self._api_key:
            raise SourceConfigError(
                "OFFER_CAMPUS_API_KEY 未配置，无法采集岗位数据。"
            )
        self._base_url = (
            base_url or os.getenv("OFFER_CAMPUS_API_BASE", DEFAULT_BASE_URL)
        ).rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def fetch_recent(self, *, limit: int) -> list[Any]:
        """The newest campus recruitment notices, exactly as the source sent them.

        Only the transport and the response envelope belong here; whether an
        item is usable is decided downstream, so the caller can report skipped
        records instead of silently receiving a shorter list.
        """

        try:
            with httpx.Client(
                transport=self._transport, timeout=self._timeout
            ) as client:
                response = client.get(
                    f"{self._base_url}/campus-recruit/recent",
                    params={"limit": limit},
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"岗位来源请求失败：{exc}") from exc

        if response.status_code in (401, 403):
            raise SourceUnavailableError("岗位来源拒绝了当前 API Key（鉴权失败）。")
        if response.status_code != 200:
            raise SourceUnavailableError(
                f"岗位来源返回 HTTP {response.status_code}，暂不可用。"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceUnavailableError("岗位来源返回了无法解析的内容。") from exc

        if not isinstance(payload, dict) or payload.get("code") != 1000:
            message = payload.get("message") if isinstance(payload, dict) else None
            raise SourceUnavailableError(
                f"岗位来源返回失败状态：{message or '响应缺少可用的业务状态码'}。"
            )

        data = payload.get("data")
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise SourceUnavailableError("岗位来源响应缺少 data.items。")
        return items


def _positions(item: dict[str, Any]) -> list[str]:
    """The openings one notice covers, as separate postings.

    ``content`` holds the opening names and ``recruitPosInfoNameList`` the job
    families; a notice that publishes neither is one posting under its own
    title. Splitting is deterministic on purpose: these are published lists,
    not prose to interpret.
    """

    for key in ("content", "recruitPosInfoNameList"):
        names = [part.strip() for part in _SPLIT_RE.split(str(item.get(key) or ""))]
        names = [name for name in names if name]
        if names:
            return names
    title = str(item.get("recruitInfoName") or "").strip()
    return [title] if title else []


def _employment_type(item: dict[str, Any], position: str) -> EmploymentType:
    """Internship when any published label says so, full-time otherwise.

    The campus feed mixes autumn recruitment with internship drives, and only
    the notice itself says which is which. Guessing from the employer would be
    invention; reading the label is not.
    """

    marker = " ".join(
        [str(item.get("recruitInfoName") or ""), str(item.get("tag") or ""), position]
    )
    return "internship" if "实习" in marker else "full_time"


def _fact_lines(item: dict[str, Any]) -> list[str]:
    """The requirement facts a notice publishes, as label lines."""

    lines = []
    for label, key in (
        ("岗位类别", "recruitPosInfoNameList"),
        ("学历要求", "domesticEducation"),
        ("毕业年份", "domesticGraduationDate"),
        ("招聘年份", "date"),
    ):
        value = str(item.get(key) or "").strip()
        if value:
            lines.append(f"{label}：{value}")
    return lines


def _source_url(item: dict[str, Any]) -> str | None:
    """The announcement link, and nothing that is not a link.

    The ``url`` field sometimes holds "投递邮箱:someone@example.com" instead of
    an address, so only something that actually looks like a URL is kept.
    """

    for key in ("announcementUrl", "url"):
        value = str(item.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            return value[:2048]
    return None


def notices_to_jobs(items: list[Any]) -> tuple[list[JobCreate], list[str]]:
    """Turn source notices into postings: facts and links, never notice text.

    The ``richText`` body is deliberately dropped here. The source license
    forbids bulk storage, and the fields a posting needs (who recruits, which
    opening, where, what degree) are short facts that travel fine. A record
    that cannot carry those facts is skipped with a warning, because a batch
    that silently shrinks is a batch nobody can argue with.
    """

    jobs: list[JobCreate] = []
    warnings: list[str] = []

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            warnings.append(f"第 {index} 条记录不是可识别的对象，已跳过。")
            continue

        notice_title = str(item.get("recruitInfoName") or "").strip()
        company = str(item.get("enterpriseName") or "").strip()
        if not company:
            warnings.append(
                f"公告「{notice_title or f'第 {index} 条'}」缺少企业名称，已跳过。"
            )
            continue

        positions = _positions(item)
        if not positions:
            warnings.append(f"公告「{notice_title or company}」没有可用的岗位名称，已跳过。")
            continue

        facts = _fact_lines(item)
        location = str(item.get("cityNameList") or "").strip() or None
        source_name = str(item.get("source") or SOURCE_NAME).strip() or SOURCE_NAME
        source_url = _source_url(item)
        context = (
            "；".join(
                part
                for part in (
                    f"「{notice_title}」" if notice_title else "",
                    str(item.get("tag") or "").strip(),
                )
                if part
            )
            or "校园招聘公告"
        )

        for position in positions:
            jobs.append(
                JobCreate(
                    title=position[:255],
                    company=company[:255],
                    description=context,
                    requirements="；".join([f"岗位：{position}", *facts]),
                    employment_type=_employment_type(item, position),
                    source_name=source_name[:255],
                    source_url=source_url,
                    location=location,
                )
            )

    return jobs, warnings
