"""F09 이해도 숫자화 + 우선순위 (8.5, 8.6). 순수 함수."""
from __future__ import annotations

UNDERSTANDING = {"앎": 1.0, "헷갈림": 0.5, "모름": 0.0, "진단 안 함": 0.5}
ACTIONS = ("지금 당장", "다음", "복습만")


def action_of(priority: int) -> str:
    if priority >= 50:
        return "지금 당장"
    if priority >= 20:
        return "다음"
    return "복습만"


def priority_of(exam_pct: int, status: str) -> int:
    """round는 파이썬 기본(.5는 가까운 짝수 쪽)."""
    return int(round(exam_pct * (1 - UNDERSTANDING.get(status, 0.5))))


def split_review(rows: list[dict], with_confusion) -> tuple[list[dict], list[dict]]:
    """'복습만' 묶음을 (펼쳐 둘 것, 접을 것)으로. 헷갈린 점을 적은 개념은 펼쳐 둔다(v1.11)."""
    keep = set(with_confusion)
    opened = [r for r in rows if r["concept_id"] in keep]
    folded = [r for r in rows if r["concept_id"] not in keep]
    return opened, folded


def compute_priorities(scores: list[dict], grading: dict) -> list[dict]:
    rows = []
    for s in scores:
        g = grading.get(s["concept_id"])
        status = g["status"] if g else "진단 안 함"
        p = priority_of(s["pct"], status)
        rows.append({
            "concept_id": s["concept_id"],
            "name": s["name"],
            "exam_pct": s["pct"],
            "status": status,
            "understanding": UNDERSTANDING.get(status, 0.5),
            "priority": p,
            "action": action_of(p),
        })
    rows.sort(key=lambda r: (-r["priority"], -r["exam_pct"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
