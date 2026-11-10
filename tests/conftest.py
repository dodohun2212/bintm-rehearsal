"""테스트 공통: 가짜 AI를 켜고 저장소 루트를 import 경로에 넣는다."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["BINTM_FAKE_AI"] = "1"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_SCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def sample_material():
    from core.extract import extract
    return extract(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes())


@pytest.fixture(scope="session")
def sample_transcript():
    return SAMPLE_SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def sample_analysis(sample_material, sample_transcript):
    """fixtures로 만든 개념·발화·점수 (AI 호출 없음)."""
    import json
    from core.concepts import clean_concepts
    from core.score import compute_scores
    from core.utterances import clean_utterances
    raw1 = json.loads((FIXTURES / "01_개념추출_결과.json").read_text(encoding="utf-8"))
    raw2 = json.loads((FIXTURES / "02_강조발화_결과.json").read_text(encoding="utf-8"))
    cres = clean_concepts(raw1, sample_material)
    utts = clean_utterances(raw2, sample_transcript, cres["concepts"])
    scores = compute_scores(cres["concepts"], utts, cres["meta_pages"])
    return {"cres": cres, "concepts": cres["concepts"], "meta": cres["meta_pages"], "utts": utts, "scores": scores}
