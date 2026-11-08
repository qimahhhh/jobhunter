r"""Run one match and one interview end to end, and print what the agent decided.

    uv run python scripts/interview_smoke.py
    uv run python scripts/interview_smoke.py --answers 4 --max-turns 6 --interactive
    uv run python scripts/interview_smoke.py --profile-id <id> --job-id <id>

The default run is hermetic: an in-memory database with a built-in sample
profile and posting, so rehearsing does not add rows to the demo data. Point it
at stored rows with ``--profile-id``/``--job-id`` and it uses ``DATABASE_URL``
instead.

The output is the point. It prints the requirement breakdown the score rests on,
the plan the interviewer committed to, and the reason recorded for every
question — because the failures worth catching here are invisible from an "ok":
a model inventing requirements, questions that could be asked of anyone, a
follow-up that did not read the previous answer, or a silent fall back to the
rule-based question. A smoke script that printed only success would hide exactly
the things it exists to show.

Exit codes: ``0`` when the run completed, ``1`` when there is no model client,
``2`` when the data cannot support the run (hard constraint, no requirements).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine  # noqa: E402 - the path setup has to run first
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from backend.app.llm import DeepSeekClient, LLMClient, LLMError  # noqa: E402
from backend.app.models import Base  # noqa: E402
from backend.app.schemas_interview import (  # noqa: E402
    InterviewAnswerRequest,
    InterviewEvaluation,
    InterviewSessionRead,
    InterviewStartRequest,
)
from backend.app.schemas_resources import (  # noqa: E402
    CapabilityProfile,
    JobCreate,
    JobMatchCreate,
    JobMatchRead,
    ProfileCreate,
    UserCreate,
    UserRequirements,
)
from backend.app.services import (  # noqa: E402
    ConstraintRejectedError,
    InterviewFinishedError,
    InterviewNotPossibleError,
    NotFoundError,
    answer_interview,
    create_job,
    create_job_match,
    create_profile,
    create_user,
    evaluate_interview,
    start_interview_session,
)

WIDTH = 72

SAMPLE_PROFILE = {
    "summary": "计算机专业本科在读，有两段后端开发实习，主要用 Python 写接口。",
    "skills": ["Python", "FastAPI", "MySQL", "Git"],
    "experiences": [
        "字节跳动 后端开发实习：负责推荐接口的批量查询优化，QPS 提升 40%",
        "校内项目：用 FastAPI 做课程预约系统，日活约 300 人",
    ],
}

SAMPLE_JOB = {
    "title": "后端开发实习生",
    "company": "示例科技",
    "description": "负责招聘平台的后端接口开发与性能优化，参与服务拆分。",
    "requirements": (
        "熟悉 Python，了解 FastAPI 或 Flask；"
        "熟悉 MySQL 与 Redis；"
        "有分布式系统设计经验；"
        "有开源项目贡献者优先"
    ),
}

# Deliberately uneven: some answers claim things the profile does not mention,
# which is where a follow-up should appear. Handing the agent four confident
# answers would test the happy path and nothing else.
SCRIPTED_ANSWERS = (
    "我在字节跳动做后端实习，用 Python + FastAPI 写推荐接口，"
    "做过一次批量查询优化，QPS 从 1.2k 提到 1.7k。",
    "缓存用的 Redis，主要放热点数据。遇到过缓存穿透，加了空值缓存和布隆过滤器。",
    "分布式这块我了解得比较浅，只在课程项目里用过消息队列做异步解耦，没有做过真正的服务拆分。",
    "Go 我只写过一点练习题，生产项目里没用过。",
)


class _CountingClient:
    """Delegates to the real client and records what the run cost.

    A rehearsal needs the timing more than the transcript: eight turns at three
    seconds each is a different demo from eight turns at one.
    """

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.calls = 0
        self.seconds = 0.0

    def complete_json(self, *, system: str, user: str) -> dict[str, object]:
        self.calls += 1
        started = time.perf_counter()
        try:
            return self.inner.complete_json(system=system, user=user)
        finally:
            self.seconds += time.perf_counter() - started


def _line(char: str = "─") -> None:
    print(char * WIDTH)


def _memory_session() -> Session:
    """A throwaway database, kept on one connection so every query sees it."""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _stored_session() -> Session:
    """The real database, opened only when the caller names stored rows.

    Imported here rather than at module scope so a hermetic run never creates
    ``ai_job_hunter.db``: the module builds its engine from ``DATABASE_URL`` on
    import, and a smoke run has no business touching that file.
    """

    from backend.app.db import SessionLocal, init_db

    init_db()
    return SessionLocal()


def _seed(session: Session) -> tuple[str, str]:
    user = create_user(
        session,
        UserCreate(email="smoke@example.com", display_name="冒烟候选人"),
    )
    profile = create_profile(
        session,
        ProfileCreate(
            user_id=user.id,
            requirements=UserRequirements(
                desired_role="后端开发实习生", employment_type="internship"
            ),
            capabilities=CapabilityProfile(**SAMPLE_PROFILE),
        ),
    )
    job = create_job(
        session,
        JobCreate(
            **SAMPLE_JOB,
            employment_type="internship",
            source_name="smoke-script",
            location="北京",
        ),
    )
    return profile.id, job.id


def _print_match(match: JobMatchRead) -> None:
    _line()
    print(
        f"匹配得分 {match.score:.2f}   置信度 {match.confidence:.2f}   "
        f"需求来源 {match.score_source}"
    )
    print(
        "硬性要求："
        + (
            "、".join(match.must_gaps) + "（未达成，仍可投递）"
            if match.must_gaps
            else "全部覆盖"
        )
    )
    print()
    for row in match.breakdown:
        print(
            f"  {row.status:<8} {row.kind:<6} {row.dimension:<10} "
            f"权重 {row.weight:<4.1f} 覆盖 {row.coverage:.2f}  {row.text}"
        )
        if row.evidence:
            print(f"           命中位置：{'/'.join(row.evidence)}")
    _line()


def _print_plan(state: InterviewSessionRead) -> None:
    print(f"\n访谈计划（{len(state.plan.targets)} 条，可以中途偏离）：")
    if state.plan.opening:
        print(f"  开场：{state.plan.opening}")
    for target in state.plan.targets:
        print(f"  - {target.requirement_id}  {target.question}")
    _print_notes(state.notes)


def _print_notes(notes: list[str]) -> None:
    """Degradations get printed, not smoothed over."""

    for note in notes:
        print(f"  ⚠ {note}")


def _print_question(state: InterviewSessionRead) -> None:
    turn = state.turns[-1]
    print(f"\n第 {turn.index} 轮 · {turn.kind} · {turn.requirement_id}")
    if turn.requirement_text:
        print(f"  对应需求：{turn.requirement_text}")
    print(f"  问：{turn.question}")
    if turn.why:
        print(f"  为什么：{turn.why}")


def _run_interview(
    session: Session,
    profile_id: str,
    job_id: str,
    client: _CountingClient,
    *,
    answers: int,
    max_turns: int,
    interactive: bool,
    requirement_texts: dict[str, str],
) -> InterviewSessionRead:
    state = start_interview_session(
        session,
        InterviewStartRequest(
            profile_id=profile_id, job_id=job_id, max_turns=max_turns
        ),
        client,
    )
    _print_plan(state)
    _print_question(state)

    asked = 0
    while asked < answers and state.status != "finished":
        if interactive:
            try:
                answer = input("  你的回答：").strip()
            except EOFError:
                break
            if not answer:
                break
        else:
            answer = SCRIPTED_ANSWERS[asked % len(SCRIPTED_ANSWERS)]
            print(f"  答：{answer}")

        known = len(state.notes)
        try:
            state = answer_interview(
                session, state.id, InterviewAnswerRequest(answer=answer), client
            )
        except InterviewFinishedError as exc:
            print(f"  ! {exc}")
            break
        _print_notes(state.notes[known:])
        asked += 1

        if state.status != "finished":
            _print_question(state)

    _line()
    if state.status == "finished":
        print(f"面试结束：{state.finish_reason}")
    else:
        print(f"未结束（已问 {len(state.turns)} 轮，上限 {state.max_turns}）")
    print(f"尚未覆盖的需求：{'、'.join(state.remaining) or '无'}")
    for requirement_id in state.remaining:
        text = requirement_texts.get(requirement_id, "")
        if text:
            print(f"  - {requirement_id}  {text}")
    return state


def _print_evaluation(evaluation: InterviewEvaluation) -> None:
    """The review: one line per requirement, each with the quote it rests on."""

    answered = sum(1 for verdict in evaluation.verdicts if verdict.verdict == "answered")
    _line()
    print(
        f"面试复盘：{answered}/{len(evaluation.verdicts)} 条答到核心"
        f"（覆盖率 {evaluation.coverage:.0%}）"
    )
    for verdict in evaluation.verdicts:
        print(f"  [{verdict.verdict}] {verdict.requirement_id}  {verdict.requirement_text}")
        if verdict.evidence:
            print(f"    原句：{verdict.evidence}")
        if verdict.gap:
            print(f"    差在：{verdict.gap}")
        if verdict.suggestion:
            print(f"    建议：{verdict.suggestion}")
    for title, items in (
        ("优势", evaluation.strengths),
        ("改进建议", evaluation.suggestions),
    ):
        if not items:
            continue
        print(f"\n{title}：")
        for item in items:
            print(f"  - {item}")
    if evaluation.overall:
        print(f"\n总评：{evaluation.overall}")
    _print_notes(evaluation.notes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-id", help="已存画像 id；与 --job-id 一起使用时读真实数据库")
    parser.add_argument("--job-id", help="已存岗位 id；与 --profile-id 一起使用时读真实数据库")
    parser.add_argument(
        "--answers", type=int, default=4, help="自动回答几轮（默认 4）"
    )
    parser.add_argument(
        "--max-turns", type=int, default=4, help="轮次上限（默认 4，默认值会跑完并给复盘）"
    )
    parser.add_argument(
        "--interactive", action="store_true", help="手动输入回答，而不是用脚本里的样例"
    )
    args = parser.parse_args()

    if bool(args.profile_id) != bool(args.job_id):
        parser.error("--profile-id 和 --job-id 需要同时给出")

    try:
        client = _CountingClient(DeepSeekClient())
    except LLMError as exc:
        print(f"没有可用的模型客户端：{exc}")
        print("在 .env 里配置 DEEPSEEK_API_KEY 后重试。")
        return 1

    name = getattr(client.inner, "name", "model")
    model = getattr(client.inner, "model", "?")
    print(f"模型：{name} / {model}")

    session = _memory_session() if not args.profile_id else _stored_session()
    started = time.perf_counter()
    try:
        if args.profile_id and args.job_id:
            profile_id, job_id = args.profile_id, args.job_id
            print("数据：真实数据库里的已存画像与岗位")
        else:
            profile_id, job_id = _seed(session)
            print("数据：内置样例画像 + 样例岗位（内存数据库，不写入演示数据）")

        match = create_job_match(
            session,
            JobMatchCreate(user_profile_id=profile_id, job_id=job_id),
            client,
        )
        match_report = JobMatchRead.model_validate(match)
        _print_match(match_report)

        state = _run_interview(
            session,
            profile_id,
            job_id,
            client,
            answers=args.answers,
            max_turns=args.max_turns,
            interactive=args.interactive,
            requirement_texts={
                row.requirement_id: row.text for row in match_report.breakdown
            },
        )
        if state.status == "finished":
            try:
                _print_evaluation(evaluate_interview(session, state.id, client))
            except LLMError as exc:
                # The review is a separate step: failing it says nothing about
                # the interview that just finished.
                print(f"\n复盘生成失败：{exc}")
        else:
            print(
                "\n面试未结束，没有复盘可看。"
                "想看完整反馈：--max-turns N --answers N（例如 --max-turns 4 --answers 4）"
            )
    except ConstraintRejectedError as exc:
        print("岗位没有通过画像的硬约束：" + "；".join(exc.outcome.rejections))
        return 2
    except InterviewNotPossibleError as exc:
        print(f"无法安排面试：{exc}")
        return 2
    except NotFoundError as exc:
        print(f"找不到记录：{exc}")
        return 2
    finally:
        session.close()

    _line()
    print(
        f"模型调用 {client.calls} 次，其中等待 {client.seconds:.1f}s，"
        f"总耗时 {time.perf_counter() - started:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
