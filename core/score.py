"""F07 출제 가능성 점수 (개발기획안 8장). AI를 부르지 않는 순수 함수."""
from __future__ import annotations

import re

# 8.1 가중치 표 (v0). 이 표 하나만 고친다.
WEIGHTS = {
    "objective": 3.0,        # 학습목표에 있음
    "page": 1.0,             # 본문 쪽당
    "page_max": 4,           # 본문 쪽은 최대 4쪽까지
    "example": 1.5,          # 예제·그림으로 과정 설명
    "exercise": 2.0,         # 연습문제에 포함 (한 번만)
    "emphasis": 1.0,         # × strength/3, 발화마다
    "exam_hint": 1.5,        # × strength/3
    "mistake_warning": 0.7,  # × strength/3
    "exercise_hint": 1.0,    # × strength/3
    "question": 0.5,         # 학우 질문 (F12, 선택)
    "deferral": -2.5,        # 발화마다 (강도와 무관)
    "skip": -1.0,            # 발화마다 (강도와 무관)
}
WEIGHTS_VERSION = "v0"

SCALED_TYPES = ("emphasis", "exam_hint", "mistake_warning", "exercise_hint")
TYPE_LABELS = {
    "emphasis": "강조", "exam_hint": "시험 암시", "mistake_warning": "실수 경고",
    "exercise_hint": "연습문제 지목", "deferral": "다음에 다룸", "skip": "가볍게 넘어감", "question": "학우 질문",
}

META_WORDS = ("목차", "학습 목표", "학습목표", "연습문제", "연습 문제", "요약", "참고문헌", "차례")
_LEAD = re.compile(r"^[\s\d.\-·•■□▶►\[\]()]*")
_TOC_LINE = re.compile(r"^\s*\d+(?:\.\d+)+\.?\s+(?=\S)(?=.*[가-힣A-Za-z])")


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def is_meta_by_rule(text: str) -> bool:
    """규칙 ①: 첫 줄이 '목차·학습 목표·연습문제·요약…'으로 시작. 규칙 ②: 앞 12줄 중 3줄 이상이 '8.1 트리' 꼴."""
    first = _LEAD.sub("", _first_line(text))
    if any(first.startswith(w) for w in META_WORDS):
        return True
    lines = [ln for ln in (text or "").splitlines() if ln.strip()][:12]
    return sum(1 for ln in lines if _TOC_LINE.match(ln)) >= 3


def detect_meta_pages(pages: list[dict], ai_meta=None, objectives_page=None, exercise_page=None) -> list[int]:
    """메타 페이지 = AI 결과 ∪ 규칙 ① ∪ 규칙 ② ∪ {1}."""
    n_pages = len(pages)
    meta = {1}
    for p in list(ai_meta or []) + [objectives_page, exercise_page]:
        if isinstance(p, int) and 1 <= p <= n_pages:
            meta.add(p)
    for p in pages:
        if is_meta_by_rule(p.get("text", "")):
            meta.add(p["n"])
    return sorted(meta)


def _short(quote: str, n: int = 28) -> str:
    q = (quote or "").strip()
    return q if len(q) <= n else q[: n - 1] + "…"


def compute_scores(concepts: list[dict], utterances: list[dict], meta_pages) -> dict:
    """개념마다 raw 점수와 근거, 0~100 pct. 정렬: pct↓, 본문 쪽수↓, 첫 등장 쪽↑."""
    meta = set(meta_pages or [])
    rows = []
    for c in concepts:
        reasons = []
        if c.get("in_objectives"):
            reasons.append({"kind": "objective", "points": WEIGHTS["objective"], "label": "학습목표"})
        body = [p for p in c.get("pages", []) if p not in meta]
        n_body = min(len(body), WEIGHTS["page_max"])
        if n_body:
            reasons.append({"kind": "page", "points": WEIGHTS["page"] * n_body, "label": f"본문 {len(body)}쪽"})
        if c.get("has_example"):
            reasons.append({"kind": "example", "points": WEIGHTS["example"], "label": "예제"})
        if c.get("has_exercise"):
            nums = c.get("exercise_numbers") or []
            label = "연습문제" + (" " + "·".join(str(n) for n in nums) if nums else "")
            reasons.append({"kind": "exercise", "points": WEIGHTS["exercise"], "label": label})
        for u in utterances:
            if u.get("concept_id") != c["id"]:
                continue
            t = u.get("type")
            if t not in WEIGHTS:
                continue  # 모르는 유형은 무시
            s = max(1, min(3, int(u.get("strength", 1) or 1)))
            pts = WEIGHTS[t] * (s / 3) if t in SCALED_TYPES else WEIGHTS[t]
            reasons.append({"kind": t, "points": round(pts, 4),
                            "label": f"{TYPE_LABELS.get(t, t)}: “{_short(u.get('quote', ''))}”",
                            "strength": s, "quote": u.get("quote", "")})
        raw = round(sum(r["points"] for r in reasons), 4)
        first_page = min(body) if body else (min(c.get("pages") or [9999]))
        rows.append({"concept_id": c["id"], "name": c["name"], "raw": max(0.0, raw), "raw_signed": raw,
                     "body_pages": body, "first_page": first_page, "reasons": reasons})
    max_raw = max((r["raw"] for r in rows), default=0.0)
    for r in rows:
        r["pct"] = int(round(r["raw"] / max_raw * 100)) if max_raw > 0 else 0
    rows.sort(key=lambda r: (-r["pct"], -len(r["body_pages"]), r["first_page"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"max_raw": max_raw, "scores": rows, "weights_version": WEIGHTS_VERSION}


def score_map(scores: dict | list) -> dict:
    rows = scores["scores"] if isinstance(scores, dict) else scores
    return {r["concept_id"]: r for r in rows}


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys
    from pathlib import Path

    # 저장된 결과로 점수 보기: python -m core.score tests/fixtures/01_개념추출_결과.json tests/fixtures/02_강조발화_결과.json
    a = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    b = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")) if len(sys.argv) > 2 else {"utterances": []}
    meta = a.get("meta_pages") or [1, a.get("objectives_page"), a.get("exercise_page")]
    res = compute_scores(a["concepts"], b["utterances"], [m for m in meta if m])
    for r in res["scores"]:
        print(r["rank"], r["name"], r["raw"], r["pct"])
