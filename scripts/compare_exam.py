# 기출 비교 (개발기획안 8.7): "출제 점수 상위 10개 중 실제 출제 개념 수"를 출력한다.
# 사용: python scripts/compare_exam.py --material 자료.pdf [--transcript 대본.md] --exam tests/기출_개념표.json
#   기출_개념표.json 형식: {"concepts": ["힙의 삽입 연산", "이진 트리의 순회", ...]}  (문제 원문은 넣지 않는다)
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import concepts as concepts_mod  # noqa: E402
from core import score, utterances  # noqa: E402
from core.extract import extract  # noqa: E402
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
    material = extract(path.read_bytes(), path.name)
    cres = concepts_mod.extract_concepts(material)
    meta = concepts_mod.meta_pages(material, cres)
    tr = Path(a.transcript).read_text(encoding="utf-8") if a.transcript else None
    utts = utterances.find_utterances(cres["concepts"], tr)
    rows = score.compute_scores(cres["concepts"], utts, meta)["scores"]
    exam = json.loads(Path(a.exam).read_text(encoding="utf-8"))["concepts"]
    top = rows[:a.top]
    hits = [r["name"] for r in top if any(e in r["name"] or r["name"] in e for e in exam)]
    print(f"상위 {a.top}개 중 실제 출제 개념 수: {len(hits)} / 기출 개념 {len(exam)}개")
    for r in top:
        print(f"{r['rank']:>2}. {r['name']} ({r['pct']}점){' ✓' if r['name'] in hits else ''}")


if __name__ == "__main__":
    main()
