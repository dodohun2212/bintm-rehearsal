"""가짜 AI 모드(BINTM_FAKE_AI=1). 키 없이 화면 확인·스크린샷·테스트에 쓴다(11.3).

호출 1·2는 tests/fixtures/의 저장된 결과를, 호출 3~5는 정해진 모양의 답을 돌려준다.
샘플 자료가 아니면 내용이 맞지 않는다.
"""
from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


@lru_cache(maxsize=None)
def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _concept_name(prompt: str) -> str:
    m = re.search(r'개념 "([^"]+)"', prompt)
    return m.group(1) if m else "개념"


def _first_page(prompt: str) -> int:
    m = re.search(r"=== 페이지 (\d+) ===", prompt)
    return int(m.group(1)) if m else 1


def _section(prompt: str, tag: str) -> str:
    """프롬프트 맨 끝의 실제 데이터 칸(설명 글 속 태그 이름이 아니라)."""
    start = prompt.rfind(f"<{tag}>")
    end = prompt.rfind(f"</{tag}>")
    return prompt[start + len(tag) + 2:end].strip() if 0 <= start < end else ""


def answer(prompt: str) -> dict:
    head = prompt.splitlines()[0] if prompt else ""
    name = _concept_name(prompt)
    p = _first_page(prompt)
    if "프롬프트 01" in head:
        return copy.deepcopy(_fixture("01_개념추출_결과.json"))
    if "프롬프트 02" in head:
        return copy.deepcopy(_fixture("02_강조발화_결과.json"))
    if "프롬프트 03-A" in head:
        fig = None
        if "순회" in name:
            fig = {"kind": "tree", "nodes": ["A", "B", "C", "D", "E", None, "F"], "caption": "이진 트리"}
        elif "힙" in name:
            fig = {"kind": "array", "items": ["90", "75", "80", "30"], "start": 1, "caption": "최대 힙 (인덱스 1부터)"}
        return {
            "question": f"{name}의 핵심 과정을 쓰고, 그렇게 하는 이유를 쓰시오.",
            "answer": f"{name}는 자료에 나온 절차대로 진행한다. 그렇게 해야 성질이 유지되기 때문이다.",
            "rubric": [{"point": "핵심 과정", "score": 6}, {"point": "이유", "score": 4}],
            "source_pages": [p],
            "figure": fig,
        }
    if "프롬프트 03-C" in head:
        return {
            "question": f"{name}에 대한 설명으로 옳은 것은?",
            "choices": [f"{name}의 올바른 설명", f"{name}과 방향을 반대로 한 설명",
                        f"{name}과 비교 대상을 바꾼 설명", f"{name}의 복잡도를 틀리게 쓴 설명"],
            "answer_index": 0,
            "explanation": f"자료는 {name}을 이렇게 설명한다(p.{p}). 방향을 반대로 한 보기는 다른 연산의 절차다.",
            "source_pages": [p],
            "figure": None,
        }
    if "프롬프트 03-B" in head:
        ans = _section(prompt, "answer")
        n = len([s for s in re.split(r"다\.", ans) if s.strip()])
        if "모르" in ans or not ans:
            score, rs, err = 0, [0, 0], "무응답"
        elif n >= 2:
            score, rs, err = 9, [6, 3], None
        else:
            score, rs, err = 5, [4, 1], "절차 누락"
        return {"score": score, "max": 10, "rubric_scores": rs, "status": "", "error_type": err,
                "reason": f"답의 내용을 자료와 비교했다 (p.{p})."}
    if "프롬프트 04" in head:
        conf = _section(prompt, "student_confusion")
        return {
            "my_gap": f"{name}의 절차 중 일부를 놓쳤다.",
            "explanation": f"자료는 {name}을 단계별로 설명한다(p.{p}).\n\n각 단계에서 무엇을 비교하는지 다시 확인한다(p.{p}).",
            "check_pages": [p],
            "source_pages": [p],
            "not_found": False,
            "not_found_note": None,
            "confusion_reply": None if conf in ("", "(없음)") else f"두 보기의 차이는 비교하는 대상이다(p.{p}).",
        }
    if "프롬프트 05" in head:
        return {
            "summary": f"{name}의 정의를 자료대로 정리한다(p.{p}).\n\n절차와 이유를 자료의 순서대로 적는다(p.{p}).",
            "key_points": [f"{name}의 핵심 절차", "시간 복잡도"],
            "pitfalls": ["비교 방향을 혼동한다"],
            "source_pages": [p],
        }
    return {}
