"""F13 시험 대비 요약 노트: 자세한 정도(코드), 강의 순서(코드), 호출 5."""
from __future__ import annotations

import json

import config
from core import prompts
from core.llm import BadJsonError, Usage, ask_json
from core.priority import NEXT, NOW
from core.schemas import NoteSection

DETAILED, NORMAL, SHORT = "자세히", "보통", "짧게"


def detail_level(action: str, pct: int, status: str) -> str:
    """자세히: 지금 당장·출제 점수 50 이상·진단 모름(20 이상) / 보통: 다음·헷갈림 / 짧게: 나머지."""
    if action == NOW or pct >= config.ESSAY_MIN_PCT or (status == "모름" and pct >= config.DIAG_MIN_PCT):
        return DETAILED
    if action == NEXT or status == "헷갈림":
        return NORMAL
    return SHORT


def lecture_order(concepts: list[dict], meta: list[int]) -> list[str]:
    """개념이 본문(메타 제외)에 처음 나오는 쪽 순서. 본문 쪽이 없으면 맨 뒤."""
    meta_set = set(meta or [])
    keyed = []
    for i, c in enumerate(concepts):
        body = [p for p in c.get("pages", []) if p not in meta_set]
        keyed.append((min(body) if body else 10**6, i, c["id"]))
    return [cid for _, _, cid in sorted(keyed)]


def professor_quotes(cid: str, utterances: list[dict], n: int = 3) -> list[dict]:
    """교수님 말은 AI가 아니라 코드가 호출 2 결과에서 강한 것부터 붙인다."""
    mine = [u for u in utterances or [] if u.get("concept_id") == cid]
    mine.sort(key=lambda u: -int(u.get("strength") or 0))
    out, seen = [], set()
    for u in mine:
        if u["quote"] in seen:
            continue
        seen.add(u["quote"])
        out.append({"quote": u["quote"], "type": u["type"], "strength": u.get("strength")})
        if len(out) >= n:
            break
    return out


def short_note(concept: dict, meta: list[int] | None = None) -> dict:
    """짧게: AI를 부르지 않고 호출 1의 한 줄 요약."""
    body = [p for p in concept.get("pages", []) if p not in set(meta or [])]
    return NoteSection(concept_id=concept["id"], detail=SHORT, summary=concept.get("summary", ""),
                       source_pages=(body or concept.get("pages", []))[:2], from_ai=False).model_dump()


def concept_json(concept: dict, detail: str, info: dict, quotes: list[dict]) -> dict:
    """호출 5의 <concept>: 이름, 자세한 정도, 출제 가능성·묶음·상태, 학습목표, 교수님 말, 진단 결과."""
    g = info.get("grading") or {}
    return {
        "name": concept["name"], "detail": detail,
        "exam_score": info.get("exam_pct"), "priority_group": info.get("action"),
        "status": info.get("status"),
        "objective_quote": concept.get("objective_quote"),
        "professor": [{"quote": q["quote"], "type": q["type"]} for q in quotes],
        "diagnosis": ({"score": g.get("score"), "error_type": g.get("error_type"), "reason": g.get("reason")}
                      if g else None),
    }


def _str_list(v, limit: int) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if isinstance(x, (str, int, float)) and str(x).strip()][:limit]


def make_note(concept: dict, detail: str, info: dict, utterances: list[dict], pages: list[dict],
              usage: Usage | None = None) -> dict:
    """호출 5 (자세히·보통만). 교수님 말은 강한 것부터 5개를 넣는다."""
    from core.concepts import to_pages
    quotes = professor_quotes(concept["id"], utterances, n=5)
    text = prompts.fill("note", CONCEPT_NAME=concept["name"], DETAIL=detail,
                        CONCEPT_JSON=json.dumps(concept_json(concept, detail, info, quotes), ensure_ascii=False),
                        PAGES=prompts.pages_text(pages))
    raw = ask_json(text, max_tokens=config.NOTE_MAX_TOKENS, usage=usage)
    allowed = [p["n"] for p in pages]
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise BadJsonError("요약이 비어 있음")
    src = [n for n in to_pages(raw.get("source_pages")) if n in allowed] or allowed[:2]
    return NoteSection(concept_id=concept["id"], detail=detail, summary=summary.strip(),
                       key_points=_str_list(raw.get("key_points"), 5 if detail == DETAILED else 3),
                       pitfalls=_str_list(raw.get("pitfalls"), 2),
                       source_pages=src, from_ai=True).model_dump()


def note_plan(concepts: list[dict], priorities: list[dict], meta: list[int]) -> list[tuple[str, str]]:
    """강의 순서대로 (개념 id, 자세한 정도)."""
    by_id = {p["concept_id"]: p for p in priorities}
    out = []
    for cid in lecture_order(concepts, meta):
        p = by_id.get(cid)
        if p is None:
            continue
        out.append((cid, detail_level(p["action"], p["exam_pct"], p["status"])))
    return out
