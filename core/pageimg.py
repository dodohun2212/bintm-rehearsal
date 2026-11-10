# F09 강의자료 PDF 한 쪽 → JPEG. 화면에서만 쓰고 AI와 내려받는 파일에는 넣지 않는다.
def page_jpeg(data: bytes, n: int, width: int = 900) -> bytes | None:
    if not data or n < 1:
        return None
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if n > doc.page_count:
                return None
            page = doc[n - 1]
            zoom = width / page.rect.width
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            return pix.tobytes("jpeg")
    except Exception:
        return None
