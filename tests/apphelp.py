"""AppTest 공용 도우미 (가짜 AI)."""
from streamlit.testing.v1 import AppTest

from tests.conftest import ROOT


def new_app() -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.run()
    return at


def click(at: AppTest, label: str) -> AppTest:
    for b in at.button:
        if b.label == label:
            b.click().run()
            return at
    raise AssertionError(f"버튼 없음: {label} / 있는 버튼: {[b.label for b in at.button]}")


def click_prefix(at: AppTest, prefix: str) -> AppTest:
    for b in at.button:
        if b.label.startswith(prefix):
            b.click().run()
            return at
    raise AssertionError(f"버튼 없음: {prefix}… / 있는 버튼: {[b.label for b in at.button]}")


def all_text(at: AppTest) -> str:
    """화면에 그린 글(마크다운·캡션·HTML·알림)을 모두 모은다."""
    parts = []
    for kind in ("markdown", "caption", "error", "warning", "info", "success"):
        parts += [str(e.value) for e in at.get(kind)]
    parts += [e.proto.body for e in at.get("html")]
    for exp in at.expander:
        parts.append(exp.label)
    for tab in at.tabs:
        parts.append(tab.label)
    return "\n".join(parts)


def sample_to_s03(at: AppTest) -> AppTest:
    click(at, "🧪 샘플로 체험")
    assert at.session_state["step"] == 2, all_text(at)[:2000]
    label = next(b.label for b in at.button if b.label.endswith("개념 진단하기"))
    click(at, label)
    return at
