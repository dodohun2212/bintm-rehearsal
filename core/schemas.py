# 6장 JSON 형식 (pydantic v2). AI 응답은 코드가 먼저 다듬은 뒤 이 형식으로 검사한다.
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

UTTERANCE_TYPES = {"emphasis", "exam_hint", "mistake_warning", "exercise_hint", "deferral", "skip", "question"}


class Concept(BaseModel):
    id: str
    name: str = Field(min_length=2)
    summary: str = ""
    pages: list[int] = Field(default_factory=list)
    in_objectives: bool = False
    objective_quote: Optional[str] = None
    has_example: bool = False
    has_exercise: bool = False
    exercise_numbers: list[int] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class Utterance(BaseModel):
    concept_id: Optional[str] = None
    concept_name: str = ""
    quote: str = Field(min_length=2)
    type: str
    strength: int = 2

    @field_validator("type")
    @classmethod
    def _type_ok(cls, v):
        if v not in UTTERANCE_TYPES:
            raise ValueError("모르는 발화 유형")
        return v


class RubricItem(BaseModel):
    point: str
    score: int


class Question(BaseModel):
    """저장 형식. kind는 '서술형' 또는 '객관식'."""
    kind: str
    question: str = Field(min_length=5)
    answer: str = ""
    rubric: list[RubricItem] = Field(default_factory=list)
    choices: list[str] = Field(default_factory=list)
    answer_index: Optional[int] = None
    explanation: str = ""
    source_pages: list[int] = Field(default_factory=list)
    figure: Optional[dict[str, Any]] = None


class Grading(BaseModel):
    score: int
    max: int = 10
    status: str
    error_type: Optional[str] = None
    reason: str = ""
    rubric_scores: list[int] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)


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
    from_ai: bool = False
