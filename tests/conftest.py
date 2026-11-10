"""테스트 공통: 가짜 AI 모드를 켜고 저장소 뿌리를 import 경로에 넣는다."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["BINTM_FAKE_AI"] = "1"

SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TRANSCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def concepts_raw():
    return json.loads((FIXTURES / "01_개념추출_결과.json").read_text(encoding="utf-8"))


@pytest.fixture
def utterances_raw():
    return json.loads((FIXTURES / "02_강조발화_결과.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def sample_material():
    from core.extract import extract

    return extract(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes())
