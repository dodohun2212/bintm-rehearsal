"""F06 강조 발화 찾기 (AI 호출 2) + 인용 검사."""
from __future__ import annotations

import json
import re

import config
from core import prompts
from core.extract import mask
from core.llm import Usage, ask_json

TYPES = {"emphasis", "exam_hint", "mistake_warning", "exercise_hint", "deferral", "skip", "question"}
TYPE_LABEL = {
    "emphasis": "강조",
    "exam_hint": "시험 암시",
    "mistake_warning": "실수 경고",
    "exercise_hint": "연습문제 지목",
    "deferral": "다음에 다룸",
    "skip": "가볍게 넘어감",
    "question": "학우 질문",
}


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def quote_in(transcript: str, quote: str) -> bool:
    """공백을 무시하고 대본에 실제로 있는지."""
    q = _squash(quote)
    return bool(q) and q in _squash(transcript)


def concepts_brief(concepts: list[dict]) -> str:
    """호출 2에는 id, name, summary, keywords만 보낸다."""
    brief = [{k: c.get(k) for k in ("id", "name", "summary", "keywords")} for c in concepts]
    return json.dumps(brief, ensure_ascii=False)


def call_utterances(transcript: str, concepts: list[dict], usage: Usage | None = None) -> dict:
    prompt = prompts.fill("utterances", CONCEPTS_JSON=concepts_brief(concepts), TRANSCRIPT=mask(transcript))
    return ask_json(prompt, max_tokens=config.UTTER_MAX_TOKENS, thinking=True, usage=usage)


def clean_utterances(raw: dict, transcript: str, concept_ids) -> list[dict]:
    """형식이 틀린 항목, 대본에 없는 인용, 모르는 유형은 그 항목만 버린다."""
    ids = set(concept_ids)
    items = raw.get("utterances") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        typ = str(item.get("type") or "").strip()
        if not quote or typ not in TYPES or not quote_in(transcript, quote):
            continue
        cid = item.get("concept_id")
        if isinstance(cid, bool):
            cid = None
        if isinstance(cid, (int, float)):
            n = int(cid)
            cid = f"c{n}" if f"c{n}" in ids else str(n)
        if cid is not None:
            cid = str(cid).strip()
            if cid in ("", "null", "None") or cid not in ids:
                cid = None
        try:
            strength = int(round(float(item.get("strength", 2))))
        except (TypeError, ValueError):
            strength = 2
        strength = max(1, min(3, strength))
        out.append({
            "concept_id": cid,
            "concept_name": str(item.get("concept_name") or ""),
            "quote": quote,
            "type": typ,
            "strength": strength,
        })
    return out


def find_utterances(transcript: str | None, concepts: list[dict], usage: Usage | None = None) -> list[dict]:
    """대본이 없으면 호출하지 않고 빈 목록. 대본은 넣기 전에 가린다(v1.8)."""
    if not transcript or not transcript.strip():
        return []
    masked = mask(transcript)
    raw = call_utterances(masked, concepts, usage)
    return clean_utterances(raw, masked, [c["id"] for c in concepts])
