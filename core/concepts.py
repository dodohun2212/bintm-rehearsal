"""F05 개념 추출 (AI 호출 1) + 결과 검사, 메타 페이지 판별(8.3)."""
from __future__ import annotations

import re

import config
from core import prompts
from core.llm import Usage, ask_json
from core.schemas import Concept, parse_pages


class NoConceptsError(Exception):
    code = "E-09"
    user_message = "이 자료에서 개념을 찾지 못했어요. 강의 슬라이드나 교재 한 장인지 확인해 주세요"


META_WORDS = ["목차", "학습 목표", "학습목표", "연습문제", "연습 문제", "요약", "참고문헌"]
_SECTION_LINE = re.compile(r"^\s*\d+\.\d+\s")


def call_concepts(material: dict, usage: Usage | None = None) -> dict:
    """호출 1. 자료 전체를 보낸다(생각 모드 켬)."""
    prompt = prompts.fill("concepts", MATERIAL=prompts.pages_block(material["pages"]))
    return ask_json(prompt, max_tokens=config.CONCEPT_MAX_TOKENS, thinking=True, usage=usage)


def clean_concepts(raw: dict, n_pages: int) -> dict:
    """형식이 틀린 개념만 버린다(v1.8). 남은 개념이 0개면 NoConceptsError."""
    items = raw.get("concepts") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        items = []
    used_ids: set[str] = set()
    used_names: set[str] = set()
    out = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in used_names:
            continue
        data = dict(item)
        data["name"] = name
        cid = item.get("id")
        cid = str(cid).strip() if cid is not None and str(cid).strip() not in ("", "null", "None") else None
        if cid is None or cid in used_ids:
            n = idx + 1
            while f"c{n}" in used_ids:
                n += 1
            cid = f"c{n}"
        data["id"] = cid
        data["pages"] = [p for p in parse_pages(item.get("pages")) if 1 <= p <= n_pages]
        try:
            c = Concept.model_validate(data)
        except Exception:
            continue
        used_ids.add(cid)
        used_names.add(name)
        out.append(c.model_dump())
    if not out:
        raise NoConceptsError("쓸 개념이 없음")

    def _page(v):
        ps = parse_pages(v)
        return ps[0] if ps and 1 <= ps[0] <= n_pages else None

    return {
        "objectives_page": _page(raw.get("objectives_page")),
        "exercise_page": _page(raw.get("exercise_page")),
        "meta_pages": [p for p in parse_pages(raw.get("meta_pages")) if 1 <= p <= n_pages],
        "concepts": out,
    }


def meta_pages(pages: list[dict], result: dict) -> list[int]:
    """메타 페이지 = AI 값 ∪ 규칙 ① ∪ 규칙 ② ∪ {1}."""
    meta = {1}
    meta.update(result.get("meta_pages") or [])
    for key in ("objectives_page", "exercise_page"):
        if result.get(key):
            meta.add(result[key])
    for p in pages:
        text = p["text"] or ""
        if any(w in text[:80] for w in META_WORDS):
            meta.add(p["n"])
            continue
        lines = [ln for ln in text.splitlines() if ln.strip()][:12]
        if sum(1 for ln in lines if _SECTION_LINE.match(ln)) >= 3:
            meta.add(p["n"])
    return sorted(meta)


def extract_concepts(material: dict, usage: Usage | None = None) -> dict:
    raw = call_concepts(material, usage)
    return clean_concepts(raw, material["n_pages"])
