"""6장 JSON 형식 (pydantic v2). AI 응답은 항목마다 이 형식으로 검사한다."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def parse_pages(value) -> list[int]:
    """쪽 번호를 숫자 목록으로. 5.0, "5", "p.5", "3-4"를 읽는다. 못 읽는 값은 버린다."""
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        value = [value]
    out: list[int] = []
    for v in value:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            if float(v).is_integer():
                out.append(int(v))
            continue
        if isinstance(v, str):
            s = v.strip().lower().replace("p.", "").replace("p", "").replace("쪽", "").strip()
            m = re.fullmatch(r"(\d+)\s*[-~–]\s*(\d+)", s)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if a <= b and b - a <= 50:
                    out.extend(range(a, b + 1))
                continue
            try:
                f = float(s)
                if f.is_integer():
                    out.append(int(f))
            except ValueError:
                continue
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


class Concept(BaseModel):
    id: str
    name: str
    summary: str = ""
    pages: list[int] = Field(default_factory=list)
    in_objectives: bool = False
    objective_quote: Optional[str] = None
    has_example: bool = False
    has_exercise: bool = False
    exercise_numbers: list[int] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    @field_validator("pages", "exercise_numbers", mode="before")
    @classmethod
    def _pages(cls, v):
        return parse_pages(v)

    @field_validator("keywords", mode="before")
    @classmethod
    def _kw(cls, v):
        if not isinstance(v, list):
            return []
        return [str(x) for x in v if x is not None]

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, v):
        return "" if v is None else str(v)

    @field_validator("in_objectives", "has_example", "has_exercise", mode="before")
    @classmethod
    def _bool(cls, v):
        return bool(v) if v is not None else False


class Utterance(BaseModel):
    concept_id: Optional[str] = None
    concept_name: str = ""
    quote: str
    type: str
    strength: int = 2


class RubricItem(BaseModel):
    point: str
    score: int


class Question(BaseModel):
    """저장 형식. kind는 "서술형"/"객관식"."""
    kind: str
    question: str
    answer: str = ""
    rubric: list[RubricItem] = Field(default_factory=list)
    choices: list[str] = Field(default_factory=list)
    answer_index: Optional[int] = None
    explanation: str = ""
    source_pages: list[int] = Field(default_factory=list)
    figure: Optional[dict] = None


class Grading(BaseModel):
    score: int
    max: int = 10
    status: str
    error_type: Optional[str] = None
    reason: str = ""
    rubric_scores: list[int] = Field(default_factory=list)
    kind: str = "서술형"


class Explanation(BaseModel):
    concept_id: str
    my_gap: str = ""
    explanation: str = ""
    check_pages: list[int] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    not_found: bool = False
    not_found_note: Optional[str] = None
    confusion_reply: Optional[str] = None


class NoteSection(BaseModel):
    concept_id: str
    detail: str
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    from_ai: bool = True
