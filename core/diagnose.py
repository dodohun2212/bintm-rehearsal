# F08 진단 대상·문제 형식, 문제 만들기(서술형 03-A, 객관식 03-C), 채점(객관식 코드, 서술형 03-B), 예시 답(F11)
import hashlib
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor

import config
from core import prompts
from core.extract import pages_text
from core.figure import figure_text, refers_elsewhere, validate_figure
from core.llm import LLMError, NoKeyError, Usage, ask_json
from core.schemas import Grading, Question

ESSAY, MCQ = "서술형", "객관식"
Q_MODES = ["섞어서", "모두 객관식", "모두 서술형"]
CHOICE_MARKS = ["①", "②", "③", "④"]
WORKERS = 6

# BR-10 예외 2: 문제가 페이지·그림을 가리킬 때 덧붙이는 한 단락
FIX_NOTE = ("\n\n## 다시 만들기\n지난 답의 문제 글이 페이지 번호(p.n, n쪽, 슬라이드)나 보이지 않는 그림·트리·표를 "
            "가리켰습니다. 학생은 이 문제 화면만 봅니다. 페이지를 가리키지 말고, 그림이 필요하면 `figure`에 "
            "데이터를 넣고 문제 글에서는 \"아래 트리\"처럼 가리키세요.")

EXAMPLE_CONFUSION = "두 보기 사이에서 고민했어요. 둘이 어떻게 다른지 모르겠어요."

REASON_DONT_KNOW = "'모르겠어요'를 골라 모름으로 표시했어요."
REASON_EMPTY = "답을 비워 두어 모름으로 표시했어요."
REASON_NO_CHOICE = "보기를 고르지 않아 모름으로 표시했어요."


class QuestionError(LLMError):
    code = "E-08"


# ---- 진단 대상과 문제 형식 ----
def diag_targets(scores: list[dict], top: int | None = None) -> list[str]:
    """출제 점수 20점 이상 전부(순위 순서). top이 있으면 그중 상위 top개."""
    ids = [s["concept_id"] for s in scores if s["pct"] >= config.DIAG_MIN_PCT]
    return ids[:top] if top else ids


def choose_kind(pct: int, q_mode: str) -> str:
    if q_mode == "모두 객관식":
        return MCQ
    if q_mode == "모두 서술형":
        return ESSAY
    return ESSAY if pct >= config.ESSAY_MIN_PCT else MCQ


def other_concepts_text(names: list[str], self_name: str) -> str:
    rest = [n for n in names if n != self_name]
    return "\n".join(f"- {n}" for n in rest) if rest else "(없음)"


def evidence_pages(concept: dict, meta: list[int], limit: int = config.MAX_EVIDENCE_PAGES) -> list[int]:
    """본문 쪽 먼저, 그다음 메타 쪽. 최대 8쪽."""
    pages = concept.get("pages", [])
    body = [p for p in pages if p not in set(meta)]
    rest = [p for p in pages if p in set(meta)]
    out = (body + rest)[:limit]
    return out


def build_prompt(kind: str, concept_name: str, pages_txt: str, others: str) -> str:
    key = "03A" if kind == ESSAY else "03C"
    return prompts.fill(key, CONCEPT_NAME=concept_name, PAGES=pages_txt, OTHER_CONCEPTS=others)


# ---- 응답 검사 ----
def _to_int(v) -> int:
    try:
        if isinstance(v, bool):
            return int(v)
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def _pages_in(value, allowed: list[int]) -> list[int]:
    from core.concepts import parse_pages
    ok = set(allowed)
    return [p for p in parse_pages(value) if p in ok]


def normalize_rubric(rubric) -> list[dict]:
    items = []
    for r in rubric if isinstance(rubric, list) else []:
        if isinstance(r, dict) and str(r.get("point") or "").strip():
            items.append({"point": str(r["point"]).strip(), "score": max(0, _to_int(r.get("score")))})
    if not items:
        return []
    total = sum(r["score"] for r in items)
    if total <= 0:
        base = 10 // len(items)
        for r in items:
            r["score"] = base
        items[0]["score"] += 10 - base * len(items)
    elif total != 10:
        for r in items:
            r["score"] = int(round(r["score"] * 10 / total))
        diff = 10 - sum(r["score"] for r in items)
        biggest = max(items, key=lambda r: r["score"])
        biggest["score"] += diff
    return items


def validate_essay(raw: dict, page_nums: list[int]) -> dict | None:
    if not isinstance(raw, dict):
        return None
    q, a = str(raw.get("question") or "").strip(), str(raw.get("answer") or "").strip()
    rubric = normalize_rubric(raw.get("rubric"))
    if len(q) < 5 or not a or not rubric:
        return None
    try:
        return Question(kind=ESSAY, question=q, answer=a, rubric=rubric,
                        source_pages=_pages_in(raw.get("source_pages"), page_nums),
                        figure=validate_figure(raw.get("figure"))).model_dump()
    except Exception:
        return None


_NUM_PREFIX = re.compile(r"^\s*(?:[①②③④⑤]|\(?[1-5A-Ea-e][.)]|[1-5]\s*번[.)]?)\s*")


def validate_mcq(raw: dict, page_nums: list[int]) -> dict | None:
    if not isinstance(raw, dict):
        return None
    q = str(raw.get("question") or "").strip()
    choices = raw.get("choices")
    if len(q) < 5 or not isinstance(choices, list) or len(choices) != 4:
        return None
    cleaned = [_NUM_PREFIX.sub("", str(c or "")).strip() for c in choices]
    if any(not c for c in cleaned) or len(set(cleaned)) != 4:
        return None
    idx = raw.get("answer_index")
    if isinstance(idx, bool) or not isinstance(idx, (int, float)) or int(idx) != idx or not (0 <= int(idx) <= 3):
        return None
    idx = int(idx)
    try:
        return Question(kind=MCQ, question=q, answer=cleaned[idx], choices=cleaned, answer_index=idx,
                        explanation=str(raw.get("explanation") or "").strip(),
                        source_pages=_pages_in(raw.get("source_pages"), page_nums),
                        figure=validate_figure(raw.get("figure"))).model_dump()
    except Exception:
        return None


def shuffle_mcq(q: dict) -> dict:
    """문제마다 고정된 seed로 보기를 섞는다. 정답 글이 따라간다."""
    seed = int(hashlib.sha256(q["question"].encode("utf-8")).hexdigest()[:8], 16)
    order = list(range(4))
    random.Random(seed).shuffle(order)
    out = dict(q)
    out["choices"] = [q["choices"][i] for i in order]
    out["answer_index"] = order.index(q["answer_index"])
    out["answer"] = out["choices"][out["answer_index"]]
    return out


# ---- 문제 만들기 ----
def _attempt(kind, name, pages_txt, others, page_nums, usage, fix=False):
    prompt = build_prompt(kind, name, pages_txt, others) + (FIX_NOTE if fix else "")
    raw = ask_json(prompt, max_tokens=config.AI_MAX_TOKENS, usage=usage)
    return validate_mcq(raw, page_nums) if kind == MCQ else validate_essay(raw, page_nums)


def make_question(concept: dict, kind: str, material: dict, meta: list[int], others: str,
                  usage: Usage | None = None) -> dict:
    """개념 하나의 문제. 객관식이 형식 오류거나 두 번 다 그림을 가리키면 서술형으로 대신 낸다."""
    page_nums = evidence_pages(concept, meta)
    pages_txt = pages_text(material, page_nums)
    name = concept["name"]
    last_err = None
    if kind == MCQ:
        try:
            q = _attempt(MCQ, name, pages_txt, others, page_nums, usage)
            if q and refers_elsewhere(q["question"], q["figure"]):
                q2 = _attempt(MCQ, name, pages_txt, others, page_nums, usage, fix=True)
                q = q2 if q2 and not refers_elsewhere(q2["question"], q2["figure"]) else None
            if q:
                return _finish(shuffle_mcq(q), concept)
        except NoKeyError:
            raise
        except LLMError as e:
            last_err = e
        kind = ESSAY  # 객관식 실패 → 서술형으로 대신
    fix = False
    for _ in range(2):
        try:
            q = _attempt(ESSAY, name, pages_txt, others, page_nums, usage, fix=fix)
        except NoKeyError:
            raise
        except LLMError as e:
            last_err, q = e, None
        if q and not refers_elsewhere(q["question"], q["figure"]):
            return _finish(q, concept)
        if q and fix:
            return _finish(q, concept)  # 두 번째도 가리키면 그대로 쓴다
        fix = bool(q)
    raise QuestionError(f"'{name}' 문제를 만들지 못함: {last_err}")


def _finish(q: dict, concept: dict) -> dict:
    q = dict(q)
    q["concept_id"] = concept["id"]
    q["concept_name"] = concept["name"]
    return q


def make_questions(targets: list[dict], material: dict, meta: list[int], q_mode: str,
                   cache=None, run_id: str | None = None, all_names: list[str] | None = None):
    """targets: [{concept, pct}]. (questions, failed_names, usage, first_error)를 돌려준다.
    all_names: 함께 진단하는 전체 개념 이름(없으면 targets의 이름).
    cache(ResultCache)를 주면 (run_id, 개념, 형식, 다른 개념) 키로 꺼내고 넣는다."""
    names = list(all_names) if all_names else [t["concept"]["name"] for t in targets]
    usage, questions, failed, first_err = Usage(), {}, [], None
    jobs = {}
    for t in targets:
        c = t["concept"]
        kind = choose_kind(t["pct"], q_mode)
        others = other_concepts_text(names, c["name"])
        key = (run_id, c["name"], kind, tuple(n for n in names if n != c["name"]))
        if cache is not None and run_id:
            hit = cache.get(key)
            if hit:
                questions[c["id"]] = hit
                continue
        jobs[c["id"]] = (c, kind, others, key)

    def work(job):
        c, kind, others, key = job
        u = Usage()
        try:
            return make_question(c, kind, material, meta, others, u), u, None
        except Exception as e:  # 개념마다 실패를 따로 잡는다
            return None, u, e

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = dict(zip(jobs.keys(), ex.map(work, jobs.values())))
    for cid, (q, u, err) in results.items():
        usage.merge(u)
        c, kind, others, key = jobs[cid]
        if q is None:
            failed.append(c["name"])
            first_err = first_err or err
            continue
        questions[cid] = q
        if cache is not None and run_id:
            cache.put(key, q)
    order = [t["concept"]["id"] for t in targets]
    questions = {cid: questions[cid] for cid in order if cid in questions}
    return questions, failed, usage, first_err


# ---- 채점 ----
def status_from_score(score: int) -> str:
    if score >= 8:
        return "앎"
    if score >= 4:
        return "헷갈림"
    return "모름"


def _no_answer(reason: str, rubric_len: int = 0) -> dict:
    return Grading(score=0, status="모름", error_type="무응답", reason=reason,
                   rubric_scores=[0] * rubric_len).model_dump()


def grade_mcq(q: dict, choice, guessed: bool) -> dict:
    if choice is None:
        return _no_answer(REASON_NO_CHOICE)
    if choice == -1:
        return _no_answer(REASON_DONT_KNOW)
    sp = q.get("source_pages", [])
    right = CHOICE_MARKS[q["answer_index"]]
    if choice == q["answer_index"]:
        if guessed:
            return Grading(score=5, status="헷갈림", error_type="찍어서 맞힘",
                           reason=f"정답({right})을 골랐지만 확신 없이 골랐어요.", source_pages=sp).model_dump()
        return Grading(score=10, status="앎", error_type=None,
                       reason=f"정답({right})을 확신하고 골랐어요.", source_pages=sp).model_dump()
    mine = CHOICE_MARKS[choice] if 0 <= choice < 4 else "?"
    return Grading(score=0, status="모름", error_type="오답",
                   reason=f"{mine}을 골랐어요. 정답은 {right}이에요.", source_pages=sp).model_dump()


def normalize_grading(raw: dict, rubric: list[dict], page_nums: list[int]) -> dict:
    """부분 점수·null·글자 점수를 정수로 바꾸고 항목 배점으로 자른다. 상태는 점수로 다시 정한다."""
    raw = raw if isinstance(raw, dict) else {}
    maxes = [r["score"] for r in rubric]
    given = raw.get("rubric_scores") if isinstance(raw.get("rubric_scores"), list) else []
    rs = []
    for i, m in enumerate(maxes):
        v = _to_int(given[i]) if i < len(given) else 0
        rs.append(min(max(0, v), m))
    if raw.get("score") is None or (isinstance(raw.get("score"), str) and not raw["score"].strip()):
        score = sum(rs)
    else:
        score = _to_int(raw.get("score"))
    score = min(10, max(0, score))
    et = raw.get("error_type")
    et = None if et in (None, "", "null", "None") else str(et)
    reason = raw.get("reason")
    reason = "" if reason is None else str(reason)
    return Grading(score=score, status=status_from_score(score), error_type=et, reason=reason,
                   rubric_scores=rs, source_pages=_pages_in(raw.get("source_pages"), page_nums)).model_dump()


def question_for_ai(q: dict) -> dict:
    """채점·설명에 넣는 문제 JSON. 그림은 글로 바꾼다."""
    out = {"kind": q["kind"], "question": q["question"], "answer": q.get("answer", "")}
    if q["kind"] == ESSAY:
        out["rubric"] = q.get("rubric", [])
    else:
        out["choices"] = [f"{CHOICE_MARKS[i]} {c}" for i, c in enumerate(q.get("choices", []))]
        out["explanation"] = q.get("explanation", "")
    out["figure"] = figure_text(q.get("figure"))
    return out


def grade_essay(q: dict, answer: str, dont_know: bool, material: dict, meta: list[int], concept: dict,
                usage: Usage | None = None) -> dict:
    n = len(q.get("rubric", []))
    if dont_know:
        return _no_answer(REASON_DONT_KNOW, n)
    if not (answer or "").strip():
        return _no_answer(REASON_EMPTY, n)
    page_nums = evidence_pages(concept, meta)
    prompt = prompts.fill("03B", CONCEPT_NAME=concept["name"],
                          QUESTION_JSON=json.dumps(question_for_ai(q), ensure_ascii=False),
                          PAGES=pages_text(material, page_nums), ANSWER=answer.strip())
    raw = ask_json(prompt, max_tokens=config.AI_MAX_TOKENS, usage=usage)
    return normalize_grading(raw, q.get("rubric", []), page_nums)


def grade_all(questions: dict, answers: dict, dont_know: dict, mcq_choice: dict, guessed: dict,
              material: dict, meta: list[int], concepts_by_id: dict, only: list[str] | None = None):
    """(grading, failed_ids, usage, first_error). 객관식은 코드, 서술형은 동시에 AI."""
    grading, failed, usage, first_err = {}, [], Usage(), None
    essay_jobs = []
    for cid, q in questions.items():
        if only is not None and cid not in only:
            continue
        if q["kind"] == MCQ:
            grading[cid] = grade_mcq(q, mcq_choice.get(cid), bool(guessed.get(cid)))
        else:
            essay_jobs.append(cid)

    def work(cid):
        u = Usage()
        try:
            g = grade_essay(questions[cid], answers.get(cid, ""), bool(dont_know.get(cid)), material, meta,
                            concepts_by_id[cid], u)
            return g, u, None
        except Exception as e:
            return None, u, e

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        res = dict(zip(essay_jobs, ex.map(work, essay_jobs)))
    for cid in essay_jobs:
        g, u, err = res[cid]
        usage.merge(u)
        if g is None:
            failed.append(cid)
            first_err = first_err or err
        else:
            grading[cid] = g
    return grading, failed, usage, first_err


def is_answered(q: dict, answer, dont_know, choice) -> bool:
    if q["kind"] == MCQ:
        if choice is None or isinstance(choice, bool) or not isinstance(choice, int):
            return False
        return choice == -1 or 0 <= choice < len(q.get("choices", []))
    return bool(dont_know) or bool((answer or "").strip())


def first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return parts[0] if parts else ""


def example_answers(questions: dict) -> dict:
    """샘플 체험용 예시 답. {concept_id: {answer, dont_know, choice, guessed, confusion}}"""
    out, ei, mi = {}, 0, 0
    for cid, q in questions.items():
        if q["kind"] == ESSAY:
            mode = ei % 3
            ei += 1
            if mode == 0:
                out[cid] = {"answer": q["answer"], "dont_know": False}
            elif mode == 1:
                out[cid] = {"answer": first_sentence(q["answer"]), "dont_know": False}
            else:
                out[cid] = {"answer": "", "dont_know": True}
        else:
            mode = mi % 3
            mi += 1
            right = q["answer_index"]
            if mode == 0:
                out[cid] = {"choice": right, "guessed": False, "confusion": ""}
            elif mode == 1:
                out[cid] = {"choice": right, "guessed": True, "confusion": EXAMPLE_CONFUSION}
            else:
                out[cid] = {"choice": (right + 1) % 4, "guessed": False, "confusion": ""}
    return out
