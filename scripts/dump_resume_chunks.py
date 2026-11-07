r"""Print the blocks and chunks for one resume file, so extraction can be eyeballed.

    .\.venv\Scripts\python scripts\dump_resume_chunks.py path\to\resume.pdf

Run it during development, not in production: the point is to see what the
parser actually produced before blaming the model for a bad profile.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.chunking import (  # noqa: E402 - the path setup has to run first
    Block,
    blocks_from_docx,
    blocks_from_pdf,
    blocks_from_text,
    chunk_blocks,
    plan_context,
    render_context,
)


def load_blocks(path: Path) -> list[Block]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return blocks_from_pdf(path)
    if suffix == ".docx":
        return blocks_from_docx(path)
    if suffix in {".txt", ".md"}:
        return blocks_from_text(path.read_text(encoding="utf-8"))
    raise SystemExit(f"unsupported file type: {suffix or path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--budget", type=int, default=6000)
    args = parser.parse_args()

    blocks = load_blocks(args.path)
    print(f"blocks: {len(blocks)}")
    for block in blocks:
        preview = block.text.replace("\n", " ")[:60]
        print(f"  {block.block_id} [{block.section}] {preview}")

    chunks = chunk_blocks(blocks, max_tokens=args.max_tokens)
    plan = plan_context(chunks, budget=args.budget)
    print(
        f"\nchunks: {len(chunks)}  tokens: {plan.total_tokens}  "
        f"mode: {plan.mode}  budget: {plan.budget}"
    )
    print("\n" + render_context(chunks))


if __name__ == "__main__":
    main()
