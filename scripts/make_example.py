"""샘플 자료로 결과 예시 만들기 (F10 결과 예시).

    python scripts/make_example.py                 # 실제 AI (키: 환경변수 또는 .streamlit/secrets.toml)
    BINTM_FAKE_AI=1 python scripts/make_example.py  # 저장된 결과로 모양만 확인
    python scripts/make_example.py --from-html 공부순서.html 요약노트.html  # 배포 앱에서 내려받은 파일로

앱과 같은 순서(샘플 → 진단(섞어서) → 예시 답 → 채점 → 우선순위 → 자동 보완 설명·요약 노트)를 core 함수만으로 돌린다.
docs/결과_예시/에 내려받기 HTML 2개, 같은 내용의 마크다운 2개, README.md를 쓴다.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from core import llm  # noqa: E402
from core.guard import kst_now, kst_today  # noqa: E402

OUT = ROOT / "docs" / "결과_예시"
SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_SCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
STUDY_MD = "공부순서_오답노트.md"
NOTES_MD = "요약노트.md"


# ---------- HTML → 마크다운 ----------

class _MD(HTMLParser):
    """내려받기 HTML을 GitHub에서 읽기 좋은 마크다운으로. 배지는 `코드`, 쪽 배지는 (p.n), 그림은 (그림) 글."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.span: list[str] = []
        self.table: list[list[str]] | None = None
        self.cell: list[str] | None = None
        self.list_depth = 0

    def _w(self, s: str) -> None:
        if self.cell is not None:
            self.cell.append(s)
        else:
            self.out.append(s)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag in ("style", "script", "title"):
            self.skip += 1
        elif tag in ("h1", "h2", "h3", "h4"):
            self._w("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in ("p", "div") and self.cell is None:
            self._w("\n\n")
        elif tag == "br":
            self._w("  \n")
        elif tag in ("ul", "ol"):
            self.list_depth += 1
            self._w("\n")
        elif tag == "li":
            self._w("\n" + "  " * (self.list_depth - 1) + "- ")
        elif tag == "b" or tag == "summary":
            self._w("**")
        elif tag == "span":
            kind = "pg" if "bt-pg" in cls else "rec" if "bt-rec" in cls else "bd" if "bt-bd" in cls else ""
            self.span.append(kind)
            self._w({"pg": " (", "rec": " (", "bd": " `"}.get(kind, ""))
        elif tag == "img":
            self._w(f"\n\n(그림) {a.get('alt', '')}\n\n")
        elif tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.table.append([])
        elif tag in ("td", "th") and self.table is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("style", "script", "title"):
            self.skip -= 1
        elif tag in ("b", "summary"):
            self._w("**" + ("\n\n" if tag == "summary" else ""))
        elif tag in ("ul", "ol"):
            self.list_depth = max(0, self.list_depth - 1)
            self._w("\n")
        elif tag == "span" and self.span:
            kind = self.span.pop()
            self._w({"pg": ")", "rec": ")", "bd": "` "}.get(kind, ""))
        elif tag in ("td", "th") and self.table is not None and self.cell is not None:
            self.table[-1].append(re.sub(r"\s+", " ", "".join(self.cell)).strip().replace("|", "\\|"))
            self.cell = None
        elif tag == "table" and self.table is not None:
            rows = [r for r in self.table if r]
            self.table = None
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [""] * (width - len(r)) for r in rows]
                lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
                lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
                self.out.append("\n\n" + "\n".join(lines) + "\n\n")

    def handle_data(self, data):
        if self.skip:
            return
        if self.span and self.span[-1] == "pg":
            data = data.strip()
        self._w(data)


def html_to_md(html_text: str) -> str:
    p = _MD()
    p.feed(html_text)
    md = "".join(p.out)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(r"\(\s*\(p\.", "(p.", md)
    return md.strip() + "\n"


def _stat_numbers(html_text: str) -> list[tuple[str, str]]:
    return re.findall(r"<div class='stat'><b>(\d+)</b>([^<]+)</div>", html_text)


# ---------- 앱과 같은 순서로 돌리기 ----------

def _load_key() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    sec = ROOT / ".streamlit" / "secrets.toml"
    if sec.exists():
        import tomllib
        data = tomllib.loads(sec.read_text(encoding="utf-8"))
        if data.get("ANTHROPIC_API_KEY"):
            llm.set_api_key(data["ANTHROPIC_API_KEY"])


def run_sample(out_dir: Path) -> dict:
    from core.concepts import extract_concepts
    from core.diagnose import (MCQ, diag_targets, evidence_pages, example_answers, grade_blank, grade_essay,
                               grade_mcq, make_question, other_concepts_text, question_kind)
    from core.explain import make_explanation
    from core.export import file_names, note_rows, notes_html, study_html
    from core.extract import extract, mask, pages_text
    from core.note import make_note
    from core.priority import auto_explain_ids, compute_priorities
    from core.score import compute_scores
    from core.utterances import find_utterances

    _load_key()
    if not llm.has_key():
        raise SystemExit("키가 없어요: ANTHROPIC_API_KEY 환경변수나 .streamlit/secrets.toml을 넣어 주세요.")
    total = llm.Usage()
    stages = {}

    def stage(name, t0):
        stages[name] = round(time.time() - t0, 1)

    t0 = time.time()
    material = extract(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes())
    transcript = mask(SAMPLE_SCRIPT.read_text(encoding="utf-8"))
    cres = extract_concepts(material, usage=total)
    utts = find_utterances(transcript, cres["concepts"], usage=total)
    scores = compute_scores(cres["concepts"], utts, cres["meta_pages"])
    stage("① 분석(개념·강조)", t0)
    cmap = {c["id"]: c for c in cres["concepts"]}
    smap = {r["concept_id"]: r for r in scores["scores"]}

    def ev(cid):
        pages = evidence_pages(cmap[cid], cres["meta_pages"]) or [1]
        return pages, pages_text(material, pages)

    targets = diag_targets(scores["scores"])
    names = [cmap[c]["name"] for c in targets]

    def pool(jobs):
        res, err = {}, {}
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {k: ex.submit(f) for k, f in jobs}
            for k, f in futs.items():
                try:
                    res[k] = f.result()
                except Exception as e:  # noqa: BLE001
                    err[k] = e
        return res, err

    t0 = time.time()
    jobs = []
    for cid in targets:
        allowed, ptext = ev(cid)
        kind = question_kind(smap[cid]["pct"], "섞어서")
        u = llm.Usage()
        jobs.append((cid, lambda cid=cid, kind=kind, allowed=allowed, ptext=ptext, u=u: (
            make_question(cmap[cid], kind, ptext, allowed, other_concepts_text(names, cmap[cid]["name"]), u), u)))
    res, _ = pool(jobs)
    questions = {cid: q for cid, (q, u) in res.items()}
    for _, (q, u) in res.items():
        total.merge(u)
    stage("② 문제 만들기", t0)
    order = [c for c in targets if c in questions]
    ex_ans = example_answers(questions, order)
    answers = {c: a.get("answer", "") for c, a in ex_ans.items() if "answer" in a}
    dont_know = {c: a.get("dont_know", False) for c, a in ex_ans.items() if "answer" in a}
    mcq_choice = {c: a["mcq_choice"] for c, a in ex_ans.items() if "mcq_choice" in a}
    guessed = {c: a["guessed"] for c, a in ex_ans.items() if "mcq_choice" in a}
    confusion = {c: a["confusion"] for c, a in ex_ans.items() if "mcq_choice" in a}

    t0 = time.time()
    grading, jobs = {}, []
    for cid in order:
        q = questions[cid]
        if q["kind"] == MCQ:
            grading[cid] = grade_mcq(q, mcq_choice[cid], guessed[cid])
        elif dont_know.get(cid):
            grading[cid] = grade_blank(q, "dont_know")
        else:
            allowed, ptext = ev(cid)
            u = llm.Usage()
            jobs.append((cid, lambda cid=cid, q=q, allowed=allowed, ptext=ptext, u=u: (
                grade_essay(cmap[cid]["name"], q, answers[cid], False, ptext, allowed, u), u)))
    res, _ = pool(jobs)
    for cid, (g, u) in res.items():
        grading[cid] = g
        total.merge(u)
    stage("③ 채점", t0)
    prios = compute_priorities(scores["scores"], grading)
    pmap = {p["concept_id"]: p for p in prios}
    conf = {c: confusion.get(c, "") if guessed.get(c) else "" for c in questions}
    ids = auto_explain_ids(prios, conf, config.AUTO_EXPLAIN_TOP)

    def ans_of(cid):
        return {"answer": answers.get(cid, ""), "dont_know": dont_know.get(cid, False),
                "mcq_choice": mcq_choice.get(cid), "guessed": guessed.get(cid, False),
                "confusion": conf.get(cid, "")}

    t0 = time.time()
    jobs = []
    for cid in ids:
        allowed, ptext = ev(cid)
        u = llm.Usage()
        jobs.append((cid, lambda cid=cid, allowed=allowed, ptext=ptext, u=u: (make_explanation(
            cmap[cid], pmap[cid]["status"], questions.get(cid), grading.get(cid), ans_of(cid), conf.get(cid, ""),
            ptext, allowed, u), u)))
    res, _ = pool(jobs)
    explanations = {cid: e for cid, (e, u) in res.items()}
    for _, (e, u) in res.items():
        total.merge(u)
    stage("④ 보완 설명", t0)
    state = {"material": material, "transcript": transcript, "transcript_source": "paste",
             "concepts": cres["concepts"], "utterances": utts, "scores": scores, "priorities": prios,
             "questions": questions, "answers": answers, "dont_know": dont_know, "mcq_choice": mcq_choice,
             "guessed": guessed, "confusion": confusion, "grading": grading, "explanations": explanations,
             "notes": {}, "meta_pages": cres["meta_pages"]}
    t0 = time.time()
    jobs = []
    for c, detail, n in note_rows(state):
        if detail in ("자세히", "보통"):
            cid = c["id"]
            allowed, ptext = ev(cid)
            u = llm.Usage()
            jobs.append((cid, lambda cid=cid, detail=detail, allowed=allowed, ptext=ptext, u=u: (make_note(
                cmap[cid], detail, pmap.get(cid), grading.get(cid), utts, ptext, allowed, u), u)))
    res, _ = pool(jobs)
    state["notes"] = {cid: n for cid, (n, u) in res.items()}
    for _, (n, u) in res.items():
        total.merge(u)
    stage("④ 요약 노트", t0)
    out_dir.mkdir(parents=True, exist_ok=True)
    f1, f2 = file_names()
    s_html, n_html = study_html(state), notes_html(state)
    (out_dir / f1).write_text(s_html, encoding="utf-8")
    (out_dir / f2).write_text(n_html, encoding="utf-8")
    (out_dir / STUDY_MD).write_text(html_to_md(s_html), encoding="utf-8")
    (out_dir / NOTES_MD).write_text(html_to_md(n_html), encoding="utf-8")
    counts = {s: sum(1 for g in grading.values() if g["status"] == s) for s in ("앎", "헷갈림", "모름")}
    lines = [
        "# 결과 예시 (샘플 자료, 앱과 같은 순서)", "",
        f"- 만든 날: {kst_now().strftime('%Y-%m-%d %H:%M')} (한국 시간)",
        f"- 모델: `{config.LLM_MODEL}`" + (" (가짜 AI 모드: 저장된 결과)" if os.environ.get("BINTM_FAKE_AI") == "1" else ""),
        f"- 만든 명령: `python scripts/make_example.py`",
        f"- 개념 {len(cres['concepts'])}개, 진단 문제 {len(questions)}개(서술형 "
        f"{sum(1 for q in questions.values() if q['kind'] != MCQ)} · 객관식 {sum(1 for q in questions.values() if q['kind'] == MCQ)})",
        f"- 예시 답 채점: 앎 {counts['앎']} · 헷갈림 {counts['헷갈림']} · 모름 {counts['모름']}",
        f"- 자동 보완 설명 {len(explanations)}개, 요약 노트(AI) {len(state['notes'])}개",
        f"- AI 호출 {total.calls}번 · 입력 토큰 {total.input_tokens:,} · 출력 토큰 {total.output_tokens:,}",
        "- 단계별 시간(초): " + ", ".join(f"{k} {v}" for k, v in stages.items()), "",
        f"- [공부 순서·오답노트 (마크다운)]({STUDY_MD}) · [HTML]({f1})",
        f"- [시험 대비 요약 노트 (마크다운)]({NOTES_MD}) · [HTML]({f2})", "",
        "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다.", ""]
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return {"stages": stages, "usage": total.to_dict(), "counts": counts}


def from_html(study: Path, notes: Path, out_dir: Path, note: str = "") -> None:
    """배포 앱 ④에서 내려받은 HTML 2개로 마크다운과 README를 만든다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    s_html = study.read_text(encoding="utf-8")
    n_html = notes.read_text(encoding="utf-8")
    if study.resolve().parent != out_dir.resolve():
        (out_dir / study.name).write_text(s_html, encoding="utf-8")
    if notes.resolve().parent != out_dir.resolve():
        (out_dir / notes.name).write_text(n_html, encoding="utf-8")
    (out_dir / STUDY_MD).write_text(html_to_md(s_html), encoding="utf-8")
    (out_dir / NOTES_MD).write_text(html_to_md(n_html), encoding="utf-8")
    st1 = ", ".join(f"{k.strip()} {v}" for v, k in _stat_numbers(s_html))
    st2 = ", ".join(f"{k.strip()} {v}" for v, k in _stat_numbers(n_html))
    lines = [
        "# 결과 예시 (샘플 자료, 배포 앱에서 내려받은 파일)", "",
        "이 PC에 AI 키 파일이 없어, 배포 앱에서 실제 AI로 샘플 한 바퀴(샘플 체험 → 진단 → 예시 답 채우기 → 채점 → "
        "공부 순서 → 요약 노트)를 돌린 뒤 ④의 내려받기 버튼 두 개가 준 HTML을 그대로 넣었어요. "
        f"마크다운은 `python scripts/make_example.py --from-html {study.name} {notes.name}`로 만들었어요.", "",
        f"- 만든 날: {kst_today().isoformat()} (한국 시간)",
        f"- 모델: `{config.LLM_MODEL}` (배포 앱 설정)",
        f"- 공부 순서: {st1}" if st1 else "- 공부 순서: (숫자 칸 없음)",
        f"- 요약 노트: {st2}" if st2 else "- 요약 노트: (숫자 칸 없음)"]
    if note:
        lines.append(f"- {note}")
    lines += ["", f"- [공부 순서·오답노트 (마크다운)]({STUDY_MD}) · [HTML]({study.name})",
              f"- [시험 대비 요약 노트 (마크다운)]({NOTES_MD}) · [HTML]({notes.name})", "",
              "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다.", ""]
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="샘플 결과 예시 만들기")
    ap.add_argument("--from-html", nargs=2, metavar=("STUDY_HTML", "NOTES_HTML"))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--note", default="", help="README에 덧붙일 한 줄(예: 배포 앱 ⑤ 사용량)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if a.from_html:
        from_html(Path(a.from_html[0]), Path(a.from_html[1]), out, a.note)
        print(f"마크다운과 README를 {out}에 썼어요.")
    else:
        r = run_sample(out)
        print(r)


if __name__ == "__main__":
    main()
