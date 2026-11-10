"""테스트 공용: 샘플 자료와 저장된 AI 결과(fixtures)로 점수까지 만든다."""
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TXT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"


def fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def sample():
    from core.concepts import clean_concepts, meta_pages
    from core.extract import extract
    from core.score import compute_scores
    from core.utterances import clean_utterances

    material = extract(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes())
    cres = clean_concepts(fixture("01_개념추출_결과.json"), material["n_pages"])
    meta = meta_pages(material["pages"], cres)
    tr = SAMPLE_TXT.read_text(encoding="utf-8")
    utts = clean_utterances(fixture("02_강조발화_결과.json"), tr, [c["id"] for c in cres["concepts"]])
    scores = compute_scores(cres["concepts"], utts, meta)["scores"]
    return {"material": material, "concepts": cres["concepts"], "meta": meta, "utterances": utts,
            "scores": scores, "transcript": tr}
