"""F01 업로드 검사, F02 페이지별 텍스트 추출, F04 개인정보 마스킹."""
from __future__ import annotations

import hashlib
import io
import re

import config

MATERIAL_EXTS = ("pdf", "pptx")
AUDIO_EXTS = ("m4a", "mp3", "wav")
EMPTY_PAGE = "(글자 없음)"
MASK = "[마스킹]"


class ScannedPdfError(Exception):
    """글자 없는 쪽이 80% 이상인 PDF (E-03)."""


class UnsupportedFileError(Exception):
    """지원하지 않는 형식 (E-01)."""


def file_ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def check_material(name: str, size: int) -> str | None:
    """강의자료 검사. 문제가 있으면 에러 번호(E-01/E-02)."""
    if file_ext(name) not in MATERIAL_EXTS:
        return "E-01"
    if size > config.MAX_MATERIAL_MB * 1024 * 1024:
        return "E-02"
    return None


def check_audio(name: str, size: int) -> str | None:
    if file_ext(name) not in AUDIO_EXTS or size > config.MAX_AUDIO_MB * 1024 * 1024:
        return "E-04"
    return None


def run_id_of(*parts: bytes | str | None) -> str:
    """파일 내용 해시 12자. 캐시 키로 쓴다."""
    h = hashlib.sha256()
    for part in parts:
        if part is None:
            continue
        h.update(part.encode("utf-8") if isinstance(part, str) else part)
    return h.hexdigest()[:12]


# ---------- F04 마스킹 ----------
# 학번: 바로 앞(공백·쌍점 포함 10자 안)에 "학번" 등이 있는 숫자 8~10자리만
_STUDENT_ID = re.compile(r"((?<![A-Za-z])(?:학번|학생번호|Student\s?ID|ID)[\s:：=]{0,10})(\d{8,10})(?!\d)", re.IGNORECASE)
_RRN = re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:01[016789]|0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def mask(text: str | None) -> str:
    """학번·주민등록번호·전화번호·이메일을 [마스킹]으로. 사람 이름과 일반 숫자는 그대로 둔다."""
    if not text:
        return text or ""
    out = _EMAIL.sub(MASK, text)
    out = _RRN.sub(MASK, out)
    out = _STUDENT_ID.sub(lambda m: m.group(1) + MASK, out)
    out = _PHONE.sub(MASK, out)
    return out


# ---------- F02 추출 ----------
def _pdf_pages(data: bytes) -> list[str]:
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [page.get_text() for page in doc]


def _pptx_pages(data: bytes) -> list[str]:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    pages = []
    for slide in prs.slides:
        lines: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    lines.append(text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    lines.append(" | ".join(cells))
        pages.append("\n".join(lines))
    return pages


def extract(name: str, data: bytes) -> dict:
    """강의자료 → material(6.1). 마스킹까지 한다. 스캔본이면 ScannedPdfError."""
    kind = file_ext(name)
    if kind == "pdf":
        raw = _pdf_pages(data)
    elif kind == "pptx":
        raw = _pptx_pages(data)
    else:
        raise UnsupportedFileError(kind)
    orig_pages = len(raw)
    if orig_pages == 0:
        raise ScannedPdfError("쪽이 없음")
    empty = sum(1 for t in raw if not t.strip())
    if empty / orig_pages >= 0.8:
        raise ScannedPdfError(f"글자 없는 쪽 {empty}/{orig_pages}")
    raw = raw[: config.MAX_PAGES]
    pages = [{"n": i + 1, "text": mask(t.strip()) if t.strip() else EMPTY_PAGE} for i, t in enumerate(raw)]
    return {
        "name": name,
        "kind": kind,
        "n_pages": len(pages),
        "orig_pages": orig_pages,
        "chars": sum(len(p["text"]) for p in pages),
        "pages": pages,
    }


def pages_text(material: dict, numbers: list[int] | None = None) -> str:
    """AI에 보낼 '=== 페이지 n ===' 덩어리. numbers가 있으면 그 쪽만."""
    wanted = set(numbers) if numbers is not None else None
    chunks = []
    for page in material["pages"]:
        if wanted is not None and page["n"] not in wanted:
            continue
        chunks.append(f"=== 페이지 {page['n']} ===\n{page['text']}")
    return "\n\n".join(chunks)
