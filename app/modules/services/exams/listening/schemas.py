from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum

class ListeningQuestionType(str, Enum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    GAP_FILL = "GAP_FILL"
    MATCHING = "MATCHING"
    MAP_DIAGRAM = "MAP_DIAGRAM"
    SENTENCE_COMPLETION = "SENTENCE_COMPLETION"
    SHORT_ANSWER = "SHORT_ANSWER"

# --- OPTIONS ---
class OptionBase(BaseModel):
    value: str
    label: str

class OptionCreate(OptionBase):
    pass

class OptionResponse(OptionBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# --- QUESTIONS ---
class ListeningQuestionBase(BaseModel):
    question_number: int = Field(..., alias="question_number")
    type: ListeningQuestionType
    text: Optional[str] = Field(None, alias="question")
    
    model_config = ConfigDict(populate_by_name=True)

class ListeningQuestionCreate(ListeningQuestionBase):
    correct_answer: str = Field(..., alias="correct_answer")
    options: Optional[List[OptionCreate]] = []

class ListeningQuestionResponse(ListeningQuestionBase):
    id: int
    options: List[OptionResponse] = []
    # correct_answer bu yerda yo'q (xavfsizlik uchun)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# --- PARTS ---
class ListeningPartBase(BaseModel):
    part_number: int = Field(..., alias="part_number")
    title: str
    instruction: str
    task_type: str = Field(..., alias="task_type")
    audio_url: str = Field(..., alias="audio_label")
    context: Optional[str] = None
    passage: Optional[str] = ""
    map_image: Optional[str] = Field(None, alias="map_image")

    model_config = ConfigDict(populate_by_name=True)

class ListeningPartCreate(ListeningPartBase):
    questions: List[ListeningQuestionCreate]
    options: Optional[List[OptionCreate]] = []

class ListeningPartResponse(ListeningPartBase):
    id: int
    questions: List[ListeningQuestionResponse]
    options: List[OptionResponse] = []

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# --- EXAM ---
class ListeningExamBase(BaseModel):
    title: str
    is_demo: bool = Field(False, alias="is_demo")
    is_free: bool = Field(False, alias="is_free")
    is_mock: bool = Field(False, alias="is_mock")
    is_active: bool = Field(True, alias="is_active")
    
    cefr_level: str = Field(..., alias="level")
    duration_minutes: int = Field(35, alias="duration")
    total_questions: int = Field(..., alias="total_questions")
    sections: str 

    model_config = ConfigDict(populate_by_name=True)

class ListeningExamCreate(ListeningExamBase):
    id: str 
    parts: List[ListeningPartCreate]

class ListeningExamUpdate(BaseModel):
    title: Optional[str] = None
    is_demo: Optional[bool] = None
    is_free: Optional[bool] = None
    is_mock: Optional[bool] = None
    is_active: Optional[bool] = None
    
    cefr_level: Optional[str] = Field(None, alias="level")
    duration_minutes: Optional[int] = Field(None, alias="duration")
    total_questions: Optional[int] = Field(None, alias="total_questions")
    sections: Optional[str] = None
    parts: Optional[List[ListeningPartCreate]] = None

    model_config = ConfigDict(populate_by_name=True)

class ListeningExamResponse(ListeningExamBase):
    id: str
    parts: List[ListeningPartResponse]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# --- RESULTS & SUBMISSION ---
class ListeningSubmission(BaseModel):
    exam_id: str
    user_answers: Dict[str, str] = Field(..., alias="user_answers")
    exam_attempt_id: Optional[int] = Field(None, alias="exam_attempt_id")

class ListeningResultResponse(BaseModel):
    id: int
    exam_id: str
    raw_score: int
    standard_score: float
    cefr_level: Optional[str]
    percentage: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ListeningQuestionReview(BaseModel):
    question_number: int
    user_answer: Optional[str] = ""
    correct_answer: str 
    is_correct: bool
    type: ListeningQuestionType

    model_config = ConfigDict(from_attributes=True)

class ListeningResultDetailResponse(BaseModel):
    summary: ListeningResultResponse
    review: List[ListeningQuestionReview]

    model_config = ConfigDict(from_attributes=True)