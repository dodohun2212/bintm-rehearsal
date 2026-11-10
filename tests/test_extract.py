"""T-08~T-11 추출과 마스킹."""
import io

import pytest

from core.extract import MASK, ExtractError, extract, mask


def test_t08_sample_pdf_20_pages(sample_material):
    assert sample_material["n_pages"] == 20
    assert all(p["text"].strip() and p["text"] != "(글자 없음)" for p in sample_material["pages"])
    assert "업힙" in sample_material["pages"][14]["text"]


def test_t09_pptx_three_slides_with_table():
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    for i in range(3):
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = f"슬라이드 {i + 1}"
    table = prs.slides[2].shapes.add_table(2, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
    table.cell(0, 0).text = "연산"
    table.cell(1, 1).text = "O(log n)"
    buf = io.BytesIO()
    prs.save(buf)
    m = extract("t.pptx", buf.getvalue())
    assert m["n_pages"] == 3 and m["kind"] == "pptx"
    assert "O(log n)" in m["pages"][2]["text"] and "연산" in m["pages"][2]["text"]


def test_t10_scanned_pdf_is_e03():
    import pymupdf
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    with pytest.raises(ExtractError) as e:
        extract("scan.pdf", doc.tobytes())
    assert e.value.code == "E-03"


def test_unsupported_format_is_e01():
    with pytest.raises(ExtractError) as e:
        extract("a.hwp", b"x")
    assert e.value.code == "E-01"


def test_t11_mask_personal_info():
    out = mask("학번 2021136001, 010-1234-5678, a@b.ac.kr, 900101-1234567")
    assert out.count(MASK) == 4
    for s in ("2021136001", "010-1234-5678", "a@b.ac.kr", "900101-1234567"):
        assert s not in out


def test_t11_mask_keeps_lecture_numbers():
    text = "INT_MAX = 2147483647, n = 10000000, 20240315"
    assert mask(text) == text
    assert mask("Student ID: 20211360") == "Student ID: " + MASK
    assert mask("홍길동 교수님") == "홍길동 교수님"
