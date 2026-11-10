"""F05 개념 추출 (AI 호출 1) + 결과 검사."""
from __future__ import annotations

from pydantic import ValidationError

from core import llm, prompts
from core.extract import material_text
from core.schemas import Concept, parse_pages
from core.score import detect_meta_pages

CONCEPT_MAX_TOKENS = 8000


class NoConceptError(Exception):
    code = "E-09"


def clean_concepts(raw: dict, material: dict) -> dict:
    """형식이 틀린 개념만 버린다. id가 없으면 c1, c2…. 쪽은 실제 범위 안만."""
    n_pages = material["n_pages"]
    items = raw.get("concepts") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        items = []
    out: list[dict] = []
    used_ids: set[str] = set()
    used_names: set[str] = set()
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        item = dict(item)
        if item.get("id") in (None, "", "null"):
            item["id"] = f"c{i}"
        item["id"] = str(item["id"])
        try:
            c = Concept.model_validate(item)
        except ValidationError:
            continue
        c.pages = [p for p in c.pages if 1 <= p <= n_pages]
        if c.id in used_ids:
            c.id = f"c{i}x"
        if c.name in used_names:
            continue
        used_ids.add(c.id)
        used_names.add(c.name)
        out.append(c.model_dump())
    if not out:
        raise NoConceptError("개념 0개")

    def one_page(v):
        p = parse_pages(v)
        return p[0] if p and 1 <= p[0] <= n_pages else None

    ai_meta = [p for p in parse_pages(raw.get("meta_pages")) if 1 <= p <= n_pages]
    obj = one_page(raw.get("objectives_page"))
    exe = one_page(raw.get("exercise_page"))
    meta = detect_meta_pages(material["pages"], ai_meta, obj, exe)
    return {"concepts": out, "meta_pages": meta, "objectives_page": obj, "exercise_page": exe}


def extract_concepts(material: dict, usage: llm.Usage | None = None) -> dict:
    prompt = prompts.fill("concepts", MATERIAL=material_text(material))
    raw = llm.ask_json(prompt, max_tokens=CONCEPT_MAX_TOKENS, thinking=True, usage=usage)
    return clean_concepts(raw, material)
