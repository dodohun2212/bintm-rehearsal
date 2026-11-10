# F09 보완 설명 (AI 호출 4) + 페이지 검사, 헷갈린 점 다듬기, "내가 놓친 점" 바로잡기
import json
import re
from concurrent.futures import ThreadPoolExecutor

import config
from core import prompts
from core.diagnose import CHOICE_MARKS, MCQ, evidence_pages, question_for_ai
from core.extract import pages_text
from core.llm import Usage, ask_json
from core.schemas import Explanation

WORKERS = 8


def clean_confusion(text) -> str:
    """공백을 한 칸으로, 300자로 자르고, 꺾쇠를 바꿔 태그를 닫지 못하게 한다."""
    if not text:
        return ""
    s = re.sub(r"\s+", " ", str(text)).strip()
    s = s[:config.CONFUSION_MAX_CHARS]
    return s.replace("<", "‹").replace(">", "›")


def diagnosis_json(concept: dict, pct: int, status: str, q: dict | None, g: dict | None,
                   answer: str = "", choice=None, guessed: bool = False) -> dict:
    d = {"concept": concept["name"], "exam_score": pct, "status": status}
    if q is None or g is None:
        d["note"] = "이 개념은 진단 문제를 내지 않았다."
        return d
    d.update(question_for_ai(q))
    if q["kind"] == MCQ:
        if choice is None:
            mine = "(고르지 않음)"
        elif choice == -1:
            mine = "모르겠어요"
        else:
            mine = f"{CHOICE_MARKS[choice]} {q['choices'][choice]}"
        d["student_answer"] = mine + (" (확신 없이 고름)" if guessed and choice not in (None, -1) else "")
        d["correct_answer"] = f"{CHOICE_MARKS[q['answer_index']]} {q['answer']}"
    else:
        d["student_answer"] = answer or ""
        d["correct_answer"] = q.get("answer", "")
    d["score"] = g.get("score")
    d["error_type"] = g.get("error_type")
    d["reason"] = g.get("reason", "")
    return d


def fix_gap(my_gap: str, status: str, reason: str) -> str:
    """진단한 개념에 '아직 확인하지 않은 개념'이나 빈 값이 오면 채점 이유에 맞는 말로 바꾼다."""
    gap = (my_gap or "").strip()
    if status == "진단 안 함":
        return gap or "아직 확인하지 않은 개념이다."
    if gap and "아직 확인하지 않은" not in gap:
        return gap
    reason = reason or ""
    if "모르겠어요" in reason:
        return "'모르겠어요'를 골라 이 문제가 물은 내용을 아직 답하지 못했다."
    if "비워" in reason or "고르지 않아" in reason:
        return "답을 하지 않아 이 문제가 물은 내용을 아직 확인하지 못했다."
    if status == "헷갈림":
        return "정답에 가까웠지만 확신이 없거나 일부가 빠졌다."
    if status == "앎":
        return "진단 문제는 맞혔다. 시험 전에 한 번 더 확인한다."
    return "진단 문제에서 틀린 부분이 있다. " + reason if reason else "진단 문제에서 틀린 부분이 있다."


def parse_explanation(raw: dict, concept_id: str, page_nums: list[int], confusion: str,
                      status: str, reason: str) -> dict:
    from core.concepts import parse_pages
    raw = raw if isinstance(raw, dict) else {}
    ok = set(page_nums)
    src = [p for p in parse_pages(raw.get("source_pages")) if p in ok]
    chk = [p for p in parse_pages(raw.get("check_pages")) if p in ok][:4]
    reply = raw.get("confusion_reply")
    reply = str(reply).strip() if (confusion and reply and str(reply).strip() not in ("null", "None")) else None
    note = raw.get("not_found_note")
    return Explanation(
        concept_id=concept_id,
        my_gap=fix_gap(str(raw.get("my_gap") or ""), status, reason),
        explanation=str(raw.get("explanation") or "").strip(),
        check_pages=chk or src[:2] or page_nums[:2],
        source_pages=src,
        not_found=bool(raw.get("not_found")),
        not_found_note=str(note) if note and str(note) not in ("null", "None") else None,
        confusion_reply=reply,
    ).model_dump()


def build_prompt(concept_name: str, diag: dict, confusion: str, pages_txt: str) -> str:
    return prompts.fill("04", CONCEPT_NAME=concept_name,
                        DIAGNOSIS_JSON=json.dumps(diag, ensure_ascii=False),
                        CONFUSION=confusion or "(없음)", PAGES=pages_txt)


def explain(job: dict, material: dict, meta: list[int], usage: Usage | None = None) -> dict:
    """job: {concept, pct, status, q, g, answer, choice, guessed, confusion}"""
    c = job["concept"]
    page_nums = evidence_pages(c, meta)
    confusion = clean_confusion(job.get("confusion"))
    diag = diagnosis_json(c, job["pct"], job["status"], job.get("q"), job.get("g"),
                          job.get("answer", ""), job.get("choice"), bool(job.get("guessed")))
    raw = ask_json(build_prompt(c["name"], diag, confusion, pages_text(material, page_nums)),
                   max_tokens=config.AI_MAX_TOKENS, usage=usage)
    reason = (job.get("g") or {}).get("reason", "")
    return parse_explanation(raw, c["id"], page_nums, confusion, job["status"], reason)


def auto_targets(priorities: list[dict], confusion: dict) -> list[str]:
    """'지금 당장' 전부 + 상위 3개 + 헷갈린 점을 적은 개념."""
    ids = [p["concept_id"] for p in priorities if p["action"] == "지금 당장"]
    for p in priorities[:config.AUTO_EXPLAIN_TOP]:
        if p["concept_id"] not in ids:
            ids.append(p["concept_id"])
    for cid, text in confusion.items():
        if clean_confusion(text) and cid not in ids:
            ids.append(cid)
    return ids


def run_parallel(fn, jobs: dict, workers: int = WORKERS):
    """jobs: {key: job}. fn(job, usage) → 결과. (results, failed_keys, usage, first_error)"""
    usage, results, failed, first_err = Usage(), {}, [], None

    def work(job):
        u = Usage()
        try:
            return fn(job, u), u, None
        except Exception as e:
            return None, u, e

    if not jobs:
        return results, failed, usage, None
    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = dict(zip(jobs.keys(), ex.map(work, jobs.values())))
    for k, (r, u, err) in res.items():
        usage.merge(u)
        if r is None:
            failed.append(k)
            first_err = first_err or err
        else:
            results[k] = r
    return results, failed, usage, first_err
