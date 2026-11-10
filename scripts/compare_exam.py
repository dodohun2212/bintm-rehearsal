"""기출 비교 (개발기획안 8.7): 상위 10개 개념 중 실제 출제된 개념 수를 센다.

사용: python scripts/compare_exam.py --material 자료.pdf [--transcript 대본.txt] --exam tests/기출_개념표.json
기출_개념표.json 형식: {"concepts": ["힙의 삭제 연산", ...]}  (문제 원문은 넣지 않는다)
실제 AI를 부른다(키 필요). 가중치를 바꾼 뒤 같은 명령을 다시 돌려 숫자를 비교한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.concepts import extract_concepts, meta_pages  # noqa: E402
from core.extract import extract  # noqa: E402
from core.score import compute_scores  # noqa: E402
from core.utterances import find_utterances  # noqa: E402
from scripts.make_example import load_key  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--material", required=True)
    ap.add_argument("--transcript")
    ap.add_argument("--exam", required=True)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    load_key()
    path = Path(a.material)
    material = extract(path.name, path.read_bytes())
    cres = extract_concepts(material)
    tr = Path(a.transcript).read_text(encoding="utf-8") if a.transcript else None
    utts = find_utterances(tr, cres["concepts"])
    scores = compute_scores(cres["concepts"], utts, meta_pages(material["pages"], cres))["scores"]
    exam = json.loads(Path(a.exam).read_text(encoding="utf-8"))["concepts"]
    top = scores[: a.top]
    hits = [r["name"] for r in top if any(e in r["name"] or r["name"] in e for e in exam)]
    print(f"상위 {a.top}개 중 실제 출제 {len(hits)}개 (기출 개념 {len(exam)}개)")
    for r in top:
        print(f"{r['rank']:>2}. {r['name']} {r['pct']}점 {'✔' if r['name'] in hits else ''}")


if __name__ == "__main__":
    main()
