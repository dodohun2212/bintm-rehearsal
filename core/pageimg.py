"""F09 강의자료 PDF 한 쪽 → JPEG. 화면에서만 쓰고 AI·내려받는 파일에는 넣지 않는다."""
from __future__ import annotations


def render_page(pdf_bytes: bytes | None, n: int, width: int = 900) -> bytes | None:
    """n쪽(1부터)을 가로 width px JPEG로. PDF가 아니거나 범위 밖이면 None."""
    if not pdf_bytes or n < 1:
        return None
    try:
        import pymupdf

        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            if n > doc.page_count:
                return None
            page = doc[n - 1]
            zoom = width / max(1.0, page.rect.width)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            return pix.tobytes("jpeg")
    except Exception:  # noqa: BLE001 (PPTX 등 PDF가 아니면 그림 없음)
        return None
