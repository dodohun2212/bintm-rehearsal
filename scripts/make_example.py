"""샘플로 결과 예시 만들기 (F10, v1.10).

앱과 같은 순서(샘플 체험 → 진단(섞어서) → 예시 답 채우기 → 채점 → 우선순위 → 자동 보완 설명·요약 노트)를
core/ 함수만으로 돌려 docs/결과_예시/에 내려받기 HTML 2개, 같은 내용의 마크다운 2개, README를 쓴다.

사용:  python scripts/make_example.py            (실제 AI, 키는 환경변수 또는 .streamlit/secrets.toml)
       BINTM_FAKE_AI=1 python scripts/make_example.py   (저장된 결과로 모양만 확인)
"""
from __future__ import annotations

import datetime as _dt
import html
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from core.concepts import extract_concepts, meta_pages  # noqa: E402
from core.diagnose import (MCQ, choose_kind, diag_targets, evidence_pages, example_answers, grade_essay,  # noqa: E402
                           local_grading, make_question)
from core.explain import make_explanation  # noqa: E402
from core.export import notes_html, study_html  # noqa: E402
from core.extract import extract, mask  # noqa: E402
from core.llm import Usage, fake_mode, run_parallel  # noqa: E402
from core.note import detail_level, make_note, short_note  # noqa: E402
from core.priority import compute_priorities  # noqa: E402
from core.score import compute_scores  # noqa: E402
from core.utterances import find_utterances  # noqa: E402

SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TXT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
OUT = ROOT / "docs" / "결과_예시"


def load_key() -> None:
    if fake_mode() or os.environ.get("ANTHROPIC_API_KEY"):
        return
    p = ROOT / ".streamlit" / "secrets.toml"
    if p.exists():
        import tomllib
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            if data.get(k):
                os.environ[k] = str(data[k])


# ---------- HTML → 마크다운 ----------

def _table_md(tbl: str) -> str:
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", tbl, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        rows.append("| " + " | ".join(html.unescape(c).replace("|", "/") for c in cells) + " |")
    if not rows:
        return ""
    n = rows[0].count("|") - 1
    return "\n\n" + rows[0] + "\n|" + "---|" * n + "\n" + "\n".join(rows[1:]) + "\n\n"


def html_to_md(doc: str) -> str:
    """우리가 만든 내보내기 HTML을 GitHub에서 읽기 좋은 마크다운으로."""
    s = re.sub(r"<head>.*?</head>", "", doc, flags=re.S)
    s = re.sub(r"<style>.*?</style>", "", s, flags=re.S)
    s = re.sub(r"<table[^>]*>.*?</table>", lambda m: _table_md(m.group(0)), s, flags=re.S)
    s = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*/?>', lambda m: "\n(그림) " + m.group(1) + "\n", s)
    s = re.sub(r'<span class="bar">.*?</span>', "", s)
    s = re.sub(r"<div class='metric'>(.*?)<b>(.*?)</b></div>", r"\n- \1: **\2**", s)
    s = re.sub(r'<span class="pg">(.*?)</span>', r"(\1)", s)
    s = re.sub(r"""<span class=["']b[^"']*["']>(.*?)</span>""", r" `\1` ", s)
    s = re.sub(r"<h1>(.*?)</h1>", r"\n# \1\n", s, flags=re.S)
    s = re.sub(r"<h2>(.*?)</h2>", r"\n## \1\n", s, flags=re.S)
    s = re.sub(r"<h3>(.*?)</h3>", r"\n### \1\n", s, flags=re.S)
    s = re.sub(r"<summary>(.*?)</summary>", r"\n**\1**\n", s, flags=re.S)
    s = re.sub(r"<li>(.*?)</li>", r"\n- \1", s, flags=re.S)
    s = re.sub(r"<b>\s*(.*?)\s*</b>", r"**\1** ", s, flags=re.S)  # '**Q. **'는 GitHub에서 굵게 안 보임
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</(p|div|ul|details)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    # 줄바꿈 한 번도 GitHub에서 줄이 바뀌도록 줄 끝에 빈칸 두 개(표·제목 줄은 그대로)
    lines = s.strip().split("\n")
    for i in range(len(lines) - 1):
        cur, nxt = lines[i], lines[i + 1]
        if cur.strip() and nxt.strip() and not cur.startswith(("#", "|")) and not nxt.startswith("|"):
            lines[i] = cur + "  "
    return "\n".join(lines) + "\n"


# ---------- 앱과 같은 순서로 돌리기 ----------

def run(out_dir: Path | None = None) -> dict:
    out_dir = Path(out_dir or OUT)
    out_dir.mkdir(parents=True, exist_ok=True)
    load_key()
    total = Usage()
    times = {}

    t = time.time()
    material = extract(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes())
    transcript = mask(SAMPLE_TXT.read_text(encoding="utf-8"))
    u = Usage()
    cres = extract_concepts(material, u)
    concepts = cres["concepts"]
    meta = meta_pages(material["pages"], cres)
    utts = find_utterances(transcript, concepts, u)
    scores = compute_scores(concepts, utts, meta)["scores"]
    total.merge(u)
    times["분석(개념·강조·점수)"] = time.time() - t

    t = time.time()
    by_id = {c["id"]: c for c in concepts}
    pct = {r["concept_id"]: r["pct"] for r in scores}
    targets = diag_targets(scores)
    names = [by_id[c]["name"] for c in targets]
    tasks = {cid: (lambda uu, c=by_id[cid], k=choose_kind(pct[cid], "섞어서"):
                   make_question(c, k, evidence_pages(c, material, meta), names, uu)) for cid in targets}
    res, errs, u = run_parallel(tasks, 6)
    total.merge(u)
    questions = {cid: res[cid] for cid in targets if cid in res}
    times["문제 만들기"] = time.time() - t

    ex = example_answers([(cid, questions[cid]) for cid in targets if cid in questions])
    answers, dont_know, mcq_choice, guessed, confusion = {}, {}, {}, {}, {}
    for cid, a in ex.items():
        if "choice" in a:
            mcq_choice[cid], guessed[cid], confusion[cid] = a["choice"], a["guessed"], a["confusion"]
        else:
            answers[cid], dont_know[cid] = a["answer"], a["dont_know"]

    t = time.time()
    grading, gtasks = {}, {}
    for cid, q in questions.items():
        g = local_grading(q, answers.get(cid), dont_know.get(cid, False), mcq_choice.get(cid), guessed.get(cid, False))
        if g is not None:
            grading[cid] = g
        else:
            gtasks[cid] = (lambda uu, q=q, a=answers[cid], p=evidence_pages(by_id[cid], material, meta):
                           grade_essay(q, a, p, uu))
    res, gerrs, u = run_parallel(gtasks, 6)
    total.merge(u)
    grading.update(res)
    times["채점"] = time.time() - t

    t = time.time()
    pr = compute_priorities(scores, grading)
    conf_ids = [cid for cid in questions if questions[cid]["kind"] == MCQ and guessed.get(cid) and confusion.get(cid)]
    ex_ids = [p["concept_id"] for p in pr if p["action"] == "지금 당장"] + [p["concept_id"] for p in pr[:config.AUTO_EXPLAIN_TOP]] + conf_ids
    ex_ids = [c for i, c in enumerate(ex_ids) if c not in ex_ids[:i]]
    details = {p["concept_id"]: detail_level(p["action"], p["exam_pct"], p["status"]) for p in pr}
    prio = {p["concept_id"]: p for p in pr}
    tasks = {}
    for cid in ex_ids:
        q = questions.get(cid) if cid in grading else None
        ans = {"answer": answers.get(cid, ""), "dont_know": dont_know.get(cid, False),
               "choice": mcq_choice.get(cid), "guessed": guessed.get(cid, False)}
        conf = confusion.get(cid, "") if cid in conf_ids else ""
        tasks[("ex", cid)] = (lambda uu, c=by_id[cid], q=q, g=grading.get(cid), a=ans, cf=conf:
                              make_explanation(c, q, g, a, cf, evidence_pages(c, material, meta), uu))
    notes = {}
    for cid, d in details.items():
        if d == "짧게":
            notes[cid] = short_note(by_id[cid])
        else:
            tasks[("note", cid)] = (lambda uu, c=by_id[cid], d=d:
                                    make_note(c, d, prio[c["id"]], grading.get(c["id"]), utts,
                                              evidence_pages(c, material, meta), uu))
    res, xerrs, u = run_parallel(tasks, 8)
    total.merge(u)
    explanations = {cid: v for (k, cid), v in res.items() if k == "ex"}
    notes.update({cid: v for (k, cid), v in res.items() if k == "note"})
    times["보완 설명·요약 노트"] = time.time() - t

    state = {
        "priorities": pr, "scores": scores, "questions": questions, "grading": grading, "answers": answers,
        "dont_know": dont_know, "mcq_choice": mcq_choice, "guessed": guessed,
        "confusion": {cid: confusion.get(cid, "") for cid in conf_ids}, "explanations": explanations,
        "notes": notes, "concepts": concepts, "meta": meta, "utterances": utts, "transcript_source": "paste",
        "material_name": SAMPLE_PDF.name, "date": _dt.date.today().isoformat(),
    }
    study, notes_doc = study_html(state), notes_html(state)
    files = {
        "결과_예시_공부순서_오답노트.html": study,
        "결과_예시_요약노트.html": notes_doc,
        "결과_예시_공부순서_오답노트.md": html_to_md(study),
        "결과_예시_요약노트.md": html_to_md(notes_doc),
    }
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")

    status_count = {k: sum(1 for g in grading.values() if g["status"] == k) for k in ("앎", "헷갈림", "모름")}
    n_mcq = sum(1 for q in questions.values() if q["kind"] == MCQ)
    errors = len(errs) + len(gerrs) + len(xerrs)
    lines = [
        "# 결과 예시 (샘플 자료)",
        "",
        "앱을 열지 않고도 결과를 읽을 수 있도록, 샘플 자료로 앱과 같은 순서(샘플 체험 → 진단(섞어서) → 예시 답 채우기 → "
        "채점 → 공부 순서·보완 설명·요약 노트)를 돌려 만든 파일이다. 출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다.",
        "",
        "| 파일 | 내용 |",
        "|---|---|",
        "| [결과_예시_공부순서_오답노트.md](결과_예시_공부순서_오답노트.md) | 공부 순서·오답노트 (GitHub에서 읽기) |",
        "| [결과_예시_요약노트.md](결과_예시_요약노트.md) | 시험 대비 요약 노트 (GitHub에서 읽기) |",
        "| [결과_예시_공부순서_오답노트.html](결과_예시_공부순서_오답노트.html) | 앱에서 내려받는 파일 그대로 |",
        "| [결과_예시_요약노트.html](결과_예시_요약노트.html) | 앱에서 내려받는 파일 그대로 |",
        "",
        "## 만든 조건과 잰 값",
        "",
        f"- 만든 날: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 모델: {'가짜 AI(BINTM_FAKE_AI=1)' if fake_mode() else config.LLM_MODEL}",
        f"- 명령어: `python scripts/make_example.py`",
        f"- 개념 {len(concepts)}개, 진단 문제 {len(questions)}개(서술형 {len(questions) - n_mcq} · 객관식 {n_mcq})",
        f"- 예시 답 채점 결과: 앎 {status_count['앎']} · 헷갈림 {status_count['헷갈림']} · 모름 {status_count['모름']}",
        f"- 보완 설명 {len(explanations)}개, 요약 노트 {len(notes)}개",
        f"- 실패한 호출 묶음 항목: {errors}개",
        f"- AI 호출 {total.calls}번, 입력 {total.input_tokens:,} 토큰, 출력 {total.output_tokens:,} 토큰",
        "",
        "| 단계 | 걸린 시간(초) |",
        "|---|---|",
    ] + [f"| {k} | {v:.1f} |" for k, v in times.items()]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"files": sorted(list(files) + ["README.md"]), "status": status_count, "times": times,
            "usage": total, "questions": len(questions), "errors": errors}


if __name__ == "__main__":
    r = run()
    print("만든 파일:", ", ".join(r["files"]))
    print("상태:", r["status"], "문제:", r["questions"], "실패:", r["errors"])
    print("시간:", {k: round(v, 1) for k, v in r["times"].items()})
    print("사용량:", r["usage"])
