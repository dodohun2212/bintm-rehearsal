"""F09 이해도 숫자화와 우선순위 (개발기획안 8.5, 8.6). 순수 함수."""
from __future__ import annotations

UNDERSTANDING = {"앎": 1.0, "헷갈림": 0.5, "모름": 0.0, "진단 안 함": 0.5}
NOT_DIAGNOSED = "진단 안 함"


def action_of(priority: int) -> str:
    if priority >= 50:
        return "지금 당장"
    if priority >= 20:
        return "다음"
    return "복습만"


def priority_of(exam_pct: int, status: str) -> int:
    # round는 파이썬 기본 동작(.5는 가까운 짝수 쪽: 48.5→48)
    return round(exam_pct * (1 - UNDERSTANDING.get(status, 0.5)))


def compute_priorities(score_rows: list[dict], grading: dict | None) -> list[dict]:
    """채점한 개념은 상태대로, 나머지(채점 실패 포함)는 '진단 안 함'."""
    grading = grading or {}
    out = []
    for r in score_rows:
        g = grading.get(r["concept_id"])
        status = g["status"] if g else NOT_DIAGNOSED
        p = priority_of(r["pct"], status)
        out.append({"concept_id": r["concept_id"], "name": r["name"], "exam_pct": r["pct"], "status": status,
                    "understanding": UNDERSTANDING.get(status, 0.5), "priority": p, "action": action_of(p)})
    out.sort(key=lambda x: (-x["priority"], -x["exam_pct"]))
    for i, x in enumerate(out, 1):
        x["rank"] = i
    return out


def auto_explain_ids(priorities: list[dict], confusion: dict | None, top: int) -> list[str]:
    """자동 보완 설명 대상: '지금 당장' 전부 + 상위 top개 + 헷갈린 점을 적은 개념 (순위 순서)."""
    confusion = confusion or {}
    ids = []
    for i, p in enumerate(priorities):
        cid = p["concept_id"]
        if p["action"] == "지금 당장" or i < top or (confusion.get(cid) or "").strip():
            ids.append(cid)
    return ids
