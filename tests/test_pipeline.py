"""T-06, T-07, T-16, T-17: 이해도·우선순위, 상태 판정, 내보내기, 저장된 AI 결과로 전체 흐름."""
from core import concepts as C
from core import diagnose, explain, note, priority, score
from core.diagnose import ESSAY, MCQ
from core.export import notes_html, study_html
from core.llm import Usage
from core.utterances import find_utterances
from tests.conftest import SAMPLE_TRANSCRIPT


def test_t06_priority_examples():
    scores = [{"concept_id": "del", "name": "힙 삭제", "pct": 97}, {"concept_id": "tr", "name": "순회", "pct": 100},
              {"concept_id": "ins", "name": "힙 삽입", "pct": 96}, {"concept_id": "pq", "name": "우선순위 큐", "pct": 50}]
    grading = {"del": {"status": "모름"}, "tr": {"status": "헷갈림"}, "ins": {"status": "앎"}}
    by = {p["concept_id"]: p for p in priority.compute_priorities(scores, grading)}
    assert [by[k]["priority"] for k in ("del", "tr", "ins", "pq")] == [97, 50, 0, 25]
    assert by["del"]["action"] == "지금 당장" and by["pq"]["action"] == "다음" and by["ins"]["action"] == "복습만"
    assert by["pq"]["status"] == "진단 안 함"


def test_t06_round_half_even():
    p = priority.compute_priorities([{"concept_id": "a", "name": "a", "pct": 97}], {"a": {"status": "헷갈림"}})
    assert p[0]["priority"] == 48  # 48.5 → 48 (파이썬 round)


def test_t07_status_rules():
    assert [diagnose.status_from_score(s) for s in (8, 7, 4, 3, 0)] == ["앎", "헷갈림", "헷갈림", "모름", "모름"]
    assert diagnose.status_from_score(6, "개념 혼동") == "모름"


def test_t16_export_empty_session():
    study = study_html({})
    notes = notes_html({})
    assert "빈틈노트 공부 순서·오답노트" in study and "1. 공부 순서" in study and "2. 오답노트" in study
    assert "우선순위 없음" in study and "진단하지 않음" in study
    assert "실제 출제를 보장하지 않습니다" in study
    assert "요약 노트 없음" in notes


def test_t16_export_escapes_tags():
    data = {"material_name": "<script>alert(1)</script>.pdf"}
    assert "<script>" not in study_html(data) and "&lt;script&gt;" in study_html(data)


def test_t17_full_pipeline_with_fixtures(sample_material):
    usage = Usage()
    found = C.extract_concepts(sample_material, usage)
    meta = score.meta_pages(sample_material["pages"], found)
    utts = find_utterances(SAMPLE_TRANSCRIPT.read_text(encoding="utf-8"), found["concepts"], usage)
    scores = score.compute_scores(found["concepts"], utts, meta)["scores"]
    targets = diagnose.diag_targets(scores)
    assert targets and all(s["pct"] >= 20 for s in scores if s["concept_id"] in targets)
    by_id = {c["id"]: c for c in found["concepts"]}
    pct = {s["concept_id"]: s["pct"] for s in scores}
    names = [by_id[c]["name"] for c in targets]
    questions = {}
    for cid in targets:
        kind = diagnose.choose_kind(pct[cid], "섞어서")
        questions[cid] = diagnose.make_question(by_id[cid], kind, sample_material, meta, names, usage)
        assert kind == (ESSAY if pct[cid] >= 50 else MCQ)
    ex = diagnose.example_answers(list(questions.values()))
    grading = {}
    for cid, q in questions.items():
        a = ex[cid]
        grading[cid] = (diagnose.grade_mcq(q, a["choice"], a["guessed"]) if q["kind"] == MCQ
                        else diagnose.grade_essay(q, a["answer"], a["dont_know"], sample_material, usage))
    prios = priority.compute_priorities(scores, grading)
    pby = {p["concept_id"]: p for p in prios}
    exps = {cid: explain.make_explanation(by_id[cid], pby[cid], questions.get(cid), grading.get(cid), sample_material, meta)
            for cid in priority.auto_explain_ids(prios, {})}
    order = note.lecture_order(found["concepts"], meta)
    notes = {cid: note.make_note(by_id[cid], note.detail_level(pby[cid]["action"], pby[cid]["exam_pct"], pby[cid]["status"]),
                                 pby[cid], grading.get(cid), utts, sample_material, meta) for cid in order}
    data = {"priorities": prios, "scores": scores, "questions": questions, "grading": grading, "explanations": exps,
            "notes": notes, "concepts": found["concepts"], "note_order": order, "utterances": utts}
    study, notes_file = study_html(data), notes_html(data)
    assert exps
    assert "image/jpeg" not in study and "image/jpeg" not in notes_file
    assert "시험 대비 요약 노트" not in study.split("<main>")[1][:200]
    assert notes_file.count('<div class="card">') == len(found["concepts"])
