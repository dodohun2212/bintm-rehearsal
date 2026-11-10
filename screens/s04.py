"""S04 우선순위 보완 학습: 공부 순서·오답노트(탭 1), 시험 대비 요약 노트(탭 2), 내려받기 2개."""
from __future__ import annotations

import streamlit as st

from core import explain, export, note, priority
from core.guard import kst_today
from core.pageimg import page_jpeg
from screens import common as C

ACTION_HELP = export.ACTION_NOTE


@st.cache_data(show_spinner=False, max_entries=200)
def cached_page(run_id: str, n: int, _data: bytes) -> bytes | None:
    """쪽 그림 캐시. PDF 바이트는 해시하지 않는 인자로 넘긴다."""
    return page_jpeg(_data, n)


def _ctx():
    s = st.session_state
    return {c["id"]: c for c in s["concepts"]}, {p["concept_id"]: p for p in s["priorities"]}


def export_data() -> dict:
    s = st.session_state
    return {
        "material_name": (s["material"] or {}).get("name"), "today": kst_today().isoformat(),
        "transcript_source": s["transcript_source"], "scores": s["scores"], "priorities": s["priorities"],
        "concepts": s["concepts"], "questions": s["questions"], "grading": s["grading"],
        "explanations": s["explanations"], "notes": s["notes"], "utterances": s["utterances"],
        "answers": s["answers"], "mcq_choice": s["mcq_choice"], "guessed": s["guessed"], "confusion": s["confusion"],
        "note_order": note.lecture_order(s["concepts"], s["meta_pages"]),
    }


def download_buttons(where: str) -> None:
    data = export_data()
    day = data["today"]
    c1, c2 = st.columns(2)
    c1.download_button("📥 공부 순서·오답노트 내려받기", export.study_html(data), export.study_filename(day),
                       mime="text/html", key=f"dl_study_{where}", width="stretch", on_click="ignore")
    c2.download_button("📒 요약 노트 내려받기", export.notes_html(data), export.notes_filename(day),
                       mime="text/html", key=f"dl_notes_{where}", width="stretch", on_click="ignore")


def make_explanations(ids: list[str]) -> None:
    """보완 설명을 동시에 만든다. 스레드에 넘길 값은 여기서 미리 꺼낸다."""
    s = st.session_state
    concepts, prios = _ctx()
    material, meta = s["material"], s["meta_pages"]
    items = {cid: dict(concept=concepts[cid], prio=prios[cid], q=s["questions"].get(cid), grading=s["grading"].get(cid),
                       answer=s["answers"].get(cid, ""), choice=s["mcq_choice"].get(cid),
                       guessed=s["guessed"].get(cid, False),
                       confusion=s["confusion"].get(cid, "") if s["guessed"].get(cid) else "")
             for cid in ids}
    if not items:
        return
    if C.ai_blocked():
        C.show_error("E-17")
        return

    def work(a, usage):
        return explain.make_explanation(a["concept"], a["prio"], a["q"], a["grading"], material, meta,
                                        a["answer"], a["choice"], a["guessed"], a["confusion"], usage)

    with st.spinner("보완 설명을 만들고 있어요…"):
        results, errors, usage, secs = C.run_parallel(work, items, "보완 설명", workers=8)
    C.add_usage(usage, "보완 설명", secs)
    s["explanations"].update(results)
    s["explain_failed"] = sorted(set(s["explain_failed"]) - set(results) | set(errors))
    if errors:
        s["explain_error"] = C.first_error_text(errors)


def note_plan() -> dict[str, str]:
    s = st.session_state
    concepts, prios = _ctx()
    out = {}
    for cid in note.lecture_order(s["concepts"], s["meta_pages"]):
        p = prios[cid]
        out[cid] = note.detail_level(p["action"], p["exam_pct"], p["status"])
    return out


def make_notes(ids: list[str]) -> None:
    s = st.session_state
    concepts, prios = _ctx()
    plan = note_plan()
    material, meta, utts = s["material"], s["meta_pages"], s["utterances"]
    for cid in ids:  # 짧게는 AI를 부르지 않는다
        if plan[cid] == "짧게":
            s["notes"][cid] = note.short_note(concepts[cid], meta)
    items = {cid: dict(concept=concepts[cid], detail=plan[cid], prio=prios[cid], grading=s["grading"].get(cid))
             for cid in ids if plan[cid] != "짧게"}
    if not items:
        return
    if C.ai_blocked():
        C.show_error("E-17")
        return

    def work(a, usage):
        return note.make_note(a["concept"], a["detail"], a["prio"], a["grading"], utts, material, meta, usage)

    with st.spinner("시험 대비 요약 노트를 만들고 있어요…"):
        results, errors, usage, secs = C.run_parallel(work, items, "요약 노트", workers=8)
    C.add_usage(usage, "요약 노트", secs)
    s["notes"].update(results)
    s["notes_failed"] = sorted(set(s["notes_failed"]) - set(results) | set(errors))
    if errors:
        s["notes_error"] = C.first_error_text(errors)


def explanation_html(e: dict) -> str:
    out = [f'<div class="bt-gap"><b>내가 놓친 점</b> {C.paragraphs(e.get("my_gap"))}</div>']
    if e.get("confusion"):
        reply = C.paragraphs(e["confusion_reply"]) if e.get("confusion_reply") else ""
        out.append(f'<div class="bt-reply"><b>💬 내가 헷갈린 점에 대한 답</b><div>“{C.esc(e["confusion"])}”</div>{reply}</div>')
    out.append(C.paragraphs(e.get("explanation")))
    if e.get("not_found"):
        out.append(f'<div class="bt-nf">올린 자료에서 찾지 못함 — {C.esc(e.get("not_found_note"))}. '
                   "교재 다른 장이나 수업 노트를 확인하세요.</div>")
    out.append(f"<div>다시 볼 페이지 {C.page_badges(e.get('check_pages'))}</div>")
    return "".join(out)


def original_pages(pages: list[int], key: str) -> None:
    data = st.session_state["material_bytes"]
    if not data or not pages:
        return
    shown = pages[:2]
    with st.expander("강의자료 원본 보기 · " + ", ".join(f"p.{p}" for p in shown)):
        for p in shown:
            img = cached_page(st.session_state["run_id"], p, data)
            if img:
                st.image(img, caption=f"p.{p}", width="stretch")


def concept_card(p: dict) -> None:
    s = st.session_state
    cid = p["concept_id"]
    q, g, e = s["questions"].get(cid), s["grading"].get(cid), s["explanations"].get(cid)
    with st.container(border=True):
        C.html_block(f'<div><b>{p["rank"]}. {C.esc(p["name"])}</b></div><div>{C.status_badge(p["status"])}'
                     f'{C.badge("출제 점수 " + str(p["exam_pct"]))}{C.badge("우선순위 " + str(p["priority"]), "b-blue")}</div>')
        if q and g:
            with st.expander(f"📝 내 문제와 답 다시 보기 · {g['status']} {g['score']}/10"):
                answer = s["answers"].get(cid, "")
                block = export.question_block(q, g, answer, s["mcq_choice"].get(cid), s["guessed"].get(cid, False),
                                              s["confusion"].get(cid, "") if s["guessed"].get(cid) else "")
                C.html_block(block)
        if e:
            C.html_block(explanation_html(e))
            original_pages(e.get("check_pages") or [], cid)
        elif cid in s["explain_failed"]:
            C.html_block('<div class="bt-red">설명을 만들지 못했어요.</div>')
            if st.button("설명 다시 만들기", key=f"re_ex_{cid}"):
                make_explanations([cid])
                st.rerun()
        else:
            if st.button("설명 보기", key=f"ex_{cid}"):
                make_explanations([cid])
                st.rerun()


def tab_study() -> None:
    s = st.session_state
    groups = priority.group_by_action(s["priorities"])
    for action in ("지금 당장", "다음"):
        rows = groups[action]
        if not rows:
            continue
        st.markdown(f"### {action} · {len(rows)}개")
        st.caption(ACTION_HELP[action])
        if action == "다음":
            todo = [p["concept_id"] for p in rows if p["concept_id"] not in s["explanations"]]
            if todo and st.button(f"'다음' 개념 설명 {len(todo)}개 한 번에 보기"):
                make_explanations(todo)
                st.rerun()
        for p in rows:
            concept_card(p)
    review = groups["복습만"]
    if review:
        st.markdown(f"### 복습만 · {len(review)}개")
        st.caption(ACTION_HELP["복습만"])
        opened, folded = priority.split_review(review, {k: v for k, v in s["confusion"].items() if s["guessed"].get(k)})
        for p in opened:  # 헷갈린 점을 적은 개념은 펼쳐 둔다
            concept_card(p)
        if folded:
            with st.expander(f"복습만 {len(folded)}개 펼치기"):
                for p in folded:
                    concept_card(p)
    with st.expander("전체 표로 보기"):
        rows = "".join(
            f"<tr><td>{p['rank']}</td><td>{C.esc(p['name'])}</td>"
            f"<td><span class='bt-bar'><i style='width:{p['exam_pct']}%'></i></span> {p['exam_pct']}점</td>"
            f"<td>{C.status_badge(p['status'])}</td>"
            f"<td><span class='bt-bar'><i style='width:{p['priority']}%'></i></span> {p['priority']}</td>"
            f"<td>{p['action']}<br><small>{p['exam_pct']} × (1 − {p['understanding']})</small></td></tr>"
            for p in s["priorities"])
        C.html_block("<div style='overflow-x:auto'><table style='width:100%;border-collapse:collapse'>"
                     "<tr><th>순위</th><th>개념</th><th>출제 점수</th><th>이해 상태</th><th>우선순위</th><th>권장</th></tr>"
                     f"{rows}</table></div>")


def tab_notes() -> bool:
    """요약 노트 탭. 새로 만들었으면 True(위쪽 내려받기 버튼을 새 값으로 다시 그리려고)."""
    s = st.session_state
    concepts, prios = _ctx()
    plan = note_plan()
    todo = [cid for cid in plan if cid not in s["notes"] and cid not in s["notes_failed"]]
    made = False
    if todo:
        make_notes(todo)
        made = True
    counts = [(d, sum(1 for cid in plan if plan[cid] == d)) for d in note.DETAILS]
    C.stats(counts)
    if s["notes_failed"]:
        st.error(f"요약 노트 {len(s['notes_failed'])}개를 만들지 못했어요.")
        if s["notes_error"]:
            with st.expander("자세한 오류"):
                st.code(s["notes_error"][:2000])
    for i, cid in enumerate(plan, start=1):
        c, p, n = concepts[cid], prios[cid], s["notes"].get(cid)
        with st.container(border=True):
            C.html_block(f'<div><b>{i}. {C.esc(c["name"])}</b></div><div>{C.badge(plan[cid], "b-blue")}'
                         f'{C.badge("출제 점수 " + str(p["exam_pct"]))}{C.status_badge(p["status"])}</div>')
            if n is None:
                C.html_block('<div class="bt-red">요약 노트를 만들지 못했어요.</div>')
                if st.button("요약 노트 다시 만들기", key=f"re_note_{cid}"):
                    s["notes_failed"] = [x for x in s["notes_failed"] if x != cid]
                    make_notes([cid])
                    st.rerun()
                continue
            body = [C.paragraphs(n.get("summary"))]
            if n.get("key_points"):
                body.append("<b>핵심</b><ul>" + "".join(f"<li>{export.rich(x)}</li>" for x in n["key_points"]) + "</ul>")
            if n.get("pitfalls"):
                body.append("<b>자주 하는 실수</b><ul>" + "".join(f"<li>{export.rich(x)}</li>" for x in n["pitfalls"]) + "</ul>")
            quotes = note.professor_quotes(s["utterances"], cid)
            if quotes and plan[cid] != "짧게":
                body.append("<b>교수님 말</b><ul>" + "".join(
                    f'<li>“{C.esc(u["quote"])}” <span class="rec">녹음</span></li>' for u in quotes) + "</ul>")
            body.append(f"<div>근거 {C.page_badges(n.get('source_pages'))}</div>")
            C.html_block("".join(body))
            original_pages(n.get("source_pages") or [], f"n_{cid}")
    return made


def render() -> None:
    s = st.session_state
    C.header(4, "우선순위 보완 학습", "출제 점수 × 모르는 정도로 공부 순서를 정하고, 자료를 근거로 빈틈을 메워요.")
    s["priorities"] = priority.compute_priorities(s["scores"], s["grading"])
    groups = priority.group_by_action(s["priorities"])
    confusion = {k: v for k, v in s["confusion"].items() if s["guessed"].get(k)}
    auto = [cid for cid in priority.auto_explain_ids(s["priorities"], confusion)
            if cid not in s["explanations"] and cid not in s["explain_failed"]]
    if auto:
        make_explanations(auto)  # 보완 설명을 먼저 만든다
    C.stats([(a, len(groups[a])) for a in groups])
    download_buttons("top")
    st.caption(C.DISCLAIMER)
    if s["explain_failed"] and s["explain_error"]:
        with st.expander(f"보완 설명 {len(s['explain_failed'])}개를 만들지 못했어요 · 자세한 오류"):
            st.code(s["explain_error"][:2000])
    t1, t2 = st.tabs(["🎯 공부 순서와 오답노트", "📒 시험 대비 요약 노트"])
    with t1:
        tab_study()
    with t2:
        made = tab_notes()
    if made:
        st.rerun()  # 위쪽 내려받기 버튼에 새 요약 노트가 들어가게 다시 그린다
    download_buttons("bottom")
    if st.button("다른 자료로 다시"):
        C.reset_all()
        st.rerun()
