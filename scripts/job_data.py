r"""Collect, review and verify real postings from the terminal.

    .\.venv\Scripts\python scripts\job_data.py collect --limit 40
    .\.venv\Scripts\python scripts\job_data.py pending
    .\.venv\Scripts\python scripts\job_data.py verify --ids <pending 里复制的前缀> --status active

The collect step is user-triggered on purpose: the source's licence covers
personal study and forbids bulk storage, so this pulls one batch, keeps the
short facts plus a link back to each announcement, and never the notice body.

The verify step is where "found a job" stops being "still hiring". Only a human
verdict moves a posting to ``active``, and the moment of that look is stored
with it. Ids may be given as unique prefixes of what ``pending`` printed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db import SessionLocal, init_db  # noqa: E402 - path setup first
from backend.app.job_sources import (  # noqa: E402
    SourceConfigError,
    SourceUnavailableError,
)
from backend.app.models import Job  # noqa: E402
from backend.app.schemas_resources import (  # noqa: E402
    JobVerificationDecision,
    JobVerificationRequest,
)
from backend.app.schemas_search import JobCollectRequest  # noqa: E402
from backend.app.services import collect_jobs, list_jobs, verify_jobs  # noqa: E402

STATUSES = ["active", "expired", "source_unavailable", "pending_verification"]


def _print_jobs(jobs: list[Job]) -> None:
    if not jobs:
        print("没有符合条件的岗位。")
        return
    for job in jobs:
        print(
            f"{job.id[:12]}  {job.verification_status:<20} {job.title[:26]}\n"
            f"              {job.company[:24]} · {job.location or '地点未标注'}"
        )
        if job.source_url:
            print(f"              {job.source_url}")
        print()


def _collect(args: argparse.Namespace) -> int:
    session = SessionLocal()
    try:
        result = collect_jobs(session, JobCollectRequest(limit=args.limit))
        print(
            f"来源: {result.source}  拉取: {result.fetched}  "
            f"新增: {len(result.created)}  更新: {len(result.updated)}"
        )
        for warning in result.warnings:
            print(f"  ! {warning}")
        print("\n待核验岗位：")
        _print_jobs(
            list_jobs(session, verification_status="pending_verification")[: args.limit]
        )
    except SourceConfigError as exc:
        print(f"配置缺失：{exc}")
        return 1
    except SourceUnavailableError as exc:
        print(f"来源不可用：{exc}")
        return 1
    finally:
        session.close()
    return 0


def _pending(args: argparse.Namespace) -> int:
    session = SessionLocal()
    try:
        jobs = list_jobs(session, verification_status=args.status)[: args.limit]
        print(f"{args.status}：{len(jobs)} 条")
        _print_jobs(jobs)
    finally:
        session.close()
    return 0


def _resolve(session, token: str) -> tuple[str | None, str | None]:
    """Full id from an exact id or an unambiguous prefix."""

    if session.get(Job, token) is not None:
        return token, None
    matches = session.query(Job).filter(Job.id.like(f"{token}%")).limit(2).all()
    if len(matches) == 1:
        return matches[0].id, None
    if not matches:
        return None, f"{token}：找不到对应的岗位"
    return None, f"{token}：前缀不唯一，请输入更长的 id"


def _verify(args: argparse.Namespace) -> int:
    session = SessionLocal()
    try:
        decisions: list[JobVerificationDecision] = []
        problems: list[str] = []
        for token in [part.strip() for part in args.ids.split(",") if part.strip()]:
            job_id, problem = _resolve(session, token)
            if problem:
                problems.append(problem)
                continue
            decisions.append(JobVerificationDecision(job_id=job_id, status=args.status))

        if decisions:
            result = verify_jobs(
                session, JobVerificationRequest(decisions=decisions)
            )
            print(f"已记录: {len(result.updated)} 条  → {args.status}")
            for item in result.rejected:
                print(f"  ! {item.job_id}: {item.reason}")
        for problem in problems:
            print(f"  ! {problem}")
        return 1 if problems else 0
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="拉取一批岗位并入库")
    collect_parser.add_argument("--limit", type=int, default=40)
    collect_parser.set_defaults(handler=_collect)

    pending_parser = subparsers.add_parser("pending", help="列出某个状态的岗位")
    pending_parser.add_argument("--status", default="pending_verification", choices=STATUSES)
    pending_parser.add_argument("--limit", type=int, default=30)
    pending_parser.set_defaults(handler=_pending)

    verify_parser = subparsers.add_parser("verify", help="记录人工核验结论")
    verify_parser.add_argument("--ids", required=True, help="逗号分隔的 id 或唯一前缀")
    verify_parser.add_argument("--status", required=True, choices=STATUSES)
    verify_parser.set_defaults(handler=_verify)

    args = parser.parse_args()
    init_db()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
