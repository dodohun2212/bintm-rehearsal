"""본문 속 (p.n) 인용 검사. 근거 페이지 밖의 번호는 그 표시만 지운다."""
from __future__ import annotations

import re

# (p.15) (p.15, p.17) (p.15·17) (p.15-16)
_CITE = re.compile(r"\s?\(\s*p\.\s*\d+(?:\s*[,·~\-–]\s*(?:p\.\s*)?\d+)*\s*\)")
_NUM = re.compile(r"\d+")
_REC = re.compile(r"\s?\(녹음\)")


def strip_bad_cites(text: str | None, allowed) -> str:
    """allowed 안의 쪽만 남긴다. 남는 쪽이 없으면 괄호째 지운다."""
    if not text:
        return text or ""
    allowed = set(allowed)

    def repl(m: re.Match) -> str:
        nums = [int(n) for n in _NUM.findall(m.group(0))]
        keep = []
        for n in nums:
            if n in allowed and n not in keep:
                keep.append(n)
        if not keep:
            return ""
        lead = " " if m.group(0).startswith(" ") else ""
        return lead + "(" + ", ".join(f"p.{n}" for n in keep) + ")"

    return _CITE.sub(repl, text)


def cited_pages(text: str | None) -> list[int]:
    out: list[int] = []
    for m in _CITE.finditer(text or ""):
        for n in _NUM.findall(m.group(0)):
            if int(n) not in out:
                out.append(int(n))
    return out


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _quote_core(q: str) -> str:
    return _nospace(q).rstrip(".!?…,~")


def check_recording_marks(text: str | None, quotes: list[str]) -> str:
    """AI가 쓴 "(녹음)"은 그 문장에 교수님 말 인용이 실제로 있을 때만 남기고 아니면 지운다."""
    if not text or "(녹음)" not in text:
        return text or ""
    cores = [c for c in (_quote_core(q) for q in quotes or []) if len(c) >= 4]
    out = []
    last = 0
    for m in _REC.finditer(text):
        before = text[last:m.start()]
        # 이 표시가 붙은 문장: 앞 문장 끝(. ! ? 줄바꿈) 뒤부터
        seg_start = max(before.rfind(". "), before.rfind("다. "), before.rfind("\n"), before.rfind("? "),
                        before.rfind("! "))
        sentence = _nospace(before[seg_start + 1:] if seg_start >= 0 else before)
        ok = any(c in sentence for c in cores)
        if not ok:
            # 따옴표로 묶은 부분이 교수님 말의 일부인지도 본다
            for q in re.findall(r"[‘'“\"]([^’'”\"]{4,})[’'”\"]", before[seg_start + 1:] if seg_start >= 0 else before):
                qn = _quote_core(q)
                if len(qn) >= 4 and any(qn in _nospace(full) for full in quotes or []):
                    ok = True
                    break
        out.append(before)
        out.append(m.group(0) if ok else "")
        last = m.end()
    out.append(text[last:])
    return "".join(out)
