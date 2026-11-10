"""F02 PDF/PPTX → 페이지별 텍스트, F04 개인정보 마스킹."""
from __future__ import annotations

import hashlib
import io
import re

import config

MASK = "[마스킹]"
NO_TEXT = "(글자 없음)"

_RRN = re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)")
_PHONE = re.compile(r"(?<![\d.])(?:01[016789]|0[2-6]\d?)[- ]?\d{3,4}[- ]?\d{4}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
# 학번: 바로 앞(공백·쌍점 포함 10자 안)에 "학번" 등이 있는 숫자 8~10자리만
_STUDENT_ID = re.compile(r"(학번|학생번호|Student\s?ID|(?<![A-Za-z])ID)([^\d\n]{0,10}?)(?<!\d)(\d{8,10})(?!\d)")


class ExtractError(Exception):
    """추출 실패. code는 화면 에러 번호."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def run_id_of(*parts: bytes | str | None) -> str:
    """파일 내용 해시 12자 (캐시 키)."""
    h = hashlib.sha256()
    for p in parts:
        if p is None:
            continue
        h.update(p if isinstance(p, bytes) else p.encode("utf-8"))
    return h.hexdigest()[:12]


def mask(text: str | None) -> str:
    """학번·주민등록번호·전화번호·이메일을 [마스킹]으로. 사람 이름과 일반 숫자는 그대로."""
    if not text:
        return text or ""
    text = _RRN.sub(MASK, text)
    text = _EMAIL.sub(MASK, text)
    text = _STUDENT_ID.sub(lambda m: m.group(1) + m.group(2) + MASK, text)
    text = _PHONE.sub(MASK, text)
    return text


def _pdf_pages(data: bytes) -> list[str]:
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [page.get_text() for page in doc]


def _pptx_pages(data: bytes) -> list[str]:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    pages = []
    for slide in prs.slides:
        parts: list[str] = []
        for shape in slide.shapes:
            parts.extend(_shape_texts(shape))
        pages.append("\n".join(p for p in parts if p.strip()))
    return pages


def _shape_texts(shape) -> list[str]:
    out: list[str] = []
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        out.append(shape.text_frame.text)
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            for cell in row.cells:
                out.append(cell.text)
    if hasattr(shape, "shapes"):  # 그룹 도형
        for sub in shape.shapes:
            out.extend(_shape_texts(sub))
    return out


def extract(name: str, data: bytes) -> dict:
    """material(6.1) 형식으로. 스캔본이면 ExtractError("E-03")."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("pdf", "pptx"):
        raise ExtractError("E-01", ext)
    if len(data) > config.MAX_MATERIAL_MB * 1024 * 1024:
        raise ExtractError("E-02", str(len(data)))
    try:
        raw = _pdf_pages(data) if ext == "pdf" else _pptx_pages(data)
    except Exception as e:  # noqa: BLE001
        raise ExtractError("E-01", f"파일을 열지 못함: {e}") from e
    original = len(raw)
    if original == 0:
        raise ExtractError("E-03", "쪽 없음")
    empty = sum(1 for t in raw if not t.strip())
    if empty / original >= 0.8:
        raise ExtractError("E-03", f"글자 없는 쪽 {empty}/{original}")
    raw = raw[: config.MAX_PAGES]
    pages = [{"n": i + 1, "text": mask(t.strip()) if t.strip() else NO_TEXT} for i, t in enumerate(raw)]
    return {"name": name, "kind": ext, "n_pages": len(pages), "original_pages": original,
            "chars": sum(len(p["text"]) for p in pages), "pages": pages}


def is_scanned_ratio(texts: list[str]) -> bool:
    if not texts:
        return True
    return sum(1 for t in texts if not t.strip()) / len(texts) >= 0.8


def material_text(material: dict) -> str:
    """AI에 보낼 때: 페이지마다 '=== 페이지 n ===' 줄을 앞에 붙인다."""
    return "\n\n".join(f"=== 페이지 {p['n']} ===\n{p['text']}" for p in material["pages"])


def pages_text(material: dict, pages: list[int]) -> str:
    want = set(pages)
    return "\n\n".join(f"=== 페이지 {p['n']} ===\n{p['text']}" for p in material["pages"] if p["n"] in want)
