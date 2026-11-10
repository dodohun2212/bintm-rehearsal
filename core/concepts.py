# F05 개념 추출 (AI 호출 1) + 검사, 8.3 메타 페이지
import re

from core import prompts
from core.extract import pages_text
from core.llm import Usage, ask_json
from core.schemas import Concept


class NoConceptsError(Exception):
    code = "E-09"


def parse_pages(value, n_pages: int | None = None) -> list[int]:
    """쪽 번호 목록을 숫자로 읽는다. 5.0, "5", "p.5", "3-4"를 받아들이고 범위 밖은 버린다(E-15)."""
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out = []
    for v in items:
        nums = []
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            nums = [int(v)]
        elif isinstance(v, str):
            m = re.search(r"(\d+)\s*[-~]\s*(\d+)", v)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if 0 < b - a < 50:
                    nums = list(range(a, b + 1))
                else:
                    nums = [a]
            else:
                m = re.search(r"\d+", v)
                nums = [int(m.group(0))] if m else []
        for n in nums:
            if n >= 1 and (n_pages is None or n <= n_pages) and n not in out:
                out.append(n)
    return out


def _page_or_none(v, n_pages):
    p = parse_pages(v, n_pages)
    return p[0] if p else None


def parse_concepts(raw: dict, n_pages: int) -> dict:
    """형식이 틀린 개념만 버리고 나머지를 쓴다. 남은 개념이 0개면 NoConceptsError."""
    items = raw.get("concepts") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        items = []
    concepts, used_ids, used_names = [], set(), set()
    # AI가 준 id는 먼저 모아 두고, 빈 id에는 겹치지 않는 c1, c2…를 붙인다
    given = {str(i.get("id")).strip() for i in items if isinstance(i, dict) and i.get("id") is not None}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if len(name) < 2 or name in used_names:
            continue
        cid = item.get("id")
        cid = str(cid).strip() if cid is not None and str(cid).strip() else ""
        if not cid or cid in used_ids:
            k = 1
            while f"c{k}" in used_ids or f"c{k}" in given:
                k += 1
            cid = f"c{k}"
        kws = item.get("keywords")
        try:
            c = Concept(
                id=cid, name=name,
                summary=str(item.get("summary") or ""),
                pages=parse_pages(item.get("pages"), n_pages),
                in_objectives=bool(item.get("in_objectives")),
                objective_quote=(str(item["objective_quote"]) if item.get("objective_quote") else None),
                has_example=bool(item.get("has_example")),
                has_exercise=bool(item.get("has_exercise")),
                exercise_numbers=parse_pages(item.get("exercise_numbers")),
                keywords=[str(k) for k in kws] if isinstance(kws, list) else [],
            )
        except Exception:
            continue
        concepts.append(c.model_dump())
        used_ids.add(cid)
        used_names.add(name)
    if not concepts:
        raise NoConceptsError("쓸 수 있는 개념이 없음")
    return {
        "objectives_page": _page_or_none(raw.get("objectives_page"), n_pages),
        "exercise_page": _page_or_none(raw.get("exercise_page"), n_pages),
        "meta_pages": parse_pages(raw.get("meta_pages"), n_pages),
        "concepts": concepts,
    }


def build_prompt(material: dict) -> str:
    return prompts.fill("01", MATERIAL=pages_text(material))


def extract_concepts(material: dict, usage: Usage | None = None) -> dict:
    raw = ask_json(build_prompt(material), max_tokens=8000, thinking=True, usage=usage)
    return parse_concepts(raw, material["n_pages"])


# ---- 8.3 메타 페이지 ----
META_WORDS = ["목차", "학습 목표", "학습목표", "연습문제", "연습 문제", "요약", "참고문헌"]
_SECTION_LINE = re.compile(r"^\s*\d+\.\d+")


def code_meta_pages(material: dict) -> set[int]:
    out = {1}
    for p in material["pages"]:
        text = p["text"]
        head = text[:80]
        if any(w in head for w in META_WORDS):
            out.add(p["n"])
            continue
        lines = [ln for ln in text.splitlines() if ln.strip()][:12]
        if sum(1 for ln in lines if _SECTION_LINE.match(ln)) >= 3:
            out.add(p["n"])
    return out


def meta_pages(material: dict, cres: dict) -> list[int]:
    """AI 값(meta_pages, objectives_page, exercise_page)과 코드 규칙 ①②의 합집합. 1쪽은 항상."""
    s = set(cres.get("meta_pages") or [])
    for k in ("objectives_page", "exercise_page"):
        if cres.get(k):
            s.add(cres[k])
    s |= code_meta_pages(material)
    return sorted(s)
