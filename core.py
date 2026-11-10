"""빈틈노트 핵심 로직: 텍스트 추출, 마스킹, AI 호출, 점수, 채점, 우선순위, 내보내기.

streamlit을 import하지 않는다. 점수·순위·이해 상태는 모두 여기서 코드로 계산한다.
"""
from __future__ import annotations

import io
import json
import random
import re

from prompts import CONCEPTS, EXPLAIN, MCQ, UTTERANCES, fill

MODEL = "claude-sonnet-5-5"  # 모델 교체는 이 줄만
MAX_PAGES = 60
MCQ_PAGE_LIMIT = 15
EXPLAIN_PAGE_LIMIT = 12
MAX_TARGETS = 6
MIN_DIAG_SCORE = 20

UTTER_TYPES = ["emphasis", "exam_hint", "mistake", "exercise_point", "defer", "skip"]
EMPHASIS_TYPES = {"emphasis", "exam_hint", "mistake", "exercise_point"}
UTTER_LABELS = {
    "emphasis": "강조",
    "exam_hint": "시험 암시",
    "mistake": "실수 경고",
    "exercise_point": "연습문제 지목",
    "defer": "다음에 다룸",
    "skip": "가볍게 넘어감",
}
# 발화 점수: 강도 비례(가중치 × 강도/3), defer·skip은 고정 감점
UTTER_WEIGHTS = {"emphasis": 1.0, "exam_hint": 1.5, "mistake": 0.7, "exercise_point": 1.0}
UTTER_PENALTY = {"defer": -2.5, "skip": -1.0}

KNOW, CONFUSED, UNKNOWN, NOT_DIAG = "앎", "헷갈림", "모름", "진단 안 함"
UNDERSTANDING = {KNOW: 1.0, CONFUSED: 0.5, UNKNOWN: 0.0, NOT_DIAG: 0.5}
DONT_KNOW = -1  # "모르겠어요" 선택값

NOW, NEXT, REVIEW = "지금 당장", "다음", "복습만"


class AppError(Exception):
    """화면에 한국어 한 줄로 보여줄 오류. detail은 '자세한 오류'에."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


class LLMError(AppError):
    pass


class InputError(AppError):
    pass


# ---------- 1. 텍스트 추출 ----------

_PAGE_MARK = re.compile(r"^=== p\.(\d+) ===\s*$", re.M)


def split_marked_pages(text: str) -> list[dict]:
    """샘플 md: '=== p.N ===' 줄로 쪽을 나눈다."""
    parts = _PAGE_MARK.split(text)
    pages = []
    for i in range(1, len(parts) - 1, 2):
        pages.append({"page": int(parts[i]), "text": parts[i + 1].strip()})
    return pages[:MAX_PAGES]


def extract_pdf(data: bytes) -> list[dict]:
    import pymupdf  # 필요할 때만 불러옴

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:
        raise InputError("PDF 파일을 열 수 없어요.", repr(e)) from e
    pages = []
    for i, page in enumerate(doc):
        if i >= MAX_PAGES:
            break
        pages.append({"page": i + 1, "text": page.get_text().strip()})
    total = sum(len(p["text"]) for p in pages)
    if not pages or total / len(pages) < 20:
        raise InputError("글자가 그림으로 들어 있는 PDF는 읽을 수 없어요.")
    return pages


def _shape_texts(shape, out: list[str]) -> None:
    """도형 안의 글을 모두 모은다 (그룹·표 포함)."""
    if getattr(shape, "shapes", None) is not None and shape.shape_type == 6:  # 그룹
        for s in shape.shapes:
            _shape_texts(s, out)
        return
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        out.append(shape.text_frame.text)
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            out.append(" | ".join(cell.text for cell in row.cells))


def extract_pptx(data: bytes) -> list[dict]:
    from pptx import Presentation

    try:
        prs = Presentation(io.BytesIO(data))
    except Exception as e:
        raise InputError("PPTX 파일을 열 수 없어요.", repr(e)) from e
    pages = []
    for i, slide in enumerate(prs.slides):
        if i >= MAX_PAGES:
            break
        texts: list[str] = []
        for shape in slide.shapes:
            _shape_texts(shape, texts)
        pages.append({"page": i + 1, "text": "\n".join(t for t in texts if t.strip()).strip()})
    if not any(p["text"] for p in pages):
        raise InputError("자료에서 글자를 찾지 못했어요.")
    return pages


def extract_file(name: str, data: bytes) -> list[dict]:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return extract_pdf(data)
    if lower.endswith(".pptx"):
        return extract_pptx(data)
    if lower.endswith(".md") or lower.endswith(".txt"):
        return split_marked_pages(data.decode("utf-8"))
    raise InputError("PDF나 PPTX 파일만 올릴 수 있어요.")


# ---------- 2. 마스킹 ----------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"01[016789]-?\d{3,4}-?\d{4}")
_STUDENT_ID = re.compile(r"(?<!\d)\d{8,10}(?!\d)")


def mask(text: str) -> str:
    """이메일 → 전화번호 → 학번 순서로 [가림] 처리."""
    text = _EMAIL.sub("[가림]", text)
    text = _PHONE.sub("[가림]", text)
    return _STUDENT_ID.sub("[가림]", text)


def mask_pages(pages: list[dict]) -> list[dict]:
    return [{"page": p["page"], "text": mask(p["text"])} for p in pages]


# ---------- 3. AI 호출 래퍼 ----------


def _parse_json(text: str):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def ask_json(prompt: str, max_tokens: int = 4000) -> dict:
    """AI를 불러 JSON(dict)을 받는다. 호출은 최대 3번."""
    try:
        import anthropic
    except Exception as e:  # 라이브러리 로드 실패
        raise LLMError("AI 라이브러리를 불러오지 못했어요.", repr(e)) from e
    try:
        client = anthropic.Anthropic(timeout=180.0)
    except Exception as e:
        raise LLMError("ANTHROPIC_API_KEY가 설정되지 않았어요. README의 실행 방법을 봐 주세요.", repr(e)) from e

    def call(p: str, mt: int) -> tuple[str, str]:
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=mt, messages=[{"role": "user", "content": p}]
            )
        except anthropic.AuthenticationError as e:
            raise LLMError("API 키가 맞지 않아요.", repr(e)) from e
        except Exception as e:  # 네트워크, 속도 제한, 서버 오류 등
            raise LLMError("AI 호출에 실패했어요. 잠시 뒤 다시 시도해 주세요.", repr(e)) from e
        text = "".join(b.text for b in resp.content if b.type == "text")
        return text, resp.stop_reason

    text, stop = call(prompt, max_tokens)
    if stop == "max_tokens":  # 잘렸으면 두 배로 한 번만
        max_tokens *= 2
        text, stop = call(prompt, max_tokens)
    data = _parse_json(text)
    if data is None:  # JSON이 안 읽히면 한 번만 다시
        text, stop = call(prompt + "\n\nJSON만 다시 출력하세요", max_tokens)
        data = _parse_json(text)
    if data is None:
        raise LLMError("AI 응답 형식이 맞지 않아요. 다시 시도해 주세요.", f"stop_reason={stop}\n{text[:800]}")
    return data


# ---------- 4. 형식 검사 도우미 ----------


def _int_list(value, allowed: set[int] | None = None) -> list[int]:
    out: list[int] = []
    if not isinstance(value, list):
        return out
    for v in value:
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if (allowed is None or n in allowed) and n not in out:
            out.append(n)
    return out


def format_pages(pages: list[dict]) -> str:
    return "\n\n".join(f"[p.{p['page']}]\n{p['text']}" for p in pages)


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


_CITE = re.compile(r"\s?\(p\.\s*(\d+)\)")


def clean_citations(text: str, allowed: list[int] | set[int]) -> str:
    """(p.n) 중 실제로 보낸 쪽이 아닌 번호는 지운다."""
    allowed = set(allowed)
    return _CITE.sub(lambda m: m.group(0) if int(m.group(1)) in allowed else "", text)


def pick_pages(concepts: list[dict], limit: int) -> list[int]:
    """개념마다 쪽을 하나씩 번갈아 넣는다. 중복 제외, 상한에서 멈춤."""
    lists = [c.get("ordered_pages") or c.get("pages", []) for c in concepts]
    out: list[int] = []
    depth = 0
    while len(out) < limit and any(depth < len(lst) for lst in lists):
        for lst in lists:
            if depth < len(lst) and lst[depth] not in out:
                out.append(lst[depth])
                if len(out) >= limit:
                    break
        depth += 1
    return out


def pages_subset(pages: list[dict], wanted: list[int]) -> list[dict]:
    want = set(wanted)
    return [p for p in pages if p["page"] in want]


# ---------- 5. AI 호출 1: 개념 ----------


def clean_concepts(data: dict, valid_pages: set[int]) -> dict:
    concepts, seen = [], set()
    for c in data.get("concepts", []) if isinstance(data.get("concepts"), list) else []:
        if not isinstance(c, dict):
            continue
        cid, name = str(c.get("id", "")).strip(), str(c.get("name", "")).strip()
        if not cid or not name or cid in seen:
            continue  # 형식이 틀린 항목만 버림
        seen.add(cid)
        concepts.append(
            {
                "id": cid,
                "name": name,
                "pages": sorted(_int_list(c.get("pages"), valid_pages)),
                "in_objectives": c.get("in_objectives") is True,
                "has_example": c.get("has_example") is True,
                "in_exercise": c.get("in_exercise") is True,
                "summary": str(c.get("summary", "")),
            }
        )
    if not concepts:
        raise LLMError("자료에서 개념을 찾지 못했어요. 다른 자료로 해 보세요.", json.dumps(data, ensure_ascii=False)[:800])
    return {"concepts": concepts[:15], "meta_pages": sorted(_int_list(data.get("meta_pages"), valid_pages))}


def run_concepts(pages: list[dict]) -> dict:
    prompt = fill(CONCEPTS, pages=format_pages(pages))
    return clean_concepts(ask_json(prompt), {p["page"] for p in pages})


# ---------- 6. AI 호출 2: 교수님 발화 ----------


def clean_utterances(data: dict, concept_ids: set[str], transcript: str) -> list[dict]:
    """대본에 실제로 있는 인용만, 올바른 개념·종류만 남긴다."""
    plain = _squash(transcript)
    out = []
    items = data.get("utterances", []) if isinstance(data, dict) else []
    for u in items if isinstance(items, list) else []:
        if not isinstance(u, dict):
            continue
        quote = str(u.get("quote", "")).strip()
        if not quote or _squash(quote) not in plain:
            continue
        if u.get("concept_id") not in concept_ids or u.get("type") not in UTTER_TYPES:
            continue
        try:
            strength = int(u.get("strength", 2))
        except (TypeError, ValueError):
            strength = 2
        out.append(
            {"concept_id": u["concept_id"], "type": u["type"], "quote": quote, "strength": min(3, max(1, strength))}
        )
    return out


def run_utterances(concepts: list[dict], transcript: str) -> list[dict]:
    if not transcript.strip():
        return []
    lines = "\n".join(f"{c['id']}: {c['name']}" for c in concepts)
    prompt = fill(UTTERANCES, concepts=lines, transcript=transcript)
    return clean_utterances(ask_json(prompt), {c["id"] for c in concepts}, transcript)


# ---------- 7. 출제 가능성 점수 ----------


def score_concepts(concepts: list[dict], utterances: list[dict], meta_pages: list[int]) -> list[dict]:
    """규칙 기반 점수. 최고점을 100으로 맞춘 0~100 정수."""
    meta = set(meta_pages)
    scored = []
    for idx, c in enumerate(concepts):
        reasons: list[tuple[str, float]] = []
        body = [p for p in c["pages"] if p not in meta]
        if c.get("in_objectives"):
            reasons.append(("학습목표", 3.0))
        if body:
            reasons.append((f"본문 {len(body)}쪽", min(4.0, 1.0 * len(body))))
        if c.get("has_example"):
            reasons.append(("예제·그림", 1.5))
        if c.get("in_exercise"):
            reasons.append(("연습문제", 2.0))
        mine = [u for u in utterances if u["concept_id"] == c["id"]]
        for u in mine:
            t = u["type"]
            pts = UTTER_WEIGHTS[t] * u["strength"] / 3 if t in UTTER_WEIGHTS else UTTER_PENALTY[t]
            reasons.append((f"{UTTER_LABELS[t]} (강도 {u['strength']})", round(pts, 2)))
        raw = max(0.0, sum(p for _, p in reasons))
        scored.append(
            {
                **c,
                "body_pages": body,
                "ordered_pages": body + [p for p in c["pages"] if p not in body],
                "utterances": mine,
                "reasons": reasons,
                "raw": raw,
                "emphasis_count": sum(1 for u in mine if u["type"] in EMPHASIS_TYPES),
                "deferred": any(u["type"] in ("defer", "skip") for u in mine),
                "_order": idx,
            }
        )
    top = max((s["raw"] for s in scored), default=0.0)
    for s in scored:
        s["score"] = round(s["raw"] / top * 100) if top > 0 else 0
    scored.sort(key=lambda s: (-s["score"], min(s["pages"]) if s["pages"] else 10**6, s["_order"]))
    return scored


def pick_targets(scored: list[dict]) -> list[dict]:
    """출제 점수 20점 이상 중 상위 최대 6개."""
    return [s for s in scored if s["score"] >= MIN_DIAG_SCORE][:MAX_TARGETS]


# ---------- 8. AI 호출 3: 객관식 ----------


_NUM_PREFIX = re.compile(r"^\s*(?:[①②③④]|\(?[1-4A-Da-d][.)])\s*")


def shuffle_question(q: dict, seed: str) -> dict | None:
    """보기 4개를 고정 시드로 섞고 정답 위치를 다시 계산. 형식이 틀리면 None."""
    choices = q.get("choices")
    if not isinstance(choices, list) or len(choices) != 4:
        return None
    choices = [_NUM_PREFIX.sub("", str(c)).strip() for c in choices]
    if any(not c for c in choices) or len(set(choices)) != 4:
        return None
    try:
        ans = int(q.get("answer_index"))
    except (TypeError, ValueError):
        return None
    if ans not in (0, 1, 2, 3) or not str(q.get("question", "")).strip():
        return None
    order = list(range(4))
    random.Random(seed).shuffle(order)
    return {
        **q,
        "question": str(q["question"]).strip(),
        "choices": [choices[i] for i in order],
        "answer_index": order.index(ans),
    }


def clean_questions(data: dict, targets: list[dict], sent_pages: list[int]) -> list[dict]:
    """대상 개념 순서대로, 형식이 맞는 문제만 남긴다 (개념당 1개)."""
    by_id: dict[str, dict] = {}
    items = data.get("questions", []) if isinstance(data, dict) else []
    for q in items if isinstance(items, list) else []:
        if isinstance(q, dict) and q.get("concept_id") not in by_id:
            by_id[q.get("concept_id")] = q
    out = []
    for t in targets:
        raw = by_id.get(t["id"])
        if raw is None:
            continue
        q = shuffle_question(raw, seed=t["id"])
        if q is None:
            continue
        q["concept_id"] = t["id"]
        q["concept_name"] = t["name"]
        q["score"] = t["score"]
        q["explanation"] = clean_citations(str(q.get("explanation", "")), sent_pages)
        q["source_pages"] = _int_list(q.get("source_pages"), set(sent_pages))
        out.append(q)
    return out


def run_mcq(targets: list[dict], pages: list[dict]) -> list[dict]:
    if not targets:
        return []
    sent = sorted(pick_pages(targets, MCQ_PAGE_LIMIT))
    lines = "\n".join(
        f"{t['id']}: {t['name']} (쪽: {', '.join(map(str, t['pages']))})" for t in targets
    )
    prompt = fill(MCQ, targets=lines, pages=format_pages(pages_subset(pages, sent)))
    return clean_questions(ask_json(prompt, max_tokens=8000), targets, sent)


# ---------- 9. 채점과 우선순위 ----------


def grade(question: dict, answer: dict | None) -> str | None:
    """답 하나를 상태로. 답하지 않았으면 None."""
    if not answer or answer.get("choice") is None:
        return None
    choice = answer["choice"]
    if choice == DONT_KNOW:
        return UNKNOWN
    if choice == question["answer_index"]:
        return CONFUSED if answer.get("guessed") else KNOW
    return UNKNOWN


def unanswered(questions: list[dict], answers: dict) -> list[int]:
    """답하지 않은 문제 번호 (1부터)."""
    return [i + 1 for i in range(len(questions)) if grade(questions[i], answers.get(i)) is None]


def example_answers(questions: list[dict]) -> dict[int, dict]:
    """샘플 체험용 예시 답: 확신 정답 → 찍은 정답 → 오답 → 모르겠어요 순서로 반복."""
    out = {}
    for i, q in enumerate(questions):
        ans = q["answer_index"]
        kind = i % 4
        if kind == 0:
            out[i] = {"choice": ans, "guessed": False}
        elif kind == 1:
            out[i] = {"choice": ans, "guessed": True}
        elif kind == 2:
            out[i] = {"choice": (ans + 1) % 4, "guessed": False}
        else:
            out[i] = {"choice": DONT_KNOW, "guessed": False}
    return out


def diagnose(questions: list[dict], answers: dict) -> dict[str, str]:
    """개념 id → 상태."""
    return {q["concept_id"]: grade(q, answers.get(i)) or UNKNOWN for i, q in enumerate(questions)}


def priority_of(score: float, state: str) -> tuple[float, str]:
    pr = round(score * (1 - UNDERSTANDING[state]), 1)
    bucket = NOW if pr >= 50 else NEXT if pr >= 20 else REVIEW
    return pr, bucket


def build_plan(scored: list[dict], states: dict[str, str]) -> list[dict]:
    """우선순위 = 출제 점수 × (1 − 이해도). 내림차순."""
    plan = []
    for s in scored:
        state = states.get(s["id"], NOT_DIAG)
        pr, bucket = priority_of(s["score"], state)
        plan.append({"concept": s, "state": state, "priority": pr, "bucket": bucket})
    plan.sort(key=lambda x: (-x["priority"], -x["concept"]["score"]))
    return plan


# ---------- 10. AI 호출 4: 보완 설명 ----------


def choice_text(q: dict | None, choice) -> str:
    if q is None or choice is None:
        return "없음"
    if choice == DONT_KNOW:
        return "모르겠어요"
    return q["choices"][choice]


def clean_explanations(data: dict, ids: set[str], sent_pages: list[int]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    items = data.get("explanations", []) if isinstance(data, dict) else []
    for e in items if isinstance(items, list) else []:
        if not isinstance(e, dict) or e.get("concept_id") not in ids or e["concept_id"] in out:
            continue
        core = clean_citations(str(e.get("core", "")).strip(), sent_pages)
        if not core:
            continue
        out[e["concept_id"]] = {
            "core": core,
            "missed": str(e.get("missed", "")).strip(),
            "review_pages": _int_list(e.get("review_pages"), set(sent_pages)),
        }
    return out


def run_explain(items: list[dict], questions: list[dict], answers: dict, pages: list[dict]) -> dict[str, dict]:
    """items: build_plan의 항목들. 개념 여러 개를 한 번에 설명한다."""
    if not items:
        return {}
    q_by_id = {q["concept_id"]: (i, q) for i, q in enumerate(questions)}
    lines = []
    for it in items:
        c = it["concept"]
        i, q = q_by_id.get(c["id"], (None, None))
        ans = answers.get(i) if i is not None else None
        lines.append(
            f"{c['id']}: {c['name']} | 상태: {it['state']} | 문제: {q['question'] if q else '없음'}"
            f" | 고른 답: {choice_text(q, ans.get('choice') if ans else None)}"
            f" | 정답: {choice_text(q, q['answer_index']) if q else '없음'}"
        )
    sent = sorted(pick_pages([it["concept"] for it in items], EXPLAIN_PAGE_LIMIT))
    prompt = fill(EXPLAIN, items="\n".join(lines), pages=format_pages(pages_subset(pages, sent)))
    result = clean_explanations(ask_json(prompt, max_tokens=8000), {it["concept"]["id"] for it in items}, sent)
    if not result:
        raise LLMError("보완 설명을 만들지 못했어요. 다시 시도해 주세요.")
    return result


def auto_explain_targets(plan: list[dict], n: int = 3) -> list[dict]:
    """우선순위 상위 n개 (0 초과만)."""
    return [it for it in plan if it["priority"] > 0][:n]


# ---------- 11. 마크다운 내보내기 ----------

DISCLAIMER = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다."


def to_markdown(source: str, plan: list[dict], questions: list[dict], answers: dict, explanations: dict) -> str:
    q_by_id = {q["concept_id"]: (i, q) for i, q in enumerate(questions)}
    lines = ["# 빈틈노트 결과", "", f"- 자료: {source}", "", "## 공부 순서", ""]
    lines += ["| 순위 | 개념 | 상태 | 출제 점수 | 우선순위 | 묶음 |", "|---|---|---|---|---|---|"]
    for n, it in enumerate(plan, 1):
        c = it["concept"]
        lines.append(f"| {n} | {c['name']} | {it['state']} | {c['score']} | {it['priority']} | {it['bucket']} |")
    lines += ["", "## 개념별 진단 결과와 보완 설명", ""]
    for n, it in enumerate(plan, 1):
        c = it["concept"]
        lines.append(f"### {n}. {c['name']} ({it['bucket']})")
        lines.append(f"- 상태: {it['state']} / 출제 점수 {c['score']} / 우선순위 {it['priority']}")
        i, q = q_by_id.get(c["id"], (None, None))
        if q:
            ans = answers.get(i) or {}
            lines.append(f"- 문제: {q['question']}")
            lines.append(f"- 고른 답: {choice_text(q, ans.get('choice'))} / 정답: {choice_text(q, q['answer_index'])}")
            if q.get("explanation"):
                lines.append(f"- 해설: {q['explanation']}")
        e = explanations.get(c["id"])
        if e:
            lines.append(f"- 핵심 설명: {e['core']}")
            if e.get("missed"):
                lines.append(f"- 내가 놓친 점: {e['missed']}")
            if e.get("review_pages"):
                lines.append("- 다시 볼 쪽: " + ", ".join(f"p.{p}" for p in e["review_pages"]))
        lines.append("")
    lines += ["---", DISCLAIMER, ""]
    return "\n".join(lines)
