"""Check a stored posting against the page it was collected from.

The probe answers one question: is the announcement still there? It answers it
in the only direction a machine can be trusted with — a page that returns 404 or
says 已截止 is evidence the posting is closed, while a page that returns 200 is
not evidence that anyone is still hiring. So ``alive`` never upgrades a posting;
it only records that the check happened.

Everything here is read-only and bounded: a timeout, a byte cap, and no
credentials. Probing is a maintenance action a person triggers, not a crawler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

Verdict = Literal["alive", "gone", "unreachable", "no_source"]

# Text a closed announcement tends to carry. Matched against the page body, not
# the URL, and only as a signal that the posting is over — never the reverse.
CLOSED_MARKERS = (
    "已下线",
    "已截止",
    "招聘已结束",
    "报名已结束",
    "该职位已关闭",
    "职位已过期",
    "投递已结束",
)

DEFAULT_TIMEOUT_SECONDS = 5.0
# Enough to cover the text of a recruitment notice; a page that needs more than
# this to say "已截止" is not the page this check is for.
MAX_BYTES = 200_000


@dataclass(frozen=True)
class ProbeOutcome:
    job_id: str
    verdict: Verdict
    detail: str


def _decode(raw: bytes, declared: str | None) -> str:
    """Text of the page, trying the encoding the server declared first.

    Chinese recruiting sites still ship GB18030 pages, and decoding those as
    UTF-8 would silently mangle the very markers this check looks for.
    """

    for candidate in (declared, "utf-8", "gb18030"):
        if not candidate:
            continue
        try:
            return raw.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="ignore")


class JobProber:
    """Fetch one source page and say whether it still exists."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        max_bytes: int = MAX_BYTES,
    ) -> None:
        self._timeout = timeout
        self._transport = transport
        self._max_bytes = max_bytes

    def probe(self, job_id: str, url: str | None) -> ProbeOutcome:
        if not url:
            return ProbeOutcome(job_id, "no_source", "岗位没有来源链接，无法核验")

        try:
            with httpx.Client(
                timeout=self._timeout,
                follow_redirects=True,
                transport=self._transport,
            ) as client:
                with client.stream("GET", url) as response:
                    status = response.status_code
                    if status in (404, 410):
                        return ProbeOutcome(job_id, "gone", f"来源返回 HTTP {status}")
                    if status >= 400:
                        # 403/429 are the site refusing a bot, not a closed job.
                        return ProbeOutcome(
                            job_id, "unreachable", f"来源返回 HTTP {status}"
                        )

                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) >= self._max_bytes:
                            break
                    text = _decode(bytes(body), response.charset_encoding)
        except httpx.HTTPError as exc:
            return ProbeOutcome(
                job_id, "unreachable", f"请求失败：{type(exc).__name__}"
            )

        for marker in CLOSED_MARKERS:
            if marker in text:
                return ProbeOutcome(job_id, "gone", f"页面出现「{marker}」")
        return ProbeOutcome(job_id, "alive", f"HTTP {status}，未出现下线标记")
