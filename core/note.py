"""F13 시험 대비 요약 노트: 자세한 정도, 강의 순서, 호출 5."""
from __future__ import annotations

import json

from pydantic import ValidationError

import config
from core import llm, prompts
from core.cites import check_recording_marks, strip_bad_cites
from core.schemas import Note, keep_pages

DETAILS = ("자세히", "보통", "짧게")


def lecture_order(concepts: list[dict], meta_pages) -> list[str]:
    """강의 순서 = 본문(메타 제외)에 처음 나오는 쪽. 본문 쪽이 없으면 맨 뒤."""
    meta = set(meta_pages or [])

    def key(item):
        i, c = item
        body = [p for p in c.get("pages", []) if p not in meta]
        return (0, min(body), i) if body else (1, 0, i)

    return [c["id"] for _, c in sorted(enumerate(concepts), key=key)]


def detail_level(action: str, exam_pct: int, status: str) -> str:
    """자세히: 지금 당장·출제 점수 50 이상·진단 모름(20점 이상) / 보통: 다음·헷갈림 / 짧게: 나머지."""
    if action == "지금 당장" or exam_pct >= config.ESSAY_MIN_PCT or (
            status == "모름" and exam_pct >= config.DIAG_MIN_PCT):
        return "자세히"
    if action == "다음" or status == "헷갈림":
        return "보통"
    return "짧게"


def short_note(concept: dict, evidence: list[int]) -> dict:
    """짧게: AI를 부르지 않고 개념 추출의 한 줄 요약을 쓴다."""
    return {"concept_id": concept["id"], "detail": "짧게", "summary": concept.get("summary", ""),
            "key_points": [], "pitfalls": [], "source_pages": list(evidence[:2]), "from_ai": False}


def concept_json(concept: dict, detail: str, prio: dict | None, g: dict | None, utts: list[dict]) -> str:
    prof = [{"quote": u["quote"], "type": u["type"], "strength": u["strength"]}
            for u in sorted([u for u in utts if u.get("concept_id") == concept["id"]],
                            key=lambda u: -int(u.get("strength", 1)))[:5]]
    d = {"name": concept["name"], "detail": detail, "summary": concept.get("summary", ""),
         "exam_pct": (prio or {}).get("exam_pct"), "action": (prio or {}).get("action"),
         "status": (prio or {}).get("status"), "objective": concept.get("objective_quote"),
         "professor": prof}
    if g:
        d["diagnosis"] = {"score": g.get("score"), "error_type": g.get("error_type"), "reason": g.get("reason")}
    return json.dumps(d, ensure_ascii=False)


def make_note(concept: dict, detail: str, prio: dict | None, g: dict | None, utts: list[dict], pages_text: str,
              allowed, usage: llm.Usage | None = None) -> dict:
    prompt = prompts.fill("note", CONCEPT_NAME=concept["name"], DETAIL=detail,
                          CONCEPT_JSON=concept_json(concept, detail, prio, g, utts), PAGES=pages_text)
    raw = llm.ask_json(prompt, max_tokens=config.NOTE_MAX_TOKENS, usage=usage)
    try:
        n = Note.model_validate(raw)
    except ValidationError as e:
        raise llm.BadJSONError(f"요약 노트 형식이 맞지 않음: {e}") from e
    allowed = set(allowed)
    quotes = [u["quote"] for u in utts if u.get("concept_id") == concept["id"]]

    def fix(s):
        return check_recording_marks(strip_bad_cites(s, allowed), quotes)

    kmax = 5 if detail == "자세히" else 3
    return {"concept_id": concept["id"], "detail": detail, "summary": fix(n.summary),
            "key_points": [fix(k) for k in n.key_points][:kmax], "pitfalls": [fix(p) for p in n.pitfalls][:2],
            "source_pages": keep_pages(n.source_pages, allowed) or sorted(allowed)[:2], "from_ai": True}
