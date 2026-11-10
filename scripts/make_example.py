"""샘플로 결과 예시 만들기 (F10, v1.10).

앱과 같은 순서(샘플 → 진단(섞어서) → 예시 답 채우기 → 채점 → 우선순위 → 자동 보완 설명·요약 노트)를
core/ 함수만으로 돌려 docs/결과_예시/에 내려받기 HTML 2개, 같은 내용의 마크다운 2개, README를 쓴다.

    python scripts/make_example.py                 # 실제 AI (환경변수 또는 .streamlit/secrets.toml의 키)
    BINTM_FAKE_AI=1 python scripts/make_example.py # 저장된 결과로 모양만 확인
    python scripts/make_example.py --from-html 공부순서.html 요약노트.html --note "배포 앱에서 내려받음"
                                                   # 배포 앱에서 내려받은 HTML 2개로 마크다운·README만 만들기
"""
from __future__ import annotations

import argparse
import datetime as _dt
import html
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "결과_예시"
SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TRANSCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
STUDY_HTML, NOTES_HTML = "공부순서_오답노트.html", "요약노트.html"
STUDY_MD, NOTES_MD = "공부순서_오답노트.md", "요약노트.md"


def load_keys() -> None:
    """환경변수가 없으면 .streamlit/secrets.toml에서 읽는다. 값은 출력하지 않는다."""
    from core.llm import set_keys
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        set_keys({k: data.get(k) for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
                  if data.get(k) and not os.environ.get(k)})


def _parallel(items, fn, workers):
    from core.llm import Usage

    def work(item):
        u = Usage()
        try:
            return True, fn(item, u), u
        except Exception as exc:
            return False, exc, u
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(work, items))


def run(out_dir: Path = OUT, today: str | None = None) -> dict:
    import config
    from core import diagnose as DG, explain as EX, export as EP, note as NT, priority as PR
    from core.concepts import extract_concepts
    from core.extract import extract, mask
    from core.llm import Usage, fake_mode, has_llm_key
    from core.score import compute_scores
    from core.utterances import find_utterances

    load_keys()
    if not has_llm_key():
        raise SystemExit("AI 키가 없어요. .streamlit/secrets.toml 또는 환경변수 ANTHROPIC_API_KEY를 넣어 주세요.")
    today = today or _dt.date.today().isoformat()
    usage, times, fails = Usage(), {}, []

    t0 = time.time()
    material = extract(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes())
    transcript = mask(SAMPLE_TRANSCRIPT.read_text(encoding="utf-8"))
    concepts = extract_concepts(material, usage)
    utter = find_utterances(transcript, concepts["concepts"], usage)
    sc = compute_scores(concepts, utter, material["pages"])
    times["분석(호출 1·2)"] = round(time.time() - t0, 1)
    cmap = {c["id"]: c for c in concepts["concepts"]}
    smap = {s["concept_id"]: s for s in sc["scores"]}

    t0 = time.time()
    targets = DG.diag_targets(sc["scores"])
    names = [cmap[c]["name"] for c in targets]
    jobs = [(cid, cmap[cid]["name"], DG.question_kind(smap[cid]["pct"], "섞어서"),
             DG.evidence_pages(cmap[cid], material, sc["meta_pages"]),
             DG.other_concepts_text(names, cmap[cid]["name"])) for cid in targets]
    questions = {}
    for job, (ok, val, u) in zip(jobs, _parallel(jobs, lambda j, u: DG.make_question(j[1], j[2], j[3], j[4], u),
                                                   config.PARALLEL_DIAG)):
        usage.merge(u)
        if ok:
            questions[job[0]] = val
        else:
            fails.append(f"문제 {job[1]}: {type(val).__name__}")
    times["진단 문제"] = round(time.time() - t0, 1)

    ex = DG.example_answers(questions)
    grading = {}
    essay_jobs = []
    for cid, q in questions.items():
        a = ex[cid]
        if q["kind"] == DG.MCQ:
            grading[cid] = DG.grade_mcq(q, a["mcq_choice"], a["guessed"])
        elif a["dont_know"]:
            grading[cid] = DG.blank_grading(DG.REASON_DONT_KNOW)
        else:
            essay_jobs.append((cid, cmap[cid]["name"], q, a["answer"],
                               DG.evidence_pages(cmap[cid], material, sc["meta_pages"])))
    t0 = time.time()
    for job, (ok, val, u) in zip(essay_jobs, _parallel(essay_jobs, lambda j, u: DG.grade_essay(j[1], j[2], j[3], j[4], u),
                                                         config.PARALLEL_DIAG)):
        usage.merge(u)
        if ok:
            grading[job[0]] = val
        else:
            fails.append(f"채점 {job[1]}: {type(val).__name__}")
    times["채점"] = round(time.time() - t0, 1)

    priorities = PR.compute_priorities(sc["scores"], grading)
    confusion = {cid: a["confusion"] for cid, a in ex.items() if a["confusion"]}
    pmap = {p["concept_id"]: p for p in priorities}
    t0 = time.time()
    study_jobs = []
    for cid in EX.auto_targets(priorities, confusion):
        study_jobs.append(("x", cid, cmap[cid]["name"], pmap[cid]["status"], questions.get(cid), grading.get(cid),
                           ex.get(cid), confusion.get(cid, ""),
                           DG.evidence_pages(cmap[cid], material, sc["meta_pages"])))
    notes = {}
    for cid, detail in NT.note_plan(concepts["concepts"], priorities, sc["meta_pages"]):
        if detail == NT.SHORT:
            notes[cid] = NT.short_note(cmap[cid], sc["meta_pages"])
        else:
            info = {"exam_pct": pmap[cid]["exam_pct"], "action": pmap[cid]["action"],
                    "status": pmap[cid]["status"], "grading": grading.get(cid)}
            study_jobs.append(("n", cid, cmap[cid], detail, info, list(utter),
                               DG.evidence_pages(cmap[cid], material, sc["meta_pages"])))

    def do(job, u):
        if job[0] == "x":
            return EX.make_explanation(*job[1:], usage=u)
        return NT.make_note(*job[2:], usage=u)

    explanations = {}
    for job, (ok, val, u) in zip(study_jobs, _parallel(study_jobs, do, config.PARALLEL_STUDY)):
        usage.merge(u)
        if not ok:
            fails.append(f"{'설명' if job[0] == 'x' else '노트'} {job[1]}: {type(val).__name__}")
        elif job[0] == "x":
            explanations[job[1]] = val
        else:
            notes[job[1]] = val
    times["④ 설명·노트"] = round(time.time() - t0, 1)

    state = dict(material=material, transcript_source="paste", scores=sc["scores"], priorities=priorities,
                 questions=questions, grading=grading,
                 answers={k: v["answer"] for k, v in ex.items()}, dont_know={k: v["dont_know"] for k, v in ex.items()},
                 mcq_choice={k: v["mcq_choice"] for k, v in ex.items()}, guessed={k: v["guessed"] for k, v in ex.items()},
                 confusion=confusion, explanations=explanations, notes=notes, concepts=concepts["concepts"],
                 utterances=utter, meta_pages=sc["meta_pages"])
    study, notes_h = EP.study_html(state, today), EP.notes_html(state, today)
    status = Counter(g["status"] for g in grading.values())
    detail = Counter(n["detail"] for n in notes.values())
    summary = {
        "today": today, "model": "가짜 AI(BINTM_FAKE_AI=1)" if fake_mode() else config.LLM_MODEL,
        "concepts": len(concepts["concepts"]), "utterances": len(utter),
        "questions": len(questions), "essay": sum(1 for q in questions.values() if q["kind"] == DG.ESSAY),
        "status": dict(status), "explanations": len(explanations), "detail": dict(detail),
        "top3": [(s["name"], s["pct"]) for s in sc["scores"][:3]], "times": times,
        "calls": usage.calls, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
        "fails": fails, "source": "make_example.py로 이 PC에서 실행",
    }
    write_outputs(out_dir, study, notes_h, summary)
    return summary


# --- HTML → 마크다운 (GitHub에서 읽기 좋게) ---
def _table_to_md(m: re.Match) -> str:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), flags=re.S)
    out = []
    for i, r in enumerate(rows):
        cells = [re.sub(r"<[^>]+>", " ", c).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, flags=re.S)]
        cells = [re.sub(r"\s+", " ", html.unescape(c)).replace("|", "\\|") for c in cells]
        out.append("| " + " | ".join(cells) + " |")
        if i == 0:
            out.append("|" + "---|" * len(cells))
    return "\n\n" + "\n".join(out) + "\n\n"


def html_to_md(text: str) -> str:
    t = re.sub(r"<head>.*?</head>", "", text, flags=re.S)
    t = re.sub(r"<style>.*?</style>", "", t, flags=re.S)
    t = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', lambda m: "\n\n(그림) " + m.group(1) + "\n\n", t)
    t = re.sub(r"<img[^>]*>", "\n\n(그림)\n\n", t)
    t = re.sub(r"<table.*?</table>", _table_to_md, t, flags=re.S)
    t = re.sub(r'<span class="pg">(p\.\d+)</span>', r" (\1)", t)
    t = re.sub(r'<span class="badge[^"]*">(.*?)</span>', lambda m: f" `{m.group(1)}`", t, flags=re.S)
    t = re.sub(r'<div class="bar">.*?</div>|<span class="bar">.*?</span>', "", t, flags=re.S)
    for n in (1, 2, 3):
        t = re.sub(rf"<h{n}[^>]*>(.*?)</h{n}>", lambda m, n=n: "\n\n" + "#" * n + " " + m.group(1).strip() + "\n\n",
                   t, flags=re.S)
    t = re.sub(r"<summary[^>]*>(.*?)</summary>", r"\n\n**\1**\n\n", t, flags=re.S)
    t = re.sub(r"<li[^>]*>(.*?)</li>", lambda m: "\n- " + m.group(1).strip(), t, flags=re.S)
    t = re.sub(r"<b>(.*?)</b>", r"**\1**", t, flags=re.S)
    t = re.sub(r"<br\s*/?>", "  \n", t)
    t = re.sub(r"</?(p|div|ul|details)[^>]*>", "\n\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() + "\n"


def write_outputs(out_dir: Path, study: str, notes_h: str, summary: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / STUDY_HTML).write_text(study, encoding="utf-8")
    (out_dir / NOTES_HTML).write_text(notes_h, encoding="utf-8")
    (out_dir / STUDY_MD).write_text(html_to_md(study), encoding="utf-8")
    (out_dir / NOTES_MD).write_text(html_to_md(notes_h), encoding="utf-8")
    (out_dir / "README.md").write_text(readme(summary), encoding="utf-8")


def readme(s: dict) -> str:
    st_ = s.get("status") or {}
    lines = [
        "# 결과 예시 (샘플 자료)", "",
        "앱을 열지 않고도 결과를 읽을 수 있게, 샘플 자료(가상 강의자료 20쪽 + 녹음 대본)로 한 바퀴 돌린 결과입니다. "
        "진단 답은 '예시 답 채우기'와 같은 규칙으로 채웠습니다.", "",
        "> 출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다.", "",
        "| 파일 | 내용 |", "|---|---|",
        f"| [{STUDY_MD}]({STUDY_MD}) · [HTML]({STUDY_HTML}) | 공부 순서·오답노트 (내려받기 파일 ①) |",
        f"| [{NOTES_MD}]({NOTES_MD}) · [HTML]({NOTES_HTML}) | 시험 대비 요약 노트 (내려받기 파일 ②) |", "",
        "## 만든 조건과 잰 값", "",
        f"- 만든 날: {s.get('today', '')}",
        f"- 만든 방법: {s.get('source', '')}",
        f"- 모델: {s.get('model', '')}",
    ]
    if s.get("concepts") is not None:
        lines.append(f"- 개념 {s['concepts']}개, 교수님 강조 발화 {s.get('utterances', '-')}개")
    if s.get("top3"):
        lines.append("- 출제 가능성 상위 3개: " + ", ".join(f"{n} {p}점" for n, p in s["top3"]))
    if s.get("questions") is not None:
        lines.append(f"- 진단 문제 {s['questions']}개(서술형 {s.get('essay', '-')} · 객관식 {s['questions'] - s.get('essay', 0)})")
    if st_:
        lines.append(f"- 진단 결과: 앎 {st_.get('앎', 0)} · 헷갈림 {st_.get('헷갈림', 0)} · 모름 {st_.get('모름', 0)}")
    if s.get("detail"):
        d = s["detail"]
        lines.append(f"- 요약 노트: 자세히 {d.get('자세히', 0)} · 보통 {d.get('보통', 0)} · 짧게 {d.get('짧게', 0)}")
    if s.get("times"):
        lines.append("- 단계별 시간: " + " · ".join(f"{k} {v}초" for k, v in s["times"].items()))
    if s.get("calls") is not None:
        lines.append(f"- AI 호출 {s['calls']}번 · 입력 {s.get('input_tokens', 0):,} 토큰 · 출력 {s.get('output_tokens', 0):,} 토큰")
    lines.append(f"- 실패: {len(s.get('fails') or [])}개" + (" (" + "; ".join(s["fails"]) + ")" if s.get("fails") else ""))
    for extra in s.get("extra") or []:
        lines.append(f"- {extra}")
    lines += ["", "다시 만들기: `python scripts/make_example.py` (키 필요, 약 2분)"]
    return "\n".join(lines) + "\n"


def from_html(study_path: str, notes_path: str, out_dir: Path, note: str, extra: list[str]) -> dict:
    """배포 앱에서 내려받은 HTML 2개로 결과 예시를 만든다."""
    study = Path(study_path).read_text(encoding="utf-8")
    notes_h = Path(notes_path).read_text(encoding="utf-8")
    m = re.search(r"(\d{4}-\d{2}-\d{2})", study)
    summary = {"today": m.group(1) if m else _dt.date.today().isoformat(), "source": note,
               "model": "claude-sonnet-5-5 (배포 앱 설정)", "extra": extra, "fails": []}
    write_outputs(out_dir, study, notes_h, summary)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="샘플로 결과 예시 만들기")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--from-html", nargs=2, metavar=("STUDY_HTML", "NOTES_HTML"))
    ap.add_argument("--note", default="배포 앱에서 샘플 체험 → 예시 답 채우기 → 채점 → ④ 후 내려받은 파일")
    ap.add_argument("--extra", action="append", default=[])
    args = ap.parse_args()
    if args.from_html:
        s = from_html(args.from_html[0], args.from_html[1], Path(args.out), args.note, args.extra)
    else:
        s = run(Path(args.out))
    print({k: v for k, v in s.items() if k not in ("extra",)})


if __name__ == "__main__":
    main()
