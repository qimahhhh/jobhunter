r"""Run the Career input stage end to end on one resume file, model included.

    .\.venv\Scripts\python scripts\extract_resume.py path\to\resume.pdf

``dump_resume_chunks.py`` stops at the prompt; this one makes the real call and
prints what came back next to the check that decides whether the draft can be
trusted. Run it before touching a prompt: most "the model got the profile
wrong" cases turn out to be a parse the model never saw correctly.

Needs ``DEEPSEEK_API_KEY`` in ``.env``, plus ``pdfplumber`` for PDF input.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
for search_path in (ROOT, HERE):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from dump_resume_chunks import load_blocks  # noqa: E402 - path setup must run first

from backend.app.chunking import (  # noqa: E402
    chunk_blocks,
    plan_context,
    render_context,
)
from backend.app.extractor import extract_profile_from_blocks  # noqa: E402
from backend.app.llm import DeepSeekClient, LLMError  # noqa: E402


class CountingClient:
    """Wraps the real client so the report can say how many calls it took."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.calls = 0

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        self.calls += 1
        return self.inner.complete_json(system=system, user=user)


def _normalize(text: str) -> str:
    return "".join(text.lower().split())


def _unsupported_skills(skills: list[str], cited_text: str) -> list[str]:
    """Skills that do not appear in the text of the chunks the model cited.

    A cheap stand-in for the check the extractor does not do yet: a citation
    that exists is not the same as a citation that supports the claim.
    """

    haystack = _normalize(cited_text)
    return [skill for skill in skills if _normalize(skill) not in haystack]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--budget", type=int, default=6000)
    parser.add_argument(
        "--show-chunks",
        action="store_true",
        help="print every chunk header with a short preview",
    )
    args = parser.parse_args()

    blocks = load_blocks(args.path)
    chunks = chunk_blocks(blocks, max_tokens=args.max_tokens)
    plan = plan_context(chunks, budget=args.budget)

    print(f"file:    {args.path}")
    print(
        f"parse:   blocks={len(blocks)} chunks={len(chunks)} "
        f"tokens={plan.total_tokens} prompt_mode={plan.mode} budget={plan.budget}"
    )
    if not chunks:
        print("\n解析没有产出任何 chunk：扫描件、纯图片或字体编码损坏，先换一份文件。")
        return

    empty_sections = {chunk.section for chunk in chunks if not chunk.text.strip()}
    if empty_sections:
        print(f"空 chunk 的 section：{sorted(empty_sections)}")

    if args.show_chunks:
        for chunk in chunks:
            preview = chunk.text.replace("\n", " ")[:80]
            print(f"  {chunk.chunk_id} [{chunk.section}] {preview}")

    context = render_context(chunks)
    readable = sum(1 for character in context if character.isalnum() or "\u4e00" <= character <= "\u9fff")
    ratio = readable / max(len(context), 1)
    print(f"readable: {ratio:.0%} of the rendered context is letters or digits")
    if ratio < 0.6:
        print("  可读字符占比过低，PDF 很可能是扫描件或字体映射坏了 —— 先别怪模型。")

    try:
        client = CountingClient(DeepSeekClient())
    except LLMError as exc:
        print(f"\n模型客户端没建起来：{exc}")
        return

    started = time.perf_counter()
    result = extract_profile_from_blocks(
        blocks, client, max_chunk_tokens=args.max_tokens  # type: ignore[arg-type]
    )
    elapsed = time.perf_counter() - started

    print(f"\nmodel:   calls={client.calls} elapsed={elapsed:.1f}s degraded={result.degraded}")
    print(f"cited:   {result.evidence or '（无）'}")
    if result.unresolved:
        print(f"  dropped: {result.unresolved}  <- 这些 chunk id 不存在，属于编造引用")

    if result.profile is None:
        print("profile: 没有可用的画像草稿")
    else:
        print(f"\nsummary: {result.profile.summary}")
        print(f"skills ({len(result.profile.skills)}): {result.profile.skills}")
        for item in result.profile.experiences:
            print(f"  - {item}")

        cited_text = "\n".join(
            chunk.text for chunk in chunks if chunk.chunk_id in set(result.evidence)
        )
        unsupported = _unsupported_skills(result.profile.skills, cited_text)
        if unsupported:
            print(
                "\n证据未覆盖的技能：" + ", ".join(unsupported)
                + "\n  引用 id 是真的，但被引 chunk 的原文里没有这些词 —— 抽查几条再决定要不要信。"
            )

    if result.notes:
        print("\nnotes:")
        for note in result.notes:
            print(f"  - {note}")

    print(
        "\n判定："
        f"\n  解析层：{len(blocks)} blocks / {len(chunks)} chunks / 可读率 {ratio:.0%}"
        f"\n  抽取层：degraded={result.degraded} 引用 {len(result.evidence)} 条，"
        f"丢弃 {len(result.unresolved)} 条"
    )


if __name__ == "__main__":
    main()
