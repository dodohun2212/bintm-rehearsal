"""F09 보완 설명 (AI 호출 4) + 페이지 검사, 헷갈린 점 다듬기, '내가 놓친 점' 바로잡기."""
from __future__ import annotations

import json
import re

import config
from core import prompts
from core.diagnose import MCQ, REASON_DONT_KNOW, REASON_EMPTY, REASON_NO_CHOICE
from core.figure import figure_text
from core.llm import Usage, ask_json
from core.priority import NOW
from core.schemas import Explanation

NONE_TEXT = "(없음)"
_WS = re.compile(r"\s+")


def clean_confusion(text: str | None) -> str:
    """공백을 한 칸으로, 300자로 자르고, 꺾쇠를 비슷한 글자로 바꿔 태그를 닫지 못하게."""
    s = _WS.sub(" ", text or "").strip()
    s = s[:config.CONFUSION_MAX_CHARS]
    return s.replace("<", "‹").replace(">", "›")


def auto_targets(priorities: list[dict], confusion: dict) -> list[str]:
    """화면이 열릴 때 자동으로 설명할 개념: '지금 당장' 전부 + 상위 3개 + 헷갈린 점을 적은 개념."""
    ids = [p["concept_id"] for p in priorities if p["action"] == NOW]
    for p in priorities[:config.AUTO_EXPLAIN_TOP]:
        if p["concept_id"] not in ids:
            ids.append(p["concept_id"])
    for p in priorities:
        cid = p["concept_id"]
        if clean_confusion((confusion or {}).get(cid)) and cid not in ids:
            ids.append(cid)
    return ids


def diagnosis_json(name: str, status: str, q: dict | None, grading: dict | None, my_answer: dict | None) -> dict:
    """호출 4의 <diagnosis>: 문제 형식, 문제(보기), 정답, 내 답, 틀린 유형과 이유."""
    d = {"concept": name, "status": status}
    if not q:
        return d
    d["kind"] = q["kind"]
    d["question"] = q["question"]
    if q.get("figure"):
        d["figure"] = figure_text(q["figure"])
    my_answer = my_answer or {}
    if q["kind"] == MCQ:
        d["choices"] = q["choices"]
        d["correct"] = q["answer"]
        c = my_answer.get("mcq_choice")
        if isinstance(c, int) and 0 <= c <= 3:
            d["my_choice"] = q["choices"][c] + (" (확신 없이 고름)" if my_answer.get("guessed") else "")
        else:
            d["my_choice"] = "모르겠어요"
        d["explanation"] = q.get("explanation", "")
    else:
        d["model_answer"] = q.get("answer", "")
        d["my_answer"] = "모르겠어요" if my_answer.get("dont_know") else (my_answer.get("answer") or "")
    if grading:
        d["score"] = grading.get("score")
        d["error_type"] = grading.get("error_type")
        d["reason"] = grading.get("reason")
    return d


def fix_gap(my_gap: str | None, status: str, grading: dict | None) -> str:
    """진단 결과와 맞지 않는 '내가 놓친 점'을 코드가 바꾼다. AI의 구체적인 문장은 그대로 둔다."""
    gap = (my_gap or "").strip()
    if status == "진단 안 함":
        return gap or "아직 확인하지 않은 개념이다."
    if gap and "아직 확인하지 않은" not in gap:
        return gap
    reason = (grading or {}).get("reason") or ""
    if reason == REASON_DONT_KNOW:
        return "'모르겠어요'를 골라 이 문제가 물은 내용을 아직 답하지 못했다."
    if reason == REASON_EMPTY:
        return "답을 비워 두어 이 문제가 물은 내용을 아직 답하지 못했다."
    if reason == REASON_NO_CHOICE:
        return "보기를 고르지 않아 이 문제가 물은 내용을 아직 확인하지 못했다."
    if status == "앎":
        return "진단 문제는 맞혔다. 아래 설명으로 한 번 더 정리한다."
    return f"진단 문제에서 놓친 부분이 있다. 채점 이유: {reason}" if reason else "진단 문제에서 놓친 부분이 있다."


def clean_explanation(raw: dict, cid: str, allowed: list[int], has_confusion: bool,
                      status: str, grading: dict | None) -> dict:
    from core.concepts import to_pages
    src = [n for n in to_pages(raw.get("source_pages")) if n in allowed]
    chk = [n for n in to_pages(raw.get("check_pages")) if n in allowed][:4]
    reply = raw.get("confusion_reply")
    reply = reply.strip() if (has_confusion and isinstance(reply, str) and reply.strip()) else None
    note = raw.get("not_found_note")
    e = Explanation(
        concept_id=cid,
        my_gap=fix_gap(raw.get("my_gap") if isinstance(raw.get("my_gap"), str) else "", status, grading),
        explanation=str(raw.get("explanation") or "").strip(),
        check_pages=chk or src[:2] or allowed[:2], source_pages=src,
        not_found=raw.get("not_found") is True or str(raw.get("not_found")).lower() == "true",
        not_found_note=note.strip() if isinstance(note, str) and note.strip() else None,
        confusion_reply=reply)
    if not e.explanation:
        raise ValueError("설명이 비어 있음")
    return e.model_dump()


def make_explanation(cid: str, name: str, status: str, q: dict | None, grading: dict | None,
                     my_answer: dict | None, confusion: str | None, pages: list[dict],
                     usage: Usage | None = None) -> dict:
    conf = clean_confusion(confusion)
    diag = diagnosis_json(name, status, q, grading, my_answer)
    text = prompts.fill("explain", CONCEPT_NAME=name,
                        DIAGNOSIS_JSON=json.dumps(diag, ensure_ascii=False),
                        CONFUSION=conf or NONE_TEXT, PAGES=prompts.pages_text(pages))
    raw = ask_json(text, max_tokens=config.AI_MAX_TOKENS, usage=usage)
    try:
        return clean_explanation(raw, cid, [p["n"] for p in pages], bool(conf), status, grading)
    except ValueError as exc:
        from core.llm import BadJsonError
        raise BadJsonError(str(exc)) from exc
