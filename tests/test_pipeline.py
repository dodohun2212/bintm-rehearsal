"""T-16 내보내기, T-17 전체 흐름(가짜 AI: 호출 1·2는 fixtures)."""
from core.diagnose import (ESSAY, MCQ, choose_kind, diag_targets, evidence_pages, example_answers, grade_essay,
                           local_grading, make_question)
from core.explain import make_explanation
from core.export import LAST_LINE, notes_html, study_html
from core.llm import run_parallel
from core.note import detail_level, make_note
from core.priority import compute_priorities
from tests.helpers import sample


def test_t16_export_empty_and_full():
    empty = {"material_name": "x.pdf", "date": "2026-11-11"}
    s, n = study_html(empty), notes_html(empty)
    assert "빈틈노트 공부 순서·오답노트" in s and "우선순위 없음" in s and "진단하지 않음" in s
    assert "요약 노트 없음" in n
    from tests.test_figure_note import _state
    full = study_html(_state())
    assert "1. 공부 순서" in full and "2. 오답노트" in full and LAST_LINE in full
    assert "출제를 보장하지 않습니다" in full and "&lt;script&gt;" in full


def test_t17_full_flow():
    s = sample()
    by_id = {c["id"]: c for c in s["concepts"]}
    pct = {r["concept_id"]: r["pct"] for r in s["scores"]}
    targets = diag_targets(s["scores"])
    assert all(pct[c] >= 20 for c in targets)
    names = [by_id[c]["name"] for c in targets]
    tasks = {c: (lambda u, c=c: make_question(by_id[c], choose_kind(pct[c]), evidence_pages(by_id[c], s["material"], s["meta"]),
                                              names, u)) for c in targets}
    qs, errs, usage = run_parallel(tasks)
    assert not errs and usage.calls == len(targets)
    for c, q in qs.items():
        assert q["kind"] == (ESSAY if pct[c] >= 50 else MCQ)
    ex = example_answers([(c, qs[c]) for c in targets])
    grading = {}
    for c, q in qs.items():
        a = ex[c]
        g = local_grading(q, a.get("answer"), a.get("dont_know", False), a.get("choice"), a.get("guessed", False))
        grading[c] = g or grade_essay(q, a["answer"], evidence_pages(by_id[c], s["material"], s["meta"]))
    assert {g["status"] for g in grading.values()} == {"앎", "헷갈림", "모름"}
    pr = compute_priorities(s["scores"], grading)
    exps = {p["concept_id"]: make_explanation(by_id[p["concept_id"]], qs.get(p["concept_id"]), grading.get(p["concept_id"]),
                                              {}, "", evidence_pages(by_id[p["concept_id"]], s["material"], s["meta"]))
            for p in pr[:3]}
    notes = {p["concept_id"]: make_note(by_id[p["concept_id"]], detail_level(p["action"], p["exam_pct"], p["status"]), p,
                                        grading.get(p["concept_id"]), s["utterances"],
                                        evidence_pages(by_id[p["concept_id"]], s["material"], s["meta"])) for p in pr}
    state = {"priorities": pr, "scores": s["scores"], "questions": qs, "grading": grading,
             "answers": {c: a.get("answer", "") for c, a in ex.items()},
             "dont_know": {c: a.get("dont_know", False) for c, a in ex.items()},
             "mcq_choice": {c: a.get("choice") for c, a in ex.items()},
             "guessed": {c: a.get("guessed", False) for c, a in ex.items()},
             "confusion": {c: a.get("confusion", "") for c, a in ex.items()}, "explanations": exps, "notes": notes,
             "concepts": s["concepts"], "meta": s["meta"], "utterances": s["utterances"], "material_name": "s.pdf",
             "date": "2026-11-11", "transcript_source": "paste"}
    study, notes_doc = study_html(state), notes_html(state)
    for doc in (study, notes_doc):
        assert "image/jpeg" not in doc
    assert "시험 대비 요약 노트" not in study
    assert notes_doc.count("class='card'") == len(s["concepts"])
