"""기출 비교 (개발기획안 8.7): 상위 10개 중 실제 출제 개념 수.

    python scripts/compare_exam.py --concepts 01결과.json --utterances 02결과.json --pdf 자료.pdf --exam tests/기출_개념표.json

기출_개념표.json 형식: {"concepts": ["힙의 삭제 연산", "이진 트리의 순회", ...]} (문제 원문은 넣지 않는다)
AI를 부르지 않는다. 저장된 호출 1·2 결과로 점수만 다시 계산한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.concepts import clean_concepts  # noqa: E402
from core.extract import extract  # noqa: E402
from core.score import compute_scores  # noqa: E402


def top_hits(score_rows: list[dict], exam_names: list[str], top: int = 10) -> tuple[int, list[str]]:
    exam = {n.strip() for n in exam_names}
    hits = [r["name"] for r in score_rows[:top] if r["name"].strip() in exam]
    return len(hits), hits


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concepts", required=True)
    ap.add_argument("--utterances")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--exam", required=True)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args(argv)
    pdf = Path(a.pdf)
    material = extract(pdf.name, pdf.read_bytes())
    cres = clean_concepts(json.loads(Path(a.concepts).read_text(encoding="utf-8")), material)
    utts = json.loads(Path(a.utterances).read_text(encoding="utf-8"))["utterances"] if a.utterances else []
    scores = compute_scores(cres["concepts"], utts, cres["meta_pages"])
    exam = json.loads(Path(a.exam).read_text(encoding="utf-8"))["concepts"]
    n, hits = top_hits(scores["scores"], exam, a.top)
    print(f"상위 {a.top}개 중 실제 출제 개념: {n}개 ({', '.join(hits)})")


if __name__ == "__main__":
    main()
