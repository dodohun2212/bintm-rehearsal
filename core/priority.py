# F09 이해도 숫자화와 우선순위 (8.5, 8.6). 순수 함수.
UNDERSTANDING = {"앎": 1.0, "헷갈림": 0.5, "모름": 0.0, "진단 안 함": 0.5}


def action_of(priority: int) -> str:
    if priority >= 50:
        return "지금 당장"
    if priority >= 20:
        return "다음"
    return "복습만"


def priority_of(exam_pct: int, status: str) -> int:
    return round(exam_pct * (1 - UNDERSTANDING.get(status, 0.5)))


def compute_priorities(scores: list[dict], grading: dict) -> list[dict]:
    """채점이 없는 개념은 '진단 안 함'. 우선순위 내림차순, 같으면 출제 점수 높은 순."""
    rows = []
    for s in scores:
        g = grading.get(s["concept_id"])
        status = g["status"] if g else "진단 안 함"
        p = priority_of(s["pct"], status)
        rows.append({"concept_id": s["concept_id"], "name": s["name"], "exam_pct": s["pct"],
                     "status": status, "understanding": UNDERSTANDING.get(status, 0.5),
                     "priority": p, "action": action_of(p)})
    rows.sort(key=lambda r: (-r["priority"], -r["exam_pct"]))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows
