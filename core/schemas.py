"""6장 JSON 형식 (pydantic v2). AI 답은 여기서 검사한 뒤 dict로 세션에 둔다."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

UTTERANCE_TYPES = ("emphasis", "exam_hint", "mistake_warning", "exercise_hint", "deferral", "skip")


def parse_pages(value: Any) -> list[int]:
    """쪽 번호를 숫자 목록으로 읽는다. 5, 5.0, "5", "p.5", "3-4" 모두 받는다."""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list[int] = []
    for v in items:
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
                if 0 < a <= b and b - a <= 50:
                    out.extend(range(a, b + 1))
                continue
            m = re.fullmatch(r"(\d+)(?:\.0+)?", s)
            if m:
                out.append(int(m.group(1)))
    seen: list[int] = []
    for n in out:
        if n not in seen:
            seen.append(n)
    return seen


def keep_pages(pages: Any, allowed: set[int] | list[int] | range) -> list[int]:
    """허용된 쪽 번호만 남긴다(E-15: 범위 밖은 조용히 지움)."""
    allowed = set(allowed)
    return [p for p in parse_pages(pages) if p in allowed]


class Concept(BaseModel):
    id: str
    name: str
    summary: str = ""
    pages: list[int] = Field(default_factory=list)
    in_objectives: bool = False
    objective_quote: str | None = None
    has_example: bool = False
    has_exercise: bool = False
    exercise_numbers: list[int] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    @field_validator("pages", "exercise_numbers", mode="before")
    @classmethod
    def _pages(cls, v):
        return parse_pages(v)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        if not str(v).strip():
            raise ValueError("이름 없음")
        return str(v).strip()

    @field_validator("keywords", mode="before")
    @classmethod
    def _kw(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v if x is not None]

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, v):
        return "" if v is None else str(v)


class Utterance(BaseModel):
    concept_id: str | None = None
    concept_name: str = ""
    quote: str
    type: str
    strength: int = 1

    @field_validator("concept_id", mode="before")
    @classmethod
    def _cid(cls, v):
        if v is None or v == "" or str(v).lower() == "null":
            return None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f"c{int(v)}"
        return str(v)

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v not in UTTERANCE_TYPES:
            raise ValueError("모르는 유형")
        return v

    @field_validator("strength", mode="before")
    @classmethod
    def _strength(cls, v):
        try:
            n = round(float(v))
        except (TypeError, ValueError):
            n = 1
        return max(1, min(3, int(n)))

    @field_validator("concept_name", mode="before")
    @classmethod
    def _cname(cls, v):
        return "" if v is None else str(v)


class RubricItem(BaseModel):
    point: str
    score: int

    @field_validator("score", mode="before")
    @classmethod
    def _score(cls, v):
        try:
            return max(0, int(round(float(v))))
        except (TypeError, ValueError):
            return 0


class Figure(BaseModel):
    kind: str
    nodes: list[Any] | None = None
    items: list[Any] | None = None
    start: int | None = None
    header: list[Any] | None = None
    rows: list[list[Any]] | None = None
    caption: str | None = None


class Explanation(BaseModel):
    my_gap: str = ""
    explanation: str
    check_pages: list[int] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    not_found: bool = False
    not_found_note: str | None = None
    confusion_reply: str | None = None

    @field_validator("check_pages", "source_pages", mode="before")
    @classmethod
    def _pages(cls, v):
        return parse_pages(v)

    @field_validator("my_gap", mode="before")
    @classmethod
    def _gap(cls, v):
        return "" if v is None else str(v)

    @field_validator("not_found", mode="before")
    @classmethod
    def _nf(cls, v):
        return bool(v) and str(v).lower() not in ("false", "0", "null")


class Note(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)

    @field_validator("source_pages", mode="before")
    @classmethod
    def _pages(cls, v):
        return parse_pages(v)

    @field_validator("key_points", "pitfalls", mode="before")
    @classmethod
    def _list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v if x]
