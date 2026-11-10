"""가짜 AI (BINTM_FAKE_AI=1). 키 없이 화면 확인·스크린샷·테스트에 쓴다.

호출 1·2는 tests/fixtures/의 저장된 결과를, 호출 3~5는 정해진 모양의 답을 돌려준다.
샘플 자료가 아니면 내용이 맞지 않는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _concept_name(prompt: str) -> str:
    m = re.search(r'개념 "(.+?)"', prompt)
    return m.group(1) if m else "개념"


def _pages(prompt: str) -> list[int]:
    nums = [int(n) for n in re.findall(r"=== 페이지 (\d+) ===", prompt)]
    return nums or [1]


def _block(prompt: str, tag: str) -> str:
    m = re.search(rf"<{tag}>\n?(.*?)\n?</{tag}>", prompt, re.S)
    return m.group(1).strip() if m else ""


def answer(prompt: str) -> dict:
    head = prompt.splitlines()[0] if prompt else ""
    name = _concept_name(prompt)
    pages = _pages(prompt)
    p = pages[0]
    if "프롬프트 01" in head:
        return _fixture("01_개념추출_결과.json")
    if "프롬프트 02" in head:
        return _fixture("02_강조발화_결과.json")
    if "프롬프트 03-A" in head:
        figure = None
        question = f"{name}의 핵심 과정을 쓰고, 그렇게 하는 이유를 쓰시오."
        if "순회" in name:
            figure = {"kind": "tree", "nodes": ["A", "B", "C", "D", "E"], "caption": "이진 트리"}
            question = "아래 트리를 중위 순회한 결과를 쓰고, 루트를 방문하는 시점을 쓰시오."
        return {
            "question": question,
            "answer": f"{name}은 자료에 나온 절차를 차례로 따른다. 그 이유는 자료에 적힌 성질을 지키기 위해서다.",
            "rubric": [{"point": "과정", "score": 6}, {"point": "이유", "score": 4}],
            "source_pages": [p],
            "figure": figure,
        }
    if "프롬프트 03-C" in head:
        figure = None
        if "힙" in name:
            figure = {"kind": "array", "items": ["90", "70", "80", "30"], "start": 1, "caption": "최대 힙"}
        return {
            "question": f"{name}에 대한 설명으로 옳은 것은?",
            "choices": [
                f"{name}의 올바른 설명이다",
                f"{name}의 방향을 반대로 한 설명이다",
                f"{name}의 비교 대상을 바꾼 설명이다",
                f"{name}의 복잡도를 틀리게 쓴 설명이다",
            ],
            "answer_index": 0,
            "explanation": f"자료는 {name}을 이렇게 설명한다(p.{p}). 방향을 반대로 한 보기는 다른 연산의 절차다.",
            "source_pages": [p],
            "figure": figure,
        }
    if "프롬프트 03-B" in head:
        try:
            q = json.loads(_block(prompt, "question"))
        except json.JSONDecodeError:
            q = {"answer": "", "rubric": [{"score": 10}]}
        model = q.get("answer", "")
        student = _block(prompt, "answer")
        rubric = [int(r.get("score", 0)) for r in q.get("rubric", [])] or [10]
        if student and len(student) >= 0.8 * len(model):
            scores = rubric
            reason, err = "절차와 이유를 모두 바르게 썼다.", None
        elif student:
            scores = [r // 2 for r in rubric]
            reason, err = f"과정은 맞지만 이유가 빠졌다 (p.{p}).", "절차 누락"
        else:
            scores = [0 for _ in rubric]
            reason, err = "답이 없다.", "무응답"
        return {"score": sum(scores), "max": 10, "rubric_scores": scores, "status": "", "error_type": err, "reason": reason}
    if "프롬프트 04" in head:
        confusion = _block(prompt, "student_confusion")
        reply = None
        if confusion and confusion != "(없음)":
            reply = f"두 보기는 비교하는 대상이 다르다(p.{p}). 자료의 절차를 따르는 쪽이 맞다(p.{p})."
        return {
            "my_gap": f"{name}의 절차 중 일부를 빠뜨렸다.",
            "explanation": f"자료는 {name}을 이렇게 설명한다(p.{p}).\n\n이 절차를 문제에 적용하면 정답에 이른다.",
            "check_pages": pages[:2],
            "source_pages": [p],
            "not_found": False,
            "not_found_note": None,
            "confusion_reply": reply,
        }
    if "프롬프트 05" in head:
        return {
            "summary": f"{name}은 자료에서 이렇게 정리된다(p.{p}).\n\n교수님은 이 부분을 강조했다(녹음).",
            "key_points": [f"{name}의 핵심 절차", "시간 복잡도"],
            "pitfalls": [f"{name}의 방향을 혼동한다"],
            "source_pages": [p],
        }
    return {}
