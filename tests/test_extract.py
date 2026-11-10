# T-08~T-11 추출과 마스킹
import io

import pytest

from core.extract import ExtractError, check_material, extract, mask


def test_t08_pdf_extract(material):
    assert material["n_pages"] == 20
    assert all(p["text"].strip() and p["text"] != "(글자 없음)" for p in material["pages"])
    assert "업힙" in material["pages"][14]["text"]


def test_t09_pptx_extract():
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    for i in range(3):
        s = prs.slides.add_slide(prs.slide_layouts[5])
        s.shapes.title.text = f"슬라이드 {i + 1}"
    tbl = prs.slides[2].shapes.add_table(2, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
    tbl.cell(0, 0).text = "연산"
    tbl.cell(1, 1).text = "O(log n)"
    buf = io.BytesIO()
    prs.save(buf)
    m = extract(buf.getvalue(), "t.pptx")
    assert m["n_pages"] == 3
    assert "O(log n)" in m["pages"][2]["text"] and "연산" in m["pages"][2]["text"]


def test_t10_scanned_pdf():
    import pymupdf
    doc = pymupdf.open()
    for _ in range(5):
        doc.new_page()
    with pytest.raises(ExtractError) as e:
        extract(doc.tobytes(), "scan.pdf")
    assert e.value.code == "E-03"


def test_t11_mask():
    out = mask("학번 2021136001, 010-1234-5678, a@b.ac.kr")
    assert out.count("[마스킹]") == 3
    assert "2021136001" not in out and "010-1234-5678" not in out and "a@b.ac.kr" not in out


def test_e01_e02_checks():
    with pytest.raises(ExtractError) as e:
        check_material("x.hwp", 10)
    assert e.value.code == "E-01"
    with pytest.raises(ExtractError) as e:
        check_material("x.pdf", 31 * 1024 * 1024)
    assert e.value.code == "E-02"
