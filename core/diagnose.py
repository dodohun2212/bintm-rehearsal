"""F08 진단: 대상·문제 형식 고르기, 문제 만들기(03-A 서술형, 03-C 객관식), 채점(코드·03-B), 예시 답(F11)."""
from __future__ import annotations

import hashlib
import json
import random
import re

import config
from core import prompts
from core.figure import figure_text, refers_to_page_or_figure, validate
from core.llm import LLMError, Usage, ask_json

ESSAY = "서술형"
MCQ = "객관식"
MODES = ("섞어서", "모두 객관식", "모두 서술형")
DONT_KNOW = -1

# 문제 글이 페이지·그림을 가리킬 때 덧붙이는 단락 (BR-10 예외 2)
FIX_NOTE = (
    "\n\n## 다시 만들기\n"
    "앞서 만든 문제 글이 페이지 번호(p.n, n쪽)나 학생이 볼 수 없는 그림·트리·표를 가리켰습니다. "
    "학생은 강의자료 없이 이 문제 화면만 봅니다. 문제 글에 페이지 번호를 쓰지 말고, 트리·배열·표가 필요하면 "
    "`figure`에 데이터로 넣은 뒤 문제 글에서는 \"아래 트리\"처럼 가리키세요.\n"
)

EXAMPLE_CONFUSION = "두 보기 사이에서 고민했어요. 둘이 어떻게 다른지 모르겠어요."

REASON_DONT_KNOW = "'모르겠어요'를 골라 모름으로 표시했어요."
REASON_BLANK = "답을 비워 두어 모름으로 표시했어요."
REASON_NO_CHOICE = "보기를 고르지 않아 모름으로 표시했어요."


class QuestionError(LLMError):
    code = "E-08"
    user_message = "AI 답을 읽지 못했어요. 다시 시도해 주세요"


# ---------- 대상과 형식 ----------

def diag_targets(scores: list[dict], top: int | None = None, min_pct: int = config.DIAG_MIN_PCT) -> list[str]:
    """출제 점수 min_pct 이상 개념 전부(순위 순서). top을 주면 그중 상위 top개."""
    ids = [r["concept_id"] for r in scores if r["pct"] >= min_pct]
    return ids[:top] if top else ids


def choose_kind(pct: int, mode: str = "섞어서") -> str:
    if mode == "모두 객관식":
        return MCQ
    if mode == "모두 서술형":
        return ESSAY
    return ESSAY if pct >= config.ESSAY_MIN_PCT else MCQ


def evidence_pages(concept: dict, material: dict, meta: list[int], limit: int = config.MAX_EVIDENCE_PAGES) -> list[dict]:
    """그 개념의 쪽 텍스트만(RAG). 본문 쪽부터, 최대 limit쪽."""
    pages = [p for p in concept.get("pages", []) if 1 <= p <= material["n_pages"]]
    m = set(meta)
    chosen = ([p for p in pages if p not in m] + [p for p in pages if p in m])[:limit]
    return [material["pages"][p - 1] for p in sorted(chosen)]


def other_concepts_text(names: list[str], self_name: str) -> str:
    others = [n for n in names if n != self_name]
    return "\n".join(f"- {n}" for n in others) if others else "(없음)"


# ---------- 문제 검사 ----------

_NUM_PREFIX = re.compile(r"^\s*(?:[①②③④⑤]|\(?[1-5A-Ea-e][\.\)]|[1-5]\s*번[\.\)]?)\s*")


def strip_number(choice: str) -> str:
    return _NUM_PREFIX.sub("", str(choice)).strip()


def _seed(text: str) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


def shuffle_choices(question: str, choices: list[str], answer_index: int):
    """문제마다 고정된 seed로 섞는다. 정답 글이 따라간다."""
    order = list(range(len(choices)))
    random.Random(_seed(question)).shuffle(order)
    new = [choices[i] for i in order]
    return new, order.index(answer_index)


def _pages_ok(value, page_nums) -> list[int]:
    from core.schemas import parse_pages
    allowed = set(page_nums)
    return [p for p in parse_pages(value) if p in allowed]


def clean_mcq(raw: dict, page_nums) -> dict | None:
    """보기 4개가 서로 다르고 정답 위치 0~3인지. 아니면 None(서술형으로 대신)."""
    if not isinstance(raw, dict):
        return None
    q = str(raw.get("question") or "").strip()
    choices = raw.get("choices")
    ai = raw.get("answer_index")
    if not q or not isinstance(choices, list) or len(choices) != 4:
        return None
    choices = [strip_number(c) for c in choices]
    if any(not c for c in choices) or len(set(choices)) != 4:
        return None
    if isinstance(ai, bool) or not isinstance(ai, (int, float)) or not float(ai).is_integer():
        return None
    ai = int(ai)
    if not 0 <= ai <= 3:
        return None
    new, idx = shuffle_choices(q, choices, ai)
    return {
        "kind": MCQ,
        "question": q,
        "choices": new,
        "answer_index": idx,
        "answer": new[idx],
        "explanation": str(raw.get("explanation") or "").strip(),
        "rubric": [],
        "source_pages": _pages_ok(raw.get("source_pages"), page_nums),
        "figure": validate(raw.get("figure")),
    }


def normalize_rubric(items) -> list[dict]:
    """루브릭 합을 10으로 맞춘다(비례)."""
    rub = []
    if isinstance(items, list):
        for it in items:
            if not isinstance(it, dict):
                continue
            point = str(it.get("point") or "").strip()
            try:
                s = float(it.get("score"))
            except (TypeError, ValueError):
                continue
            if point and s > 0:
                rub.append({"point": point, "score": s})
    if not rub:
        return [{"point": "모범 답안의 핵심 내용", "score": 10}]
    total = sum(r["score"] for r in rub)
    scaled = [max(1, int(round(r["score"] * 10 / total))) for r in rub]
    diff = 10 - sum(scaled)
    big = scaled.index(max(scaled))
    scaled[big] = max(1, scaled[big] + diff)
    for r, s in zip(rub, scaled):
        r["score"] = s
    return rub


def clean_essay(raw: dict, page_nums) -> dict | None:
    if not isinstance(raw, dict):
        return None
    q = str(raw.get("question") or "").strip()
    if not q:
        return None
    return {
        "kind": ESSAY,
        "question": q,
        "answer": str(raw.get("answer") or "").strip(),
        "rubric": normalize_rubric(raw.get("rubric")),
        "choices": [],
        "answer_index": None,
        "explanation": "",
        "source_pages": _pages_ok(raw.get("source_pages"), page_nums),
        "figure": validate(raw.get("figure")),
    }


# ---------- 문제 만들기 ----------

def _prompt(kind: str, concept: dict, pages: list[dict], other_names: list[str]) -> str:
    return prompts.fill(
        "essay" if kind == ESSAY else "mcq",
        CONCEPT_NAME=concept["name"],
        OTHER_CONCEPTS=other_concepts_text(other_names, concept["name"]),
        PAGES=prompts.pages_block(pages),
    )


def _try_mcq(concept, pages, other_names, usage) -> dict | None:
    nums = [p["n"] for p in pages]
    base = _prompt(MCQ, concept, pages, other_names)
    for attempt in range(2):
        raw = ask_json(base + (FIX_NOTE if attempt else ""), max_tokens=config.AI_MAX_TOKENS, usage=usage)
        q = clean_mcq(raw, nums)
        if q is None:
            return None  # 형식이 틀리면 서술형으로 대신
        if not refers_to_page_or_figure(q["question"], q["figure"] is not None):
            return q
    return None  # 두 번 다 그림·페이지를 가리킴 → 서술형으로


def _try_essay(concept, pages, other_names, usage) -> dict:
    nums = [p["n"] for p in pages]
    base = _prompt(ESSAY, concept, pages, other_names)
    last = None
    for attempt in range(2):
        need_fix = last is not None and refers_to_page_or_figure(last["question"], last["figure"] is not None)
        raw = ask_json(base + (FIX_NOTE if need_fix else ""), max_tokens=config.AI_MAX_TOKENS, usage=usage)
        q = clean_essay(raw, nums)
        if q is None:
            continue
        last = q
        if not refers_to_page_or_figure(q["question"], q["figure"] is not None):
            return q
    if last is not None:
        return last
    raise QuestionError("서술형 문제 형식이 두 번 다 틀림")


def make_question(concept: dict, kind: str, pages: list[dict], other_names: list[str],
                  usage: Usage | None = None) -> dict:
    """개념 하나의 문제. 객관식이 안 되면 서술형으로 대신 낸다."""
    q = None
    if kind == MCQ:
        q = _try_mcq(concept, pages, other_names, usage)
    if q is None:
        q = _try_essay(concept, pages, other_names, usage)
    q["concept_id"] = concept["id"]
    q["name"] = concept["name"]
    q["requested_kind"] = kind
    return q


# ---------- 채점 ----------

def status_from_score(score: int) -> str:
    if score >= 8:
        return "앎"
    if score >= 4:
        return "헷갈림"
    return "모름"


def _to_int(v) -> int | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return int(round(f))


def clean_grading(raw: dict, rubric: list[dict]) -> dict:
    """부분 점수·null·글자도 받아 정수로 바꾸고 배점으로 자른다. 상태는 코드가 점수로 정한다."""
    if not isinstance(raw, dict):
        raise QuestionError("채점 응답이 객체가 아님")
    maxes = [int(r["score"]) for r in rubric] or [10]
    rs_raw = raw.get("rubric_scores")
    rs_raw = rs_raw if isinstance(rs_raw, list) else []
    rs = []
    for i, m in enumerate(maxes):
        v = _to_int(rs_raw[i]) if i < len(rs_raw) else None
        rs.append(max(0, min(v if v is not None else 0, m)))
    score = _to_int(raw.get("score"))
    if score is None:
        score = sum(rs)
    score = max(0, min(score, 10))
    et = raw.get("error_type")
    et = None if et is None or str(et).strip() in ("", "null", "None") else str(et).strip()
    reason = raw.get("reason")
    return {
        "kind": ESSAY,
        "score": score,
        "max": 10,
        "status": status_from_score(score),
        "error_type": et,
        "reason": "" if reason is None else str(reason),
        "rubric_scores": rs,
    }


def zero_grading(kind: str, reason: str, error_type: str = "무응답") -> dict:
    return {"kind": kind, "score": 0, "max": 10, "status": "모름", "error_type": error_type,
            "reason": reason, "rubric_scores": []}


def grade_mcq(q: dict, choice, guessed: bool) -> dict:
    """객관식은 코드가 채점(AI 호출 없음)."""
    if choice is None or isinstance(choice, bool):
        return zero_grading(MCQ, REASON_NO_CHOICE)
    if choice == DONT_KNOW:
        return zero_grading(MCQ, REASON_DONT_KNOW)
    if choice == q["answer_index"]:
        if guessed:
            return {"kind": MCQ, "score": 5, "max": 10, "status": "헷갈림", "error_type": "찍어서 맞힘",
                    "reason": "정답을 골랐지만 확신 없이 골랐어요.", "rubric_scores": []}
        return {"kind": MCQ, "score": 10, "max": 10, "status": "앎", "error_type": None,
                "reason": "정답을 확신하고 골랐어요.", "rubric_scores": []}
    return {"kind": MCQ, "score": 0, "max": 10, "status": "모름", "error_type": "오답",
            "reason": f"고른 보기는 정답이 아니에요. 정답은 {q['answer_index'] + 1}번이에요.", "rubric_scores": []}


def is_answered(q: dict, answer: str | None, dont_know: bool, choice) -> bool:
    if q["kind"] == MCQ:
        if choice is None or isinstance(choice, bool) or not isinstance(choice, int):
            return False
        return choice == DONT_KNOW or 0 <= choice < len(q["choices"])
    return bool(dont_know) or bool((answer or "").strip())


def local_grading(q: dict, answer: str | None, dont_know: bool, choice, guessed: bool) -> dict | None:
    """AI 없이 정해지는 채점. 서술형에 답이 있으면 None(AI 채점 필요)."""
    if q["kind"] == MCQ:
        return grade_mcq(q, choice, guessed)
    if dont_know:
        return zero_grading(ESSAY, REASON_DONT_KNOW)
    if not (answer or "").strip():
        return zero_grading(ESSAY, REASON_BLANK)
    return None


def safe_text(text: str, limit: int | None = None) -> str:
    """학생이 쓴 글: 공백을 한 칸으로, 꺾쇠를 바꿔 태그를 닫지 못하게."""
    t = " ".join((text or "").split())
    if limit:
        t = t[:limit]
    return t.replace("<", "‹").replace(">", "›")


def clean_confusion(text: str | None) -> str:
    return safe_text(text or "", config.CONFUSION_MAX_CHARS)


def grade_essay(q: dict, answer: str, pages: list[dict], usage: Usage | None = None) -> dict:
    """서술형 답을 AI(03-B)로 채점."""
    qjson = {"question": q["question"], "answer": q["answer"], "rubric": q["rubric"]}
    if q.get("figure"):
        qjson["figure"] = figure_text(q["figure"])
    prompt = prompts.fill(
        "grade",
        CONCEPT_NAME=q.get("name", ""),
        QUESTION_JSON=json.dumps(qjson, ensure_ascii=False, indent=1),
        PAGES=prompts.pages_block(pages),
        ANSWER=(answer or "").replace("<", "‹").replace(">", "›"),
    )
    raw = ask_json(prompt, max_tokens=config.AI_MAX_TOKENS, usage=usage)
    return clean_grading(raw, q["rubric"])


# ---------- 샘플 체험용 예시 답 (F11) ----------

def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=다\.)\s+|(?<=[.!?])\s+", (text or "").strip())
    return parts[0].strip() if parts and parts[0].strip() else (text or "").strip()


def example_answers(questions: list[tuple[str, dict]]) -> dict:
    """문제 순서대로 돌려 가며 답을 만든다. 앎·헷갈림·모름과 헷갈린 점이 모두 나오게."""
    out = {}
    ie = im = 0
    for cid, q in questions:
        if q["kind"] == ESSAY:
            k = ie % 3
            ie += 1
            if k == 0:
                out[cid] = {"answer": q["answer"], "dont_know": False}
            elif k == 1:
                out[cid] = {"answer": _first_sentence(q["answer"]), "dont_know": False}
            else:
                out[cid] = {"answer": "", "dont_know": True}
        else:
            k = im % 3
            im += 1
            a = q["answer_index"]
            if k == 0:
                out[cid] = {"choice": a, "guessed": False, "confusion": ""}
            elif k == 1:
                out[cid] = {"choice": a, "guessed": True, "confusion": EXAMPLE_CONFUSION}
            else:
                out[cid] = {"choice": (a + 1) % len(q["choices"]), "guessed": False, "confusion": ""}
    return out
