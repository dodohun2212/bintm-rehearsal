"""F05 개념 추출 (AI 호출 1) + 결과 검사. 형식이 틀린 항목만 버린다 (v1.8)."""
from __future__ import annotations

import re

import config
from core import prompts
from core.llm import Usage, ask_json
from core.schemas import Concept
from core.score import meta_pages

E09 = "이 자료에서 개념을 찾지 못했어요. 강의 슬라이드나 교재 한 장인지 확인해 주세요"


class NoConceptsError(Exception):
    code = "E-09"


def to_pages(value, n_pages: int | None = None) -> list[int]:
    """쪽 번호를 숫자 목록으로: 5, 5.0, "5", "p.5", "3-4", [..] 모두 받는다. 범위 밖은 버린다(E-15)."""
    out: list[int] = []
    items = value if isinstance(value, (list, tuple)) else [value]
    for v in items:
        if v is None or isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            if float(v).is_integer():
                out.append(int(v))
            continue
        s = str(v).strip().lower().replace("p.", "").replace("p", "").replace("쪽", "").strip()
        m = re.fullmatch(r"(\d+)\s*[-~–]\s*(\d+)", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < b - a < 50:
                out.extend(range(a, b + 1))
            continue
        m = re.fullmatch(r"(\d+)(?:\.0+)?", s)
        if m:
            out.append(int(m.group(1)))
    seen = []
    for n in out:
        if (n_pages is None or 1 <= n <= n_pages) and n not in seen:
            seen.append(n)
    return sorted(seen)


def _page_or_none(value, n_pages):
    pages = to_pages(value, n_pages)
    return pages[0] if pages else None


def _bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "y", "예")
    return bool(v)


def clean_concepts(raw: dict, n_pages: int) -> dict:
    """항목마다 따로 검사해 틀린 항목만 버린다. id가 비면 c1, c2…를 붙인다."""
    items = raw.get("concepts") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        items = []
    used_ids: set[str] = set()
    used_names: set[str] = set()
    concepts = []
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or len(name.strip()) < 2:
            continue
        name = name.strip()
        if name in used_names:
            continue
        cid = item.get("id")
        cid = str(cid).strip() if cid not in (None, "", "null") else ""
        if cid and cid.isdigit():
            cid = f"c{cid}"
        if not cid or cid in used_ids:
            k = i
            while f"c{k}" in used_ids:
                k += 1
            cid = f"c{k}"
        try:
            kws = item.get("keywords") or []
            c = Concept(
                id=cid, name=name, summary=str(item.get("summary") or ""),
                pages=to_pages(item.get("pages"), n_pages),
                in_objectives=_bool(item.get("in_objectives")),
                objective_quote=item.get("objective_quote") if isinstance(item.get("objective_quote"), str) else None,
                has_example=_bool(item.get("has_example")),
                has_exercise=_bool(item.get("has_exercise")),
                exercise_numbers=to_pages(item.get("exercise_numbers")),
                keywords=[str(k) for k in kws if isinstance(k, (str, int, float))] if isinstance(kws, list) else [],
            )
        except Exception:
            continue
        used_ids.add(cid)
        used_names.add(name)
        concepts.append(c.model_dump())
    if not concepts:
        raise NoConceptsError(E09)
    return {
        "objectives_page": _page_or_none(raw.get("objectives_page"), n_pages),
        "exercise_page": _page_or_none(raw.get("exercise_page"), n_pages),
        "meta_pages": to_pages(raw.get("meta_pages") or [], n_pages),
        "concepts": concepts,
    }


def extract_concepts(material: dict, usage: Usage | None = None) -> dict:
    """호출 1: 자료 전체를 보내 개념 목록을 받는다. 메타 페이지는 AI 값과 코드 규칙의 합집합."""
    text = prompts.fill("concepts", MATERIAL=prompts.pages_text(material["pages"]))
    raw = ask_json(text, max_tokens=config.CONCEPT_MAX_TOKENS, thinking=True, usage=usage)
    result = clean_concepts(raw, material["n_pages"])
    result["meta_pages_final"] = meta_pages(result, material["pages"])
    return result


def concept_list_for_ai(concepts: list[dict]) -> list[dict]:
    """호출 2에 넣는 개념 목록(id, name, summary, keywords만)."""
    return [{"id": c["id"], "name": c["name"], "summary": c.get("summary", ""),
             "keywords": c.get("keywords", [])} for c in concepts]
