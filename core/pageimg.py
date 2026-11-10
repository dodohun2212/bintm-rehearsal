"""F09 강의자료 PDF 한 쪽 → JPEG. 화면에서만 쓰고 AI와 내려받는 파일에는 넣지 않는다."""
from __future__ import annotations

PAGE_WIDTH = 900


def page_jpeg(data: bytes | None, page_no: int, width: int = PAGE_WIDTH) -> bytes | None:
    """PDF가 아니거나 쪽 번호가 범위 밖이면 None."""
    if not data or page_no < 1:
        return None
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if page_no > doc.page_count:
                return None
            page = doc[page_no - 1]
            zoom = width / max(page.rect.width, 1)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            return pix.tobytes("jpeg")
    except Exception:
        return None
