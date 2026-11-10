# BINTM_FAKE_AI=1일 때 실제 AI 대신 답한다 (키 없이 화면 확인·테스트용, 11.3).
# 호출 1·2는 tests/fixtures/의 저장된 결과, 호출 3~5는 정해진 모양의 답. 샘플 자료가 아니면 내용이 맞지 않는다.
import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _name(prompt: str) -> str:
    m = re.search(r'개념 "(.+?)"', prompt)
    return m.group(1) if m else "개념"


def _pages(prompt: str) -> list[int]:
    seg = prompt.split("<pages>")[-1]
    return [int(x) for x in re.findall(r"=== 페이지 (\d+) ===", seg)] or [1]


def _tag(prompt: str, tag: str) -> str:
    if f"<{tag}>" not in prompt:
        return ""
    return prompt.rsplit(f"<{tag}>", 1)[1].split(f"</{tag}>")[0].strip()


def answer(prompt: str) -> dict:
    head = prompt.splitlines()[0] if prompt else ""
    if "프롬프트 01" in head:
        return _fixture("01_개념추출_결과.json")
    if "프롬프트 02" in head:
        return _fixture("02_강조발화_결과.json")
    name, pages = _name(prompt), _pages(prompt)
    p = pages[0]
    if "프롬프트 03-A" in head:
        if "순회" in name:
            return {"question": "아래 트리를 중위 순회한 결과를 쓰고, 중위 순회에서 루트를 언제 방문하는지 쓰시오.",
                    "answer": "중위 순회 결과는 D B E A C F이다. 중위 순회는 왼쪽 서브트리를 모두 방문한 뒤 루트를 방문한다.",
                    "rubric": [{"point": "순회 결과", "score": 6}, {"point": "루트 방문 시점", "score": 4}],
                    "source_pages": [p], "figure": {"kind": "tree", "nodes": ["A", "B", "C", "D", "E", None, "F"],
                                                    "caption": "이진 트리"}}
        return {"question": f"{name}의 핵심 과정을 쓰고, 그렇게 하는 이유를 쓰시오.",
                "answer": f"{name}은 자료에 나온 절차대로 한 단계씩 진행한다. 그 이유는 자료에 나온 조건을 계속 지키기 위해서이다.",
                "rubric": [{"point": "과정", "score": 6}, {"point": "이유", "score": 4}],
                "source_pages": [p], "figure": None}
    if "프롬프트 03-C" in head:
        fig = None
        if "힙" in name:
            fig = {"kind": "array", "items": ["90", "75", "80", "30"], "start": 1, "caption": "최대 힙"}
        return {"question": f"{name}에 대한 설명으로 옳은 것은?",
                "choices": [f"{name}의 올바른 설명이다", f"{name}과 방향을 반대로 한 설명이다",
                            f"{name}과 비교 대상을 바꾼 설명이다", f"{name}의 복잡도를 틀리게 쓴 설명이다"],
                "answer_index": 0,
                "explanation": f"자료는 {name}을 이렇게 설명한다(p.{p}). 방향을 반대로 한 보기는 다른 연산의 절차다.",
                "source_pages": [p], "figure": fig}
    if "프롬프트 03-B" in head:
        ans = _tag(prompt, "answer")
        if len(ans) >= 40:
            return {"score": 9, "max": 10, "rubric_scores": [6, 3], "status": "앎", "error_type": None,
                    "reason": f"과정과 이유를 모두 썼다 (p.{p})."}
        if len(ans) >= 10:
            return {"score": 5, "max": 10, "rubric_scores": [4, 1], "status": "헷갈림", "error_type": "절차 누락",
                    "reason": f"과정은 맞지만 이유가 빠졌다 (p.{p})."}
        return {"score": 2, "max": 10, "rubric_scores": [2, 0], "status": "모름", "error_type": "기타",
                "reason": f"묻는 내용과 다른 답이다 (p.{p})."}
    if "프롬프트 04" in head:
        conf = _tag(prompt, "student_confusion")
        return {"my_gap": f"{name}의 절차 중 일부를 놓쳤다.",
                "explanation": f"자료는 {name}을 '정해진 절차대로 진행한다'고 설명한다(p.{p}).\n\n"
                               f"그 이유는 '조건을 지키기 위해서'이다(p.{pages[-1]}).",
                "check_pages": pages[:2], "source_pages": pages[:2], "not_found": False, "not_found_note": None,
                "confusion_reply": (None if conf in ("", "(없음)") else
                                    f"두 보기는 비교하는 대상이 다르다. 자료는 '정해진 대상과 비교한다'고 쓴다(p.{p}).")}
    if "프롬프트 05" in head:
        return {"summary": f"{name}은 자료의 핵심 개념이다(p.{p}).\n\n절차는 자료에 나온 순서대로 진행한다(p.{p}).",
                "key_points": [f"{name}의 정의 (p.{p})", "절차 순서를 외운다"],
                "pitfalls": ["방향을 반대로 혼동한다"], "source_pages": [p]}
    return {}
