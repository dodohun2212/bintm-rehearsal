"""T-16, T-17: 내보내기와 전체 흐름(가짜 AI로 S01→S04, AI 호출 없음)."""
from collections import Counter

from core import diagnose as DG
from core import explain as EX
from core import export as EP
from core import note as NT
from core import priority as PR
from core.concepts import extract_concepts
from core.llm import Usage
from core.score import compute_scores
from core.utterances import find_utterances


def run_flow(material, transcript, mode="섞어서"):
    u = Usage()
    c = extract_concepts(material, u)
    ut = find_utterances(transcript, c["concepts"], u)
    sc = compute_scores(c, ut, material["pages"])
    cmap = {x["id"]: x for x in c["concepts"]}
    pct = {s["concept_id"]: s["pct"] for s in sc["scores"]}
    targets = DG.diag_targets(sc["scores"])
    names = [cmap[i]["name"] for i in targets]
    qs = {cid: DG.make_question(cmap[cid]["name"], DG.question_kind(pct[cid], mode),
                                DG.evidence_pages(cmap[cid], material, sc["meta_pages"]),
                                DG.other_concepts_text(names, cmap[cid]["name"]), u) for cid in targets}
    ex = DG.example_answers(qs)
    gr = {}
    for cid, q in qs.items():
        a = ex[cid]
        if q["kind"] == DG.MCQ:
            gr[cid] = DG.grade_mcq(q, a["mcq_choice"], a["guessed"])
        elif a["dont_know"]:
            gr[cid] = DG.blank_grading(DG.REASON_DONT_KNOW)
        else:
            gr[cid] = DG.grade_essay(cmap[cid]["name"], q, a["answer"], DG.evidence_pages(cmap[cid], material), u)
    pr = PR.compute_priorities(sc["scores"], gr)
    conf = {k: v["confusion"] for k, v in ex.items() if v["confusion"]}
    pmap = {p["concept_id"]: p for p in pr}
    exps = {cid: EX.make_explanation(cid, cmap[cid]["name"], pmap[cid]["status"], qs.get(cid), gr.get(cid),
                                     ex.get(cid), conf.get(cid, ""), DG.evidence_pages(cmap[cid], material), u)
            for cid in EX.auto_targets(pr, conf)}
    notes = {}
    for cid, d in NT.note_plan(c["concepts"], pr, sc["meta_pages"]):
        info = {**pmap[cid], "grading": gr.get(cid)}
        notes[cid] = (NT.short_note(cmap[cid], sc["meta_pages"]) if d == NT.SHORT
                      else NT.make_note(cmap[cid], d, info, ut, DG.evidence_pages(cmap[cid], material), u))
    state = dict(material=material, transcript_source="paste", scores=sc["scores"], priorities=pr, questions=qs,
                 grading=gr, answers={k: v["answer"] for k, v in ex.items()},
                 dont_know={k: v["dont_know"] for k, v in ex.items()},
                 mcq_choice={k: v["mcq_choice"] for k, v in ex.items()},
                 guessed={k: v["guessed"] for k, v in ex.items()}, confusion=conf, explanations=exps,
                 notes=notes, concepts=c["concepts"], utterances=ut, meta_pages=sc["meta_pages"])
    return state, sc, u


def test_t17_full_flow(material, transcript):
    state, sc, u = run_flow(material, transcript)
    qs = state["questions"]
    pct = {s["concept_id"]: s["pct"] for s in sc["scores"]}
    assert set(qs) == {cid for cid, p in pct.items() if p >= 20}  # 20점 이상만 진단
    for cid, q in qs.items():
        assert q["kind"] == ("서술형" if pct[cid] >= 50 else "객관식")
    assert Counter(g["status"] for g in state["grading"].values()).keys() >= {"앎", "헷갈림", "모름"}
    study, notes = EP.study_html(state), EP.notes_html(state)
    for h in (study, notes):
        assert "image/jpeg" not in h and "data:image/jpeg" not in h
    assert "시험 대비 요약 노트" not in study and "핵심 1" not in study  # 요약 노트는 다른 파일에만
    assert notes.count('class="note-card') == len(state["concepts"])
    assert state["explanations"] and state["priorities"]
    assert u.calls > 0


def test_t17_no_transcript(material):
    state, sc, _ = run_flow(material, "")
    assert state["utterances"] == [] and sc["scores"][0]["pct"] == 100  # 녹음 없이도 끝까지


def test_t16_export_empty_and_escape():
    empty = {}
    study = EP.study_html(empty)
    assert "빈틈노트 공부 순서·오답노트" in study and "우선순위 없음" in study and "진단하지 않음" in study
    assert EP.LAST_LINE in study and EP.DISCLAIMER in study
    assert "요약 노트 없음" in EP.notes_html(empty)
    state = {"priorities": [{"concept_id": "c1", "name": "<script>x</script>", "exam_pct": 80, "status": "모름",
                             "understanding": 0.0, "priority": 80, "action": "지금 당장", "rank": 1}],
             "scores": [{"concept_id": "c1", "name": "x", "pct": 80, "reasons": [], "pages": [3], "body_pages": [3]}]}
    h = EP.study_html(state)
    assert "<script>x" not in h and "&lt;script&gt;" in h
    assert "1. 공부 순서" in h and "2. 오답노트" in h
