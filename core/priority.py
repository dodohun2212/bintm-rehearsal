"""F09 이해도 숫자화와 우선순위 (8.5, 8.6). 순수 함수."""
from __future__ import annotations

import config

UNDERSTANDING = {"앎": 1.0, "헷갈림": 0.5, "모름": 0.0, "진단 안 함": 0.5}
ACTIONS = ("지금 당장", "다음", "복습만")


def understanding_of(status: str) -> float:
    return UNDERSTANDING.get(status, 0.5)


def action_of(priority: int) -> str:
    if priority >= 50:
        return "지금 당장"
    if priority >= 20:
        return "다음"
    return "복습만"


def compute_priorities(scores: list[dict], grading: dict) -> list[dict]:
    """priority = round(exam_pct × (1 − 이해도)). 내림차순, 같으면 출제 점수 높은 순."""
    rows = []
    for s in scores:
        g = grading.get(s["concept_id"])
        status = g["status"] if g else "진단 안 함"
        u = understanding_of(status)
        p = round(s["pct"] * (1 - u))
        rows.append({"concept_id": s["concept_id"], "name": s["name"], "exam_pct": s["pct"],
                     "status": status, "understanding": u, "priority": p, "action": action_of(p),
                     "rank_exam": s.get("rank", 0)})
    rows.sort(key=lambda r: (-r["priority"], -r["exam_pct"], r["rank_exam"]))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def group_by_action(prios: list[dict]) -> dict[str, list[dict]]:
    groups = {a: [] for a in ACTIONS}
    for p in prios:
        groups[p["action"]].append(p)
    return groups


def split_review(review: list[dict], confusion: dict) -> tuple[list[dict], list[dict]]:
    """'복습만' 중 헷갈린 점을 적은 개념은 펼쳐 두고, 나머지는 접는다."""
    opened = [p for p in review if (confusion.get(p["concept_id"]) or "").strip()]
    folded = [p for p in review if not (confusion.get(p["concept_id"]) or "").strip()]
    return opened, folded


def auto_explain_ids(prios: list[dict], confusion: dict) -> list[str]:
    """자동으로 보완 설명을 만들 개념: '지금 당장' 전부 + 상위 3개 + 헷갈린 점을 적은 개념."""
    ids: list[str] = []
    for i, p in enumerate(prios):
        if p["action"] == "지금 당장" or i < config.AUTO_EXPLAIN_TOP or (confusion.get(p["concept_id"]) or "").strip():
            ids.append(p["concept_id"])
    return ids
