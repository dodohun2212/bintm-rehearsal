"""BINTM_FAKE_AI=1일 때 실제 AI 대신 답한다 (11.3). 키 없이 화면 확인·스크린샷·테스트용.

호출 1·2는 tests/fixtures/의 저장된 결과, 호출 3~5는 정해진 모양의 답. 샘플 자료가 아니면 내용이 맞지 않는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
NO_CONFUSION = "(없음)"


def _pages(prompt: str) -> list[int]:
    return [int(n) for n in re.findall(r"=== 페이지 (\d+) ===", prompt)] or [1]


def _name(prompt: str) -> str:
    m = re.search(r'개념 "([^"]+)"', prompt)
    return m.group(1) if m else "개념"


def _tag(prompt: str, tag: str) -> str:
    m = re.findall(rf"<{tag}>\n?(.*?)\n?</{tag}>", prompt, flags=re.S)
    return m[-1].strip() if m else ""


def answer(prompt: str) -> dict:
    head = prompt[:80]
    pages = _pages(prompt)
    p = pages[min(1, len(pages) - 1)]
    name = _name(prompt)
    if "프롬프트 01" in head:
        return json.loads((FIXTURES / "01_개념추출_결과.json").read_text(encoding="utf-8"))
    if "프롬프트 02" in head:
        return json.loads((FIXTURES / "02_강조발화_결과.json").read_text(encoding="utf-8"))
    if "프롬프트 03-A" in head:
        fig = None
        if "순회" in name:
            fig = {"kind": "tree", "nodes": ["A", "B", "C", "D", "E"], "caption": "이진 트리"}
        return {"question": f"{name}의 과정을 설명하고, 그 이유를 쓰시오." + (" 아래 트리를 보고 답하시오." if fig else ""),
                "answer": f"{name}은 자료의 절차대로 진행한다. 그 이유는 자료가 설명한 규칙을 지키기 위해서다.",
                "rubric": [{"point": "과정", "score": 6}, {"point": "이유", "score": 4}],
                "source_pages": [p], "figure": fig}
    if "프롬프트 03-C" in head:
        fig = {"kind": "array", "items": ["90", "75", "80"], "start": 1} if "배열" in name else None
        return {"question": f"{name}에 대한 설명으로 옳은 것은?",
                "choices": [f"{name}의 올바른 설명", f"{name}과 방향을 반대로 한 설명",
                            f"{name}에서 비교 대상을 바꾼 설명", f"{name}의 복잡도를 틀리게 쓴 설명"],
                "answer_index": 0,
                "explanation": f"자료는 {name}을 이렇게 설명한다(p.{p}). 방향을 반대로 한 보기는 다른 연산이다.",
                "source_pages": [p], "figure": fig}
    if "프롬프트 03-B" in head:
        ans = _tag(prompt, "answer")
        score = 9 if len(ans) >= 40 else (5 if len(ans) >= 8 else 2)
        rs = [min(6, round(score * 0.6)), score - min(6, round(score * 0.6))]
        return {"score": score, "max": 10, "rubric_scores": rs, "status": "", "error_type": None if score >= 8 else "절차 누락",
                "reason": f"자료의 절차와 비교해 채점했다 (p.{p})."}
    if "프롬프트 04" in head:
        conf = _tag(prompt, "student_confusion")
        return {"my_gap": f"{name}의 절차 한 부분을 놓쳤다.",
                "explanation": f"자료는 {name}을 단계별로 설명한다(p.{p}).\n\n핵심은 정해진 순서를 지키는 것이다(p.{pages[0]}).",
                "check_pages": pages[:2], "source_pages": pages[:2], "not_found": False, "not_found_note": None,
                "confusion_reply": (f"두 보기의 차이는 비교 방향이다(p.{p})." if conf and conf != NO_CONFUSION else None)}
    if "프롬프트 05" in head:
        return {"summary": f"{name}의 정의를 자료대로 정리한다(p.{p}).\n\n절차와 이유를 함께 기억한다(p.{pages[0]}).",
                "key_points": [f"{name} 핵심 1", f"{name} 핵심 2", f"{name} 핵심 3"],
                "pitfalls": [f"{name}의 방향을 혼동한다"], "source_pages": pages[:2]}
    return {}
