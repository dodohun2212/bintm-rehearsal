"""F05 개념 추출 (AI 호출 1) + 결과 검사. 형식이 틀린 개념만 버린다."""
from __future__ import annotations

import json

from pydantic import ValidationError

from core import llm, prompts
from core.extract import pages_text
from core.schemas import Concept, keep_pages, parse_pages


class NoConceptsError(Exception):
    """쓸 수 있는 개념이 0개 (E-09)."""


def clean_concepts(raw: dict, n_pages: int) -> dict:
    """AI 답을 검사한다. 틀린 항목만 버리고, id가 비면 c1, c2…를 붙인다."""
    allowed = range(1, n_pages + 1)
    items = raw.get("concepts") if isinstance(raw, dict) else None
    concepts: list[dict] = []
    used_ids: set[str] = set()
    used_names: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        data = dict(item)
        cid = data.get("id")
        data["id"] = str(cid).strip() if cid not in (None, "", "null") else ""
        try:
            concept = Concept.model_validate({**data, "id": data["id"] or "tmp"})
        except ValidationError:
            continue
        concept.pages = keep_pages(concept.pages, allowed)
        if concept.name in used_names:
            continue
        cid = data["id"]
        if not cid or cid in used_ids:
            k = len(concepts) + 1
            while f"c{k}" in used_ids:
                k += 1
            cid = f"c{k}"
        concept.id = cid
        used_ids.add(cid)
        used_names.add(concept.name)
        concepts.append(concept.model_dump())
    if not concepts:
        raise NoConceptsError("개념 0개")

    def one_page(v):
        pages = keep_pages(parse_pages(v), allowed)
        return pages[0] if pages else None

    return {
        "objectives_page": one_page(raw.get("objectives_page")),
        "exercise_page": one_page(raw.get("exercise_page")),
        "meta_pages": keep_pages(parse_pages(raw.get("meta_pages")), allowed),
        "concepts": concepts,
    }


def extract_concepts(material: dict, usage: llm.Usage | None = None) -> dict:
    prompt = prompts.fill("concepts", MATERIAL=pages_text(material))
    raw = llm.ask_json(prompt, max_tokens=8000, thinking=True, usage=usage)
    return clean_concepts(raw, material["n_pages"])


def concepts_for_prompt(concepts: list[dict]) -> str:
    """호출 2에 넣는 개념 목록(id, name, summary, keywords만)."""
    slim = [{k: c[k] for k in ("id", "name", "summary", "keywords")} for c in concepts]
    return json.dumps(slim, ensure_ascii=False)
