"""T-49: 결과 예시 만들기(가짜 AI)와 HTML → 마크다운 변환."""
import importlib.util

from tests.conftest import ROOT


def _load():
    spec = importlib.util.spec_from_file_location("make_example", ROOT / "scripts" / "make_example.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_t49_run_writes_five_files(tmp_path):
    me = _load()
    result = me.run(tmp_path)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == sorted(me.NAMES)
    counts = result["info"]["counts"]
    assert counts["앎"] > 0 and counts["헷갈림"] > 0 and counts["모름"] > 0
    md = (tmp_path / "공부순서_오답노트.md").read_text(encoding="utf-8")
    assert "<div" not in md and "<span" not in md and "base64" not in md
    assert md.startswith("# 빈틈노트 공부 순서·오답노트")
    assert "README" not in md
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "가짜 AI" in readme and "단계별 시간" in readme


def test_t49_markdown_conversion():
    me = _load()
    html = ('<html><head><style>.x{}</style><title>t</title></head><body><h2>1. 공부 순서</h2>'
            '<p>삽입은 끝에 넣는다 <span class="pg">p.15</span> <span class="badge ok">앎</span></p>'
            '<img alt="이진 트리(레벨 순서 [A, B])" src="data:image/svg+xml;base64,AAAA"/>'
            '<table><tr><th>연산</th><th>복잡도</th></tr><tr><td>삽입</td><td>O(log n)</td></tr></table></body></html>')
    md = me.html_to_markdown(html)
    assert "## 1. 공부 순서" in md
    assert "(p.15)" in md and "`앎`" in md
    assert "(그림) 이진 트리(레벨 순서 [A, B])" in md and "base64" not in md
    assert "| 연산 | 복잡도 |" in md and "|---|---|" in md and "| 삽입 | O(log n) |" in md
    assert ".x{}" not in md
