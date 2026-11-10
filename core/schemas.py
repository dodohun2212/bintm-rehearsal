"""6장 JSON 형식 (pydantic v2). AI 답은 코드가 먼저 다듬은 뒤 이 형식으로 검사한다."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

UTTER_TYPES = ("emphasis", "exam_hint", "mistake_warning", "exercise_hint", "deferral", "skip", "question")


class Concept(BaseModel):
    id: str
    name: str = Field(min_length=1)
    summary: str = ""
    pages: list[int] = []
    in_objectives: bool = False
    objective_quote: Optional[str] = None
    has_example: bool = False
    has_exercise: bool = False
    exercise_numbers: list[int] = []
    keywords: list[str] = []


class Utterance(BaseModel):
    concept_id: Optional[str] = None
    concept_name: str = ""
    quote: str = Field(min_length=1)
    type: Literal["emphasis", "exam_hint", "mistake_warning", "exercise_hint", "deferral", "skip", "question"]
    strength: int = Field(ge=1, le=3)


class RubricItem(BaseModel):
    point: str
    score: int


class Question(BaseModel):
    kind: Literal["서술형", "객관식"]
    question: str = Field(min_length=1)
    answer: str = ""
    rubric: list[RubricItem] = []
    choices: list[str] = []
    answer_index: Optional[int] = None
    explanation: str = ""
    source_pages: list[int] = []
    figure: Optional[dict] = None


class Grading(BaseModel):
    score: int = Field(ge=0, le=10)
    max: int = 10
    status: Literal["앎", "헷갈림", "모름"]
    error_type: Optional[str] = None
    reason: str = ""
    rubric_scores: Optional[list[int]] = None


class Explanation(BaseModel):
    concept_id: str
    my_gap: str = ""
    explanation: str = ""
    check_pages: list[int] = []
    source_pages: list[int] = []
    not_found: bool = False
    not_found_note: Optional[str] = None
    confusion_reply: Optional[str] = None


class NoteSection(BaseModel):
    concept_id: str
    detail: Literal["자세히", "보통", "짧게"]
    summary: str = ""
    key_points: list[str] = []
    pitfalls: list[str] = []
    source_pages: list[int] = []
    from_ai: bool = True
