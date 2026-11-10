"""T-08~T-11: 추출·스캔본·마스킹."""
import io

import pytest

from core.extract import ScannedPdfError, check_audio, check_material, extract, mask, pages_text
from tests.conftest import SAMPLE_PDF


def test_t08_sample_pdf_has_20_pages(sample_material):
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
    material = extract("test.pptx", buf.getvalue())
    assert material["n_pages"] == 3
    assert "O(log n)" in material["pages"][2]["text"]
    assert "연산" in material["pages"][2]["text"]


def test_t10_scanned_pdf_detected():
    import pymupdf

    doc = pymupdf.open()
    for _ in range(5):
        doc.new_page()
    with pytest.raises(ScannedPdfError):
        extract("scan.pdf", doc.tobytes())


def test_t11_mask_personal_info():
    text = "학번 2021136001, 010-1234-5678, a@b.ac.kr, 900101-1234567"
    out = mask(text)
    assert out.count("[마스킹]") == 4
    for raw in ("2021136001", "1234-5678", "a@b.ac.kr", "900101-1234567"):
        assert raw not in out


def test_t11_mask_keeps_lecture_numbers():
    text = "INT_MAX = 2147483647, n = 10000000, 20240315"
    assert mask(text) == text


def test_mask_student_id_needs_context():
    assert mask("Student ID: 20211360") == "Student ID: [마스킹]"
    assert mask("배열 크기 20211360") == "배열 크기 20211360"


def test_upload_checks():
    assert check_material("a.hwp", 10) == "E-01"
    assert check_material("a.pdf", 31 * 1024 * 1024) == "E-02"
    assert check_material("a.PDF", 1000) is None
    assert check_audio("a.m4a", 26 * 1024 * 1024) == "E-04"
    assert check_audio("a.wav", 1000) is None


def test_pages_text_marks_pages(sample_material):
    text = pages_text(sample_material, [3, 15])
    assert "=== 페이지 3 ===" in text and "=== 페이지 15 ===" in text
    assert "=== 페이지 4 ===" not in text
