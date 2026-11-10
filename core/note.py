# F13 시험 대비 요약 노트: 자세한 정도(코드), 강의 순서(코드), 호출 5
import json

import config
from core import prompts
from core.diagnose import evidence_pages
from core.extract import pages_text
from core.llm import Usage, ask_json
from core.schemas import NoteSection

DETAILS = ["자세히", "보통", "짧게"]


def detail_level(action: str, exam_pct: int, status: str) -> str:
    if action == "지금 당장" or exam_pct >= config.ESSAY_MIN_PCT or (
            status == "모름" and exam_pct >= config.DIAG_MIN_PCT):
        return "자세히"
    if action == "다음" or status == "헷갈림":
        return "보통"
    return "짧게"


def lecture_order(concepts: list[dict], meta: list[int]) -> list[str]:
    """개념이 본문(메타 제외)에 처음 나오는 쪽 순서. 본문 쪽이 없으면 맨 뒤."""
    m = set(meta)

    def key(item):
        i, c = item
        body = [p for p in c.get("pages", []) if p not in m]
        return (min(body) if body else 10 ** 6, i)

    return [c["id"] for _, c in sorted(enumerate(concepts), key=key)]


def professor_quotes(utterances: list[dict], concept_id: str, k: int = 3) -> list[dict]:
    """코드가 강한 것부터 고른다(AI가 지어내지 않게)."""
    mine = [u for u in utterances if u.get("concept_id") == concept_id]
    mine.sort(key=lambda u: -int(u.get("strength", 1)))
    return mine[:k]


def build_prompt(concept: dict, detail: str, info: dict, pages_txt: str) -> str:
    return prompts.fill("05", CONCEPT_NAME=concept["name"], DETAIL=detail,
                        CONCEPT_JSON=json.dumps(info, ensure_ascii=False), PAGES=pages_txt)


def concept_info(concept: dict, detail: str, pr: dict, utterances: list[dict], g: dict | None) -> dict:
    return {
        "name": concept["name"], "detail": detail,
        "exam_score": pr["exam_pct"], "priority_group": pr["action"], "status": pr["status"],
        "objective": concept.get("objective_quote"),
        "professor": [{"quote": u["quote"], "type": u["type"]} for u in professor_quotes(utterances, concept["id"], 5)],
        "diagnosis": ({"score": g.get("score"), "error_type": g.get("error_type"), "reason": g.get("reason")}
                      if g else None),
    }


def parse_note(raw: dict, concept_id: str, detail: str, page_nums: list[int]) -> dict:
    from core.concepts import parse_pages
    raw = raw if isinstance(raw, dict) else {}
    kp_max = 5 if detail == "자세히" else 3
    kps = [str(x).strip() for x in (raw.get("key_points") or []) if str(x).strip()][:kp_max]
    pits = [str(x).strip() for x in (raw.get("pitfalls") or []) if str(x).strip()][:2]
    src = [p for p in parse_pages(raw.get("source_pages")) if p in set(page_nums)] or page_nums[:2]
    summary = str(raw.get("summary") or "").strip()
    if not summary:
        raise ValueError("요약이 비어 있음")
    return NoteSection(concept_id=concept_id, detail=detail, summary=summary, key_points=kps,
                       pitfalls=pits, source_pages=src, from_ai=True).model_dump()


def make_note(job: dict, material: dict, meta: list[int], usage: Usage | None = None) -> dict:
    """job: {concept, detail, pr, g, utterances}"""
    c = job["concept"]
    page_nums = evidence_pages(c, meta)
    info = concept_info(c, job["detail"], job["pr"], job.get("utterances", []), job.get("g"))
    raw = ask_json(build_prompt(c, job["detail"], info, pages_text(material, page_nums)),
                   max_tokens=config.NOTE_MAX_TOKENS, usage=usage)
    return parse_note(raw, c["id"], job["detail"], page_nums)


def short_note(concept: dict, meta: list[int]) -> dict:
    """'짧게'는 AI를 부르지 않고 개념 추출의 한 줄 요약을 쓴다."""
    pages = evidence_pages(concept, meta)[:2]
    return NoteSection(concept_id=concept["id"], detail="짧게", summary=concept.get("summary", ""),
                       source_pages=pages, from_ai=False).model_dump()
