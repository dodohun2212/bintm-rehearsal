"""F06 강조 발화 찾기 (AI 호출 2) + 인용 검사(대본에 실제로 있는 문장만)."""
from __future__ import annotations

import json
import re

import config
from core import prompts
from core.concepts import concept_list_for_ai
from core.extract import mask
from core.llm import Usage, ask_json
from core.schemas import UTTER_TYPES, Utterance

E10 = "녹음에서 강조한 말을 찾지 못했어요. 자료만으로 점수를 계산했어요"

_WS = re.compile(r"\s+")


def squash(text: str) -> str:
    return _WS.sub("", text or "")


def quote_in(quote: str, transcript: str) -> bool:
    q = squash(quote)
    return bool(q) and q in squash(transcript)


def _concept_id(value, ids: set[str]):
    """발화의 concept_id를 글자로. 숫자 5면 "5"나 "c5" 중 있는 쪽, 목록에 없으면 None."""
    if value is None or value == "null":
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value).strip()
    if s in ids:
        return s
    if s.isdigit() and f"c{s}" in ids:
        return f"c{s}"
    return None


def _strength(v) -> int | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return int(min(3, max(1, round(n))))


def clean_utterances(raw: dict, transcript: str, concept_ids: set[str]) -> list[dict]:
    """항목마다 검사: 모르는 유형은 버리고, 강도는 1~3으로 자르고, 대본에 없는 인용은 버린다."""
    items = raw.get("utterances") if isinstance(raw, dict) else None
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        quote = item.get("quote")
        if t not in UTTER_TYPES or not isinstance(quote, str) or not quote_in(quote, transcript):
            continue
        strength = _strength(item.get("strength"))
        if strength is None:
            continue
        try:
            u = Utterance(concept_id=_concept_id(item.get("concept_id"), concept_ids),
                          concept_name=str(item.get("concept_name") or ""),
                          quote=quote.strip(), type=t, strength=strength)
        except Exception:
            continue
        out.append(u.model_dump())
    return out


def find_utterances(transcript: str, concepts: list[dict], usage: Usage | None = None) -> list[dict]:
    """호출 2: 대본 전체 + 개념 목록. 대본은 보내기 전에 다시 한 번 가린다."""
    if not transcript or not transcript.strip():
        return []
    masked = mask(transcript)
    text = prompts.fill("utterances",
                        CONCEPTS_JSON=json.dumps(concept_list_for_ai(concepts), ensure_ascii=False),
                        TRANSCRIPT=masked)
    raw = ask_json(text, max_tokens=config.UTTERANCE_MAX_TOKENS, thinking=True, usage=usage)
    return clean_utterances(raw, masked, {c["id"] for c in concepts})
