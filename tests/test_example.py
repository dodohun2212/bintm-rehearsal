"""T-49 결과 예시 만들기·마크다운 변환 (가짜 AI)."""
import sys

from tests.conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import make_example  # noqa: E402


def test_t49_make_example_fake(tmp_path):
    r = make_example.run_sample(tmp_path)
    files = sorted(p.name for p in tmp_path.iterdir())
    assert "README.md" in files and make_example.STUDY_MD in files and make_example.NOTES_MD in files
    assert len([f for f in files if f.endswith(".html")]) == 2
    md = (tmp_path / make_example.STUDY_MD).read_text(encoding="utf-8")
    assert "## 1. 공부 순서" in md and "## 2. 오답노트" in md and "(p." in md and "<span" not in md
    assert "(그림)" in md or "| " in md
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "단계별 시간" in readme and "AI 호출" in readme
    assert set(r["counts"]) == {"앎", "헷갈림", "모름"}


def test_t49_from_html(tmp_path):
    src = tmp_path / "src"
    make_example.run_sample(src)
    htmls = sorted(p for p in src.iterdir() if p.suffix == ".html")
    study = next(p for p in htmls if "공부순서" in p.name)
    notes = next(p for p in htmls if "요약노트" in p.name)
    out = tmp_path / "out"
    make_example.main(["--from-html", str(study), str(notes), "--out", str(out), "--note", "⑤ 사용량 메모"])
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "배포 앱" in readme and "⑤ 사용량 메모" in readme and "지금 당장" in readme
    assert (out / make_example.NOTES_MD).read_text(encoding="utf-8").startswith("# 빈틈노트 시험 대비 요약 노트")


def test_md_converter_badges_and_tables():
    md = make_example.html_to_md("<h2>제목</h2><p>글 <span class='bt-pg'>p.3</span> "
                                 "<span class='bt-bd bt-bd-ok'>앎</span></p><table><tr><th>a</th></tr><tr><td>1</td></tr></table>")
    assert "## 제목" in md and "(p.3)" in md and "`앎`" in md and "| a |" in md
