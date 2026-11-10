"""T-49 결과 예시 만들기와 마크다운 변환 (가짜 AI)."""
import importlib.util
import re

import pytest

from conftest import ROOT


@pytest.fixture(scope="module")
def mk():
    spec = importlib.util.spec_from_file_location("make_example", ROOT / "scripts" / "make_example.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_t49_run_writes_five_files(mk, tmp_path):
    s = mk.run(tmp_path, today="2026-11-11")
    files = sorted(p.name for p in tmp_path.iterdir())
    assert len(files) == 5
    assert sum(f.endswith(".html") for f in files) == 2
    assert sum(f.endswith(".md") and f != "README.md" for f in files) == 2
    assert "README.md" in files
    for status in ("앎", "헷갈림", "모름"):
        assert s["status"].get(status, 0) > 0
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "모델" in readme and "단계별 시간" in readme
    md = (tmp_path / mk.STUDY_MD).read_text(encoding="utf-8")
    assert not re.search(r"<[a-zA-Z/!][^>\n]*>", md)
    assert "data:image" not in md
    assert "(그림)" in md


def test_t49_html_to_md_pieces(mk):
    h = ('<html><head><style>.x{}</style></head><body><h1>제목</h1><h2>1. 공부 순서</h2>'
         '<p>설명 <span class="pg">p.15</span></p><span class="badge st-모름">모름</span>'
         '<img alt="이진 트리: [A, B]" src="data:image/svg+xml;base64,AAAA">'
         '<table><tr><th>인덱스</th><th>1</th></tr><tr><th>값</th><td>90</td></tr></table>'
         '<ul><li>핵심</li></ul></body></html>')
    md = mk.html_to_md(h)
    assert "# 제목" in md and "## 1. 공부 순서" in md
    assert "(p.15)" in md
    assert "`모름`" in md
    assert "| 인덱스 | 1 |" in md and "|---|---|" in md
    assert "(그림) 이진 트리: [A, B]" in md
    assert "- 핵심" in md
    assert "data:image" not in md and "<" not in md


def test_t50_readme_and_grading_tone():
    """T-50: README에 잠든 앱 깨우는 법과 '신호가 같으면 같은 점수', 03B 채점 이유는 '~다' 말투."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Yes, get this app back up!" in readme
    assert "AI가 찾은 신호가 같으면" in readme
    assert "세션 메모리에만" not in readme
    assert "<!--" not in readme  # 채우지 않은 자리표시가 없음
    p03b = (ROOT / "prompts" / "03B_채점_v1.md").read_text(encoding="utf-8")
    assert '"~다"' in p03b


def test_file_names_use_korean_date():
    """서버가 UTC여도 내려받는 파일 이름은 한국 날짜."""
    from core.export import file_names
    from core.guard import today_kst
    a, b = file_names()
    assert today_kst().isoformat() in a and today_kst().isoformat() in b
