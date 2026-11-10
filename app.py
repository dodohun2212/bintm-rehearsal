"""빈틈노트 화면 진입점: 예전 모듈 버리기, 페이지 설정, CSS, 사이드바, 화면 고르기만 한다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WATCH_PACKAGES = ("core", "screens")


def _drop_stale_modules() -> bool:
    """재배포 때 예전 core·screens·config 모듈과 프롬프트를 버린다.

    Streamlit Cloud는 app.py만 다시 실행하고 이미 불러온 모듈은 예전 것을 쓴다.
    모듈·프롬프트 파일의 수정 시각을 sys에 기록해 두고, 바뀌었으면 sys.modules에서 지우고
    서버 공용 캐시(st.cache_resource)도 비운다. 프롬프트는 기록에 없어도 바뀐 것으로 본다.
    """
    files = [ROOT / "config.py"]
    for pkg in WATCH_PACKAGES:
        files += sorted((ROOT / pkg).glob("*.py"))
    prompt_files = sorted((ROOT / "prompts").glob("*.md"))
    now = {str(p): p.stat().st_mtime for p in files + prompt_files}
    before = getattr(sys, "_bintm_mtimes", None)
    changed = before is not None and any(before.get(k) != v for k, v in now.items() if not k.endswith(".md"))
    prompt_changed = any((before or {}).get(str(p)) != now[str(p)] for p in prompt_files)
    sys._bintm_mtimes = now
    if not (changed or prompt_changed):
        return False
    for name in list(sys.modules):
        if name == "config" or name.split(".")[0] in WATCH_PACKAGES:
            del sys.modules[name]
    try:
        import streamlit as st

        st.cache_resource.clear()
    except Exception:
        pass
    return True


_drop_stale_modules()

import streamlit as st  # noqa: E402

st.set_page_config(page_title="빈틈노트", page_icon="📝", layout="centered")

from screens import common as C  # noqa: E402
from screens import s01, s02, s03, s04, s05  # noqa: E402

C.load_secrets()
C.init_state()
st.markdown(C.CSS, unsafe_allow_html=True)

SCREENS = {1: s01, 2: s02, 3: s03, 4: s04, 5: s05}


def allowed(step: int) -> bool:
    s = st.session_state
    if step in (1, 5):
        return True
    if step in (2, 3):
        return s["scores"] is not None and (step == 2 or bool(s["diag_ids"]) or bool(s["questions"]))
    return bool(s["grading"]) and (not s["grade_failed"] or s["skip_failed"])


with st.sidebar:
    st.markdown("### 빈틈노트")
    for n, label in C.STEP_NAMES.items():
        current = st.session_state["step"] == n
        if st.button(label, key=f"nav_{n}", type="primary" if current else "secondary",
                     disabled=not allowed(n), width="stretch"):
            st.session_state["step"] = n
            st.rerun()
    st.divider()
    if st.button("처음부터", width="stretch"):
        C.reset_all()
        st.rerun()
    st.caption(C.DISCLAIMER)

step = st.session_state["step"]
if not allowed(step):
    step = 1
    st.session_state["step"] = 1
SCREENS[step].render()
