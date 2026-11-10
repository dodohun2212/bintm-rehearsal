"""BINTM_FAKE_AI=1일 때 실제 AI 대신 답한다(키 없이 화면 확인·테스트용).

호출 1·2는 tests/fixtures의 저장된 결과, 호출 3~5는 정해진 모양의 답을 돌려준다.
입력 칸은 프롬프트의 **마지막** <tag>…</tag>에서 읽는다(프롬프트 본문이 같은 태그 이름을 먼저 말한다).
"""
from __future__ import annotations

import copy
import json
import os
import re
from functools import lru_cache
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def enabled() -> bool:
    return os.environ.get("BINTM_FAKE_AI", "").strip() in ("1", "true", "True", "yes")


@lru_cache(maxsize=None)
def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def last_tag(prompt: str, tag: str) -> str:
    """마지막 <tag>…</tag> 안의 글."""
    start = prompt.rfind(f"<{tag}>")
    end = prompt.rfind(f"</{tag}>")
    if start < 0 or end < start:
        return ""
    return prompt[start + len(tag) + 2:end].strip()


def _concept_name(prompt: str) -> str:
    m = re.search(r'개념 "(.+?)"', prompt)
    return m.group(1) if m else "개념"


def _pages(prompt: str) -> list[int]:
    return [int(n) for n in re.findall(r"=== 페이지 (\d+) ===", last_tag(prompt, "pages"))]


def _first_sentence(text: str) -> str:
    m = re.match(r"(.+?다\.)", text.strip())
    return m.group(1) if m else text.strip()


def answer(prompt: str) -> dict:
    head = prompt.lstrip().splitlines()[0] if prompt.strip() else ""
    if "프롬프트 01" in head:
        return copy.deepcopy(_fixture("01_개념추출_결과.json"))
    if "프롬프트 02" in head:
        return copy.deepcopy(_fixture("02_강조발화_결과.json"))
    name = _concept_name(prompt)
    pages = _pages(prompt) or [1]
    p0 = pages[-1] if len(pages) > 1 else pages[0]
    if "프롬프트 03-A" in head:
        fig = None
        if "순회" in name:
            fig = {"kind": "tree", "nodes": ["+", "*", "-", "a", "b", "c", "d"], "caption": "수식 트리"}
        return {"question": f"{name}에서 핵심 과정이 어떻게 진행되는지 쓰고, 그렇게 하는 이유를 쓰시오."
                            + (" 아래 트리를 보고 답하시오." if fig else ""),
                "answer": f"{name}은 자료에 적힌 절차대로 한 단계씩 진행한다. 그렇게 해야 자료가 말한 조건을 지킬 수 있다.",
                "rubric": [{"point": "과정을 순서대로 씀", "score": 6}, {"point": "이유를 씀", "score": 4}],
                "source_pages": [p0], "figure": fig}
    if "프롬프트 03-C" in head:
        fig = None
        if "삽입" in name:
            fig = {"kind": "array", "items": ["90", "70", "80", "30"], "start": 1, "caption": "최대 힙 (인덱스 1부터)"}
        return {"question": f"{name}에 대한 설명으로 옳은 것은?" + (" 아래 배열을 보고 고르시오." if fig else ""),
                "choices": [f"{name}의 틀린 설명 A", f"{name}의 옳은 설명", f"{name}의 틀린 설명 B",
                            f"{name}의 틀린 설명 C"],
                "answer_index": 1,
                "explanation": f"자료는 {name}을 이렇게 설명한다(p.{p0}). 설명 A는 다른 개념의 절차다.",
                "source_pages": [p0], "figure": fig}
    if "프롬프트 03-B" in head:
        ans = re.sub(r"\s+", "", last_tag(prompt, "answer"))
        try:
            q = json.loads(last_tag(prompt, "question"))
            model = re.sub(r"\s+", "", q.get("answer", ""))
            n_items = len(q.get("rubric") or []) or 2
        except (ValueError, AttributeError):
            model, n_items = "", 2
        if model and model in ans:
            scores, err, reason = [6, 4], None, f"과정과 이유를 모두 맞게 썼다 (p.{p0})."
        elif model and len(ans) >= len(model) * 0.4:
            scores, err, reason = [4, 2], "절차 누락", f"과정은 맞지만 이유가 빠졌다 (p.{p0})."
        else:
            scores, err, reason = [1, 0], "개념 혼동", f"다른 개념의 절차와 바꿔 썼다 (p.{p0})."
        scores = (scores + [0] * n_items)[:n_items]
        return {"score": sum(scores), "max": 10, "rubric_scores": scores, "status": "참고",
                "error_type": err, "reason": reason}
    if "프롬프트 04" in head:
        conf = last_tag(prompt, "student_confusion")
        reply = None
        if conf and conf != "(없음)":
            reply = f"학생이 견준 두 가지 중 자료가 말하는 쪽이 맞다(p.{p0}). 다른 하나는 다른 연산의 절차다."
        return {"my_gap": f"{name}의 절차 중 일부를 빠뜨렸다.",
                "explanation": f"자료는 {name}을 '정해진 절차대로 진행한다'고 설명한다(p.{p0}).\n\n"
                               f"이렇게 해야 조건이 지켜진다(p.{pages[0]}).\n\n문제의 값에 적용하면 정답에 이른다.",
                "check_pages": pages[:2], "source_pages": pages[:2], "not_found": False,
                "not_found_note": None, "confusion_reply": reply}
    if "프롬프트 05" in head:
        detail = "자세히" if "**자세히**" in prompt else "보통"
        n = 3 if detail == "자세히" else 2
        return {"summary": f"{name}은 자료의 핵심 개념이다(p.{p0}).\n\n절차와 이유를 함께 기억한다(p.{pages[0]}).",
                "key_points": [f"{name} 핵심 {i + 1}" for i in range(n)],
                "pitfalls": [f"{name}을 다른 개념과 혼동한다"] if detail == "자세히" else [],
                "source_pages": [p0]}
    return {}
