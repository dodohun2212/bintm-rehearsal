"""F06 강조 발화 찾기 (AI 호출 2) + 인용 검사."""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from core import llm, prompts
from core.schemas import Utterance

UTTERANCE_MAX_TOKENS = 6000


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def concepts_json(concepts: list[dict]) -> str:
    """호출 2에 넣는 개념 목록: id, name, summary, keywords만."""
    slim = [{"id": c["id"], "name": c["name"], "summary": c.get("summary", ""),
             "keywords": c.get("keywords", [])} for c in concepts]
    return json.dumps(slim, ensure_ascii=False)


def clean_utterances(raw: dict, transcript: str, concepts: list[dict]) -> list[dict]:
    """형식이 틀린 항목만 버리고, 대본에 없는 인용은 버린다.
    같은 (문장, 개념)은 그 문장이 대본에 나온 횟수까지만 남긴다.
    개념이 없는 연습문제 지목은 "n번"을 연습문제 번호와 맞춰 개념마다 하나씩 붙인다."""
    items = raw.get("utterances") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    ids = {c["id"] for c in concepts}
    by_name = {c["name"]: c["id"] for c in concepts}
    script = _nospace(transcript)
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            u = Utterance.model_validate(item)
        except ValidationError:
            continue
        q = _nospace(u.quote)
        if not q or q not in script:
            continue  # 대본에 없는 인용
        if u.concept_id is not None and u.concept_id not in ids:
            num = u.concept_id.lstrip("c")
            u.concept_id = f"c{num}" if f"c{num}" in ids else by_name.get(u.concept_name)
        if u.concept_id and not u.concept_name:
            u.concept_name = next((c["name"] for c in concepts if c["id"] == u.concept_id), "")
        if u.type == "exercise_hint" and u.concept_id is None:
            nums = {int(n) for n in re.findall(r"(\d+)\s*번", u.quote)}
            matched = [c for c in concepts if nums & set(c.get("exercise_numbers") or [])]
            if matched:
                for c in matched:
                    d = u.model_dump()
                    d["concept_id"], d["concept_name"] = c["id"], c["name"]
                    out.append(d)
                continue
        out.append(u.model_dump())
    # 같은 (문장, 개념) 중복 제한
    kept: list[dict] = []
    seen: dict[tuple, int] = {}
    for d in out:
        q = _nospace(d["quote"])
        key = (q, d["concept_id"], d["concept_name"] if d["concept_id"] is None else "")
        limit = max(1, script.count(q))
        if seen.get(key, 0) >= limit:
            continue
        seen[key] = seen.get(key, 0) + 1
        kept.append(d)
    return kept


def find_utterances(transcript: str, concepts: list[dict], usage: llm.Usage | None = None) -> list[dict]:
    if not transcript or not transcript.strip():
        return []
    prompt = prompts.fill("utterances", CONCEPTS_JSON=concepts_json(concepts), TRANSCRIPT=transcript)
    raw = llm.ask_json(prompt, max_tokens=UTTERANCE_MAX_TOKENS, thinking=True, usage=usage)
    return clean_utterances(raw, transcript, concepts)


def emphasis_count(utterances: list[dict]) -> int:
    """S02 '교수님 강조' 숫자: 개념에 붙은 서로 다른 문장 수."""
    return len({u["quote"] for u in utterances if u.get("concept_id")})


def professor_quotes(utterances: list[dict], concept_id: str, n: int = 3) -> list[dict]:
    """개념에 붙은 교수님 말을 강한 것부터 n개 (감점 유형 제외, 같은 문장은 한 번)."""
    good = [u for u in utterances if u.get("concept_id") == concept_id
            and u.get("type") in ("emphasis", "exam_hint", "mistake_warning", "exercise_hint")]
    good.sort(key=lambda u: -int(u.get("strength", 1)))
    out, seen = [], set()
    for u in good:
        if u["quote"] in seen:
            continue
        seen.add(u["quote"])
        out.append(u)
        if len(out) >= n:
            break
    return out
