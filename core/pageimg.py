"""F09 강의자료 PDF 한 쪽 → JPEG. 화면에서만 쓰고 AI·내려받는 파일에는 넣지 않는다."""
from __future__ import annotations


def page_jpeg(data: bytes | None, n: int, width: int = 900) -> bytes | None:
    """PDF n쪽(1부터)을 가로 width px JPEG로. PDF가 아니거나 범위 밖이면 None."""
    if not data or n < 1:
        return None
    try:
        import pymupdf as fitz

        with fitz.open(stream=data, filetype="pdf") as doc:
            if n > doc.page_count:
                return None
            page = doc[n - 1]
            zoom = width / page.rect.width
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            return pix.tobytes("jpeg")
    except Exception:
        return None
