"""테스트는 항상 가짜 AI 모드로 돈다(키 없이, 비용 0)."""
import os
import sys
from pathlib import Path

os.environ["BINTM_FAKE_AI"] = "1"
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
