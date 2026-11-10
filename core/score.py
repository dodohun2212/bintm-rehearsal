# F07 출제 가능성 점수 (8장). AI를 부르지 않는다. 가중치 표는 이 딕셔너리 하나뿐이다.
WEIGHTS = {
    "objective": 3.0,        # 학습목표에 있음
    "page": 1.0,             # 본문 쪽당
    "page_max": 4,           # 본문 쪽 최대 개수
    "example": 1.5,          # 예제·그림으로 과정 설명
    "exercise": 2.0,         # 연습문제에 포함 (한 번만)
    "emphasis": 1.0,         # × strength/3, 발화마다
    "exam_hint": 1.5,        # × strength/3, 발화마다
    "mistake_warning": 0.7,  # × strength/3, 발화마다
    "exercise_hint": 1.0,    # × strength/3, 발화마다
    "question": 0.5,         # 학우 질문, 질문마다
    "deferral": -2.5,        # 발화마다
    "skip": -1.0,            # 발화마다
}
WEIGHTS_VERSION = "v0"

TYPE_LABELS = {
    "emphasis": "강조", "exam_hint": "시험 암시", "mistake_warning": "실수 경고",
    "exercise_hint": "연습문제 지목", "question": "학우 질문", "deferral": "다음에 다룸", "skip": "가볍게 넘어감",
}
SCALED = {"emphasis", "exam_hint", "mistake_warning", "exercise_hint"}


def body_pages(pages: list[int], meta: list[int]) -> list[int]:
    m = set(meta)
    return [p for p in pages if p not in m]


def utterance_points(u: dict) -> float:
    t = u.get("type")
    if t not in WEIGHTS or t in ("page", "page_max"):
        return 0.0
    w = WEIGHTS[t]
    if t in SCALED:
        s = min(3, max(1, int(u.get("strength", 2))))
        return w * s / 3
    return w


def compute_scores(concepts: list[dict], utterances: list[dict], meta: list[int]) -> dict:
    rows = []
    for c in concepts:
        reasons = []
        if c.get("in_objectives"):
            reasons.append({"kind": "objective", "points": WEIGHTS["objective"], "label": "학습목표"})
        body = body_pages(c.get("pages", []), meta)
        if body:
            n = min(len(body), WEIGHTS["page_max"])
            reasons.append({"kind": "page", "points": WEIGHTS["page"] * n, "label": f"본문 {len(body)}쪽"})
        if c.get("has_example"):
            reasons.append({"kind": "example", "points": WEIGHTS["example"], "label": "예제"})
        if c.get("has_exercise"):
            nums = ", ".join(str(x) for x in c.get("exercise_numbers", []))
            reasons.append({"kind": "exercise", "points": WEIGHTS["exercise"],
                            "label": f"연습문제 {nums}".strip()})
        for u in utterances:
            if u.get("concept_id") != c["id"] or u.get("type") not in TYPE_LABELS:
                continue
            pts = utterance_points(u)
            reasons.append({"kind": u["type"], "points": round(pts, 4),
                            "label": f"{TYPE_LABELS[u['type']]}: “{u.get('quote', '')}”",
                            "strength": u.get("strength")})
        raw = round(sum(r["points"] for r in reasons), 4)
        rows.append({"concept_id": c["id"], "name": c["name"], "raw": max(0.0, raw), "raw_before": raw,
                     "pct": 0, "body_pages": body, "pages": c.get("pages", []), "reasons": reasons})
    max_raw = max((r["raw"] for r in rows), default=0.0)
    for r in rows:
        r["pct"] = int(round(r["raw"] / max_raw * 100)) if max_raw > 0 else 0
    rows.sort(key=lambda r: (-r["pct"], -len(r["body_pages"]), min(r["pages"]) if r["pages"] else 9999))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return {"max_raw": max_raw, "scores": rows}
