"""AI를 부르지 않는 테스트. python -m pytest -q"""
import os
import sys

# 프로젝트 루트를 import 경로에 넣는다
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import core  # noqa: E402


def read(name):
    with open(os.path.join(ROOT, "samples", name), encoding="utf-8") as f:
        return f.read()


SAMPLE = read("sample_lecture.md")
TRANSCRIPT = read("sample_transcript.md")


def fake_concepts():
    return [
        {"id": "c1", "name": "힙의 삽입", "pages": [9, 12], "in_objectives": True, "has_example": True, "in_exercise": True},
        {"id": "c2", "name": "순회", "pages": [5, 12], "in_objectives": True, "has_example": True, "in_exercise": True},
        {"id": "c3", "name": "BST 삭제", "pages": [7], "in_objectives": False, "has_example": False, "in_exercise": False},
    ]


# 1. 샘플 쪽 나누기
def test_split_sample_12_pages():
    pages = core.split_marked_pages(SAMPLE)
    assert len(pages) == 12
    assert pages[0]["page"] == 1 and pages[-1]["page"] == 12


# 2. 마스킹
def test_mask():
    out = core.mask("메일 a@b.com 전화 010-1234-5678 학번 2024123456 끝")
    assert "a@b.com" not in out and "010-1234-5678" not in out and "2024123456" not in out
    assert out.count("[가림]") == 3


# 3. 점수
def test_score_order():
    utter = [
        {"concept_id": "c1", "type": "exam_hint", "quote": "x", "strength": 3},
        {"concept_id": "c1", "type": "mistake", "quote": "x", "strength": 2},
        {"concept_id": "c2", "type": "emphasis", "quote": "x", "strength": 3},
        {"concept_id": "c3", "type": "defer", "quote": "x", "strength": 2},
    ]
    scored = core.score_concepts(fake_concepts(), utter, [1, 2, 12])
    assert scored[0]["name"] == "힙의 삽입" and scored[0]["score"] == 100
    assert scored[-1]["name"] == "BST 삭제"
    assert all(isinstance(s["score"], int) and 0 <= s["score"] <= 100 for s in scored)


# 4. 발화 검사
def test_utterance_check():
    data = {
        "utterances": [
            {"concept_id": "c1", "type": "exam_hint", "quote": "업힙 과정은   시험에 무조건 냅니다", "strength": 3},
            {"concept_id": "c1", "type": "emphasis", "quote": "대본에 없는 말입니다", "strength": 3},
            {"concept_id": "c9", "type": "emphasis", "quote": "힙이 오늘의 핵심입니다", "strength": 3},
            {"concept_id": "c1", "type": "wrong", "quote": "힙이 오늘의 핵심입니다", "strength": 3},
            {"concept_id": "c1", "type": "emphasis", "quote": "힙이 오늘의 핵심입니다", "strength": 9},
        ]
    }
    out = core.clean_utterances(data, {"c1", "c2"}, TRANSCRIPT)
    assert [u["quote"] for u in out] == ["업힙 과정은   시험에 무조건 냅니다", "힙이 오늘의 핵심입니다"]
    assert out[1]["strength"] == 3


# 5. 채점
def test_grade():
    q = {"answer_index": 2}
    assert core.grade(q, {"choice": 2, "guessed": False}) == "앎"
    assert core.grade(q, {"choice": 2, "guessed": True}) == "헷갈림"
    assert core.grade(q, {"choice": 1, "guessed": False}) == "모름"
    assert core.grade(q, {"choice": -1, "guessed": False}) == "모름"
    assert core.grade(q, None) is None


# 6. 우선순위
def test_priority():
    assert core.priority_of(80, "모름") == (80.0, "지금 당장")
    assert core.priority_of(80, "헷갈림") == (40.0, "다음")
    assert core.priority_of(80, "앎") == (0.0, "복습만")
    assert core.priority_of(30, "진단 안 함") == (15.0, "복습만")


# 7. 보기 섞기
def test_shuffle():
    q = {"question": "문제", "choices": ["정답", "오답1", "오답2", "오답3"], "answer_index": 0}
    a = core.shuffle_question(q, "c1")
    b = core.shuffle_question(q, "c1")
    assert a == b
    assert a["choices"][a["answer_index"]] == "정답"
    assert core.shuffle_question({**q, "choices": ["a", "b", "c"]}, "c1") is None
    assert core.shuffle_question({**q, "choices": ["a", "a", "b", "c"]}, "c1") is None
    assert core.shuffle_question({**q, "answer_index": 4}, "c1") is None


# 8. 예시 답
def test_example_answers():
    qs = [{"answer_index": i % 4, "concept_id": f"c{i}"} for i in range(4)]
    ans = core.example_answers(qs)
    assert ans[0] == {"choice": 0, "guessed": False}
    assert ans[1] == {"choice": 1, "guessed": True}
    assert ans[2]["choice"] != 2 and ans[2]["choice"] in range(4)
    assert ans[3]["choice"] == -1
    assert [core.grade(qs[i], ans[i]) for i in range(4)] == ["앎", "헷갈림", "모름", "모름"]


# 9. 인용 검사
def test_citations():
    out = core.clean_citations("힙은 완전 이진 트리예요 (p.3). 삽입은 끝에 해요 (p.9).", [3, 4])
    assert "(p.3)" in out and "(p.9)" not in out


# 10. 전체 흐름 (ask_json 가짜)
def fake_ask(prompt, max_tokens=4000):
    if "<targets>" in prompt:
        return {
            "questions": [
                {"concept_id": cid, "question": f"{cid} 문제", "choices": ["가", "나", "다", "라"],
                 "answer_index": 1, "explanation": "이유예요 (p.9) (p.99)", "source_pages": [9, 99]}
                for cid in ["c1", "c2", "c3", "c4", "c5", "c6"]
            ]
        }
    if "<items>" in prompt:
        # 지시문에도 '<items>'가 있으므로 마지막 태그 블록을 읽는다
        block = prompt.rsplit("<items>\n", 1)[1].split("\n</items>")[0]
        ids = [line.split(":")[0] for line in block.strip().splitlines()]
        return {"explanations": [{"concept_id": i, "core": "설명이에요 (p.9).", "missed": "놓쳤어요.", "review_pages": [9]} for i in ids]}
    if "<transcript>" in prompt:
        return {"utterances": [
            {"concept_id": "c1", "type": "exam_hint", "quote": "업힙 과정은 시험에 무조건 냅니다", "strength": 3},
            {"concept_id": "c2", "type": "emphasis", "quote": "순회는 진짜 중요합니다", "strength": 3},
            {"concept_id": "c5", "type": "defer", "quote": "BST 삭제는 시간이 없어서 다음 주에 다시 봅니다", "strength": 2},
        ]}
    return {
        "concepts": [
            {"id": "c1", "name": "힙의 삽입", "pages": [9, 12], "in_objectives": True, "has_example": True, "in_exercise": True},
            {"id": "c2", "name": "트리 순회", "pages": [5, 12], "in_objectives": True, "has_example": True, "in_exercise": True},
            {"id": "c3", "name": "힙의 삭제", "pages": [10, 12], "in_objectives": True, "has_example": True, "in_exercise": True},
            {"id": "c4", "name": "우선순위 큐", "pages": [11, 12], "in_objectives": True, "has_example": False, "in_exercise": True},
            {"id": "c5", "name": "BST 삭제", "pages": [7], "in_objectives": False, "has_example": False, "in_exercise": False},
            {"id": "c6", "name": "깊이와 높이", "pages": [3], "in_objectives": True, "has_example": True, "in_exercise": False},
        ],
        "meta_pages": [1, 2, 12],
    }


def test_full_flow(monkeypatch):
    monkeypatch.setattr(core, "ask_json", fake_ask)
    pages = core.mask_pages(core.split_marked_pages(SAMPLE))
    res = core.run_concepts(pages)
    utter = core.run_utterances(res["concepts"], core.mask(TRANSCRIPT))
    assert len(utter) == 3
    scored = core.score_concepts(res["concepts"], utter, res["meta_pages"])
    targets = core.pick_targets(scored)
    questions = core.run_mcq(targets, pages)
    assert questions and all("(p.99)" not in q["explanation"] for q in questions)
    answers = core.example_answers(questions)
    assert core.unanswered(questions, answers) == []
    states = core.diagnose(questions, answers)
    plan = core.build_plan(scored, states)
    assert [p["priority"] for p in plan] == sorted([p["priority"] for p in plan], reverse=True)
    top = core.auto_explain_targets(plan)
    expl = core.run_explain(top, questions, answers, pages)
    assert set(expl) == {it["concept"]["id"] for it in top}
    md = core.to_markdown("샘플", plan, questions, answers, expl)
    assert "# 빈틈노트 결과" in md and "공부 순서" in md
