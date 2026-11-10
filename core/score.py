"""F07 출제 가능성 점수 (개발기획안 8장). AI를 부르지 않는 순수 함수."""
from __future__ import annotations

import re

# 8.1 가중치 표 (v0). 바꾸면 버전을 올리고 README에 적는다.
WEIGHTS = {
    "objective": 3.0,        # 학습목표에 있음
    "page": 1.0,             # 본문 쪽당
    "page_max": 4,           # 본문 쪽수 상한
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

SCALED_TYPES = ("emphasis", "exam_hint", "mistake_warning", "exercise_hint")
FLAT_TYPES = ("deferral", "skip", "question")
TYPE_LABELS = {
    "emphasis": "강조",
    "exam_hint": "시험 암시",
    "mistake_warning": "실수 경고",
    "exercise_hint": "연습문제 지목",
    "deferral": "다음에 다룸",
    "skip": "가볍게 넘어감",
    "question": "학우 질문",
}

META_TITLES = ("목차", "학습 목표", "학습목표", "연습문제", "연습 문제", "요약", "참고문헌", "차례")
_SECTION_PREFIX = re.compile(r"^[\s\d.·\-–—•▪■□●○◆◇*#]*")
_SECTION_LINE = re.compile(r"^\d+(?:\.\d+)+\s+\S*[가-힣A-Za-z]")


def first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def is_meta_by_rule(text: str) -> bool:
    """규칙 ① 첫 줄 제목, 규칙 ② 앞 12줄 중 절 번호 줄 3개 이상."""
    head = _SECTION_PREFIX.sub("", first_line(text))
    if any(head.startswith(t) for t in META_TITLES):
        return True
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()][:12]
    return sum(1 for l in lines if _SECTION_LINE.match(l)) >= 3


def meta_pages(material_pages: list[dict], ai_result: dict | None = None) -> list[int]:
    """메타 페이지 = AI 값(meta_pages·objectives_page·exercise_page) ∪ 규칙 ① ∪ 규칙 ② ∪ {1}."""
    ai_result = ai_result or {}
    n_max = len(material_pages)
    found = {1}
    found.update(p for p in ai_result.get("meta_pages") or [] if 1 <= p <= n_max)
    for key in ("objectives_page", "exercise_page"):
        p = ai_result.get(key)
        if isinstance(p, int) and 1 <= p <= n_max:
            found.add(p)
    for page in material_pages:
        if is_meta_by_rule(page.get("text", "")):
            found.add(page["n"])
    return sorted(found)


def _short(quote: str, n: int = 24) -> str:
    quote = quote.strip()
    return quote if len(quote) <= n else quote[: n - 1] + "…"


def compute_scores(concepts: list[dict], utterances: list[dict], meta: list[int]) -> dict:
    """개념마다 raw·pct·근거를 만든다. 같은 입력이면 항상 같은 결과."""
    meta_set = set(meta)
    rows = []
    for c in concepts:
        reasons = []
        if c.get("in_objectives"):
            reasons.append({"kind": "objective", "points": WEIGHTS["objective"], "label": "학습목표"})
        body = [p for p in c.get("pages", []) if p not in meta_set]
        n_body = min(len(body), WEIGHTS["page_max"])
        if n_body:
            reasons.append({"kind": "page", "points": WEIGHTS["page"] * n_body, "label": f"본문 {len(body)}쪽"})
        if c.get("has_example"):
            reasons.append({"kind": "example", "points": WEIGHTS["example"], "label": "예제"})
        if c.get("has_exercise"):
            nums = c.get("exercise_numbers") or []
            label = "연습문제" + (" " + ", ".join(str(n) for n in nums) if nums else "")
            reasons.append({"kind": "exercise", "points": WEIGHTS["exercise"], "label": label})
        for u in utterances:
            if u.get("concept_id") != c["id"]:
                continue
            kind = u.get("type")
            if kind in SCALED_TYPES:
                pts = WEIGHTS[kind] * (u.get("strength", 2) / 3)
            elif kind in FLAT_TYPES:
                pts = WEIGHTS[kind]
            else:
                continue  # 모르는 유형은 무시
            reasons.append({
                "kind": kind,
                "points": round(pts, 4),
                "label": f"{TYPE_LABELS[kind]}: “{_short(u.get('quote', ''))}”",
                "strength": u.get("strength"),
            })
        raw = round(sum(r["points"] for r in reasons), 4)
        rows.append({
            "concept_id": c["id"],
            "name": c["name"],
            "raw": max(raw, 0.0),
            "body_pages": body,
            "first_page": min(c.get("pages") or [10**6]),
            "reasons": reasons,
        })
    max_raw = max((r["raw"] for r in rows), default=0.0)
    for r in rows:
        r["pct"] = int(round(r["raw"] / max_raw * 100)) if max_raw > 0 else 0
    rows.sort(key=lambda r: (-r["pct"], -len(r["body_pages"]), r["first_page"]))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return {"max_raw": max_raw, "scores": rows}


def badges(score_row: dict) -> list[tuple[str, bool]]:
    """S02 근거 배지 (글, 감점인지). 강조 등은 개수로 묶는다."""
    out: list[tuple[str, bool]] = []
    counts: dict[str, int] = {}
    for r in score_row["reasons"]:
        if r["kind"] in ("objective", "example"):
            out.append((r["label"], False))
        elif r["kind"] in ("page", "exercise"):
            out.append((r["label"], False))
        else:
            counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    for kind, n in counts.items():
        label = TYPE_LABELS[kind] + (f" ×{n}" if n > 1 else "")
        out.append((label, kind in ("deferral", "skip")))
    return out
