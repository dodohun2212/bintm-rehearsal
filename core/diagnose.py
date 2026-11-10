"""F08 진단: 대상·문제 형식 고르기, 문제 만들기(03-A 서술형, 03-C 객관식), 채점(03-B·코드), 예시 답."""
from __future__ import annotations

import hashlib
import json
import random
import re

import config
from core import prompts
from core.figure import check_figure, figure_text, points_away
from core.llm import BadJsonError, KeyMissingError, LLMError, Usage, ask_json
from core.schemas import Question

MODES = ("섞어서", "모두 객관식", "모두 서술형")
ESSAY, MCQ = "서술형", "객관식"

# 문제가 페이지·그림을 가리킬 때 덧붙이는 단락 (BR-10 예외 2)
FIX_NOTE = ("\n\n## 다시 만들기\n앞서 만든 문제가 학생이 볼 수 없는 페이지 번호(p.n, n쪽)나 그림을 가리켰습니다. "
            "학생은 이 문제 화면만 봅니다. 문제 글에 페이지 번호나 \"그림 참고\" 같은 말을 쓰지 말고, "
            "트리·배열·표가 필요하면 그 데이터를 `figure`에 넣어 다시 만드세요.")

EXAMPLE_CONFUSION = "두 보기 사이에서 고민했어요. 둘이 어떻게 다른지 모르겠어요."

REASON_DONT_KNOW = "'모르겠어요'를 골라 모름으로 표시했어요."
REASON_EMPTY = "답을 비워 두어 모름으로 표시했어요."
REASON_NO_CHOICE = "보기를 고르지 않아 모름으로 표시했어요."

ERROR_TYPES = ("개념 혼동", "비교 방향 오류", "복잡도 오류", "절차 누락", "무응답", "기타")


class BadQuestion(Exception):
    """AI 문제의 형식이 틀림."""


# --- 대상과 형식 ---
def diag_targets(scores: list[dict], top: int | None = None) -> list[str]:
    """출제 점수 DIAG_MIN_PCT 이상 개념 전부(순위 순서). top이 있으면 그중 상위 top개."""
    ids = [s["concept_id"] for s in scores if s["pct"] >= config.DIAG_MIN_PCT]
    return ids[:top] if top else ids


def question_kind(pct: int, mode: str) -> str:
    if mode == "모두 객관식":
        return MCQ
    if mode == "모두 서술형":
        return ESSAY
    return ESSAY if pct >= config.ESSAY_MIN_PCT else MCQ


def other_concepts_text(names: list[str], self_name: str) -> str:
    others = [n for n in names if n != self_name]
    return "\n".join(f"- {n}" for n in others) if others else "(없음)"


def evidence_pages(concept: dict, material: dict, meta: list[int] | None = None) -> list[dict]:
    """그 개념의 pages 텍스트만(RAG), 최대 MAX_EVIDENCE_PAGES쪽. 넘치면 본문 쪽부터."""
    by_n = {p["n"]: p for p in material["pages"]}
    pages = [n for n in concept.get("pages", []) if n in by_n]
    if len(pages) > config.MAX_EVIDENCE_PAGES:
        meta_set = set(meta or [])
        body = [n for n in pages if n not in meta_set]
        rest = [n for n in pages if n in meta_set]
        pages = sorted((body + rest)[:config.MAX_EVIDENCE_PAGES])
    if not pages:  # 쪽 정보가 없으면 첫 쪽들
        pages = sorted(by_n)[:2]
    return [by_n[n] for n in pages]


# --- 문제 만들기 ---
def _clean_pages(value, allowed: list[int]) -> list[int]:
    from core.concepts import to_pages
    return [n for n in to_pages(value) if n in allowed]


def _to_int(v) -> int:
    """부분 점수(2.5)·null·글자도 정수로. 파이썬 round(.5는 가까운 짝수). 잘못된 값은 0."""
    if isinstance(v, bool) or v is None:
        return 0
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def clean_essay(raw: dict, allowed: list[int]) -> dict:
    q = raw.get("question")
    if not isinstance(q, str) or not q.strip():
        raise BadQuestion("문제 글 없음")
    rubric = []
    for item in raw.get("rubric") or []:
        if isinstance(item, dict) and str(item.get("point") or "").strip():
            rubric.append({"point": str(item["point"]).strip(), "score": max(0, _to_int(item.get("score")))})
    if not rubric:
        raise BadQuestion("루브릭 없음")
    total = sum(r["score"] for r in rubric)
    if total != 10:  # 비례로 맞춤
        if total <= 0:
            base = [10 // len(rubric)] * len(rubric)
        else:
            base = [int(r["score"] * 10 / total) for r in rubric]
        base[0] += 10 - sum(base)
        for r, s in zip(rubric, base):
            r["score"] = s
    data = Question(kind=ESSAY, question=q.strip(), answer=str(raw.get("answer") or "").strip(),
                    rubric=rubric, source_pages=_clean_pages(raw.get("source_pages"), allowed),
                    figure=check_figure(raw.get("figure")))
    return data.model_dump()


_NUMBERING = re.compile(r"^\s*(?:[①②③④⑤]|\(?[1-5A-Ea-e가-라][.)]|[1-5]\s*번)\s*")


def strip_number(choice: str) -> str:
    return _NUMBERING.sub("", choice, count=1).strip()


def clean_mcq(raw: dict, allowed: list[int]) -> dict:
    """보기 4개가 서로 다르고 정답 위치가 0~3인지 검사. 보기 앞 번호를 지운 뒤 고정 seed로 섞는다."""
    q = raw.get("question")
    choices = raw.get("choices")
    idx = raw.get("answer_index")
    if not isinstance(q, str) or not q.strip():
        raise BadQuestion("문제 글 없음")
    if not isinstance(choices, list) or len(choices) != 4:
        raise BadQuestion("보기 4개가 아님")
    choices = [strip_number(str(c)) for c in choices]
    if any(not c for c in choices) or len(set(choices)) != 4:
        raise BadQuestion("빈 보기 또는 겹치는 보기")
    if isinstance(idx, bool) or not isinstance(idx, (int, float)) or int(idx) != idx or not 0 <= int(idx) <= 3:
        raise BadQuestion("정답 위치가 0~3이 아님")
    correct = choices[int(idx)]
    shuffled = shuffle_choices(q.strip(), choices)
    new_idx = shuffled.index(correct)
    data = Question(kind=MCQ, question=q.strip(), answer=correct, choices=shuffled, answer_index=new_idx,
                    explanation=str(raw.get("explanation") or "").strip(),
                    source_pages=_clean_pages(raw.get("source_pages"), allowed),
                    figure=check_figure(raw.get("figure")))
    return data.model_dump()


def shuffle_choices(question: str, choices: list[str]) -> list[str]:
    """문제 글로 정한 고정 seed로 섞는다(같은 문제는 같은 순서)."""
    seed = int(hashlib.sha256(question.encode("utf-8")).hexdigest()[:8], 16)
    out = list(choices)
    random.Random(seed).shuffle(out)
    return out


def _prompt(kind: str, name: str, pages: list[dict], others: str) -> str:
    return prompts.fill("essay" if kind == ESSAY else "mcq", CONCEPT_NAME=name,
                        OTHER_CONCEPTS=others, PAGES=prompts.pages_text(pages))


def _one(kind: str, name: str, pages: list[dict], others: str, usage: Usage | None, fix: bool) -> dict:
    text = _prompt(kind, name, pages, others) + (FIX_NOTE if fix else "")
    raw = ask_json(text, max_tokens=config.AI_MAX_TOKENS, usage=usage)
    allowed = [p["n"] for p in pages]
    return clean_essay(raw, allowed) if kind == ESSAY else clean_mcq(raw, allowed)


def _with_fix(kind: str, name: str, pages: list[dict], others: str, usage: Usage | None) -> dict:
    """문제가 페이지·그림을 가리키면 '## 다시 만들기'를 붙여 한 번 더. 객관식이 또 걸리면 BadQuestion."""
    q = _one(kind, name, pages, others, usage, fix=False)
    if not points_away(q["question"], bool(q.get("figure"))):
        return q
    q2 = _one(kind, name, pages, others, usage, fix=True)
    if points_away(q2["question"], bool(q2.get("figure"))) and kind == MCQ:
        raise BadQuestion("객관식이 두 번 다 그림·페이지를 가리킴")
    return q2


def make_question(name: str, kind: str, pages: list[dict], others: str, usage: Usage | None = None) -> dict:
    """개념 하나의 문제. 2번까지 시도. 객관식 형식이 틀리면 같은 개념의 서술형으로 대신 낸다."""
    last: Exception | None = None
    for _ in range(2):
        try:
            if kind == MCQ:
                try:
                    return _with_fix(MCQ, name, pages, others, usage)
                except BadQuestion:
                    return _with_fix(ESSAY, name, pages, others, usage)
            return _with_fix(ESSAY, name, pages, others, usage)
        except KeyMissingError:
            raise
        except (LLMError, BadQuestion) as exc:
            last = exc
    if isinstance(last, LLMError):
        raise last
    raise BadJsonError(f"문제 형식 오류: {last}")


# --- 채점 ---
def status_of(score: int) -> str:
    if score >= 8:
        return "앎"
    if score >= 4:
        return "헷갈림"
    return "모름"


def is_answered(q: dict, answer: str | None = None, dont_know: bool = False, mcq_choice=None) -> bool:
    """객관식은 보기(0~3) 또는 '모르겠어요'(-1), 서술형은 공백 아닌 답 또는 '모르겠어요' 체크."""
    if q["kind"] == MCQ:
        return isinstance(mcq_choice, int) and not isinstance(mcq_choice, bool) and -1 <= mcq_choice <= 3
    return bool(dont_know) or bool((answer or "").strip())


def blank_grading(reason: str) -> dict:
    return {"score": 0, "max": 10, "status": "모름", "error_type": "무응답", "reason": reason,
            "rubric_scores": None}


def grade_mcq(q: dict, choice, guessed: bool) -> dict:
    """객관식은 코드가 채점(AI 호출 없음)."""
    if choice is None or not isinstance(choice, int) or isinstance(choice, bool) or not -1 <= choice <= 3:
        return blank_grading(REASON_NO_CHOICE)
    if choice == -1:
        return blank_grading(REASON_DONT_KNOW)
    if choice == q["answer_index"]:
        if guessed:
            return {"score": 5, "max": 10, "status": "헷갈림", "error_type": "찍어서 맞힘",
                    "reason": "정답을 골랐지만 확신 없이 골라 헷갈림으로 표시했어요.", "rubric_scores": None}
        return {"score": 10, "max": 10, "status": "앎", "error_type": None,
                "reason": "정답을 확신하고 골랐어요.", "rubric_scores": None}
    return {"score": 0, "max": 10, "status": "모름", "error_type": "오답",
            "reason": f"고른 보기가 정답이 아니에요. 정답: {q['answer']}", "rubric_scores": None}


def clean_grading(raw: dict, rubric: list[dict]) -> dict:
    """부분 점수·null·글자를 정수로 바꾸고 항목 배점으로 자른다. 상태는 코드가 점수로 정한다."""
    scores = raw.get("rubric_scores")
    clean_rs = None
    if isinstance(scores, list):
        clean_rs = []
        for i, item in enumerate(rubric):
            v = _to_int(scores[i]) if i < len(scores) else 0
            clean_rs.append(min(max(v, 0), item["score"]))
    if raw.get("score") is None and clean_rs is not None:
        score = sum(clean_rs)
    else:
        score = _to_int(raw.get("score"))
    score = min(max(score, 0), 10)
    et = raw.get("error_type")
    if not isinstance(et, str) or et.strip().lower() in ("", "null", "none"):
        et = None
    reason = raw.get("reason")
    return {"score": score, "max": 10, "status": status_of(score), "error_type": et,
            "reason": reason.strip() if isinstance(reason, str) else "", "rubric_scores": clean_rs}


def grade_essay(name: str, q: dict, answer: str, pages: list[dict], usage: Usage | None = None) -> dict:
    """서술형 하나를 AI(03-B)로 채점. 빈 답은 코드가 0점 모름(안전장치)."""
    if not (answer or "").strip():
        return blank_grading(REASON_EMPTY)
    qjson = {"question": q["question"], "answer": q.get("answer", ""), "rubric": q.get("rubric", []),
             "figure": figure_text(q.get("figure"))}
    text = prompts.fill("grade", CONCEPT_NAME=name, QUESTION_JSON=json.dumps(qjson, ensure_ascii=False),
                        PAGES=prompts.pages_text(pages), ANSWER=answer.strip())
    raw = ask_json(text, max_tokens=config.AI_MAX_TOKENS, usage=usage)
    return clean_grading(raw, q.get("rubric", []))


# --- 샘플 체험용 예시 답 (F11) ---
def first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return parts[0] if parts and parts[0] else (text or "").strip()


def example_answers(questions: dict) -> dict:
    """문제 순서대로 돌려 가며 예시 답을 만든다. 앎·헷갈림·모름과 헷갈린 점이 모두 나오게."""
    out = {}
    n_essay = n_mcq = 0
    for cid, q in questions.items():
        a = {"answer": "", "dont_know": False, "mcq_choice": None, "guessed": False, "confusion": ""}
        if q["kind"] == ESSAY:
            step = n_essay % 3
            n_essay += 1
            if step == 0:
                a["answer"] = q.get("answer", "") or "잘 모르겠다."
            elif step == 1:
                a["answer"] = first_sentence(q.get("answer", "")) or "잘 모르겠다."
            else:
                a["dont_know"] = True
        else:
            step = n_mcq % 3
            n_mcq += 1
            if step == 0:
                a["mcq_choice"] = q["answer_index"]
            elif step == 1:
                a["mcq_choice"] = q["answer_index"]
                a["guessed"] = True
                a["confusion"] = EXAMPLE_CONFUSION
            else:
                a["mcq_choice"] = (q["answer_index"] + 1) % 4
        out[cid] = a
    return out
