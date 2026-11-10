"""F09 이해도 숫자화와 우선순위 (8.5, 8.6). 외부 호출이 없는 순수 함수."""
from __future__ import annotations

UNDERSTANDING = {"앎": 1.0, "헷갈림": 0.5, "모름": 0.0, "진단 안 함": 0.5}
NOW, NEXT, REVIEW = "지금 당장", "다음", "복습만"


def action_for(priority: int) -> str:
    if priority >= 50:
        return NOW
    if priority >= 20:
        return NEXT
    return REVIEW


def compute_priorities(scores: list[dict], grading: dict) -> list[dict]:
    """priority = round(exam_pct × (1 − 이해도)). 내림차순, 같으면 exam_pct 높은 순."""
    rows = []
    for order, s in enumerate(scores):
        g = grading.get(s["concept_id"]) if grading else None
        status = g["status"] if g else "진단 안 함"
        u = UNDERSTANDING[status]
        p = round(s["pct"] * (1 - u))
        rows.append({"concept_id": s["concept_id"], "name": s["name"], "exam_pct": s["pct"],
                     "status": status, "understanding": u, "priority": p,
                     "action": action_for(p), "_o": order})
    rows.sort(key=lambda r: (-r["priority"], -r["exam_pct"], r["_o"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r.pop("_o")
    return rows


def group(priorities: list[dict]) -> dict[str, list[dict]]:
    out = {NOW: [], NEXT: [], REVIEW: []}
    for p in priorities:
        out[p["action"]].append(p)
    return out


def split_review(review: list[dict], confusion: dict) -> tuple[list[dict], list[dict]]:
    """'복습만' 중 헷갈린 점을 적은 개념은 펼친 쪽, 나머지는 접힌 쪽 (v1.11)."""
    shown = [p for p in review if (confusion or {}).get(p["concept_id"], "").strip()]
    folded = [p for p in review if p not in shown]
    return shown, folded
