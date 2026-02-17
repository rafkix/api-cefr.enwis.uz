from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum

# --- ENUMS ---
class WritingTaskType(str, Enum):
    TASK_1_1_INFORMAL = "TASK_1_1_INFORMAL"
    TASK_1_2_FORMAL = "TASK_1_2_FORMAL"
    TASK_2_ESSAY = "TASK_2_ESSAY"

# --- TASK SCHEMAS ---
class WritingTaskBase(BaseModel):
    part_number: int = Field(..., description="1 yoki 2-qism", alias="partNumber")
    type: WritingTaskType
    topic: str = Field(..., description="Savol matni")
    instruction: str = Field(..., description="Yo'riqnoma")
    context_text: Optional[str] = Field(None, description="Vaziyat tavsifi", alias="contextText")
    min_words: int = Field(50, alias="minWords")
    max_words: int = Field(200, alias="maxWords")
    
    model_config = ConfigDict(populate_by_name=True)

class WritingTaskCreate(WritingTaskBase):
    pass

class WritingTaskResponse(WritingTaskBase):
    id: int
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
# --- EXAM SCHEMAS ---
class WritingExamBase(BaseModel):
    title: str
    cefr_level: str = Field("Multilevel", alias="cefrLevel")
    duration_minutes: int = Field(60, alias="durationMinutes")
    is_demo: bool = Field(False, alias="isDemo")
    is_free: bool = Field(False, alias="isFree")
    is_mock: bool = Field(False, alias="isMock")
    is_active: bool = Field(True, alias="isActive")
    
    model_config = ConfigDict(populate_by_name=True)

class WritingExamCreate(WritingExamBase):
    id: str = Field(..., description="Slug: writing-test-1")
    tasks: List[WritingTaskCreate]

class WritingExamUpdate(BaseModel):
    title: Optional[str] = None
    cefr_level: Optional[str] = Field(None, alias="cefrLevel")
    duration_minutes: Optional[int] = Field(None, alias="durationMinutes")
    is_demo: Optional[bool] = Field(None, alias="isDemo")
    is_free: Optional[bool] = Field(None, alias="isFree")
    is_mock: Optional[bool] = Field(None, alias="isMock")
    is_active: Optional[bool] = Field(None, alias="isActive")
    tasks: Optional[List[WritingTaskCreate]] = None

    model_config = ConfigDict(populate_by_name=True)

class WritingExamResponse(WritingExamBase):
    id: str
    created_at: datetime = Field(..., alias="createdAt")
    tasks: List[WritingTaskResponse]
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
# --- AI EVALUATION DETAILS ---
class AICriteriaScore(BaseModel):
    task_achievement: float = Field(..., alias="taskAchievement")
    grammar: float
    vocabulary: float
    coherence: float
    mechanics: float
    model_config = ConfigDict(populate_by_name=True)
    

class AIEvaluationDetail(BaseModel):
    score: float
    word_count: int = Field(..., alias="wordCount")
    feedback: str
    criteria: AICriteriaScore
    # Union[List[str], str] orqali xatolikni oldini olamiz
    suggestions: Union[List[str], str] 
    
    model_config = ConfigDict(populate_by_name=True)

# --- USER SUBMISSION ---
class WritingSubmission(BaseModel):
    exam_id: str = Field(..., alias="examId")
    attempt_id: int = Field(..., alias="attemptId")
    user_responses: Dict[str, str] = Field(..., alias="userResponses")
    model_config = ConfigDict(populate_by_name=True)

# --- RESULT RESPONSE ---
class WritingResultResponse(BaseModel):
    id: int
    user_id: int = Field(serialization_alias="userId")
    exam_id: str = Field(serialization_alias="examId")
    overall_score: float = Field(serialization_alias="overallScore")
    raw_score: float = Field(serialization_alias="rawScore")
    
    # evaluations lug'atida endi task1.1, task1.2 va task2 kalitlari bo'ladi
    evaluations: Dict[str, AIEvaluationDetail] = Field(validation_alias="ai_evaluation")
    user_responses: Dict[str, str] = Field(validation_alias="user_responses", serialization_alias="userResponses")
    
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
