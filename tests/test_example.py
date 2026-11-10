"""T-49 결과 예시 만들기와 마크다운 변환 (가짜 AI)."""
from scripts.make_example import html_to_md, run


def test_t49_make_example(tmp_path):
    r = run(tmp_path)
    assert len(r["files"]) == 5 and all((tmp_path / f).exists() for f in r["files"])
    assert all(r["status"][k] > 0 for k in ("앎", "헷갈림", "모름"))
    md = (tmp_path / "결과_예시_공부순서_오답노트.md").read_text(encoding="utf-8")
    assert "<div" not in md and "data:image" not in md and "<span" not in md
    assert md.startswith("# ") or "\n# " in md
    assert "(p." in md and "`" in md
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "모델" in readme and "앎" in readme


def test_t49_md_conversion():
    html = ("<html><head><style>x{}</style></head><body><h1>제목</h1><h2>1. 공부 순서</h2>"
            "<p>설명 <span class=\"pg\">p.5</span></p><span class=\"b ok\">앎</span>"
            "<img alt=\"이진 트리: [A, B]\" src=\"data:image/svg+xml;base64,AAA\"/>"
            "<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table></body></html>")
    md = html_to_md(html)
    assert "# 제목" in md and "## 1. 공부 순서" in md and "(p.5)" in md and "`앎`" in md
    assert "(그림) 이진 트리: [A, B]" in md and "| a | b |" in md and "|---|---|" in md
    assert "data:image" not in md and "<" not in md
