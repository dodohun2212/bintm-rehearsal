# 테스트는 가짜 AI 모드로 돈다 (AI 호출 없음, 비용 0).
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
FIX = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def material():
    from core.extract import extract
    return extract(SAMPLE_PDF.read_bytes(), SAMPLE_PDF.name)


@pytest.fixture(scope="session")
def transcript():
    return SAMPLE_TRANSCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def analysis(material, transcript):
    from core.concepts import meta_pages, parse_concepts
    from core.score import compute_scores
    from core.utterances import parse_utterances
    cres = parse_concepts(json.loads((FIX / "01_개념추출_결과.json").read_text(encoding="utf-8")), material["n_pages"])
    meta = meta_pages(material, cres)
    utts = parse_utterances(json.loads((FIX / "02_강조발화_결과.json").read_text(encoding="utf-8")), transcript,
                            [c["id"] for c in cres["concepts"]])
    scores = compute_scores(cres["concepts"], utts, meta)["scores"]
    return {"cres": cres, "concepts": cres["concepts"], "meta": meta, "utts": utts, "scores": scores}
