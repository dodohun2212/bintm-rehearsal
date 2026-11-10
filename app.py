"""빈틈노트 화면 진입점: 페이지 설정, CSS, 예전 모듈 버리기, 사이드바, 화면 고르기만."""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
_WATCH_DIRS = ("core", "screens")


def module_mtimes() -> dict:
    """core·screens·config 모듈과 프롬프트 파일의 수정 시각."""
    out = {}
    for d in _WATCH_DIRS:
        for p in (ROOT / d).glob("*.py"):
            out[str(p)] = p.stat().st_mtime
    out[str(ROOT / "config.py")] = (ROOT / "config.py").stat().st_mtime
    for p in (ROOT / "prompts").glob("*.md"):
        out[str(p)] = p.stat().st_mtime
    return out


def stale(old: dict | None, new: dict) -> bool:
    """재배포로 파일이 바뀌었는지. 프롬프트 파일은 기록에 없어도 바뀐 것으로 본다."""
    if old is None:
        return False
    for path, mt in new.items():
        if path not in old:
            if path.endswith(".md"):
                return True
            continue
        if old[path] != mt:
            return True
    return False


def drop_stale_modules() -> None:
    """Streamlit Cloud는 재배포 때 app.py만 다시 실행한다. 바뀐 모듈은 sys.modules에서 지워 새로 읽는다."""
    new = module_mtimes()
    old = getattr(sys, "_bintm_mtimes", None)
    loaded = any(m == "config" or m.startswith(("core.", "screens.")) for m in sys.modules)
    if stale(old, new) or (old is None and loaded):
        for name in list(sys.modules):
            if name in ("config", "core", "screens") or name.startswith(("core.", "screens.")):
                del sys.modules[name]
        st.cache_resource.clear()
    sys._bintm_mtimes = new


drop_stale_modules()

import config  # noqa: E402
from core import llm, stt  # noqa: E402
from screens import common, s01, s02, s03, s04, s05  # noqa: E402

st.set_page_config(page_title="빈틈노트", page_icon="📝", layout="centered")
st.html(common.PAGE_CSS)


def _secret(name: str):
    try:
        return st.secrets.get(name)
    except Exception:  # noqa: BLE001 (secrets.toml이 없으면 환경변수로)
        return None


llm.set_api_key(_secret("ANTHROPIC_API_KEY"))
stt.set_api_key(_secret("OPENAI_API_KEY"))
common.init_state()
S = common.S

# 새로고침으로 세션이 사라졌는데 ②~④에 있으면 ①로 (E-14)
if S["step"] in (2, 3, 4) and S["scores"] is None:
    S["step"] = 1


def can_open(step: int) -> bool:
    if step in (1, 5):
        return True
    if step == 2:
        return S["scores"] is not None
    if step == 3:
        return bool(S["diag_ids"]) and bool(S["questions"]) or S["step"] == 3
    return S["priorities"] is not None


with st.sidebar:
    st.markdown("### 📝 빈틈노트")
    for i, name in enumerate(common.STEP_NAMES, 1):
        current = S["step"] == i
        if st.button(name, key=f"bt_nav_{i}", type="primary" if current else "secondary",
                     disabled=not can_open(i), width="stretch"):
            S["step"] = i
            st.rerun()
    st.divider()
    if st.button("처음부터", key="bt_nav_reset", width="stretch"):
        common.reset_state()
        st.rerun()
    st.caption(f"모델: {config.LLM_MODEL}")

SCREENS = {1: s01.render, 2: s02.render, 3: s03.render, 4: s04.render, 5: s05.render}
SCREENS[S["step"]]()
