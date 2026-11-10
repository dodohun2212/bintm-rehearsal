# T-49 결과 예시 만들기와 마크다운 변환 (가짜 AI)
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location("make_example", ROOT / "scripts" / "make_example.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_t49_run(tmp_path):
    m = _mod()
    r = m.run(tmp_path)
    assert len(r["files"]) == 5
    assert all(r["counts"][s] > 0 for s in ("앎", "헷갈림", "모름"))
    md = (tmp_path / "공부순서_오답노트.md").read_text(encoding="utf-8")
    assert "<div" not in md and "base64" not in md and "# 빈틈노트 공부 순서·오답노트" in md
    assert "(p." in md and "`" in md and "(그림) " in md


def test_t49_html_to_md():
    m = _mod()
    h = ('<h2>제목</h2><p>설명 <span class="pg">p.3</span></p><span class="badge ok">앎</span>'
         '<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>'
         '<img alt="이진 트리 [A, B]" src="data:image/svg+xml;base64,AAAA">')
    md = m.html_to_md(h)
    assert "## 제목" in md and "(p.3)" in md and "`앎`" in md and "| a | b |" in md
    assert "(그림) 이진 트리 [A, B]" in md and "base64" not in md and "<" not in md
