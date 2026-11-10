"""F13 시험 대비 요약 노트: 자세한 정도(코드), 강의 순서(코드), 호출 5."""
from __future__ import annotations

import json

from pydantic import ValidationError

import config
from core import llm, prompts
from core.diagnose import evidence_pages
from core.explain import strip_bad_cites
from core.extract import pages_text
from core.schemas import NoteAI, keep_pages

DETAILS = ("자세히", "보통", "짧게")
LIMITS = {"자세히": (5, 2), "보통": (3, 1)}  # (핵심 개수, 실수 개수)


def detail_level(action: str, pct: int, status: str) -> str:
    """자세히: 지금 당장·출제 점수 50 이상·진단 모름(20점 이상). 보통: 다음·헷갈림. 짧게: 나머지."""
    if action == "지금 당장" or pct >= config.ESSAY_MIN_PCT or (status == "모름" and pct >= config.DIAG_MIN_PCT):
        return "자세히"
    if action == "다음" or status == "헷갈림":
        return "보통"
    return "짧게"


def lecture_order(concepts: list[dict], meta: list[int]) -> list[str]:
    """강의 순서 = 본문(메타 제외)에 처음 나오는 쪽. 본문 쪽이 없으면 맨 뒤."""
    meta_set = set(meta)

    def key(item):
        i, c = item
        body = [p for p in c.get("pages", []) if p not in meta_set]
        return (min(body) if body else 10**6, i)

    return [c["id"] for _, c in sorted(enumerate(concepts), key=key)]


def professor_quotes(utterances: list[dict], concept_id: str, k: int = 3) -> list[dict]:
    """교수님 말: 코드가 강도 높은 것부터 k개(같은 문장은 한 번). AI가 지어내지 않게."""
    seen, out = set(), []
    rows = [u for u in utterances if u.get("concept_id") == concept_id]
    for u in sorted(rows, key=lambda u: -u.get("strength", 0)):
        if u["quote"] in seen:
            continue
        seen.add(u["quote"])
        out.append(u)
        if len(out) >= k:
            break
    return out


def short_note(concept: dict, meta: list[int]) -> dict:
    """짧게: AI를 부르지 않고 개념 추출의 한 줄 요약을 쓴다."""
    return {"concept_id": concept["id"], "detail": "짧게", "from_ai": False,
            "summary": concept.get("summary", ""), "key_points": [], "pitfalls": [],
            "source_pages": evidence_pages(concept, meta)[:2]}


def clean_note(raw: dict, detail: str, pages: list[int]) -> dict:
    try:
        n = NoteAI.model_validate(raw if isinstance(raw, dict) else {})
    except ValidationError as exc:
        raise llm.BadJSONError("요약 노트 형식이 틀림") from exc
    k, p = LIMITS[detail]
    return {"detail": detail, "from_ai": True,
            "summary": strip_bad_cites(n.summary, pages),
            "key_points": [strip_bad_cites(x, pages) for x in n.key_points[:k]],
            "pitfalls": [strip_bad_cites(x, pages) for x in n.pitfalls[:p]],
            "source_pages": keep_pages(n.source_pages, pages) or pages[:2]}


def note_payload(concept: dict, detail: str, prio: dict, grading: dict | None, utterances: list[dict]) -> dict:
    return {
        "name": concept["name"], "detail": detail, "exam_pct": prio["exam_pct"],
        "action": prio["action"], "status": prio["status"],
        "objective": concept.get("objective_quote"),
        "professor": [{"quote": u["quote"], "type": u["type"]} for u in professor_quotes(utterances, concept["id"], 5)],
        "diagnosis": None if not grading else {
            "score": grading.get("score"), "error_type": grading.get("error_type"), "reason": grading.get("reason")},
    }


def make_note(concept: dict, detail: str, prio: dict, grading: dict | None, utterances: list[dict],
              material: dict, meta: list[int], usage: llm.Usage | None = None) -> dict:
    if detail == "짧게":
        return short_note(concept, meta)
    pages = evidence_pages(concept, meta)
    payload = note_payload(concept, detail, prio, grading, utterances)
    prompt = prompts.fill("note", CONCEPT_NAME=concept["name"], DETAIL=detail,
                          CONCEPT_JSON=json.dumps(payload, ensure_ascii=False), PAGES=pages_text(material, pages))
    raw = llm.ask_json(prompt, max_tokens=config.NOTE_MAX_TOKENS, usage=usage)
    out = clean_note(raw, detail, pages)
    out["concept_id"] = concept["id"]
    return out
