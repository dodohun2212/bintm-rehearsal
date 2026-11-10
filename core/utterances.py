# F06 강조 발화 찾기 (AI 호출 2) + 인용 검사
import json
import re

from core import prompts
from core.extract import mask
from core.llm import Usage, ask_json
from core.schemas import Utterance


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def quote_in_transcript(quote: str, transcript: str) -> bool:
    """공백을 무시하고 대본에 실제로 있는지."""
    q = _squash(quote)
    return bool(q) and q in _squash(transcript)


def _fix_concept_id(value, ids: set[str]):
    if value is None:
        return None
    s = str(value).strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        s = str(int(value))
    if s in ids:
        return s
    if f"c{s}" in ids:
        return f"c{s}"
    return None


def parse_utterances(raw: dict, transcript: str, concept_ids) -> list[dict]:
    ids = set(concept_ids)
    items = raw.get("utterances") if isinstance(raw, dict) else None
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            strength = int(round(float(item.get("strength", 2))))
        except (TypeError, ValueError):
            strength = 2
        try:
            u = Utterance(
                concept_id=_fix_concept_id(item.get("concept_id"), ids),
                concept_name=str(item.get("concept_name") or ""),
                quote=str(item.get("quote") or "").strip(),
                type=str(item.get("type") or ""),
                strength=min(3, max(1, strength)),
            )
        except Exception:
            continue
        if not quote_in_transcript(u.quote, transcript):
            continue
        out.append(u.model_dump())
    return out


def build_prompt(concepts: list[dict], transcript: str) -> str:
    slim = [{"id": c["id"], "name": c["name"], "summary": c.get("summary", ""),
             "keywords": c.get("keywords", [])} for c in concepts]
    return prompts.fill("02", CONCEPTS_JSON=json.dumps(slim, ensure_ascii=False),
                        TRANSCRIPT=mask(transcript))


def find_utterances(concepts: list[dict], transcript: str | None, usage: Usage | None = None) -> list[dict]:
    if not transcript or not transcript.strip():
        return []
    transcript = mask(transcript)
    raw = ask_json(build_prompt(concepts, transcript), max_tokens=6000, thinking=True, usage=usage)
    return parse_utterances(raw, transcript, [c["id"] for c in concepts])
