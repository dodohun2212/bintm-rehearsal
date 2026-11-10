"""T-16, T-17 내보내기와 전체 흐름(AI 호출을 fixtures·가짜 AI로)."""
import re

import config
from core.diagnose import (MCQ, ESSAY, diag_targets, evidence_pages, example_answers, grade_essay, grade_mcq,
                           make_question, other_concepts_text, question_kind)
from core.explain import make_explanation
from core.export import note_rows, notes_html, study_html
from core.extract import pages_text
from core.priority import auto_explain_ids, compute_priorities
from tests.test_figure_note import _state


def _visible_text(html: str) -> str:
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


def test_t16_export_example_and_empty():
    s = study_html(_state())
    assert "빈틈노트 공부 순서·오답노트" in s and "1. 공부 순서" in s and "2. 오답노트" in s
    assert "실제 출제를 보장하지 않습니다." in s.split("class='foot'")[1]
    assert "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다." in s
    assert "%" not in _visible_text(s)
    empty = {}
    e1, e2 = study_html(empty), notes_html(empty)
    assert "우선순위 없음" in e1 and "진단하지 않음" in e1 and "요약 노트 없음" in e2
    assert "출제를 보장하지 않습니다" in e2


def test_t17_full_pipeline(sample_material, sample_analysis):
    concepts, meta, scores = sample_analysis["concepts"], sample_analysis["meta"], sample_analysis["scores"]
    cmap = {c["id"]: c for c in concepts}
    smap = {r["concept_id"]: r for r in scores["scores"]}
    targets = diag_targets(scores["scores"])
    assert all(smap[c]["pct"] >= config.DIAG_MIN_PCT for c in targets)
    assert all(r["concept_id"] in targets for r in scores["scores"] if r["pct"] >= config.DIAG_MIN_PCT)
    names = [cmap[c]["name"] for c in targets]
    qs = {}
    for cid in targets:
        pages = evidence_pages(cmap[cid], meta)
        kind = question_kind(smap[cid]["pct"], "섞어서")
        q = make_question(cmap[cid], kind, pages_text(sample_material, pages), pages,
                          other_concepts_text(names, cmap[cid]["name"]))
        assert q["kind"] == (ESSAY if smap[cid]["pct"] >= 50 else MCQ)
        qs[cid] = q
    ex = example_answers(qs, targets)
    grading = {}
    for cid, q in qs.items():
        a = ex[cid]
        pages = evidence_pages(cmap[cid], meta)
        if q["kind"] == MCQ:
            grading[cid] = grade_mcq(q, a["mcq_choice"], a["guessed"])
        else:
            grading[cid] = grade_essay(cmap[cid]["name"], q, a["answer"], a["dont_know"],
                                       pages_text(sample_material, pages), pages)
    prios = compute_priorities(scores["scores"], grading)
    conf = {c: ex[c].get("confusion", "") for c in qs}
    ids = auto_explain_ids(prios, conf, config.AUTO_EXPLAIN_TOP)
    exps = {}
    for cid in ids:
        pages = evidence_pages(cmap[cid], meta)
        st = next(p["status"] for p in prios if p["concept_id"] == cid)
        exps[cid] = make_explanation(cmap[cid], st, qs.get(cid), grading.get(cid), ex.get(cid, {}),
                                     conf.get(cid, ""), pages_text(sample_material, pages), pages)
        assert set(exps[cid]["source_pages"]) <= set(pages)
    state = {"material": sample_material, "concepts": concepts, "meta_pages": meta, "utterances": sample_analysis["utts"],
             "scores": scores, "priorities": prios, "questions": qs, "grading": grading, "explanations": exps,
             "answers": {c: a.get("answer", "") for c, a in ex.items()},
             "dont_know": {c: a.get("dont_know", False) for c, a in ex.items()},
             "mcq_choice": {c: a.get("mcq_choice") for c, a in ex.items()},
             "guessed": {c: a.get("guessed", False) for c, a in ex.items()}, "confusion": conf, "notes": {}}
    s, n = study_html(state), notes_html(state)
    assert "image/jpeg" not in s and "image/jpeg" not in n
    assert len(note_rows(state)) == len(concepts)
    assert n.count("class='bt-card'") == len(concepts)
    assert "시험 대비 요약 노트" in n and "2. 오답노트" not in n
