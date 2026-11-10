"""기출 비교 (개발기획안 8.7): 샘플·자기 자료의 출제 점수 상위 10개 중 실제 출제 개념이 몇 개인지.

    BINTM_FAKE_AI=1 python scripts/compare_exam.py --exam tests/기출_개념표.json
    python scripts/compare_exam.py --material 내자료.pdf --transcript 대본.txt --exam 기출_개념표.json

기출_개념표.json 형식: {"concepts": ["이진 트리의 순회", "힙의 삭제 연산", ...]}  (문제 원문은 넣지 않는다)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import concepts as C  # noqa: E402
from core import score  # noqa: E402
from core.extract import extract, mask  # noqa: E402
from core.utterances import find_utterances  # noqa: E402


def top_hits(ranked: list[str], exam: list[str], k: int = 10) -> int:
    """상위 k개 이름 중 기출 개념과 이름이 겹치는(한쪽이 다른 쪽을 포함) 개수."""
    hits = 0
    for name in ranked[:k]:
        if any(e in name or name in e for e in exam):
            hits += 1
    return hits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--material", default=str(ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"))
    ap.add_argument("--transcript", default=str(ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"))
    ap.add_argument("--exam", required=True)
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()
    path = Path(args.material)
    material = extract(path.name, path.read_bytes())
    transcript = mask(Path(args.transcript).read_text(encoding="utf-8")) if args.transcript else ""
    found = C.extract_concepts(material)
    utts = find_utterances(transcript, found["concepts"])
    scores = score.compute_scores(found["concepts"], utts, score.meta_pages(material["pages"], found))["scores"]
    exam = json.loads(Path(args.exam).read_text(encoding="utf-8"))["concepts"]
    ranked = [s["name"] for s in scores]
    print(f"상위 {args.top}개 중 실제 출제 개념: {top_hits(ranked, exam, args.top)} / {min(args.top, len(ranked))}")
    for s in scores[: args.top]:
        print(f"{s['rank']:>2}. {s['name']} {s['pct']}점")


if __name__ == "__main__":
    main()
