from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

# --- 1. ENUMS ---
class SkillType(str, Enum):
    READING = "READING"
    LISTENING = "LISTENING"
    WRITING = "WRITING"
    SPEAKING = "SPEAKING"

# --- 2. BASE MOCK EXAM SCHEMAS ---
class MockExamBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    image_file: Optional[str] = None
    cefr_level: str = "Multilevel"
    duration_minutes: int = 180
    price: float = 0.0
    is_active: bool = True
    reading_id: Optional[str] = None
    listening_id: Optional[str] = None
    writing_id: Optional[str] = None
    speaking_id: Optional[str] = None

class MockExamCreate(MockExamBase):
    id: str = Field(..., description="Unique slug ID")

class MockExamUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    image_file: Optional[str] = None
    cefr_level: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[float] = None
    is_active: Optional[bool] = None
    reading_id: Optional[str] = None
    listening_id: Optional[str] = None
    writing_id: Optional[str] = None
    speaking_id: Optional[str] = None

# --- 3. RESPONSE SCHEMAS (Frontend uchun asosiy) ---
class UserMockExamResponse(BaseModel):
    id: str
    title: str
    cefr_level: str
    price: float
    is_active: bool
    is_purchased: bool = False
    reading_id: Optional[str] = None
    listening_id: Optional[str] = None
    writing_id: Optional[str] = None
    speaking_id: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

# --- 4. PROCESS SCHEMAS (Submission Logic) ---
class MockSkillSubmit(BaseModel):
    raw_score: float = Field(0.0, ge=0, le=75)
    user_answers: Optional[Dict] = Field(default_factory=dict)

class MockSkillAttemptResponse(BaseModel):
    id: int
    attempt_id: int
    user_id: int  # Shu yerga qo'shildi
    skill: SkillType
    raw_score: float
    scaled_score: float 
    cefr_level: Optional[str] = None
    is_checked: bool
    submitted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class MockSkillStatusResponse(BaseModel):
    skill: str
    is_checked: bool
    is_submitted: bool
    submitted_at: Optional[datetime] = None

# --- 5. ATTEMPT & RESULT SCHEMAS ---
class MockExamStartResponse(BaseModel):
    attempt_id: int = Field(..., validation_alias="id") 
    mock_exam_id: str
    started_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MockExamAttemptDetail(BaseModel):
    id: int
    mock_exam_id: str
    user_id: int  # Shu yerga qo'shildi
    started_at: datetime
    is_finished: bool
    skills: List[MockSkillAttemptResponse]
    
    model_config = ConfigDict(from_attributes=True)

class MockExamResultResponse(BaseModel):
    id: int
    attempt_id: int
    user_id: int
    reading_ball: float
    listening_ball: float
    writing_ball: float
    speaking_ball: float
    overall_score: float
    cefr_level: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- 6. PURCHASE SCHEMAS ---
class MockPurchaseResponse(BaseModel):
    id: int
    user_id: int
    mock_exam_id: str
    is_active: bool
    comment: Optional[str] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
