"""Demo script — runs all 5 research questions and saves output to artefacts/.

Usage:
    python scripts/demo.py                  # live API calls
    python scripts/demo.py --offline        # uses cached results only (no-network)

Output is saved to artefacts/demo_output.txt for submission.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cli import format_answer
from src.core.researcher import research

QUESTIONS_FILE = Path(__file__).parent.parent / "data" / "research_questions.json"
ARTEFACTS_DIR = Path(__file__).parent.parent / "artefacts"


def load_questions() -> list[dict]:
    with open(QUESTIONS_FILE) as f:
        return json.load(f)["questions"]


async def run_question(text: str, no_cache: bool) -> str:
    answer = await research(text, no_cache=no_cache)
    return format_answer(answer)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all 5 demo research questions")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use cached results only — no network calls (requires prior run)",
    )
    args = parser.parse_args()

    questions = load_questions()
    ARTEFACTS_DIR.mkdir(exist_ok=True)
    output_path = ARTEFACTS_DIR / "demo_output.txt"

    lines = [
        "=" * 72,
        f"Async Research Assistant — Demo Run",
        f"Timestamp : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Mode      : {'offline (cache only)' if args.offline else 'live API calls'}",
        f"Questions : {len(questions)}",
        "=" * 72,
        "",
    ]

    for i, q in enumerate(questions, 1):
        text = q["text"]
        difficulty = q.get("difficulty", "?")
        print(f"\n[{i}/{len(questions)}] ({difficulty}) {text}")

        try:
            formatted = asyncio.run(run_question(text, no_cache=not args.offline))
            lines.append(f"Q{i} [{difficulty.upper()}]: {text}")
            lines.append(formatted)
        except Exception as exc:
            error_line = f"Q{i} FAILED: {exc}"
            print(f"  ERROR: {exc}")
            lines.append(error_line)
            lines.append("")

    # Write to artefacts/
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ Output saved to {output_path}")
    print(f"  {len(questions)} questions processed")


if __name__ == "__main__":
    main()