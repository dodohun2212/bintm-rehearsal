"""F13 시험 대비 요약 노트: 자세한 정도(코드), 강의 순서(코드), 호출 5."""
from __future__ import annotations

import json

import config
from core import prompts
from core.llm import Usage, ask_json
from core.schemas import parse_pages

DETAILS = ("자세히", "보통", "짧게")


def detail_level(action: str, exam_pct: int, status: str) -> str:
    if action == "지금 당장" or exam_pct >= config.ESSAY_MIN_PCT or (status == "모름" and exam_pct >= config.DIAG_MIN_PCT):
        return "자세히"
    if action == "다음" or status == "헷갈림":
        return "보통"
    return "짧게"


def lecture_order(concepts: list[dict], meta: list[int]) -> list[str]:
    """개념이 본문(메타 제외)에 처음 나오는 쪽 순서. 본문 쪽이 없으면 맨 뒤."""
    m = set(meta)
    big = 10 ** 6

    def key(item):
        i, c = item
        body = [p for p in c.get("pages", []) if p not in m]
        return (min(body) if body else big, i)

    return [c["id"] for _, c in sorted(enumerate(concepts), key=key)]


def professor_quotes(cid: str, utterances: list[dict], n: int = 3) -> list[dict]:
    """교수님 말은 AI가 아니라 코드가 호출 2 결과에서 강한 것부터 붙인다."""
    seen, out = set(), []
    for u in sorted((u for u in utterances if u.get("concept_id") == cid), key=lambda u: -int(u.get("strength", 1))):
        if u["quote"] in seen:
            continue
        seen.add(u["quote"])
        out.append({"quote": u["quote"], "type": u["type"], "strength": u.get("strength", 1)})
        if len(out) >= n:
            break
    return out


def note_payload(concept: dict, detail: str, prio: dict, grading: dict | None, utterances: list[dict]) -> dict:
    d = {
        "name": concept["name"],
        "detail": detail,
        "exam_score": prio.get("exam_pct"),
        "study_group": prio.get("action"),
        "status": prio.get("status"),
        "objective": concept.get("objective_quote"),
        "professor": [{"quote": u["quote"], "type": u["type"]} for u in professor_quotes(concept["id"], utterances, 5)],
    }
    if grading:
        d["diagnosis"] = {"score": f"{grading['score']}/10", "error_type": grading.get("error_type"),
                          "reason": grading.get("reason", "")}
    return d


def note_prompt(concept, detail, prio, grading, utterances, pages) -> str:
    return prompts.fill(
        "note",
        CONCEPT_NAME=concept["name"],
        DETAIL=detail,
        CONCEPT_JSON=json.dumps(note_payload(concept, detail, prio, grading, utterances), ensure_ascii=False, indent=1),
        PAGES=prompts.pages_block(pages),
    )


def short_note(concept: dict) -> dict:
    """짧게: AI를 부르지 않고 개념 추출의 한 줄 요약을 쓴다."""
    return {"concept_id": concept["id"], "detail": "짧게", "summary": concept.get("summary", ""),
            "key_points": [], "pitfalls": [], "source_pages": list(concept.get("pages", []))[:2], "from_ai": False}


def clean_note(raw: dict, cid: str, detail: str, page_nums) -> dict:
    allowed = set(page_nums)
    src = [p for p in parse_pages(raw.get("source_pages")) if p in allowed] or list(page_nums)[:2]

    def strs(v, n):
        return [str(x).strip() for x in v if x is not None and str(x).strip()][:n] if isinstance(v, list) else []

    return {
        "concept_id": cid,
        "detail": detail,
        "summary": str(raw.get("summary") or "").strip(),
        "key_points": strs(raw.get("key_points"), 5 if detail == "자세히" else 3),
        "pitfalls": strs(raw.get("pitfalls"), 2),
        "source_pages": src,
        "from_ai": True,
    }


def make_note(concept: dict, detail: str, prio: dict, grading: dict | None, utterances: list[dict],
              pages: list[dict], usage: Usage | None = None) -> dict:
    if detail == "짧게":
        return short_note(concept)
    raw = ask_json(note_prompt(concept, detail, prio, grading, utterances, pages),
                   max_tokens=config.NOTE_MAX_TOKENS, usage=usage)
    return clean_note(raw, concept["id"], detail, [p["n"] for p in pages])
