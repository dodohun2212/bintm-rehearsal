"""F08 진단: 대상 고르기, 문제 형식, 문제 만들기(03-A 서술형, 03-C 객관식), 채점(03-B, 객관식은 코드)."""
from __future__ import annotations

import hashlib
import json
import random
import re

from pydantic import ValidationError

import config
from core import llm, prompts
from core.extract import pages_text
from core.figure import figure_text, needs_fix, validate_figure
from core.schemas import ERROR_TYPES, EssayQuestionAI, MCQuestionAI, keep_pages

# 문제가 페이지·그림을 가리킬 때 덧붙이는 한 단락 (BR-10 예외 ②)
FIX_NOTE = (
    "\n\n## 다시 만들기\n"
    "지난번 문제 글이 학생이 볼 수 없는 페이지 번호나 그림을 가리켰습니다. 학생은 이 문제 화면만 봅니다. "
    "문제 글에 페이지 번호(p.n, n쪽)나 \"그림\", \"위 트리\" 같은 말을 쓰지 말고, "
    "트리·배열·표가 필요하면 그 데이터를 `figure`에 넣고 문제 글에서는 \"아래 트리\"처럼 가리키세요."
)
EXAMPLE_CONFUSION = "두 보기 사이에서 고민했어요. 둘이 어떻게 다른지 모르겠어요."
MODES = ("섞어서", "모두 객관식", "모두 서술형")
ESSAY, MCQ = "서술형", "객관식"
DONT_KNOW = -1

REASON_BLANK = "답을 비워 두어 모름으로 표시했어요."
REASON_DONT_KNOW = "'모르겠어요'를 골라 모름으로 표시했어요."
REASON_NOT_CHOSEN = "보기를 고르지 않아 모름으로 표시했어요."


class QuestionError(Exception):
    """두 번 시도해도 문제를 만들지 못함."""


# ---------- 대상·형식 ----------
def diag_targets(scores: list[dict], top: int | None = None) -> list[str]:
    """출제 점수 20점 이상 개념(순위 순서). top이 있으면 그중 상위 top개(빠른 진단)."""
    ids = [s["concept_id"] for s in scores if s["pct"] >= config.DIAG_MIN_PCT]
    return ids[:top] if top else ids


def quick_default(n_targets: int, from_sample: bool) -> bool:
    """빠른 진단 기본값: 직접 올린 자료이고 대상이 8개보다 많을 때만 켠다(샘플은 끈다)."""
    return (not from_sample) and n_targets > config.QUICK_DIAG_AUTO_OVER


def choose_kind(pct: int, mode: str) -> str:
    if mode == "모두 객관식":
        return MCQ
    if mode == "모두 서술형":
        return ESSAY
    return ESSAY if pct >= config.ESSAY_MIN_PCT else MCQ


def evidence_pages(concept: dict, meta: list[int]) -> list[int]:
    """호출 3·4·5에 넣는 근거 쪽. 본문 쪽을 먼저, 최대 8쪽."""
    pages = concept.get("pages") or []
    body = [p for p in pages if p not in set(meta)]
    rest = [p for p in pages if p in set(meta)]
    chosen = (body + rest)[: config.MAX_EVIDENCE_PAGES]
    return sorted(chosen) or [1]


def other_concepts_text(names: list[str], own: str) -> str:
    others = [n for n in names if n != own]
    return "\n".join(f"- {n}" for n in others) if others else "(없음)"


def clean_student_text(text: str | None, limit: int | None = None) -> str:
    """학생이 쓴 글: 공백을 한 칸으로, 꺾쇠를 ‹ ›로(태그를 닫지 못하게), limit이 있으면 자른다."""
    out = re.sub(r"\s+", " ", text or "").strip()
    out = out.replace("<", "‹").replace(">", "›")
    if limit:
        out = out[:limit]
    return out


# ---------- 문제 검사 ----------
_CHOICE_NO = re.compile(r"^\s*(?:[①②③④⑤]|\(?[1-5A-Ea-e]\)|[1-5A-E]\.(?!\d))\s*")


def strip_choice_number(text: str) -> str:
    return _CHOICE_NO.sub("", str(text)).strip()


def check_mcq(raw: dict) -> dict | None:
    """보기 4개가 서로 다르고 정답 위치가 0~3이면 정리한 문제, 아니면 None."""
    try:
        q = MCQuestionAI.model_validate(raw)
    except (ValidationError, TypeError):
        return None
    choices = [strip_choice_number(c) for c in q.choices]
    if len(choices) != 4 or any(not c for c in choices) or len(set(choices)) != 4:
        return None
    if not (0 <= q.answer_index <= 3):
        return None
    return {"question": q.question, "choices": choices, "answer_index": q.answer_index,
            "explanation": q.explanation, "source_pages": q.source_pages, "figure": q.figure}


def shuffle_mcq(q: dict, seed_text: str) -> dict:
    """문제마다 고정된 seed로 보기를 섞는다. 정답이 따라간다."""
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16)
    order = list(range(len(q["choices"])))
    random.Random(seed).shuffle(order)
    out = dict(q)
    out["choices"] = [q["choices"][i] for i in order]
    out["answer_index"] = order.index(q["answer_index"])
    return out


def _to_int(v) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def clean_rubric(rubric) -> list[dict]:
    items = []
    for r in rubric or []:
        if isinstance(r, dict) and str(r.get("point", "")).strip():
            items.append({"point": str(r["point"]).strip(), "score": max(0, _to_int(r.get("score")))})
    if not items:
        return []
    total = sum(r["score"] for r in items)
    if total != 10:  # 합이 10이 아니면 비례로 맞춘다
        if total <= 0:
            base = [10 // len(items)] * len(items)
        else:
            base = [int(r["score"] * 10 / total) for r in items]
        base[-1] += 10 - sum(base)
        for r, s in zip(items, base):
            r["score"] = s
    return items


def check_essay(raw: dict) -> dict | None:
    try:
        q = EssayQuestionAI.model_validate(raw)
    except (ValidationError, TypeError):
        return None
    rubric = clean_rubric(q.rubric)
    if not rubric:
        return None
    return {"question": q.question, "answer": q.answer, "rubric": rubric,
            "source_pages": q.source_pages, "figure": q.figure}


def _finish(concept: dict, kind: str, q: dict, pages: list[int], others_key: str) -> dict:
    q = dict(q)
    q["figure"] = validate_figure(q.get("figure"))
    q["source_pages"] = keep_pages(q.get("source_pages") or [], pages) or pages[:2]
    if kind == MCQ:
        q = shuffle_mcq(q, f"{concept['id']}|{concept['name']}|{q['question']}")
        q["answer"] = q["choices"][q["answer_index"]]
        q["rubric"] = None
    else:
        q["choices"] = None
        q["answer_index"] = None
        q["explanation"] = None
    q.update({"concept_id": concept["id"], "name": concept["name"], "kind": kind, "pages": pages})
    return q


def make_question(concept: dict, kind: str, material: dict, meta: list[int], other_names: list[str],
                  usage: llm.Usage | None = None) -> dict:
    """문제 1개. 객관식 형식이 틀리거나 두 번 다 그림을 가리키면 서술형으로 대신 낸다."""
    pages = evidence_pages(concept, meta)
    values = dict(CONCEPT_NAME=concept["name"], OTHER_CONCEPTS=other_concepts_text(other_names, concept["name"]),
                  PAGES=pages_text(material, pages))
    if kind == MCQ:
        fix = False
        for _ in range(2):
            prompt = prompts.fill("mcq", **values) + (FIX_NOTE if fix else "")
            q = check_mcq(llm.ask_json(prompt, usage=usage))
            if q is None:
                break  # 형식이 틀리면 서술형으로
            if needs_fix(q["question"], validate_figure(q.get("figure"))):
                fix = True
                continue
            return _finish(concept, MCQ, q, pages, "")
        kind = ESSAY
    fix = False
    last = None
    for _ in range(2):
        prompt = prompts.fill("essay", **values) + (FIX_NOTE if fix else "")
        try:
            q = check_essay(llm.ask_json(prompt, usage=usage))
        except llm.BadJSONError:
            q = None
        if q is None:
            continue
        last = q
        if needs_fix(q["question"], validate_figure(q.get("figure"))):
            fix = True
            continue
        return _finish(concept, ESSAY, q, pages, "")
    if last is not None:
        return _finish(concept, ESSAY, last, pages, "")
    raise QuestionError(f"{concept['name']} 문제를 만들지 못함")


# ---------- 답했는지·예시 답 ----------
def is_answered(q: dict, answer: str | None = None, dont_know: bool = False, choice: int | None = None) -> bool:
    if q["kind"] == MCQ:
        return choice is not None and (choice == DONT_KNOW or 0 <= choice < len(q.get("choices") or []))
    return bool(dont_know) or bool((answer or "").strip())


def first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return parts[0] if parts else ""


def example_answers(questions: list[dict]) -> dict:
    """샘플 체험용 예시 답. 서술형: 모범 답안 → 첫 문장 → 모르겠어요. 객관식: 확신 정답 → 찍어서 정답 → 오답."""
    out = {}
    n_essay = n_mcq = 0
    for q in questions:
        cid = q["concept_id"]
        if q["kind"] == ESSAY:
            step = n_essay % 3
            n_essay += 1
            if step == 0:
                out[cid] = {"answer": q["answer"], "dont_know": False}
            elif step == 1:
                out[cid] = {"answer": first_sentence(q["answer"]), "dont_know": False}
            else:
                out[cid] = {"answer": "", "dont_know": True}
        else:
            step = n_mcq % 3
            n_mcq += 1
            right = q["answer_index"]
            if step == 0:
                out[cid] = {"choice": right, "guessed": False, "confusion": ""}
            elif step == 1:
                out[cid] = {"choice": right, "guessed": True, "confusion": EXAMPLE_CONFUSION}
            else:
                out[cid] = {"choice": (right + 1) % len(q["choices"]), "guessed": False, "confusion": ""}
    return out


# ---------- 채점 ----------
def status_from_score(score: int, error_type: str | None = None) -> str:
    """8 이상 앎, 4~7 헷갈림("개념 혼동"이면 모름), 3 이하 모름."""
    if score >= 8:
        return "앎"
    if score >= 4:
        return "모름" if error_type == "개념 혼동" else "헷갈림"
    return "모름"


def no_answer(kind: str, reason: str) -> dict:
    return {"kind": kind, "score": 0, "max": 10, "status": "모름", "error_type": "무응답",
            "reason": reason, "rubric_scores": None}


def grade_mcq(q: dict, choice: int | None, guessed: bool = False) -> dict:
    """객관식은 코드가 채점한다(AI 호출 없음)."""
    if choice is None:
        return no_answer(MCQ, REASON_NOT_CHOSEN)
    if choice == DONT_KNOW:
        return no_answer(MCQ, REASON_DONT_KNOW)
    right = q["answer_index"]
    if choice == right and not guessed:
        g = {"score": 10, "status": "앎", "error_type": None, "reason": "정답을 확신하고 골랐어요."}
    elif choice == right:
        g = {"score": 5, "status": "헷갈림", "error_type": "찍어서 맞힘",
             "reason": "정답이지만 확신 없이 골라 헷갈림으로 봤어요."}
    else:
        g = {"score": 0, "status": "모름", "error_type": "오답",
             "reason": f"{'①②③④'[choice]}을 골랐지만 정답은 {'①②③④'[right]}이에요."}
    g.update({"kind": MCQ, "max": 10, "rubric_scores": None})
    return g


def clean_grading(raw: dict, rubric: list[dict]) -> dict:
    """AI 채점 결과 정리. 부분 점수·null·글자도 받아들이고, 총점은 잘라 낸 루브릭 점수의 합."""
    raw = raw if isinstance(raw, dict) else {}
    maxes = [r["score"] for r in rubric]
    given = raw.get("rubric_scores")
    given = given if isinstance(given, list) else []
    scores = [min(max(0, _to_int(v)), m) for v, m in zip(given, maxes)]
    if len(given) == len(maxes):
        total = sum(scores)
    else:
        total = min(max(0, _to_int(raw.get("score"))), 10)
        scores = None
    err = raw.get("error_type")
    err = None if err in (None, "", "null", "None") else str(err).strip()
    if err is not None and err not in ERROR_TYPES:
        err = "기타"
    reason = raw.get("reason")
    reason = "" if reason in (None, "null") else str(reason).strip()
    return {"kind": ESSAY, "score": total, "max": 10, "status": status_from_score(total, err),
            "error_type": err, "reason": reason, "rubric_scores": scores}


def grade_essay(q: dict, answer: str, dont_know: bool, material: dict, usage: llm.Usage | None = None) -> dict:
    if dont_know:
        return no_answer(ESSAY, REASON_DONT_KNOW)
    if not (answer or "").strip():
        return no_answer(ESSAY, REASON_BLANK)
    question_json = json.dumps({"question": q["question"], "answer": q["answer"], "rubric": q["rubric"],
                                "figure": figure_text(q.get("figure")) or None}, ensure_ascii=False)
    prompt = prompts.fill("grade", CONCEPT_NAME=q["name"], QUESTION_JSON=question_json,
                          PAGES=pages_text(material, q["pages"]), ANSWER=clean_student_text(answer))
    raw = llm.ask_json(prompt, usage=usage)
    return clean_grading(raw, q["rubric"])
