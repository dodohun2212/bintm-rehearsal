# 샘플 자료로 결과 예시 만들기 (F10, v1.10).
# 앱과 같은 순서: 샘플 → 진단(섞어서) → 예시 답 채우기 → 채점 → 우선순위 → 자동 보완 설명·요약 노트.
# 사용: python scripts/make_example.py  (키는 환경변수 ANTHROPIC_API_KEY 또는 .streamlit/secrets.toml)
#       BINTM_FAKE_AI=1 python scripts/make_example.py  (가짜 AI로 모양만 확인)
import datetime as dt
import html
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from core import concepts as concepts_mod  # noqa: E402
from core import diagnose, explain, export, note, priority, score, utterances  # noqa: E402
from core.extract import extract  # noqa: E402
from core.llm import Usage  # noqa: E402

SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TRANSCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
OUT_DIR = ROOT / "docs" / "결과_예시"


def load_key() -> None:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("BINTM_FAKE_AI") == "1":
        return
    secrets = ROOT / ".streamlit" / "secrets.toml"
    if secrets.exists():
        import tomllib
        data = tomllib.loads(secrets.read_text(encoding="utf-8"))
        for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            if data.get(k):
                os.environ[k] = str(data[k])


# ---- HTML → 마크다운 ----
def _table_md(m) -> str:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S)
    cells = [[re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)]
             for r in rows]
    cells = [r for r in cells if r]
    if not cells:
        return ""
    n = max(len(r) for r in cells)
    cells = [r + [""] * (n - len(r)) for r in cells]
    lines = ["| " + " | ".join(cells[0]) + " |", "|" + "---|" * n]
    lines += ["| " + " | ".join(r) + " |" for r in cells[1:]]
    return "\n\n" + "\n".join(lines) + "\n\n"


def html_to_md(src: str) -> str:
    s = re.sub(r"<(style|title|head)[^>]*>.*?</\1>", "", src, flags=re.S)
    s = re.sub(r'<span class="pg">(p\.[^<]*)</span>', r"(\1)", s)
    s = re.sub(r'<span class="badge[^"]*"[^>]*>(.*?)</span>', r" `\1` ", s)
    s = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r"\n\n(그림) \1\n\n", s)
    s = re.sub(r"<table[^>]*>.*?</table>", _table_md, s, flags=re.S)
    for i in range(1, 5):
        s = re.sub(rf"<h{i}[^>]*>(.*?)</h{i}>", lambda m, i=i: "\n\n" + "#" * i + " " + m.group(1).strip() + "\n\n",
                   s, flags=re.S)
    s = re.sub(r"<summary[^>]*>(.*?)</summary>", r"\n\n**\1**\n\n", s, flags=re.S)
    s = re.sub(r"<b>(.*?)</b>", r"**\1**", s, flags=re.S)
    s = re.sub(r"<li[^>]*>", "\n- ", s)
    s = re.sub(r"<br\s*/?>", "  \n", s)
    s = re.sub(r"</?(p|div|ul|ol|details)[^>]*>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip() + "\n"


# ---- 앱과 같은 순서로 돌리기 ----
def run(out_dir: Path = OUT_DIR) -> dict:
    load_key()
    out_dir.mkdir(parents=True, exist_ok=True)
    times, usage = {}, Usage()

    t = time.time()
    material = extract(SAMPLE_PDF.read_bytes(), SAMPLE_PDF.name)
    transcript = SAMPLE_TRANSCRIPT.read_text(encoding="utf-8")
    cres = concepts_mod.extract_concepts(material, usage)
    meta = concepts_mod.meta_pages(material, cres)
    utts = utterances.find_utterances(cres["concepts"], transcript, usage)
    scores = score.compute_scores(cres["concepts"], utts, meta)["scores"]
    times["① 분석(개념·강조·점수)"] = time.time() - t

    by_id = {c["id"]: c for c in cres["concepts"]}
    pct = {s["concept_id"]: s["pct"] for s in scores}
    t = time.time()
    targets = [{"concept": by_id[cid], "pct": pct[cid]} for cid in diagnose.diag_targets(scores)]
    questions, q_failed, u, _ = diagnose.make_questions(targets, material, meta, "섞어서")
    usage.merge(u)
    times["② 문제 만들기"] = time.time() - t

    ex = diagnose.example_answers(questions)
    answers = {k: v.get("answer", "") for k, v in ex.items() if "answer" in v}
    dont_know = {k: v.get("dont_know", False) for k, v in ex.items() if "answer" in v}
    mcq_choice = {k: v["choice"] for k, v in ex.items() if "choice" in v}
    guessed = {k: v["guessed"] for k, v in ex.items() if "choice" in v}
    confusion = {k: v["confusion"] for k, v in ex.items() if v.get("confusion")}
    t = time.time()
    grading, g_failed, u, _ = diagnose.grade_all(questions, answers, dont_know, mcq_choice, guessed,
                                                  material, meta, by_id)
    usage.merge(u)
    times["③ 채점"] = time.time() - t

    pri = priority.compute_priorities(scores, grading)
    t = time.time()
    exp_ids = explain.auto_targets(pri, confusion)
    pr_by = {p["concept_id"]: p for p in pri}
    jobs = {}
    for cid in exp_ids:
        q = questions.get(cid)
        jobs[("exp", cid)] = {"concept": by_id[cid], "pct": pr_by[cid]["exam_pct"], "status": pr_by[cid]["status"],
                              "q": q, "g": grading.get(cid), "answer": answers.get(cid, ""),
                              "choice": mcq_choice.get(cid), "guessed": guessed.get(cid),
                              "confusion": confusion.get(cid, "")}
    notes = {}
    for p in pri:
        d = note.detail_level(p["action"], p["exam_pct"], p["status"])
        if d == "짧게":
            notes[p["concept_id"]] = note.short_note(by_id[p["concept_id"]], meta)
        else:
            jobs[("note", p["concept_id"])] = {"concept": by_id[p["concept_id"]], "detail": d, "pr": p,
                                               "g": grading.get(p["concept_id"]), "utterances": utts}

    def do(job, u):
        if "detail" in job:
            return note.make_note(job, material, meta, u)
        return explain.explain(job, material, meta, u)

    res, failed, u, _ = explain.run_parallel(do, jobs)
    usage.merge(u)
    times["④ 보완 설명·요약 노트"] = time.time() - t
    explanations = {k[1]: v for k, v in res.items() if k[0] == "exp"}
    notes.update({k[1]: v for k, v in res.items() if k[0] == "note"})

    today = dt.date.today().isoformat()
    state = {"material": material, "transcript_source": "paste", "date": today, "scores": scores,
             "priorities": pri, "questions": questions, "grading": grading, "answers": answers,
             "dont_know": dont_know, "mcq_choice": mcq_choice, "guessed": guessed, "confusion": confusion,
             "explanations": explanations, "notes": notes, "concepts": cres["concepts"], "meta_pages": meta,
             "utterances": utts}
    study, notes_doc = export.study_html(state), export.notes_html(state)
    files = {
        "공부순서_오답노트.html": study, "요약노트.html": notes_doc,
        "공부순서_오답노트.md": html_to_md(study), "요약노트.md": html_to_md(notes_doc),
    }
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")

    counts = {s: sum(1 for g in grading.values() if g["status"] == s) for s in ("앎", "헷갈림", "모름")}
    kinds = {k: sum(1 for q in questions.values() if q["kind"] == k) for k in ("서술형", "객관식")}
    fake = os.environ.get("BINTM_FAKE_AI") == "1"
    lines = [
        "# 결과 예시 (샘플 자료)", "",
        "앱을 열지 않고도 빈틈노트의 결과를 읽을 수 있게, 샘플 자료로 앱과 같은 순서를 돌려 만든 파일입니다.",
        "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다.", "",
        "| 파일 | 내용 |", "|---|---|",
        "| [공부순서_오답노트.md](공부순서_오답노트.md) · [HTML](공부순서_오답노트.html) | 공부 순서와 오답노트 |",
        "| [요약노트.md](요약노트.md) · [HTML](요약노트.html) | 시험 대비 요약 노트 |", "",
        "## 만든 조건", "",
        f"- 만든 날: {today}",
        f"- 모델: {'가짜 AI(BINTM_FAKE_AI=1, 모양 확인용)' if fake else config.LLM_MODEL}",
        "- 입력: `samples/` 가상 강의자료 20쪽 + 녹음 대본, 문제 형식 섞어서",
        "- 답: 앱의 \"예시 답 채우기 (샘플 체험용)\"와 같은 규칙(`core/diagnose.py`의 `example_answers`)",
        f"- 개념 {len(cres['concepts'])}개, 진단 문제 {len(questions)}개(서술형 {kinds['서술형']} · 객관식 {kinds['객관식']}), "
        f"문제 만들기 실패 {len(q_failed)}개, 채점 실패 {len(g_failed)}개",
        f"- 진단 결과: 앎 {counts['앎']} · 헷갈림 {counts['헷갈림']} · 모름 {counts['모름']}",
        f"- 보완 설명 {len(explanations)}개, 요약 노트 {len(notes)}개(AI가 쓴 것 {sum(1 for n in notes.values() if n['from_ai'])}개), "
        f"실패 {len(failed)}개", "",
        "## 단계별 시간 (이 스크립트 실행에서 잰 값)", "", "| 단계 | 초 |", "|---|---|",
    ]
    lines += [f"| {k} | {v:.1f} |" for k, v in times.items()]
    lines += ["", f"AI 호출 {usage.calls}번, 입력 토큰 {usage.input_tokens:,} · 출력 토큰 {usage.output_tokens:,}", "",
              "다시 만들기: `python scripts/make_example.py`"]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"files": sorted(p.name for p in out_dir.iterdir()), "counts": counts, "times": times,
            "usage": usage, "questions": len(questions), "kinds": kinds}


if __name__ == "__main__":
    r = run(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT_DIR)
    print("파일:", r["files"])
    print("진단:", r["counts"], r["kinds"])
    print("시간:", {k: round(v, 1) for k, v in r["times"].items()})
    print("사용량:", r["usage"])
