"""F01 파일 검사, F02 페이지별 텍스트 추출, F04 마스킹."""
from __future__ import annotations

import hashlib
import io
import re

import config


class ExtractError(Exception):
    code = "E-01"
    user_message = "PDF나 PPTX만 올릴 수 있어요. 한글(hwp)은 파일 → PDF로 저장해 주세요"


class UnsupportedFileError(ExtractError):
    code = "E-01"


class TooLargeError(ExtractError):
    code = "E-02"
    user_message = "파일이 너무 커요(최대 30MB). 한 장만 따로 저장해 올려 주세요"


class ScannedPDFError(ExtractError):
    code = "E-03"
    user_message = "이 PDF는 글자가 그림으로 들어 있어 읽을 수 없어요. 글자가 선택되는 PDF를 올려 주세요"


class AudioError(ExtractError):
    code = "E-04"
    user_message = "녹음은 m4a/mp3/wav 25MB까지예요. 길면 앞부분만 잘라 올리거나 대본 붙여넣기를 써 주세요"


EMPTY_PAGE = "(글자 없음)"


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def check_material(name: str, size: int) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("pdf", "pptx"):
        raise UnsupportedFileError(f"확장자 {ext}")
    if size > config.MAX_MATERIAL_MB * 1024 * 1024:
        raise TooLargeError(f"{size} bytes")
    return ext


def check_audio(name: str, size: int) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("m4a", "mp3", "wav") or size > config.MAX_AUDIO_MB * 1024 * 1024:
        raise AudioError(f"{ext}, {size} bytes")
    return ext


def extract_pdf(data: bytes) -> list[str]:
    import pymupdf as fitz

    with fitz.open(stream=data, filetype="pdf") as doc:
        return [page.get_text() for page in doc]


def _shape_texts(shape) -> list[str]:
    out = []
    if getattr(shape, "shape_type", None) == 6 and hasattr(shape, "shapes"):  # 그룹 도형
        for sub in shape.shapes:
            out.extend(_shape_texts(sub))
        return out
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        t = shape.text_frame.text.strip()
        if t:
            out.append(t)
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            for cell in row.cells:
                t = cell.text.strip()
                if t:
                    out.append(t)
    return out


def extract_pptx(data: bytes) -> list[str]:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    pages = []
    for slide in prs.slides:
        texts = []
        for shape in slide.shapes:
            texts.extend(_shape_texts(shape))
        pages.append("\n".join(texts))
    return pages


def extract(name: str, data: bytes) -> dict:
    """material 딕셔너리(6.1)를 만든다. 스캔본이면 ScannedPDFError."""
    kind = check_material(name, len(data))
    raw = extract_pdf(data) if kind == "pdf" else extract_pptx(data)
    if not raw:
        raise ScannedPDFError("쪽 없음")
    empty = sum(1 for t in raw if not t.strip())
    if empty / len(raw) >= 0.8:
        raise ScannedPDFError(f"글자 없는 쪽 {empty}/{len(raw)}")
    truncated = len(raw) > config.MAX_PAGES
    raw = raw[: config.MAX_PAGES]
    pages = [{"n": i + 1, "text": mask(t.strip()) if t.strip() else EMPTY_PAGE} for i, t in enumerate(raw)]
    return {
        "name": name,
        "kind": kind,
        "n_pages": len(pages),
        "chars": sum(len(p["text"]) for p in pages),
        "pages": pages,
        "truncated": truncated,
    }


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:0\d{1,2}[-. ]?\d{3,4}[-. ]?\d{4})(?!\d)")
_STUDENT_ID = re.compile(r"(?<!\d)\d{8,10}(?!\d)")


def mask(text: str) -> str:
    """학번(숫자 8~10자리), 전화번호, 이메일을 [마스킹]으로. 사람 이름은 건드리지 않는다."""
    if not text:
        return text
    text = _EMAIL.sub("[마스킹]", text)
    text = _PHONE.sub("[마스킹]", text)
    text = _STUDENT_ID.sub("[마스킹]", text)
    return text
