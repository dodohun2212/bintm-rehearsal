"""AI가 돌려주는 JSON의 모양(개발기획안 6장). 형식이 틀린 값은 여기서 거르거나 고친다."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

UTTERANCE_TYPES = ("emphasis", "exam_hint", "mistake_warning", "exercise_hint", "deferral", "skip")
ERROR_TYPES = ("개념 혼동", "비교 방향 오류", "복잡도 오류", "절차 누락", "무응답", "기타")


def parse_pages(value: Any) -> list[int]:
    """쪽 번호를 숫자 목록으로 읽는다. 5, 5.0, "5", "p.5", "3-4", [..] 모두 받는다."""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    out: list[int] = []
    for item in items:
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            out.append(int(item))
            continue
        if isinstance(item, str):
            nums = [int(x) for x in re.findall(r"\d+", item)]
            if re.search(r"\d+\s*[-~]\s*\d+", item) and len(nums) == 2 and nums[0] <= nums[1] <= nums[0] + 50:
                out.extend(range(nums[0], nums[1] + 1))
            else:
                out.extend(nums)
    seen: list[int] = []
    for n in out:
        if n not in seen:
            seen.append(n)
    return seen


def keep_pages(pages: list[int], allowed) -> list[int]:
    """허용한 쪽 번호만 남긴다(E-15: 범위 밖은 조용히 지운다)."""
    allowed_set = set(allowed)
    return [p for p in pages if p in allowed_set]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, v):
        text = _text(v)
        if not text:
            raise ValueError("이름 없음")
        return text

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, v):
        return _text(v)

    @field_validator("objective_quote", mode="before")
    @classmethod
    def _quote(cls, v):
        text = _text(v)
        return text or None

    @field_validator("keywords", mode="before")
    @classmethod
    def _keywords(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v if x is not None]

    @field_validator("in_objectives", "has_example", "has_exercise", mode="before")
    @classmethod
    def _bool(cls, v):
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes", "예")
        return bool(v)


class Utterance(BaseModel):
    concept_id: Optional[str] = None
    concept_name: str = ""
    quote: str
    type: Literal["emphasis", "exam_hint", "mistake_warning", "exercise_hint", "deferral", "skip"]
    strength: int = 2

    @field_validator("concept_id", mode="before")
    @classmethod
    def _cid(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f"c{int(v)}"
        text = str(v).strip()
        if text.isdigit():
            return f"c{text}"
        return text or None

    @field_validator("concept_name", mode="before")
    @classmethod
    def _cname(cls, v):
        return _text(v)

    @field_validator("quote", mode="before")
    @classmethod
    def _quote(cls, v):
        text = _text(v)
        if not text:
            raise ValueError("인용 없음")
        return text

    @field_validator("strength", mode="before")
    @classmethod
    def _strength(cls, v):
        try:
            n = int(round(float(v)))
        except (TypeError, ValueError):
            n = 2
        return max(1, min(3, n))


class Figure(BaseModel):
    kind: str


class EssayQuestionAI(BaseModel):
    question: str
    answer: str
    rubric: list[dict]
    source_pages: list[int] = Field(default_factory=list)
    figure: Optional[dict] = None

    @field_validator("source_pages", mode="before")
    @classmethod
    def _pages(cls, v):
        return parse_pages(v)

    @field_validator("question", "answer", mode="before")
    @classmethod
    def _required(cls, v):
        text = _text(v)
        if not text:
            raise ValueError("빈 글")
        return text


class MCQuestionAI(BaseModel):
    question: str
    choices: list[str]
    answer_index: int
    explanation: str = ""
    source_pages: list[int] = Field(default_factory=list)
    figure: Optional[dict] = None

    @field_validator("source_pages", mode="before")
    @classmethod
    def _pages(cls, v):
        return parse_pages(v)

    @field_validator("question", mode="before")
    @classmethod
    def _required(cls, v):
        text = _text(v)
        if not text:
            raise ValueError("빈 문제")
        return text

    @field_validator("explanation", mode="before")
    @classmethod
    def _expl(cls, v):
        return _text(v)


class ExplanationAI(BaseModel):
    my_gap: str = ""
    explanation: str = ""
    check_pages: list[int] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    not_found: bool = False
    not_found_note: Optional[str] = None
    confusion_reply: Optional[str] = None

    @field_validator("check_pages", "source_pages", mode="before")
    @classmethod
    def _pages(cls, v):
        return parse_pages(v)

    @field_validator("my_gap", "explanation", mode="before")
    @classmethod
    def _txt(cls, v):
        return _text(v)

    @field_validator("not_found_note", "confusion_reply", mode="before")
    @classmethod
    def _opt(cls, v):
        text = _text(v)
        return None if text in ("", "null", "None") else text

    @field_validator("not_found", mode="before")
    @classmethod
    def _bool(cls, v):
        if isinstance(v, str):
            return v.strip().lower() == "true"
        return bool(v)


class NoteAI(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)

    @field_validator("source_pages", mode="before")
    @classmethod
    def _pages(cls, v):
        return parse_pages(v)

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, v):
        text = _text(v)
        if not text:
            raise ValueError("요약 없음")
        return text

    @field_validator("key_points", "pitfalls", mode="before")
    @classmethod
    def _list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
