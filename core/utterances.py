"""F06 강조 발화 찾기 (AI 호출 2) + 인용 검사. 대본에 실제로 있는 문장만 남긴다."""
from __future__ import annotations

import re

from pydantic import ValidationError

from core import llm, prompts
from core.concepts import concepts_for_prompt
from core.extract import mask
from core.schemas import Utterance

_SPACE = re.compile(r"\s+")


def _squash(text: str) -> str:
    return _SPACE.sub("", text or "")


def quote_in_transcript(quote: str, transcript: str) -> bool:
    """공백을 무시하고 대본 안에 그대로 있는지."""
    q = _squash(quote)
    return bool(q) and q in _squash(transcript)


def clean_utterances(raw: dict, transcript: str, concept_ids: set[str]) -> list[dict]:
    items = raw.get("utterances") if isinstance(raw, dict) else None
    out: list[dict] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            utt = Utterance.model_validate(item)
        except ValidationError:
            continue  # 모르는 유형·빈 인용 등은 버린다
        if not quote_in_transcript(utt.quote, transcript):
            continue
        if utt.concept_id is not None and utt.concept_id not in concept_ids:
            utt.concept_id = None
        out.append(utt.model_dump())
    return out


def find_utterances(transcript: str | None, concepts: list[dict], usage: llm.Usage | None = None) -> list[dict]:
    """대본이 없으면 호출하지 않고 빈 목록. 대본은 가린 뒤 보낸다."""
    if not transcript or not transcript.strip():
        return []
    masked = mask(transcript)
    prompt = prompts.fill("utterances", CONCEPTS_JSON=concepts_for_prompt(concepts), TRANSCRIPT=masked)
    raw = llm.ask_json(prompt, max_tokens=6000, thinking=True, usage=usage)
    return clean_utterances(raw, masked, {c["id"] for c in concepts})
