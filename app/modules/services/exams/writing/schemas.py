from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator, field_validator

from .models import (
    CEFRLevel,
    WritingStyle,
    ScoringMode,
    WritingCriterion,
    FeedbackSource,
)


# ==========================================================
# BASE
# ==========================================================

class ORMModel(BaseModel):
    model_config = {
        "from_attributes": True,
        "extra": "forbid",
    }


# ==========================================================
# FORMAT
# ==========================================================

class WritingCriterionConfigRead(BaseModel):
    criterion: WritingCriterion
    weight: float


class WritingCriterionWeightCreate(BaseModel):
    criterion: WritingCriterion
    weight: float = Field(..., gt=0, le=1)


class WritingFormatBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    cefr_level: CEFRLevel

    min_words: int = Field(..., ge=1)
    max_words: int = Field(..., ge=1)

    style: WritingStyle
    scoring_mode: ScoringMode
    penalty_enabled: bool = False

    @model_validator(mode="after")
    def validate_words(self):
        if self.min_words >= self.max_words:
            raise ValueError("min_words must be < max_words")
        return self


class WritingFormatCreate(WritingFormatBase):
    criterion_weights: List[WritingCriterionWeightCreate]

    @model_validator(mode="after")
    def validate_weights(self):
        total = sum(c.weight for c in self.criterion_weights)
        if abs(total - 1.0) > 1e-6:
            raise ValueError("Criterion weights must sum to 1.0")
        return self


class WritingFormatRead(ORMModel):
    id: int
    name: str
    cefr_level: CEFRLevel
    min_words: int
    max_words: int
    style: WritingStyle
    scoring_mode: ScoringMode
    penalty_enabled: bool
    created_at: datetime
    criterion_configs: List[WritingCriterionConfigRead]


# ==========================================================
# TASK
# ==========================================================

class WritingTaskBase(BaseModel):
    part_number: int = Field(..., ge=1)
    sub_part: Optional[int] = Field(None, ge=1)

    topic: str = Field(..., min_length=5)
    instruction: str = Field(..., min_length=5)
    context_text: Optional[str] = None

    format_id: int


class WritingTaskCreate(WritingTaskBase):
    pass


class WritingTaskRead(ORMModel):
    id: int
    exam_id: str
    part_number: int
    sub_part: Optional[int]
    topic: str
    instruction: str
    context_text: Optional[str]
    created_at: datetime
    format: WritingFormatRead


# ==========================================================
# EXAM
# ==========================================================

class WritingExamBase(BaseModel):
    title: str = Field(..., min_length=3)
    cefr_level: CEFRLevel
    duration_minutes: int = Field(default=60, ge=10, le=240)

    is_demo: bool = False
    is_free: bool = False
    is_mock: bool = False
    is_active: bool = True


# 🔥 CLIENT year/sequence_number yubormaydi
class WritingExamCreate(WritingExamBase):
    tasks: List[WritingTaskCreate]

    @model_validator(mode="after")
    def validate_unique_tasks(self):
        seen = set()
        for t in self.tasks:
            key = (t.part_number, t.sub_part)
            if key in seen:
                raise ValueError("Duplicate task structure")
            seen.add(key)
        return self


class WritingExamUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    title: Optional[str] = Field(None, min_length=3)
    cefr_level: Optional[CEFRLevel] = None
    duration_minutes: Optional[int] = Field(None, ge=10, le=240)

    is_demo: Optional[bool] = None
    is_free: Optional[bool] = None
    is_mock: Optional[bool] = None
    is_active: Optional[bool] = None

    tasks: Optional[List[WritingTaskCreate]] = None


class WritingExamRead(ORMModel):
    id: str
    year: int
    sequence_number: int
    title: str
    cefr_level: CEFRLevel
    duration_minutes: int
    is_demo: bool
    is_free: bool
    is_mock: bool
    is_active: bool
    created_at: datetime
    tasks: List[WritingTaskRead]


# ==========================================================
# SUBMISSION
# ==========================================================

class WritingAnswerSubmit(BaseModel):
    task_id: int
    content: str = Field(..., min_length=10)

    @field_validator("content")
    @classmethod
    def strip_text(cls, v: str):
        v = v.strip()
        if not v:
            raise ValueError("Content cannot be empty")
        return v


class WritingSubmitRequest(BaseModel):
    answers: List[WritingAnswerSubmit]


# ==========================================================
# RESULT / SCORE
# ==========================================================

class WritingScoreRead(ORMModel):
    id: int
    criterion: WritingCriterion
    score: float
    created_at: datetime


class WritingFeedbackRead(ORMModel):
    id: int
    source: FeedbackSource
    model_name: Optional[str]
    content: str
    created_at: datetime


class WritingAnswerResultRead(ORMModel):
    id: int
    task_id: int
    content: str
    word_count: int
    penalty: float
    raw_score: Optional[float]
    scaled_score: Optional[float]
    created_at: datetime
    scores: List[WritingScoreRead]
    feedbacks: List[WritingFeedbackRead]


class WritingResultRead(ORMModel):
    id: int
    user_id: int
    exam_id: str
    raw_score: Optional[float]
    scaled_score: Optional[float]
    cefr_level: Optional[CEFRLevel]
    is_finalized: bool
    created_at: datetime
    answers: List[WritingAnswerResultRead]