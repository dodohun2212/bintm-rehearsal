"""F08 진단 대상·문제 형식 고르기, 문제 만들기(서술형 03-A·객관식 03-C), 채점(03-B·코드), 예시 답."""
from __future__ import annotations

import hashlib
import json
import random
import re

import config
from core import llm, prompts
from core.cites import strip_bad_cites
from core.figure import figure_text, points_outside, validate_figure
from core.html import choice_is, choice_obj
from core.schemas import RubricItem, keep_pages

MODES = ("섞어서", "모두 객관식", "모두 서술형")
ESSAY, MCQ = "서술형", "객관식"
ERROR_TYPES = ("개념 혼동", "비교 방향 오류", "복잡도 오류", "절차 누락", "계산 실수", "무응답", "기타")
EXAMPLE_CONFUSION = "두 보기 사이에서 고민했어요. 둘이 어떻게 다른지 모르겠어요."

# BR-10 예외 2: 문제가 페이지·그림을 가리킬 때 덧붙이는 한 단락
FIX_NOTE = ("\n\n## 다시 만들기\n앞에서 만든 문제 글이 학생이 볼 수 없는 페이지 번호(p.n, n쪽, 슬라이드)나 "
            "figure에 없는 그림·트리·표를 가리켰습니다. 학생은 강의자료를 펴지 않고 문제 화면만 봅니다. "
            "페이지 번호를 쓰지 말고, 트리·배열·표가 필요하면 figure에 데이터를 넣어 문제를 다시 만드세요.")

REASON_DONT_KNOW = "'모르겠어요'를 골라 모름으로 표시했어요."
REASON_EMPTY = "답을 비워 두어 모름으로 표시했어요."
REASON_NO_CHOICE = "보기를 고르지 않아 모름으로 표시했어요."


# ---------- 진단 대상과 문제 형식 ----------

def diag_targets(score_rows: list[dict], top: int | None = None, min_pct: int = config.DIAG_MIN_PCT) -> list[str]:
    """출제 점수 min_pct 이상 개념 전부(순위 순서). top이면 그중 상위 top개."""
    ids = [r["concept_id"] for r in score_rows if r["pct"] >= min_pct]
    return ids[:top] if top else ids


def quick_default(n_targets: int, from_sample: bool) -> bool:
    """빠른 진단 기본값: 직접 올린 자료이고 대상이 QUICK_DIAG_AUTO_OVER개보다 많을 때만 켠다."""
    return (not from_sample) and n_targets > config.QUICK_DIAG_AUTO_OVER


def question_kind(pct: int, mode: str) -> str:
    if mode == "모두 객관식":
        return MCQ
    if mode == "모두 서술형":
        return ESSAY
    return ESSAY if pct >= config.ESSAY_MIN_PCT else MCQ


def other_concepts_text(names: list[str], self_name: str) -> str:
    others = [n for n in names if n != self_name]
    return "\n".join(f"- {n}" for n in others) if others else "(없음)"


def evidence_pages(concept: dict, meta_pages, limit: int = config.MAX_EVIDENCE_PAGES) -> list[int]:
    """근거 쪽: 본문 쪽을 먼저, 메타 쪽은 뒤에. 최대 limit쪽."""
    meta = set(meta_pages or [])
    pages = concept.get("pages") or []
    body = [p for p in pages if p not in meta]
    rest = [p for p in pages if p in meta]
    return sorted((body + rest)[:limit])


def clean_text(s: str | None, max_chars: int | None = None) -> str:
    """공백을 한 칸으로, 꺾쇠를 ‹ ›로(태그를 닫지 못하게), 필요하면 자른다."""
    t = re.sub(r"\s+", " ", s or "").strip().replace("<", "‹").replace(">", "›")
    return t[:max_chars] if max_chars else t


# ---------- 문제 검사 ----------

def normalize_rubric(items) -> list[dict] | None:
    if not isinstance(items, list):
        return None
    rub = []
    for it in items:
        if not isinstance(it, dict) or not str(it.get("point", "")).strip():
            continue
        r = RubricItem.model_validate({"point": str(it["point"]).strip(), "score": it.get("score", 0)})
        rub.append(r.model_dump())
    if not rub:
        return None
    total = sum(r["score"] for r in rub)
    if total != 10:
        if total <= 0:
            base = [10 // len(rub)] * len(rub)
        else:
            base = [int(r["score"] * 10 / total) for r in rub]
        rem = 10 - sum(base)
        order = sorted(range(len(rub)), key=lambda i: -rub[i]["score"])
        for k in range(rem):
            base[order[k % len(rub)]] += 1
        for r, s in zip(rub, base):
            r["score"] = s
    return rub


def validate_essay(raw, allowed) -> dict | None:
    if not isinstance(raw, dict):
        return None
    q = str(raw.get("question") or "").strip()
    a = str(raw.get("answer") or "").strip()
    rub = normalize_rubric(raw.get("rubric"))
    if not q or not a or not rub:
        return None
    src = keep_pages(raw.get("source_pages"), allowed) or sorted(allowed)[:2]
    return {"kind": ESSAY, "question": q, "answer": a, "rubric": rub, "choices": None, "answer_index": None,
            "explanation": None, "source_pages": src, "figure": validate_figure(raw.get("figure"))}


_NUM_PREFIX = re.compile(r"^\s*(?:[①②③④⑤]|\(?[1-5A-Ea-e]\)|[1-5A-E]\.|[1-5]번)\s*")


def strip_choice_number(s: str) -> str:
    return _NUM_PREFIX.sub("", str(s or "")).strip()


def validate_mcq(raw, allowed) -> dict | None:
    """보기 4개가 서로 다르고 정답 위치가 0~3인지. 보기 앞 번호는 지운다."""
    if not isinstance(raw, dict):
        return None
    q = str(raw.get("question") or "").strip()
    choices = raw.get("choices")
    if not q or not isinstance(choices, list) or len(choices) != 4:
        return None
    choices = [strip_choice_number(c) for c in choices]
    if any(not c for c in choices) or len(set(choices)) != 4:
        return None
    idx = raw.get("answer_index")
    if isinstance(idx, bool):
        return None
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return None
    if not 0 <= idx <= 3:
        return None
    allowed = set(allowed)
    return {"kind": MCQ, "question": q, "choices": choices, "answer_index": idx, "answer": choices[idx],
            "rubric": None, "explanation": strip_bad_cites(str(raw.get("explanation") or ""), allowed),
            "source_pages": keep_pages(raw.get("source_pages"), allowed) or sorted(allowed)[:2],
            "figure": validate_figure(raw.get("figure"))}


def shuffle_choices(q: dict, seed_key: str) -> dict:
    """문제마다 고정된 seed로 보기를 섞는다. 정답 글이 따라간다."""
    seed = int(hashlib.sha256((seed_key + q["question"]).encode("utf-8")).hexdigest()[:12], 16)
    order = list(range(4))
    random.Random(seed).shuffle(order)
    q = dict(q)
    old = q["choices"]
    q["choices"] = [old[i] for i in order]
    q["answer_index"] = order.index(q["answer_index"])
    q["answer"] = q["choices"][q["answer_index"]]
    return q


# ---------- 문제 만들기 ----------

def _fill_question(kind: str, name: str, pages_text: str, others: str) -> str:
    key = "essay" if kind == ESSAY else "mcq"
    return prompts.fill(key, CONCEPT_NAME=name, PAGES=pages_text, OTHER_CONCEPTS=others)


def _make_essay(name, pages_text, allowed, others, usage):
    prompt = _fill_question(ESSAY, name, pages_text, others)
    q = validate_essay(llm.ask_json(prompt, max_tokens=config.AI_MAX_TOKENS, usage=usage), allowed)
    if q is None or points_outside(q["question"], q["figure"]):
        q2 = validate_essay(llm.ask_json(prompt + FIX_NOTE, max_tokens=config.AI_MAX_TOKENS, usage=usage), allowed)
        if q2 is not None:
            q = q2
    if q is None:
        raise llm.BadJSONError("서술형 문제 형식이 맞지 않음")
    return q


def _make_mcq(name, pages_text, allowed, others, usage):
    prompt = _fill_question(MCQ, name, pages_text, others)
    q = validate_mcq(llm.ask_json(prompt, max_tokens=config.AI_MAX_TOKENS, usage=usage), allowed)
    if q is not None and not points_outside(q["question"], q["figure"]):
        return q
    q = validate_mcq(llm.ask_json(prompt + FIX_NOTE, max_tokens=config.AI_MAX_TOKENS, usage=usage), allowed)
    if q is not None and not points_outside(q["question"], q["figure"]):
        return q
    return None


def make_question(concept: dict, kind: str, pages_text: str, allowed, others: str,
                  usage: llm.Usage | None = None) -> dict:
    """개념 하나의 진단 문제. 객관식이 형식에 안 맞거나 답을 못 읽으면 같은 개념의 서술형으로 대신 낸다."""
    allowed = list(allowed)
    if kind == MCQ:
        try:
            q = _make_mcq(concept["name"], pages_text, allowed, others, usage)
        except llm.BadJSONError:
            q = None
        if q is not None:
            q = shuffle_choices(q, concept["id"] + concept["name"])
            q["concept_id"] = concept["id"]
            q["requested_kind"] = MCQ
            return q
    q = _make_essay(concept["name"], pages_text, allowed, others, usage)
    q["concept_id"] = concept["id"]
    q["requested_kind"] = kind
    return q


# ---------- 답했는지, 채점 ----------

def is_answered(q: dict, answer: str | None = None, dont_know: bool = False, mcq_choice: int | None = None) -> bool:
    if q.get("kind") == MCQ:
        if mcq_choice is None or isinstance(mcq_choice, bool):
            return False
        return mcq_choice == -1 or 0 <= int(mcq_choice) < len(q.get("choices") or [])
    return bool(dont_know) or bool((answer or "").strip())


def status_from_score(score: int, error_type: str | None = None) -> str:
    """8 이상 앎, 4~7 헷갈림, 3 이하 모름. '개념 혼동'은 4~7점이어도 모름."""
    if score >= 8:
        return "앎"
    if score >= 4:
        return "모름" if error_type == "개념 혼동" else "헷갈림"
    return "모름"


def _grading(score, status, error_type, reason, source_pages, rubric_scores=None, **extra) -> dict:
    d = {"score": int(score), "max": 10, "status": status, "error_type": error_type, "reason": reason,
         "rubric_scores": rubric_scores, "source_pages": list(source_pages or [])}
    d.update(extra)
    return d


def grade_blank(q: dict, why: str) -> dict:
    """AI 없이 0점 모름. why: 'dont_know' / 'empty' / 'no_choice'."""
    reason = {"dont_know": REASON_DONT_KNOW, "empty": REASON_EMPTY, "no_choice": REASON_NO_CHOICE}[why]
    return _grading(0, "모름", "무응답", reason, q.get("source_pages"), by_code=True)


def grade_mcq(q: dict, choice: int | None, guessed: bool = False) -> dict:
    """객관식은 코드가 채점(AI 호출 없음)."""
    if choice is None or isinstance(choice, bool) or not (choice == -1 or 0 <= choice < 4):
        return grade_blank(q, "no_choice")
    if choice == -1:
        return grade_blank(q, "dont_know")
    right = q["answer_index"]
    if choice == right:
        if guessed:
            return _grading(5, "헷갈림", "찍어서 맞힘",
                            f"정답 {choice_obj(right)} 골랐지만 확신 없이 골라 헷갈림으로 표시했어요.",
                            q.get("source_pages"), by_code=True)
        return _grading(10, "앎", None, f"정답 {choice_obj(right)} 확신하고 골랐어요.", q.get("source_pages"),
                        by_code=True)
    return _grading(0, "모름", "오답", f"{choice_obj(choice)} 골랐지만 정답은 {choice_is(right)}.",
                    q.get("source_pages"), by_code=True)


def _to_int(v) -> int:
    try:
        if isinstance(v, bool):
            return 0
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def normalize_grading(raw: dict, q: dict, allowed) -> dict:
    """AI 채점 정리: 부분 점수·null·글자도 정수로, 항목 배점으로 자르고, 총점은 항목 합(수가 다르면 AI 총점)."""
    raw = raw if isinstance(raw, dict) else {}
    rub = q.get("rubric") or []
    items = raw.get("rubric_scores")
    if isinstance(items, list) and len(items) == len(rub) and rub:
        rs = [max(0, min(_to_int(v), int(r["score"]))) for v, r in zip(items, rub)]
        total = sum(rs)
    else:
        rs = None
        total = max(0, min(10, _to_int(raw.get("score"))))
    et = raw.get("error_type")
    if et is None or str(et).strip().lower() in ("", "null", "none"):
        et = None
    elif et not in ERROR_TYPES:
        et = "기타"
    reason = raw.get("reason")
    reason = "" if reason is None else strip_bad_cites(str(reason), allowed)
    return _grading(total, status_from_score(total, et), et, reason, q.get("source_pages"), rubric_scores=rs)


def question_json_for_grading(q: dict) -> str:
    d = {"question": q["question"], "answer": q["answer"], "rubric": q.get("rubric") or []}
    ft = figure_text(q.get("figure"))
    if ft:
        d["figure"] = ft
    return json.dumps(d, ensure_ascii=False)


def grade_essay(concept_name: str, q: dict, answer: str, dont_know: bool, pages_text: str, allowed,
                usage: llm.Usage | None = None) -> dict:
    if dont_know:
        return grade_blank(q, "dont_know")
    if not (answer or "").strip():
        return grade_blank(q, "empty")
    prompt = prompts.fill("grade", CONCEPT_NAME=concept_name, QUESTION_JSON=question_json_for_grading(q),
                          PAGES=pages_text, ANSWER=clean_text(answer))
    raw = llm.ask_json(prompt, max_tokens=config.AI_MAX_TOKENS, usage=usage)
    return normalize_grading(raw, q, allowed)


# ---------- 샘플 체험용 예시 답 (F11) ----------

def _first_sentence(text: str) -> str:
    m = re.match(r"\s*(.+?[다요]\.)(\s|$)", text or "")
    return m.group(1) if m else (text or "").strip()


def example_answers(questions: dict, order: list[str]) -> dict:
    """서술형끼리 차례로: 모범 답안 전체 → 첫 문장만 → '모르겠어요'.
    객관식끼리 차례로: (정답, 확신) → (정답, 찍음, 헷갈린 점) → (정답 다음 보기, 확신)."""
    out = {}
    e = m = 0
    for cid in order:
        q = questions.get(cid)
        if not q:
            continue
        if q["kind"] == MCQ:
            k = m % 3
            m += 1
            right = q["answer_index"]
            if k == 0:
                out[cid] = {"mcq_choice": right, "guessed": False, "confusion": ""}
            elif k == 1:
                out[cid] = {"mcq_choice": right, "guessed": True, "confusion": EXAMPLE_CONFUSION}
            else:
                out[cid] = {"mcq_choice": (right + 1) % 4, "guessed": False, "confusion": ""}
        else:
            k = e % 3
            e += 1
            if k == 0:
                out[cid] = {"answer": q["answer"], "dont_know": False}
            elif k == 1:
                out[cid] = {"answer": _first_sentence(q["answer"]), "dont_know": False}
            else:
                out[cid] = {"answer": "", "dont_know": True}
    return out
