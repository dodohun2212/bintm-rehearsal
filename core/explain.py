"""F09 보완 설명 (AI 호출 4) + 페이지·본문 인용 검사."""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

import config
from core import llm, prompts
from core.diagnose import DONT_KNOW, MCQ, REASON_BLANK, REASON_DONT_KNOW, clean_student_text, evidence_pages
from core.extract import pages_text
from core.figure import figure_text
from core.schemas import ExplanationAI, keep_pages

_CITE = re.compile(r"\s?\((?:p\.|P\.)\s?[\d\s,~\-p.P]+\)")
_NUM = re.compile(r"\d+")
NOT_CHECKED = "아직 확인하지 않은"


def strip_bad_cites(text: str | None, allowed) -> str | None:
    """본문의 (p.n) 중 근거 페이지 밖인 번호를 지운다. 남는 번호가 없으면 표시째 지운다."""
    if not text:
        return text
    allowed_set = set(allowed)

    def repl(m: re.Match) -> str:
        nums = [int(n) for n in _NUM.findall(m.group(0))]
        good = [n for n in nums if n in allowed_set]
        if not good:
            return ""
        lead = " " if m.group(0).startswith(" ") else ""
        if good == nums:
            return m.group(0)
        return lead + "(" + ", ".join(f"p.{n}" for n in good) + ")"

    return _CITE.sub(repl, text)


def fix_gap(my_gap: str, status: str, grading: dict | None) -> str:
    """'내가 놓친 점'이 진단 결과와 맞지 않으면 채점 이유에 맞는 말로 바꾼다."""
    gap = (my_gap or "").strip()
    if status == "진단 안 함":
        return gap or "아직 진단하지 않은 개념이다. 출제 점수가 낮아 문제를 내지 않았다."
    if gap and NOT_CHECKED not in gap:
        return gap
    reason = (grading or {}).get("reason", "")
    if reason == REASON_DONT_KNOW:
        return "'모르겠어요'를 골라 이 문제가 물은 내용을 아직 답하지 못했다."
    if reason == REASON_BLANK:
        return "답을 비워 두어 이 문제가 물은 내용을 아직 답하지 못했다."
    if reason:
        return f"채점 이유: {reason}"
    return f"진단 결과는 '{status}'이다."


def diagnosis_payload(concept: dict, prio: dict, q: dict | None, grading: dict | None,
                      answer: str = "", choice: int | None = None, guessed: bool = False) -> dict:
    """호출 4의 <diagnosis>: 문제 글, 그림(글), 정답·모범 답안, 학생 답, 채점까지 모두 넣는다."""
    data = {"concept": concept["name"], "summary": concept.get("summary", ""),
            "exam_pct": prio["exam_pct"], "status": prio["status"]}
    if q is None or grading is None:
        data["question"] = None
        return data
    data.update({"kind": q["kind"], "question": q["question"], "figure": figure_text(q.get("figure")) or None,
                 "score": grading.get("score"), "error_type": grading.get("error_type"),
                 "reason": grading.get("reason")})
    if q["kind"] == MCQ:
        data["choices"] = [f"{'①②③④'[i]} {c}" for i, c in enumerate(q["choices"])]
        data["correct"] = f"{'①②③④'[q['answer_index']]} {q['answer']}"
        if choice is None:
            data["student_choice"] = "(고르지 않음)"
        elif choice == DONT_KNOW:
            data["student_choice"] = "모르겠어요"
        else:
            data["student_choice"] = f"{'①②③④'[choice]} {q['choices'][choice]}" + (" (확신 없이 고름)" if guessed else "")
        data["explanation"] = q.get("explanation")
    else:
        data["model_answer"] = q["answer"]
        data["rubric"] = q["rubric"]
        data["student_answer"] = clean_student_text(answer) or "(답 없음)"
    return data


def clean_explanation(raw: dict, pages: list[int], has_confusion: bool, status: str, grading: dict | None) -> dict:
    try:
        e = ExplanationAI.model_validate(raw if isinstance(raw, dict) else {})
    except ValidationError:
        e = ExplanationAI()
    if not e.explanation:
        raise llm.BadJSONError("설명이 비어 있음")
    source = keep_pages(e.source_pages, pages) or pages[:2]
    check = (keep_pages(e.check_pages, pages) or source)[:4]
    reply = strip_bad_cites(e.confusion_reply, pages) if has_confusion else None
    note = e.not_found_note
    if e.not_found and not note:
        note = "올린 자료에는 이 설명에 필요한 내용이 없음"
    return {"my_gap": fix_gap(e.my_gap, status, grading),
            "explanation": strip_bad_cites(e.explanation, pages),
            "check_pages": check, "source_pages": source,
            "not_found": bool(e.not_found), "not_found_note": note if e.not_found else None,
            "confusion_reply": reply}


def make_explanation(concept: dict, prio: dict, q: dict | None, grading: dict | None, material: dict,
                     meta: list[int], answer: str = "", choice: int | None = None, guessed: bool = False,
                     confusion: str = "", usage: llm.Usage | None = None) -> dict:
    pages = q["pages"] if q else evidence_pages(concept, meta)
    conf = clean_student_text(confusion, config.CONFUSION_MAX_CHARS)
    payload = diagnosis_payload(concept, prio, q, grading, answer, choice, guessed)
    prompt = prompts.fill("explain", CONCEPT_NAME=concept["name"],
                          DIAGNOSIS_JSON=json.dumps(payload, ensure_ascii=False),
                          CONFUSION=conf or "(없음)", PAGES=pages_text(material, pages))
    raw = llm.ask_json(prompt, usage=usage)
    out = clean_explanation(raw, pages, bool(conf), prio["status"], grading)
    out["concept_id"] = concept["id"]
    out["confusion"] = conf or None
    return out
