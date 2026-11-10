"""F01 형식 검사, F02 페이지별 텍스트 추출, F04 마스킹."""
from __future__ import annotations

import hashlib
import io
import re

import config

MATERIAL_EXTS = ("pdf", "pptx")
AUDIO_EXTS = ("m4a", "mp3", "wav")

E01 = "PDF나 PPTX만 올릴 수 있어요. 한글(hwp)은 파일 → PDF로 저장해 주세요"
E02 = f"파일이 너무 커요(최대 {config.MAX_MATERIAL_MB}MB). 한 장만 따로 저장해 올려 주세요"
E03 = "이 PDF는 글자가 그림으로 들어 있어 읽을 수 없어요. 글자가 선택되는 PDF를 올려 주세요"
E04 = f"녹음은 m4a/mp3/wav {config.MAX_AUDIO_MB}MB까지예요. 길면 앞부분만 잘라 올리거나 대본 붙여넣기를 써 주세요"
E13 = f"앞 {config.MAX_PAGES}쪽만 분석해요. 한 장씩 올리면 더 정확해요"

NO_TEXT = "(글자 없음)"


class MaterialError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def check_material(name: str, size: int) -> None:
    if ext_of(name) not in MATERIAL_EXTS:
        raise MaterialError("E-01", E01)
    if size > config.MAX_MATERIAL_MB * 1024 * 1024:
        raise MaterialError("E-02", E02)


def check_audio(name: str, size: int) -> None:
    if ext_of(name) not in AUDIO_EXTS or size > config.MAX_AUDIO_MB * 1024 * 1024:
        raise MaterialError("E-04", E04)


def run_id(data: bytes) -> str:
    """파일 내용 해시 12자."""
    return hashlib.sha256(data).hexdigest()[:12]


# --- 마스킹 (F04) ---
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:01[016789]|0\d{1,2})[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)")
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


# --- 추출 (F02) ---
def extract_pdf(data: bytes) -> list[str]:
    import pymupdf
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [page.get_text() for page in doc]


def extract_pptx(data: bytes) -> list[str]:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    out = []
    for slide in prs.slides:
        lines = []
        for shape in slide.shapes:
            lines.extend(_shape_texts(shape))
        out.append("\n".join(x for x in lines if x.strip()))
    return out


def _shape_texts(shape) -> list[str]:
    lines = []
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        lines.append(shape.text_frame.text)
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    if hasattr(shape, "shapes"):  # 그룹 도형
        for sub in shape.shapes:
            lines.extend(_shape_texts(sub))
    return lines


def extract(name: str, data: bytes) -> dict:
    """material(6.1). 120쪽 넘으면 앞 120쪽만(truncated=True). 스캔본이면 E-03."""
    check_material(name, len(data))
    kind = ext_of(name)
    try:
        texts = extract_pdf(data) if kind == "pdf" else extract_pptx(data)
    except MaterialError:
        raise
    except Exception as exc:  # 깨진 파일
        raise MaterialError("E-01", E01) from exc
    if not texts:
        raise MaterialError("E-03", E03)
    empty = sum(1 for t in texts if not t.strip())
    if empty / len(texts) >= 0.8:
        raise MaterialError("E-03", E03)
    truncated = len(texts) > config.MAX_PAGES
    texts = texts[:config.MAX_PAGES]
    pages = [{"n": i + 1, "text": mask(t.strip()) if t.strip() else NO_TEXT} for i, t in enumerate(texts)]
    return {"name": name, "kind": kind, "n_pages": len(pages),
            "chars": sum(len(p["text"]) for p in pages), "pages": pages, "truncated": truncated}
