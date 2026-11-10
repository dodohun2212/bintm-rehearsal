# F01 형식 검사, F02 페이지별 텍스트 추출, F04 개인정보 마스킹
import hashlib
import io
import re

import config

MATERIAL_EXT = {"pdf", "pptx"}
AUDIO_EXT = {"m4a", "mp3", "wav"}


class ExtractError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def run_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def check_material(name: str, size: int) -> str:
    ext = ext_of(name)
    if ext not in MATERIAL_EXT:
        raise ExtractError("E-01")
    if size > config.MAX_MATERIAL_MB * 1024 * 1024:
        raise ExtractError("E-02")
    return ext


def check_audio(name: str, size: int) -> str:
    ext = ext_of(name)
    if ext not in AUDIO_EXT or size > config.MAX_AUDIO_MB * 1024 * 1024:
        raise ExtractError("E-04")
    return ext


# ---- F04 마스킹 ----
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\d)(?:0\d{1,2})[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)")
_STUDENT_ID = re.compile(r"(?<!\d)\d{8,10}(?!\d)")
MASK = "[마스킹]"


def mask(text: str) -> str:
    """학번(숫자 8~10자리), 전화번호, 이메일을 [마스킹]으로. 사람 이름은 건드리지 않는다."""
    if not text:
        return text
    text = _EMAIL.sub(MASK, text)
    text = _PHONE.sub(MASK, text)
    text = _STUDENT_ID.sub(MASK, text)
    return text


# ---- F02 추출 ----
def _pdf_pages(data: bytes) -> list[str]:
    import pymupdf
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [page.get_text() for page in doc]


def _pptx_pages(data: bytes) -> list[str]:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    pages = []
    for slide in prs.slides:
        lines = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                lines.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    lines.append(" | ".join(cell.text for cell in row.cells))
        pages.append("\n".join(x for x in lines if x))
    return pages


def extract(data: bytes, name: str) -> dict:
    """PDF/PPTX → material {name, kind, n_pages, chars, pages[], truncated}. 마스킹까지 한다."""
    kind = check_material(name, len(data))
    try:
        raw = _pdf_pages(data) if kind == "pdf" else _pptx_pages(data)
    except ExtractError:
        raise
    except Exception as e:
        raise ExtractError("E-01", f"파일을 열지 못함: {e}") from e
    truncated = len(raw) > config.MAX_PAGES
    raw = raw[:config.MAX_PAGES]
    if not raw:
        raise ExtractError("E-03")
    empty = sum(1 for t in raw if not t.strip())
    if empty / len(raw) >= 0.8:
        raise ExtractError("E-03")
    pages = []
    for i, t in enumerate(raw, start=1):
        t = mask(t.strip()) if t.strip() else "(글자 없음)"
        pages.append({"n": i, "text": t})
    return {"name": name, "kind": kind, "n_pages": len(pages),
            "chars": sum(len(p["text"]) for p in pages), "pages": pages, "truncated": truncated}


def pages_text(material: dict, nums: list[int] | None = None) -> str:
    """페이지마다 '=== 페이지 n ===' 줄을 붙여 한 덩어리로."""
    want = set(nums) if nums is not None else None
    parts = []
    for p in material["pages"]:
        if want is None or p["n"] in want:
            parts.append(f"=== 페이지 {p['n']} ===\n{p['text']}")
    return "\n\n".join(parts)
