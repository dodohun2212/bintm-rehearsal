"""F07 출제 가능성 점수 (8장). AI를 부르지 않는 순수 함수. 가중치 표는 이 딕셔너리 하나뿐이다."""
from __future__ import annotations

# 8.1 가중치 v0
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
    "question": 0.5,         # 학우 질문, 질문마다
    "deferral": -2.5,        # 발화마다
    "skip": -1.0,            # 발화마다
}
STRENGTH_SCALED = {"emphasis", "exam_hint", "mistake_warning", "exercise_hint"}
LABELS = {
    "emphasis": "강조",
    "exam_hint": "시험 암시",
    "mistake_warning": "실수 경고",
    "exercise_hint": "연습문제 지목",
    "question": "학우 질문",
    "deferral": "다음에 다룸",
    "skip": "가볍게 넘어감",
}


def body_pages(concept: dict, meta: list[int]) -> list[int]:
    m = set(meta)
    return [p for p in concept.get("pages", []) if p not in m]


def _short(q: str, n: int = 28) -> str:
    return q if len(q) <= n else q[:n] + "…"


def compute_scores(concepts: list[dict], utterances: list[dict], meta: list[int]) -> dict:
    """개념마다 raw 점수와 근거를 만들고, 가장 높은 개념 = 100점으로 맞춘다."""
    rows = []
    for c in concepts:
        reasons = []
        if c.get("in_objectives"):
            reasons.append({"kind": "objective", "points": WEIGHTS["objective"], "label": "학습목표"})
        body = body_pages(c, meta)
        n_body = min(len(body), WEIGHTS["page_max"])
        if n_body:
            reasons.append({"kind": "page", "points": WEIGHTS["page"] * n_body, "label": f"본문 {len(body)}쪽"})
        if c.get("has_example"):
            reasons.append({"kind": "example", "points": WEIGHTS["example"], "label": "예제"})
        if c.get("has_exercise"):
            nums = c.get("exercise_numbers") or []
            label = "연습문제 " + ", ".join(str(n) for n in nums) if nums else "연습문제"
            reasons.append({"kind": "exercise", "points": WEIGHTS["exercise"], "label": label})
        for u in utterances:
            if u.get("concept_id") != c["id"]:
                continue
            t = u.get("type")
            if t not in WEIGHTS:
                continue
            s = int(u.get("strength", 2))
            pts = WEIGHTS[t] * (s / 3) if t in STRENGTH_SCALED else WEIGHTS[t]
            reasons.append({
                "kind": t,
                "points": round(pts, 4),
                "label": f"{LABELS[t]}: “{_short(u.get('quote', ''))}”",
                "strength": s,
                "quote": u.get("quote", ""),
            })
        raw = round(sum(r["points"] for r in reasons), 4)
        rows.append({
            "concept_id": c["id"],
            "name": c["name"],
            "raw": max(raw, 0.0),
            "raw_before_clip": raw,
            "body_pages": body,
            "first_page": min(c.get("pages") or [10 ** 6]),
            "reasons": reasons,
        })
    max_raw = max((r["raw"] for r in rows), default=0.0)
    for r in rows:
        r["pct"] = int(round(r["raw"] / max_raw * 100)) if max_raw > 0 else 0
    rows.sort(key=lambda r: (-r["pct"], -len(r["body_pages"]), r["first_page"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"max_raw": max_raw, "scores": rows}


def badges(score_row: dict) -> list[tuple[str, bool]]:
    """근거 배지 (글, 감점 여부). 같은 종류의 발화는 ×n으로 묶는다."""
    out: list[tuple[str, bool]] = []
    counts: dict[str, int] = {}
    for r in score_row.get("reasons", []):
        k = r["kind"]
        if k in ("objective", "page", "example", "exercise"):
            out.append((r["label"], False))
        else:
            counts[k] = counts.get(k, 0) + 1
    for k, n in counts.items():
        label = LABELS.get(k, k) + (f" ×{n}" if n > 1 else "")
        out.append((label, k in ("deferral", "skip")))
    return out
