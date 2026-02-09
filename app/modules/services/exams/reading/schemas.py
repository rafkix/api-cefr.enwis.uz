from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from enum import Enum
from datetime import datetime

class ReadingQuestionType(str, Enum):
    GAP_FILL = "GAP_FILL"
    GAP_FILL_FILL = "GAP_FILL_FILL"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TRUE_FALSE_NOT_GIVEN = "TRUE_FALSE_NOT_GIVEN"
    HEADINGS_MATCH = "HEADINGS_MATCH"
    TEXT_MATCH = "TEXT_MATCH"
    MULTIPLE_SELECT = "MULTIPLE_SELECT"

# --- OPTIONS ---
class ReadingOptionBase(BaseModel):
    label: str
    value: str

class ReadingOptionCreate(ReadingOptionBase):
    pass

class ReadingOptionResponse(ReadingOptionBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# --- QUESTIONS ---
class ReadingQuestionBase(BaseModel):
    question_number: int
    type: ReadingQuestionType
    text: str
    word_limit: int = 0

class ReadingQuestionCreate(ReadingQuestionBase):
    correct_answer: List[str]
    options: List[ReadingOptionCreate] = Field(default_factory=list)

class ReadingQuestionResponse(ReadingQuestionBase):
    id: int
    options: List[ReadingOptionResponse] = Field(default_factory=list)
    # correct_answer bu yerda yo'q (xavfsizlik uchun)

    model_config = ConfigDict(from_attributes=True)

# --- PARTS ---
class ReadingPartBase(BaseModel):
    title: str
    description: Optional[str] = None
    passage: str

class ReadingPartCreate(ReadingPartBase):
    questions: List[ReadingQuestionCreate]

class ReadingPartResponse(ReadingPartBase):
    id: int
    questions: List[ReadingQuestionResponse]

    model_config = ConfigDict(from_attributes=True)

# --- TEST (EXAM) ---
class ReadingTestBase(BaseModel):
    title: str
    cefr_level: str
    language: str = "en"
    duration_minutes: int = 60
    total_questions: Optional[int] = None
    
    is_demo: bool = False
    is_free: bool = False
    is_mock: bool = False
    is_active: bool = True

class ReadingTestCreate(ReadingTestBase):
    id: str
    parts: List[ReadingPartCreate]

class ReadingTestUpdate(BaseModel):
    title: Optional[str] = None
    cefr_level: Optional[str] = None
    duration_minutes: Optional[int] = None
    total_questions: Optional[int] = None
    is_demo: Optional[bool] = None
    is_free: Optional[bool] = None
    is_mock: Optional[bool] = None
    is_active: Optional[bool] = None
    parts: Optional[List[ReadingPartCreate]] = None

class ReadingTestResponse(ReadingTestBase):
    id: str
    created_at: datetime
    parts: List[ReadingPartResponse]

    model_config = ConfigDict(from_attributes=True)

# --- RESULTS & SUBMISSION ---
class UserAnswer(BaseModel):
    question_id: int
    answers: List[str]

class ReadingSubmitRequest(BaseModel):
    answers: List[UserAnswer]
    exam_attempt_id: Optional[int] = None

class ReadingResultResponse(BaseModel):
    id: int
    raw_score: int
    percentage: float
    cefr_level: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ReadingQuestionReview(BaseModel):
    question_number: int
    user_answer: List[str]
    correct_answer: List[str]
    is_correct: bool
    type: ReadingQuestionType

class ReadingResultDetailResponse(BaseModel):
    summary: ReadingResultResponse
    review: List[ReadingQuestionReview]