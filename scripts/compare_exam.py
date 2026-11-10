"""기출 비교 (개발기획안 8.7): 출제 가능성 상위 10개 중 실제로 출제된 개념 수를 센다.

    python scripts/compare_exam.py --material 실제자료_비공개/8장.pdf --exam tests/기출_개념표.json [--transcript 대본.txt]

기출_개념표.json 형식: {"concepts": ["힙의 삽입 연산", "이진 트리의 순회"]} (문제 원문은 넣지 않는다)
키는 환경변수 또는 .streamlit/secrets.toml에서 읽는다. 측정한 숫자는 이 명령어와 함께 README에 적는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def matches(name: str, exam: list[str]) -> bool:
    n = name.replace(" ", "")
    return any(e.replace(" ", "") in n or n in e.replace(" ", "") for e in exam)


def main() -> None:
    ap = argparse.ArgumentParser(description="출제 가능성 상위 10개 중 실제 출제 개념 수")
    ap.add_argument("--material", required=True)
    ap.add_argument("--exam", required=True)
    ap.add_argument("--transcript")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    from core.concepts import extract_concepts
    from core.extract import extract, mask
    from core.score import compute_scores
    from core.utterances import find_utterances
    from make_example import load_keys

    load_keys()
    path = Path(args.material)
    material = extract(path.name, path.read_bytes())
    concepts = extract_concepts(material)
    transcript = mask(Path(args.transcript).read_text(encoding="utf-8")) if args.transcript else ""
    utter = find_utterances(transcript, concepts["concepts"]) if transcript else []
    scores = compute_scores(concepts, utter, material["pages"])["scores"]
    exam = json.loads(Path(args.exam).read_text(encoding="utf-8")).get("concepts", [])
    top = scores[:args.top]
    hits = [s["name"] for s in top if matches(s["name"], exam)]
    for s in top:
        print(f"{s['rank']:>2}. {s['name']} {s['pct']}점 {'✔ 출제' if s['name'] in hits else ''}")
    print(f"상위 {args.top}개 중 실제 출제 {len(hits)}개 (기출 개념 {len(exam)}개)")


if __name__ == "__main__":
    main()
