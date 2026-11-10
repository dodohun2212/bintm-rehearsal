"""T-08~T-11: 추출과 마스킹."""
import io

import pytest

from core.extract import MASK, MaterialError, check_material, extract, mask


def test_t08_sample_pdf_20_pages(material):
    assert material["n_pages"] == 20
    assert all(p["text"].strip() and p["text"] != "(글자 없음)" for p in material["pages"])
    assert "업힙" in material["pages"][14]["text"]  # 15쪽


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
    assert "연산" in m["pages"][2]["text"] and "O(log n)" in m["pages"][2]["text"]


def test_t10_scanned_pdf_is_e03():
    import pymupdf
    doc = pymupdf.open()
    for _ in range(5):
        page = doc.new_page()
        page.draw_rect(pymupdf.Rect(50, 50, 200, 200), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    data = doc.tobytes()
    with pytest.raises(MaterialError) as e:
        extract("scan.pdf", data)
    assert e.value.code == "E-03"


def test_t11_mask():
    out = mask("학번 2021136001, 010-1234-5678, a@b.ac.kr")
    assert "2021136001" not in out and "010-1234-5678" not in out and "a@b.ac.kr" not in out
    assert out.count(MASK) == 3
    assert mask("김교수님 8장") == "김교수님 8장"  # 사람 이름과 짧은 숫자는 그대로


def test_e01_e02_checks():
    with pytest.raises(MaterialError) as e:
        check_material("a.hwp", 10)
    assert e.value.code == "E-01"
    with pytest.raises(MaterialError) as e:
        check_material("a.pdf", 31 * 1024 * 1024)
    assert e.value.code == "E-02"
