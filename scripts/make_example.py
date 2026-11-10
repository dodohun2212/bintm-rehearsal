"""샘플로 결과 예시 만들기 (F10). 앱과 같은 순서로 core 함수만 돌린다.

    python scripts/make_example.py                 # 실제 AI (키: 환경변수 또는 .streamlit/secrets.toml)
    BINTM_FAKE_AI=1 python scripts/make_example.py # 가짜 AI로 모양만 확인
    python scripts/make_example.py --from-html 공부순서.html 요약노트.html   # 배포 앱에서 내려받은 파일로

결과: docs/결과_예시/ 에 HTML 2개, 같은 내용의 마크다운 2개, README.md
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
from core import concepts as C  # noqa: E402
from core import diagnose, explain, export, note, priority, score  # noqa: E402
from core.extract import extract, mask  # noqa: E402
from core.guard import kst_today  # noqa: E402
from core.llm import Usage, fake_mode  # noqa: E402
from core.utterances import find_utterances  # noqa: E402

SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TRANSCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
OUT = ROOT / "docs" / "결과_예시"
NAMES = ("공부순서_오답노트.html", "요약노트.html", "공부순서_오답노트.md", "요약노트.md", "README.md")


def load_key() -> None:
    """키: 환경변수 → .streamlit/secrets.toml. 값은 출력하지 않는다."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        import tomllib

        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            if data.get(name) and not os.environ.get(name):
                os.environ[name] = str(data[name])


def _parallel(fn, items: dict, workers: int = 6):
    usages = {k: Usage() for k in items}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {k: pool.submit(fn, v, usages[k]) for k, v in items.items()}
        results = {}
        for k, fut in futures.items():
            try:
                results[k] = fut.result()
            except Exception as exc:  # 한 개념이 실패해도 나머지는 쓴다
                print(f"실패: {k} {type(exc).__name__}")
    total = Usage()
    for u in usages.values():
        total.merge(u)
    return results, total


def run(out_dir: Path = OUT) -> dict:
    usage, times = Usage(), {}
    t = time.perf_counter()
    material = extract(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes())
    transcript = mask(SAMPLE_TRANSCRIPT.read_text(encoding="utf-8"))
    found = C.extract_concepts(material, usage)
    meta = score.meta_pages(material["pages"], found)
    utts = find_utterances(transcript, found["concepts"], usage)
    scores = score.compute_scores(found["concepts"], utts, meta)["scores"]
    times["분석"] = time.perf_counter() - t

    by_id = {c["id"]: c for c in found["concepts"]}
    pct = {s["concept_id"]: s["pct"] for s in scores}
    targets = diagnose.diag_targets(scores)
    names = [by_id[c]["name"] for c in targets]
    t = time.perf_counter()
    questions, u = _parallel(lambda cid, us: diagnose.make_question(
        by_id[cid], diagnose.choose_kind(pct[cid], "섞어서"), material, meta, names, us), {c: c for c in targets})
    usage.merge(u)
    questions = {c: questions[c] for c in targets if c in questions}
    times["문제 만들기"] = time.perf_counter() - t

    ex = diagnose.example_answers(list(questions.values()))
    answers = {c: a.get("answer", "") for c, a in ex.items()}
    dont_know = {c: a.get("dont_know", False) for c, a in ex.items()}
    choice = {c: a.get("choice") for c, a in ex.items()}
    guessed = {c: a.get("guessed", False) for c, a in ex.items()}
    confusion = {c: a.get("confusion", "") for c, a in ex.items()}
    t = time.perf_counter()
    grading = {c: diagnose.grade_mcq(q, choice[c], guessed[c]) for c, q in questions.items() if q["kind"] == diagnose.MCQ}
    essays = {c: q for c, q in questions.items() if q["kind"] == diagnose.ESSAY}
    graded, u = _parallel(lambda q, us: diagnose.grade_essay(q, answers[q["concept_id"]], dont_know[q["concept_id"]],
                                                             material, us), essays)
    usage.merge(u)
    grading.update(graded)
    times["채점"] = time.perf_counter() - t

    prios = priority.compute_priorities(scores, grading)
    pby = {p["concept_id"]: p for p in prios}
    conf = {c: v for c, v in confusion.items() if guessed.get(c)}
    t = time.perf_counter()
    exps, u = _parallel(lambda cid, us: explain.make_explanation(
        by_id[cid], pby[cid], questions.get(cid), grading.get(cid), material, meta, answers.get(cid, ""),
        choice.get(cid), guessed.get(cid, False), conf.get(cid, ""), us),
        {c: c for c in priority.auto_explain_ids(prios, conf)}, workers=8)
    usage.merge(u)
    times["보완 설명"] = time.perf_counter() - t
    order = note.lecture_order(found["concepts"], meta)
    t = time.perf_counter()
    notes, u = _parallel(lambda cid, us: note.make_note(
        by_id[cid], note.detail_level(pby[cid]["action"], pby[cid]["exam_pct"], pby[cid]["status"]), pby[cid],
        grading.get(cid), utts, material, meta, us), {c: c for c in order}, workers=8)
    usage.merge(u)
    times["요약 노트"] = time.perf_counter() - t

    day = kst_today().isoformat()
    data = {"material_name": material["name"], "today": day, "transcript_source": "paste", "scores": scores,
            "priorities": prios, "concepts": found["concepts"], "questions": questions, "grading": grading,
            "explanations": exps, "notes": notes, "utterances": utts, "answers": answers, "mcq_choice": choice,
            "guessed": guessed, "confusion": conf, "note_order": order}
    counts = {s: sum(1 for g in grading.values() if g["status"] == s) for s in ("앎", "헷갈림", "모름")}
    info = {"how": "scripts/make_example.py" + (" (가짜 AI)" if fake_mode() else " (실제 AI)"), "day": day,
            "model": "가짜 AI" if fake_mode() else config.LLM_MODEL, "concepts": len(found["concepts"]),
            "questions": len(questions), "essay": len(essays), "counts": counts, "times": times,
            "usage": usage, "explained": len(exps), "notes": len(notes)}
    return write_outputs(out_dir, export.study_html(data), export.notes_html(data), info)


# ---------- HTML → 마크다운 ----------
class _ToMarkdown(HTMLParser):
    BLOCK = {"p", "div", "ul", "table", "details", "h1", "h2", "h3", "h4", "li", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.span_stack: list[str] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.table_rows = 0

    def _emit(self, text: str) -> None:
        if self.cell is not None:
            self.cell.append(text)
        else:
            self.out.append(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag in ("style", "script", "title", "head"):
            self.skip += 1
            return
        if tag in ("h1", "h2", "h3", "h4"):
            self._emit("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in ("p", "div", "details") and self.cell is None:
            self._emit("\n\n")
        elif tag == "li":
            self._emit("\n- ")
        elif tag == "b" or tag == "summary":
            self._emit("**")
        elif tag == "br":
            self._emit(" ")
        elif tag == "img":
            self._emit("(그림) " + (a.get("alt") or "").replace("문제 그림: ", ""))
        elif tag == "table":
            self._emit("\n\n")
            self.table_rows = 0
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif tag == "span":
            kind = "pg" if "pg" in cls.split() else ("rec" if "rec" in cls.split() else
                                                      ("badge" if "badge" in cls else ""))
            self.span_stack.append(kind)
            if kind == "pg":
                self._emit("(")
            elif kind == "badge":
                self._emit("`")
            elif kind == "rec":
                self._emit("(")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "title", "head"):
            self.skip = max(0, self.skip - 1)
            return
        if tag == "b" or tag == "summary":
            self._emit("**")
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip().replace("|", "\\|"))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            line = "| " + " | ".join(self.row) + " |"
            self.out.append(line + "\n")
            if self.table_rows == 0:
                self.out.append("|" + "---|" * len(self.row) + "\n")
            self.table_rows += 1
            self.row = None
        elif tag == "span" and self.span_stack:
            kind = self.span_stack.pop()
            if kind == "pg":
                self._emit(")")
            elif kind == "badge":
                self._emit("` ")
            elif kind == "rec":
                self._emit(")")

    def handle_data(self, data):
        if self.skip:
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip():
            self._emit(text)


def html_to_markdown(html_text: str) -> str:
    parser = _ToMarkdown()
    parser.feed(html_text)
    md = "".join(parser.out)
    md = md.replace("(녹음)", "(녹음)").replace("(p.", "(p.")
    md = re.sub(r"\(\(p\.", "(p.", md)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def write_outputs(out_dir: Path, study: str, notes: str, info: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / NAMES[0]).write_text(study, encoding="utf-8")
    (out_dir / NAMES[1]).write_text(notes, encoding="utf-8")
    (out_dir / NAMES[2]).write_text(html_to_markdown(study), encoding="utf-8")
    (out_dir / NAMES[3]).write_text(html_to_markdown(notes), encoding="utf-8")
    (out_dir / NAMES[4]).write_text(readme(info), encoding="utf-8")
    return {"files": [out_dir / n for n in NAMES], "info": info}


def readme(info: dict) -> str:
    lines = ["# 결과 예시 (샘플 자료)", "",
             "앱을 열지 않고도 결과를 읽을 수 있게, 샘플 자료(가상 강의자료 20쪽 + 대본)로 한 바퀴 돌린 결과입니다. "
             f"{export.DISCLAIMER}.", "",
             f"- 만든 날: {info['day']}", f"- 만든 방법: {info['how']}", f"- 모델: {info['model']}"]
    if info.get("concepts"):
        lines.append(f"- 개념 {info['concepts']}개, 진단 문제 {info['questions']}개(서술형 {info['essay']} · "
                     f"객관식 {info['questions'] - info['essay']})")
    if info.get("counts"):
        c = info["counts"]
        lines.append(f"- 진단 결과(예시 답 채우기): 앎 {c['앎']} · 헷갈림 {c['헷갈림']} · 모름 {c['모름']}")
    if info.get("times"):
        lines.append("- 단계별 시간: " + " · ".join(f"{k} {v:.1f}초" for k, v in info["times"].items()))
    u = info.get("usage")
    if u is not None:
        lines.append(f"- AI 호출 {u.calls}번, 입력 {u.input_tokens:,} · 출력 {u.output_tokens:,} 토큰")
    if info.get("note"):
        lines += ["", info["note"]]
    lines += ["", "| 파일 | 내용 |", "|---|---|",
              f"| [{NAMES[2]}]({NAMES[2]}) | 공부 순서·오답노트 (GitHub에서 읽기 좋은 마크다운) |",
              f"| [{NAMES[3]}]({NAMES[3]}) | 시험 대비 요약 노트 (마크다운) |",
              f"| [{NAMES[0]}]({NAMES[0]}) | 앱의 '📥 공부 순서·오답노트 내려받기' 파일 그대로 |",
              f"| [{NAMES[1]}]({NAMES[1]}) | 앱의 '📒 요약 노트 내려받기' 파일 그대로 |", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--from-html", nargs=2, metavar=("STUDY", "NOTES"))
    ap.add_argument("--note", default="", help="README에 덧붙일 한 줄(--from-html일 때 잰 값 등)")
    args = ap.parse_args()
    out = Path(args.out)
    if args.from_html:
        study = Path(args.from_html[0]).read_text(encoding="utf-8")
        notes = Path(args.from_html[1]).read_text(encoding="utf-8")
        day = re.search(r"\d{4}-\d{2}-\d{2}", study)
        info = {"how": "배포 앱에서 샘플 체험 → 예시 답 채우기 → 채점 → ④ 내려받기 2개(실제 AI)",
                "day": day.group(0) if day else kst_today().isoformat(), "model": config.LLM_MODEL, "note": args.note}
        result = write_outputs(out, study, notes, info)
    else:
        load_key()
        result = run(out)
    for f in result["files"]:
        print(f.relative_to(ROOT) if f.is_relative_to(ROOT) else f)


if __name__ == "__main__":
    main()
