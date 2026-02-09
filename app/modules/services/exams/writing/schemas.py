from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, List, Optional, Any
from datetime import datetime
from .models import WritingTaskType

# --- TASK ---
class WritingTaskBase(BaseModel):
    part_number: int = Field(..., alias="partNumber")
    type: WritingTaskType
    topic: str
    instruction: str
    context_text: Optional[str] = Field(None, alias="contextText")
    min_words: int = Field(..., alias="minWords")
    max_words: int = Field(..., alias="maxWords")

    model_config = ConfigDict(populate_by_name=True)

class WritingTaskCreate(WritingTaskBase):
    pass

class WritingTaskResponse(WritingTaskBase):
    id: int
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# --- EXAM ---
class WritingExamBase(BaseModel):
    title: str
    isDemo: bool = Field(False, alias="is_demo")
    duration_minutes: int = Field(60, alias="duration")

    model_config = ConfigDict(populate_by_name=True)

class WritingExamCreate(WritingExamBase):
    id: str # writing-test-1
    tasks: List[WritingTaskCreate]

class WritingExamUpdate(BaseModel):
    title: Optional[str] = None
    isDemo: Optional[bool] = Field(None, alias="is_demo")
    duration_minutes: Optional[int] = Field(None, alias="duration")
    tasks: Optional[List[WritingTaskCreate]] = None

    model_config = ConfigDict(populate_by_name=True)

class WritingExamResponse(WritingExamBase):
    id: str
    tasks: List[WritingTaskResponse]
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# --- SUBMISSION ---
class WritingSubmission(BaseModel):
    exam_id: str
    # Key: Task ID (str), Value: User yozgan matn
    user_responses: Dict[str, str]

# --- AI EVALUATION DETAILS ---
class AICriteriaScore(BaseModel):
    task_achievement: float = Field(..., alias="Task Achievement")
    grammar: float = Field(..., alias="Grammar")
    vocabulary: float = Field(..., alias="Vocabulary")
    coherence: float = Field(..., alias="Coherence & Cohesion")
    mechanics: float = Field(..., alias="Punctuation & Spelling")

class AITaskEvaluation(BaseModel):
    score: float
    feedback: str
    criteria: Optional[AICriteriaScore] = None
    suggestions: List[str]

class WritingResultResponse(BaseModel):
    id: int
    exam_id: str
    overall_score: float
    ai_evaluation: Optional[Dict[str, AITaskEvaluation]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class WritingResultDetailResponse(BaseModel):
    summary: WritingResultResponse
    user_responses: Dict[str, str]
    model_config = ConfigDict(from_attributes=True)