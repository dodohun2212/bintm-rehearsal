# T-16 내보내기, T-17 전체 흐름 (AI 호출을 fixtures·가짜 AI로 대체)
from core import diagnose, explain, export, note, priority
from core.diagnose import ESSAY, MCQ


def test_t16_empty_and_titles():
    empty = {"material": {"name": "x"}, "date": "d"}
    s, n = export.study_html(empty), export.notes_html(empty)
    assert "빈틈노트 공부 순서·오답노트" in s and "1. 공부 순서" in s and "2. 오답노트" in s
    assert "우선순위 없음" in s and "진단하지 않음" in s and "실제 출제를 보장하지 않습니다" in s
    assert "요약 노트 없음" in n and "출제를 보장하지 않습니다" in n


def test_t17_full_flow(material, analysis):
    scores, concepts, meta = analysis["scores"], analysis["concepts"], analysis["meta"]
    by_id = {c["id"]: c for c in concepts}
    targets = diagnose.diag_targets(scores)
    pct = {s["concept_id"]: s["pct"] for s in scores}
    assert all(pct[c] >= 20 for c in targets) and len(targets) == sum(1 for s in scores if s["pct"] >= 20)
    qs, failed, usage, _ = diagnose.make_questions([{"concept": by_id[c], "pct": pct[c]} for c in targets],
                                                   material, meta, "섞어서")
    assert not failed and usage.calls == len(targets)
    for cid, q in qs.items():
        assert q["kind"] == (ESSAY if pct[cid] >= 50 else MCQ)
    ex = diagnose.example_answers(qs)
    grading, gf, _, _ = diagnose.grade_all(
        qs, {k: v["answer"] for k, v in ex.items() if "answer" in v},
        {k: v["dont_know"] for k, v in ex.items() if "answer" in v},
        {k: v["choice"] for k, v in ex.items() if "choice" in v},
        {k: v["guessed"] for k, v in ex.items() if "choice" in v}, material, meta, by_id)
    assert not gf and set(grading) == set(qs)
    assert {g["status"] for g in grading.values()} == {"앎", "헷갈림", "모름"}
    pri = priority.compute_priorities(scores, grading)
    exp_ids = explain.auto_targets(pri, {})
    jobs = {cid: {"concept": by_id[cid], "pct": pct[cid], "status": p["status"], "q": qs.get(cid),
                  "g": grading.get(cid)} for cid in exp_ids for p in pri if p["concept_id"] == cid}
    exps, ef, _, _ = explain.run_parallel(lambda j, u: explain.explain(j, material, meta, u), jobs)
    assert not ef and exps
    notes = {}
    for p in pri:
        d = note.detail_level(p["action"], p["exam_pct"], p["status"])
        notes[p["concept_id"]] = (note.short_note(by_id[p["concept_id"]], meta) if d == "짧게" else
                                  note.make_note({"concept": by_id[p["concept_id"]], "detail": d, "pr": p,
                                                  "g": grading.get(p["concept_id"]), "utterances": []}, material, meta))
    state = {"material": material, "date": "d", "scores": scores, "priorities": pri, "questions": qs,
             "grading": grading, "explanations": exps, "notes": notes, "concepts": concepts, "meta_pages": meta,
             "utterances": analysis["utts"], "mcq_choice": {}, "answers": {}, "guessed": {}, "confusion": {}}
    study, notes_doc = export.study_html(state), export.notes_html(state)
    assert "image/jpeg" not in study and "image/jpeg" not in notes_doc
    assert "시험 대비 요약 노트" not in study and "2. 오답노트" not in notes_doc
    assert notes_doc.count('<div class="card">') == len(concepts)
    assert "출제를 보장하지 않습니다" in study


def test_source_pages_out_of_range_removed():
    ex = explain.parse_explanation({"source_pages": [3, 99], "check_pages": [99], "explanation": "e"},
                                   "c1", [3, 4], "", "모름", "")
    assert ex["source_pages"] == [3] and 99 not in ex["check_pages"]
