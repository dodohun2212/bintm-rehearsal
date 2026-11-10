"""F09 보완 설명 (AI 호출 4) + 페이지·인용 검사."""
from __future__ import annotations

import json

from pydantic import ValidationError

import config
from core import llm, prompts
from core.cites import strip_bad_cites
from core.diagnose import MCQ, clean_text
from core.figure import figure_text
from core.html import choice_label
from core.schemas import Explanation, keep_pages


def sanitize_confusion(text: str | None) -> str:
    """헷갈린 점: 공백 정리, 300자 자르기, 꺾쇠 바꾸기. 비면 ""."""
    return clean_text(text, config.CONFUSION_MAX_CHARS)


def student_answer_text(q: dict | None, ans: dict) -> str:
    if not q:
        return "(문제 없음)"
    if q.get("kind") == MCQ:
        c = ans.get("mcq_choice")
        if c is None:
            return "(고르지 않음)"
        if c == -1:
            return "모르겠어요"
        txt = f"{choice_label(c)} {q['choices'][c]}"
        return txt + (" (확신 없이 고름)" if ans.get("guessed") else "")
    if ans.get("dont_know"):
        return "모르겠어요"
    return clean_text(ans.get("answer")) or "(빈 답)"


def diagnosis_json(concept: dict, status: str, q: dict | None, g: dict | None, ans: dict) -> str:
    """호출 4의 <diagnosis>: 문제 글, 그림(글), 정답·모범 답안, 학생 답, 채점."""
    d = {"concept": concept["name"], "status": status}
    if q:
        d["kind"] = q.get("kind")
        d["question"] = q.get("question")
        ft = figure_text(q.get("figure"))
        if ft:
            d["figure"] = ft
        if q.get("kind") == MCQ:
            d["choices"] = [f"{choice_label(i)} {c}" for i, c in enumerate(q.get("choices") or [])]
            d["correct"] = f"{choice_label(q['answer_index'])} {q['answer']}"
            d["explanation"] = q.get("explanation")
        else:
            d["model_answer"] = q.get("answer")
            d["rubric"] = q.get("rubric")
        d["student_answer"] = student_answer_text(q, ans)
    if g:
        d["score"] = g.get("score")
        d["error_type"] = g.get("error_type")
        d["reason"] = g.get("reason")
    return json.dumps(d, ensure_ascii=False)


def fix_gap(my_gap: str, status: str, g: dict | None) -> str:
    """진단한 개념인데 '아직 확인하지 않은 개념'이라 쓰거나 비어 있으면 채점 이유에 맞는 말로 바꾼다."""
    gap = (my_gap or "").strip()
    if status == "진단 안 함":
        return gap or "아직 확인하지 않은 개념이다."
    if gap and "아직 확인하지 않은" not in gap:
        return gap
    if g and g.get("error_type") == "무응답":
        return "문제가 물은 내용을 아직 답하지 못했다."
    if g and g.get("reason"):
        return "진단 문제에서 " + str(g["reason"]).rstrip(".") + "."
    return "진단 문제에서 놓친 부분이 있다."


def make_explanation(concept: dict, status: str, q: dict | None, g: dict | None, ans: dict, confusion: str,
                     pages_text: str, allowed, usage: llm.Usage | None = None) -> dict:
    conf = sanitize_confusion(confusion)
    prompt = prompts.fill("explain", CONCEPT_NAME=concept["name"],
                          DIAGNOSIS_JSON=diagnosis_json(concept, status, q, g, ans),
                          CONFUSION=conf or "(없음)", PAGES=pages_text)
    raw = llm.ask_json(prompt, max_tokens=config.AI_MAX_TOKENS, usage=usage)
    try:
        ex = Explanation.model_validate(raw)
    except ValidationError as e:
        raise llm.BadJSONError(f"보완 설명 형식이 맞지 않음: {e}") from e
    allowed = set(allowed)
    d = ex.model_dump()
    d["source_pages"] = keep_pages(d["source_pages"], allowed)
    d["check_pages"] = keep_pages(d["check_pages"], allowed)[:4] or sorted(allowed)[:2]
    d["explanation"] = strip_bad_cites(d["explanation"], allowed)
    d["my_gap"] = fix_gap(strip_bad_cites(d["my_gap"], allowed), status, g)
    if conf:
        d["confusion"] = conf
        d["confusion_reply"] = strip_bad_cites(d["confusion_reply"], allowed) if d.get("confusion_reply") else None
    else:
        d["confusion"] = ""
        d["confusion_reply"] = None  # 적은 게 없으면 AI가 써도 버린다
    if not d["not_found"]:
        d["not_found_note"] = None
    d["concept_id"] = concept["id"]
    d["status"] = status
    return d
