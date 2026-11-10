"""F07 출제 가능성 점수 (8장). AI를 부르지 않는 순수 함수. 가중치 표는 이 파일 맨 위 하나뿐이다."""
from __future__ import annotations

import re

# 8.1 출제 가능성 점수 가중치 (v0)
WEIGHTS = {
    "objective": 3.0,        # 학습목표에 있음
    "page": 1.0,             # 본문 쪽당
    "page_max": 4,           # 본문 쪽수 상한
    "example": 1.5,          # 예제·그림으로 과정 설명
    "exercise": 2.0,         # 연습문제에 포함 (한 번만)
    "emphasis": 1.0,         # 강조 발화 × (strength/3)
    "exam_hint": 1.5,        # 시험 암시 × (strength/3)
    "mistake_warning": 0.7,  # 실수 경고 × (strength/3)
    "exercise_hint": 1.0,    # 연습문제 지목 × (strength/3)
    "question": 0.5,         # 학우 질문, 질문마다 (F12, 선택)
    "deferral": -2.5,        # 다음에 다룸, 발화마다
    "skip": -1.0,            # 가볍게 넘어감, 발화마다
}
WEIGHT_VERSION = "v0"

SCALED = ("emphasis", "exam_hint", "mistake_warning", "exercise_hint")
FIXED = ("question", "deferral", "skip")
NEGATIVE = ("deferral", "skip")

TYPE_LABEL = {
    "emphasis": "강조", "exam_hint": "시험 암시", "mistake_warning": "실수 경고",
    "exercise_hint": "연습문제 지목", "question": "학우 질문",
    "deferral": "다음에 다룸", "skip": "가볍게 넘어감",
}

META_WORDS = ("목차", "학습 목표", "학습목표", "연습문제", "연습 문제", "요약", "참고문헌")
_SECTION_LINE = re.compile(r"^\s*\d+\.\d+")


def is_meta_text(text: str) -> bool:
    """코드 규칙 ①(첫 80자에 메타 단어) 또는 ②(앞 12줄 중 3줄 이상이 절 번호로 시작)."""
    head = (text or "")[:80]
    if any(w in head for w in META_WORDS):
        return True
    lines = [ln for ln in (text or "").splitlines() if ln.strip()][:12]
    return sum(1 for ln in lines if _SECTION_LINE.match(ln)) >= 3


def meta_pages(concepts_result: dict, pages: list[dict] | None = None) -> list[int]:
    """메타 페이지 = AI 값(meta_pages·objectives_page·exercise_page) ∪ 코드 규칙 ①② ∪ {1}."""
    meta = {1}
    for n in concepts_result.get("meta_pages") or []:
        if isinstance(n, int):
            meta.add(n)
    for key in ("objectives_page", "exercise_page"):
        n = concepts_result.get(key)
        if isinstance(n, int):
            meta.add(n)
    for p in pages or []:
        if is_meta_text(p.get("text", "")):
            meta.add(p["n"])
    return sorted(meta)


def _num(text: str) -> str:
    return text.replace("\n", " ").strip()


def compute_scores(concepts_result: dict, utterances: list[dict], pages: list[dict] | None = None) -> dict:
    """개념마다 raw와 근거(reasons)를 만들고, 가장 큰 raw = 100점인 pct로 바꿔 내림차순 정렬."""
    meta = set(concepts_result.get("meta_pages_final") or meta_pages(concepts_result, pages))
    by_concept: dict[str, list[dict]] = {}
    for u in utterances or []:
        cid = u.get("concept_id")
        if cid is None or u.get("type") not in WEIGHTS:
            continue  # 개념 목록 밖 발화, 모르는 유형은 점수에 넣지 않는다
        by_concept.setdefault(cid, []).append(u)

    rows = []
    for order, c in enumerate(concepts_result.get("concepts") or []):
        reasons = []
        if c.get("in_objectives"):
            reasons.append({"kind": "objective", "points": WEIGHTS["objective"], "label": "학습목표"})
        body = sorted(p for p in set(c.get("pages") or []) if p not in meta)
        n_body = min(len(body), WEIGHTS["page_max"])
        if n_body:
            reasons.append({"kind": "page", "points": WEIGHTS["page"] * n_body, "label": f"본문 {len(body)}쪽"})
        if c.get("has_example"):
            reasons.append({"kind": "example", "points": WEIGHTS["example"], "label": "예제"})
        if c.get("has_exercise"):
            nums = ",".join(str(x) for x in c.get("exercise_numbers") or [])
            reasons.append({"kind": "exercise", "points": WEIGHTS["exercise"],
                            "label": f"연습문제 {nums}".strip()})
        for u in by_concept.get(c["id"], []):
            t = u["type"]
            strength = int(u.get("strength") or 1)
            pts = WEIGHTS[t] * (strength / 3) if t in SCALED else WEIGHTS[t]
            reasons.append({"kind": t, "points": round(pts, 4),
                            "label": f"{TYPE_LABEL[t]}: “{_num(u.get('quote', ''))}”",
                            "strength": strength, "quote": u.get("quote", "")})
        raw = round(sum(r["points"] for r in reasons), 4)
        all_pages = sorted(set(c.get("pages") or []))
        rows.append({
            "concept_id": c["id"], "name": c["name"], "raw": raw, "raw_clipped": max(raw, 0.0),
            "body_pages": body, "pages": all_pages, "reasons": reasons,
            "first_page": body[0] if body else (all_pages[0] if all_pages else 10**6),
            "_order": order,
        })

    max_raw = max((r["raw_clipped"] for r in rows), default=0.0)
    for r in rows:
        r["pct"] = int(round(r["raw_clipped"] / max_raw * 100)) if max_raw > 0 else 0
    rows.sort(key=lambda r: (-r["pct"], -len(r["body_pages"]), r["first_page"], r["_order"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r.pop("_order", None)
    return {"max_raw": max_raw, "scores": rows, "meta_pages": sorted(meta)}


def badges(score: dict) -> list[tuple[str, bool]]:
    """S02 근거 배지: (글, 감점 여부). 같은 종류 발화는 ×n으로 묶는다."""
    out: list[tuple[str, bool]] = []
    counts: dict[str, int] = {}
    for r in score.get("reasons", []):
        k = r["kind"]
        if k == "objective":
            out.append(("학습목표", False))
        elif k == "page":
            out.append((r["label"], False))
        elif k == "example":
            out.append(("예제", False))
        elif k == "exercise":
            out.append((r["label"], False))
        else:
            counts[k] = counts.get(k, 0) + 1
    for k, n in counts.items():
        label = TYPE_LABEL.get(k, k) + (f" ×{n}" if n > 1 else "")
        out.append((label, k in NEGATIVE))
    return out
