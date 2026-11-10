"""F09 보완 설명 (AI 호출 4) + 페이지 검사, "내가 놓친 점" 바로잡기."""
from __future__ import annotations

import json

import config
from core import prompts
from core.diagnose import DONT_KNOW, MCQ, REASON_BLANK, REASON_DONT_KNOW, clean_confusion
from core.figure import figure_text
from core.llm import Usage, ask_json
from core.schemas import parse_pages

GENERIC_GAP = "아직 확인하지 않은 개념"


def diagnosis_payload(concept: dict, q: dict | None, grading: dict | None, ans: dict | None) -> dict:
    ans = ans or {}
    status = grading["status"] if grading else "진단 안 함"
    d = {"concept": concept["name"], "status": status, "summary": concept.get("summary", "")}
    if q and grading:
        d["kind"] = q["kind"]
        d["question"] = q["question"]
        if q.get("figure"):
            d["figure"] = figure_text(q["figure"])
        if q["kind"] == MCQ:
            d["choices"] = [f"{i + 1}. {c}" for i, c in enumerate(q["choices"])]
            d["correct"] = f"{q['answer_index'] + 1}. {q['answer']}"
            ch = ans.get("choice")
            if ch == DONT_KNOW:
                d["my_choice"] = "모르겠어요"
            elif isinstance(ch, int) and 0 <= ch < len(q["choices"]):
                d["my_choice"] = f"{ch + 1}. {q['choices'][ch]}" + (" (확신 없이 고름)" if ans.get("guessed") else "")
            else:
                d["my_choice"] = "(고르지 않음)"
            d["explanation"] = q.get("explanation", "")
        else:
            d["model_answer"] = q["answer"]
            d["my_answer"] = "모르겠어요" if ans.get("dont_know") else (ans.get("answer") or "")
        d["score"] = f"{grading['score']}/10"
        d["error_type"] = grading.get("error_type")
        d["reason"] = grading.get("reason", "")
    return d


def fix_gap(my_gap: str | None, status: str, grading: dict | None) -> str:
    """진단 결과와 맞지 않는 "내가 놓친 점"을 바로잡는다. AI의 구체적인 문장은 그대로 둔다."""
    gap = (my_gap or "").strip()
    if gap and GENERIC_GAP not in gap:
        return gap
    if status == "진단 안 함" or not grading:
        return gap or "출제 가능성 점수가 낮아 진단 문제를 풀지 않은 개념이다. 자료로 한 번 확인한다."
    reason = grading.get("reason", "")
    if reason == REASON_DONT_KNOW:
        return "'모르겠어요'를 골라 진단 문제가 물은 내용을 아직 답하지 못했다."
    if reason == REASON_BLANK:
        return "답을 비워 두어 진단 문제가 물은 내용을 아직 답하지 못했다."
    if status == "앎":
        return "진단 문제는 맞혔다. 핵심을 한 번 더 확인한다."
    return f"진단 문제에서 {status} 판정을 받았다: {reason}".strip()


def clean_explanation(raw: dict, cid: str, page_nums, confusion: str, status: str, grading: dict | None) -> dict:
    allowed = set(page_nums)
    src = [p for p in parse_pages(raw.get("source_pages")) if p in allowed]
    chk = [p for p in parse_pages(raw.get("check_pages")) if p in allowed][:4]
    reply = raw.get("confusion_reply")
    reply = str(reply).strip() if reply and confusion else None
    note = raw.get("not_found_note")
    return {
        "concept_id": cid,
        "my_gap": fix_gap(raw.get("my_gap"), status, grading),
        "explanation": str(raw.get("explanation") or "").strip(),
        "check_pages": chk or src[:2] or list(page_nums)[:2],
        "source_pages": src,
        "not_found": bool(raw.get("not_found")),
        "not_found_note": str(note).strip() if note else None,
        "confusion_reply": reply or None,
        "confusion": confusion or "",
    }


def explain_prompt(concept, q, grading, ans, confusion: str, pages: list[dict]) -> str:
    return prompts.fill(
        "explain",
        CONCEPT_NAME=concept["name"],
        DIAGNOSIS_JSON=json.dumps(diagnosis_payload(concept, q, grading, ans), ensure_ascii=False, indent=1),
        CONFUSION=clean_confusion(confusion) or "(없음)",
        PAGES=prompts.pages_block(pages),
    )


def make_explanation(concept: dict, q: dict | None, grading: dict | None, ans: dict | None,
                     confusion: str | None, pages: list[dict], usage: Usage | None = None) -> dict:
    conf = clean_confusion(confusion)
    prompt = explain_prompt(concept, q, grading, ans, conf, pages)
    raw = ask_json(prompt, max_tokens=config.AI_MAX_TOKENS, usage=usage)
    status = grading["status"] if grading else "진단 안 함"
    return clean_explanation(raw, concept["id"], [p["n"] for p in pages], conf, status, grading)
