"""모든 테스트는 가짜 AI 모드로 돈다(키 없이, 비용 0)."""
import json
import os
import sys
from pathlib import Path

import pytest

os.environ["BINTM_FAKE_AI"] = "1"
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TRANSCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def material():
    from core.extract import extract
    return extract(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes())


@pytest.fixture(scope="session")
def transcript():
    return SAMPLE_TRANSCRIPT.read_text(encoding="utf-8")


@pytest.fixture()
def concepts_fx():
    return json.loads((FIXTURES / "01_개념추출_결과.json").read_text(encoding="utf-8"))


@pytest.fixture()
def utterances_fx():
    return json.loads((FIXTURES / "02_강조발화_결과.json").read_text(encoding="utf-8"))
